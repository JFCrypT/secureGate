#!/usr/bin/env python3

from pathlib import Path
import argparse
import sqlite3
import sys

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
    extract_embedding,
)


DB_PATH = ROOT_DIR / "data" / "db" / "securegate.db"
K_BIO_PATH = ROOT_DIR / "local" / "keys" / "k_bio"

MATCH_THRESHOLD = 0.45
EXPECTED_MODEL_VERSION = "sface_2021dec"
EXPECTED_ALGORITHM_VERSION = "AES-256-GCM-v1"


def build_aad(external_id, model_version, algorithm_version):
    return (
        f"{external_id}|"
        f"{model_version}|"
        f"{algorithm_version}"
    ).encode("utf-8")


def load_active_templates():
    if not DB_PATH.is_file():
        raise RuntimeError(f"Base inexistente: {DB_PATH}")

    if not K_BIO_PATH.is_file():
        raise RuntimeError(f"K_bio inexistente: {K_BIO_PATH}")

    key = K_BIO_PATH.read_bytes()

    if len(key) != 32:
        raise RuntimeError(
            "K_bio debe tener exactamente 32 bytes."
        )

    aesgcm = AESGCM(key)

    templates = []

    try:
        with sqlite3.connect(DB_PATH) as connection:
            connection.execute("PRAGMA foreign_keys = ON;")

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
                ORDER BY u.external_id, t.template_id
                """
            ).fetchall()

    except sqlite3.Error as exc:
        raise RuntimeError(f"SQLite: {exc}") from exc

    if not rows:
        raise RuntimeError(
            "No existen templates biométricos activos."
        )

    for (
        external_id,
        ciphertext,
        nonce,
        model_version,
        algorithm_version,
    ) in rows:

        if model_version != EXPECTED_MODEL_VERSION:
            raise RuntimeError(
                f"Modelo incompatible para {external_id}: "
                f"{model_version}"
            )

        if algorithm_version != EXPECTED_ALGORITHM_VERSION:
            raise RuntimeError(
                f"Algoritmo incompatible para {external_id}: "
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
                f"No se pudo autenticar/descifrar "
                f"un template de {external_id}"
            ) from exc

        embedding = np.frombuffer(
            plaintext,
            dtype=np.float32,
        ).copy()

        if embedding.size != 128:
            raise RuntimeError(
                f"Embedding inválido para {external_id}: "
                f"{embedding.size} dimensiones"
            )

        templates.append(
            (
                external_id,
                embedding.reshape(1, -1),
            )
        )

    return templates


def recognize(query_embedding, recognizer, templates):
    best_user = None
    best_score = -1.0

    query = query_embedding.reshape(1, -1)

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


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Reconocimiento biométrico secureGate "
            "contra templates cifrados."
        )
    )

    parser.add_argument(
        "image",
        type=Path,
        help="Imagen facial de consulta.",
    )

    args = parser.parse_args()

    image_path = args.image.expanduser().resolve()

    if not image_path.is_file():
        print(f"[ERROR] Imagen inexistente: {image_path}")
        return 1

    try:
        recognizer = create_recognizer()

        query_embedding = extract_embedding(
            image_path,
            recognizer,
        )

        templates = load_active_templates()

        best_user, best_score = recognize(
            query_embedding,
            recognizer,
            templates,
        )

    except RuntimeError as exc:
        print(f"[ERROR] {exc}")
        return 2

    print("[secureGate] Reconocimiento biométrico")
    print(f"[INFO] Imagen: {image_path.name}")
    print(f"[INFO] Templates activos: {len(templates)}")
    print(f"[INFO] Mejor coincidencia: {best_user}")
    print(f"[INFO] Similitud coseno: {best_score:.6f}")
    print(f"[INFO] Threshold: {MATCH_THRESHOLD:.2f}")

    if best_score >= MATCH_THRESHOLD:
        print(
            f"[ACCESO] USUARIO VÁLIDO: {best_user}"
        )
        return 0

    print("[ACCESO] USUARIO NO AUTORIZADO")
    return 3


if __name__ == "__main__":
    sys.exit(main())
