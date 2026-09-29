#!/usr/bin/env python3

from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError
import argparse
from datetime import datetime
import os
import sqlite3
import sys
import time

import cv2
import numpy as np
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


ROOT_DIR = Path(__file__).resolve().parents[1]

sys.path.insert(
    0,
    str(ROOT_DIR / "raspberry"),
)

from securegate.vision.pipeline import (
    create_recognizer,
    extract_embedding_from_image,
)
from securegate.alerts import (
    DEFAULT_TIMEZONE,
    TelegramConfigurationError,
    TelegramDeliveryError,
    TelegramNotifier,
    is_restricted_time,
    load_timezone,
)


DB_PATH = ROOT_DIR / "data" / "db" / "securegate.db"
K_BIO_PATH = ROOT_DIR / "local" / "keys" / "k_bio"

MATCH_THRESHOLD = 0.45
DECISION_FRAMES = 3
REQUIRED_MATCHES = 2

EXPECTED_MODEL_VERSION = "sface_2021dec"
EXPECTED_ALGORITHM_VERSION = "AES-256-GCM-v1"


def build_aad(
    external_id,
    model_version,
    algorithm_version,
):
    return (
        f"{external_id}|"
        f"{model_version}|"
        f"{algorithm_version}"
    ).encode("utf-8")


def capture_frame(url, timeout):
    request = Request(
        url,
        headers={
            "User-Agent": "secureGate/1.0",
            "Accept": "image/jpeg",
        },
    )

    try:
        with urlopen(request, timeout=timeout) as response:
            data = response.read()

    except URLError as exc:
        raise RuntimeError(
            f"No se pudo acceder a ESP-CAM: {exc}"
        ) from exc

    if not data:
        raise RuntimeError(
            "ESP-CAM devolvió una respuesta vacía."
        )

    buffer = np.frombuffer(
        data,
        dtype=np.uint8,
    )

    image = cv2.imdecode(
        buffer,
        cv2.IMREAD_COLOR,
    )

    if image is None:
        raise RuntimeError(
            "No se pudo decodificar JPEG."
        )

    return image


def load_active_templates():
    if not DB_PATH.is_file():
        raise RuntimeError(
            f"Base inexistente: {DB_PATH}"
        )

    if not K_BIO_PATH.is_file():
        raise RuntimeError(
            f"K_bio inexistente: {K_BIO_PATH}"
        )

    key = K_BIO_PATH.read_bytes()

    if len(key) != 32:
        raise RuntimeError(
            "K_bio debe tener exactamente 32 bytes."
        )

    aesgcm = AESGCM(key)

    try:
        with sqlite3.connect(DB_PATH) as connection:
            connection.execute(
                "PRAGMA foreign_keys = ON;"
            )

            rows = connection.execute(
                """
                SELECT
                    u.external_id,
                    t.ciphertext,
                    t.nonce,
                    t.model_version,
                    t.algorithm_version
                FROM biometric_templates t
                JOIN users u
                  ON u.user_id = t.user_id
                WHERE u.active = 1
                  AND t.active = 1
                ORDER BY u.external_id,
                         t.template_id
                """
            ).fetchall()

    except sqlite3.Error as exc:
        raise RuntimeError(
            f"SQLite: {exc}"
        ) from exc

    if not rows:
        raise RuntimeError(
            "No existen templates activos."
        )

    templates = []

    for (
        external_id,
        ciphertext,
        nonce,
        model_version,
        algorithm_version,
    ) in rows:

        if model_version != EXPECTED_MODEL_VERSION:
            raise RuntimeError(
                f"Modelo incompatible: {model_version}"
            )

        if algorithm_version != EXPECTED_ALGORITHM_VERSION:
            raise RuntimeError(
                f"Algoritmo incompatible: "
                f"{algorithm_version}"
            )

        aad = build_aad(
            external_id,
            model_version,
            algorithm_version,
        )

        try:
            plaintext = aesgcm.decrypt(
                nonce,
                ciphertext,
                aad,
            )

        except Exception as exc:
            raise RuntimeError(
                f"Falló descifrado para {external_id}"
            ) from exc

        embedding = np.frombuffer(
            plaintext,
            dtype=np.float32,
        ).copy()

        if embedding.size != 128:
            raise RuntimeError(
                f"Embedding inválido para "
                f"{external_id}"
            )

        templates.append(
            (
                external_id,
                embedding.reshape(1, -1),
            )
        )

    return templates


def recognize(
    query_embedding,
    recognizer,
    templates,
):
    query = query_embedding.reshape(1, -1)

    best_user = None
    best_score = -1.0

    for external_id, stored_embedding in templates:
        score = recognizer.match(
            query,
            stored_embedding,
            cv2.FaceRecognizerSF_FR_COSINE,
        )

        if score > best_score:
            best_score = score
            best_user = external_id

    return best_user, best_score


def evaluate_window(
    url,
    timeout,
    interval,
    recognizer,
    templates,
):
    results = []

    attempts = 0
    max_attempts = 10

    while (
        len(results) < DECISION_FRAMES
        and attempts < max_attempts
    ):
        attempts += 1

        try:
            image = capture_frame(
                url,
                timeout,
            )

            query_embedding = (
                extract_embedding_from_image(
                    image,
                    recognizer,
                )
            )

        except RuntimeError:
            time.sleep(interval)
            continue

        best_user, best_score = recognize(
            query_embedding,
            recognizer,
            templates,
        )

        results.append(
            (
                best_user,
                best_score,
                image,
            )
        )

        time.sleep(interval)

    return results


def decide(results):
    valid_results = [
        (user, score)
        for user, score, _image in results
        if score >= MATCH_THRESHOLD
    ]

    if not valid_results:
        return None, 0, 0.0

    counts = {}

    for user, score in valid_results:
        counts[user] = counts.get(user, 0) + 1

    best_user = max(
        counts,
        key=counts.get,
    )

    matches = counts[best_user]

    user_scores = [
        score
        for user, score in valid_results
        if user == best_user
    ]

    average_score = (
        sum(user_scores) / len(user_scores)
    )

    if matches >= REQUIRED_MATCHES:
        return (
            best_user,
            matches,
            average_score,
        )

    return (
        None,
        matches,
        average_score,
    )


def select_alert_image(results, recognized_user):
    if recognized_user is None:
        candidates = results
    else:
        candidates = [
            result
            for result in results
            if result[0] == recognized_user
        ]

    if not candidates:
        candidates = results

    return max(
        candidates,
        key=lambda result: result[1],
    )[2]


def build_alert_caption(moment, recognized_user):
    if recognized_user is None:
        result = "Usuario no autorizado"
    else:
        result = f"Usuario reconocido: {recognized_user}"

    timezone_name = getattr(
        moment.tzinfo,
        "key",
        str(moment.tzinfo),
    )

    return "\n".join(
        [
            "🚨 ALERTA: intento de ingreso fuera de horario",
            f"Horario: {moment.strftime('%d/%m/%Y %H:%M:%S')}",
            f"Zona horaria: {timezone_name}",
            f"Resultado: {result}",
        ]
    )


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Runtime continuo de reconocimiento "
            "facial secureGate."
        )
    )

    parser.add_argument(
        "url",
        help="URL /capture de ESP-CAM.",
    )

    parser.add_argument(
        "--timeout",
        type=float,
        default=5.0,
    )

    parser.add_argument(
        "--interval",
        type=float,
        default=0.4,
    )

    parser.add_argument(
        "--cooldown",
        type=float,
        default=3.0,
    )

    parser.add_argument(
        "--alert-cooldown",
        type=float,
        default=60.0,
        help=(
            "Segundos mínimos entre alertas repetidas "
            "del mismo resultado."
        ),
    )

    parser.add_argument(
        "--timezone",
        default=os.environ.get(
            "SECUREGATE_TIMEZONE",
            DEFAULT_TIMEZONE,
        ),
        help=(
            "Zona horaria IANA usada para evaluar "
            "los horarios de acceso."
        ),
    )

    args = parser.parse_args()

    if args.alert_cooldown < 0:
        parser.error(
            "--alert-cooldown no puede ser negativo."
        )

    try:
        alert_timezone = load_timezone(args.timezone)
        notifier = TelegramNotifier.from_environment()
    except (
        ValueError,
        TelegramConfigurationError,
    ) as exc:
        print(f"[ERROR] Configuración de alertas: {exc}")
        return 1

    print("[secureGate] Runtime continuo ESP-CAM")
    print(f"[INFO] URL: {args.url}")
    print(
        f"[INFO] Threshold: "
        f"{MATCH_THRESHOLD:.2f}"
    )
    print(
        f"[INFO] Regla temporal: "
        f"{REQUIRED_MATCHES} de "
        f"{DECISION_FRAMES} frames"
    )
    print(f"[INFO] Zona horaria: {args.timezone}")

    if notifier is None:
        print(
            "[ADVERTENCIA] Alertas Telegram deshabilitadas: "
            "faltan TELEGRAM_BOT_TOKEN y TELEGRAM_CHAT_ID."
        )
    else:
        print("[INFO] Alertas Telegram habilitadas.")

    try:
        recognizer = create_recognizer()
        templates = load_active_templates()

    except RuntimeError as exc:
        print(f"[ERROR] {exc}")
        return 1

    print(
        f"[INFO] Templates activos: "
        f"{len(templates)}"
    )
    print("[INFO] Esperando rostro...")
    print("[INFO] Ctrl+C para finalizar.")
    print()

    last_alert_by_result = {}

    try:
        while True:
            results = evaluate_window(
                args.url,
                args.timeout,
                args.interval,
                recognizer,
                templates,
            )

            if len(results) < DECISION_FRAMES:
                time.sleep(args.interval)
                continue

            print("[INFO] Ventana de decisión:")

            for index, (user, score, _image) in enumerate(
                results,
                start=1,
            ):
                print(
                    f"  frame {index}: "
                    f"{user} | "
                    f"score={score:.6f}"
                )

            user, matches, average_score = decide(
                results
            )

            if user is not None:
                print(
                    f"[INFO] Coincidencias válidas: "
                    f"{matches}/{DECISION_FRAMES}"
                )
                print(
                    f"[INFO] Score medio válido: "
                    f"{average_score:.6f}"
                )
                print(
                    f"[ACCESO] USUARIO VÁLIDO: "
                    f"{user}"
                )
            else:
                print(
                    "[ACCESO] USUARIO "
                    "NO AUTORIZADO"
                )

            event_time = datetime.now(alert_timezone)

            if (
                notifier is not None
                and is_restricted_time(event_time)
            ):
                result_key = user or "unauthorized"
                monotonic_now = time.monotonic()
                last_alert = last_alert_by_result.get(
                    result_key,
                    float("-inf"),
                )

                if (
                    monotonic_now - last_alert
                    >= args.alert_cooldown
                ):
                    last_alert_by_result[result_key] = (
                        monotonic_now
                    )
                    alert_image = select_alert_image(
                        results,
                        user,
                    )
                    caption = build_alert_caption(
                        event_time,
                        user,
                    )

                    try:
                        notifier.send_photo(
                            alert_image,
                            caption,
                            captured_at=event_time,
                        )
                        print(
                            "[ALERTA] Telegram: mensaje y "
                            "foto enviados."
                        )
                    except TelegramDeliveryError as exc:
                        print(
                            "[ERROR] Telegram: "
                            f"{exc}"
                        )

            print()

            time.sleep(args.cooldown)

    except KeyboardInterrupt:
        print()
        print("[secureGate] Runtime detenido.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
