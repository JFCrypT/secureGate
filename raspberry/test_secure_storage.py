#!/usr/bin/env python3

from pathlib import Path
import argparse
import sqlite3
import sys

import cv2
import numpy as np

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


ROOT_DIR = Path(__file__).resolve().parents[1]

MODEL_DIR = ROOT_DIR / "models"
DB_PATH = ROOT_DIR / "data" / "db" / "securegate.db"
K_BIO_PATH = ROOT_DIR / "local" / "keys" / "k_bio"

YUNET_MODEL = MODEL_DIR / "face_detection_yunet_2023mar.onnx"
SFACE_MODEL = MODEL_DIR / "face_recognition_sface_2021dec.onnx"

YUNET_THRESHOLD = 0.7
MODEL_VERSION = "sface_2021dec"
ALGORITHM_VERSION = "AES-256-GCM-v1"


def extract_embedding(image_path, recognizer):
    image = cv2.imread(str(image_path))

    if image is None:
        raise RuntimeError(f"No se pudo leer la imagen: {image_path}")

    height, width = image.shape[:2]

    detector = cv2.FaceDetectorYN.create(
        str(YUNET_MODEL),
        "",
        (width, height),
        YUNET_THRESHOLD,
        0.3,
        5000,
    )

    _, faces = detector.detect(image)

    if faces is None or len(faces) == 0:
        raise RuntimeError("No se detectó ningún rostro.")

    if len(faces) != 1:
        raise RuntimeError(
            f"Se detectaron {len(faces)} rostros; "
            "se requiere exactamente uno."
        )

    aligned = recognizer.alignCrop(image, faces[0])
    embedding = recognizer.feature(aligned)

    return np.asarray(
        embedding,
        dtype=np.float32,
    ).reshape(-1)


def build_aad(external_id):
    return (
        f"{external_id}|{MODEL_VERSION}|{ALGORITHM_VERSION}"
    ).encode("utf-8")


def main():
    parser = argparse.ArgumentParser(
        description="Prueba almacenamiento biométrico seguro."
    )

    parser.add_argument(
        "image",
        type=Path,
        help="Imagen facial de prueba.",
    )

    parser.add_argument(
        "--user",
        default="user_001",
        help="Identificador pseudonimizado del usuario.",
    )

    args = parser.parse_args()

    image_path = args.image.expanduser().resolve()
    external_id = args.user

    if not image_path.is_file():
        print(f"[ERROR] Imagen inexistente: {image_path}")
        return 1

    if not K_BIO_PATH.is_file():
        print(f"[ERROR] K_bio inexistente: {K_BIO_PATH}")
        return 1

    if not DB_PATH.is_file():
        print(f"[ERROR] Base inexistente: {DB_PATH}")
        return 1

    key = K_BIO_PATH.read_bytes()

    if len(key) != 32:
        print("[ERROR] K_bio debe tener exactamente 32 bytes.")
        return 1

    recognizer = cv2.FaceRecognizerSF.create(
        str(SFACE_MODEL),
        "",
    )

    print("[secureGate] Secure Biometric Storage")
    print(f"[INFO] Usuario: {external_id}")
    print(f"[INFO] Imagen: {image_path.name}")

    try:
        embedding = extract_embedding(
            image_path,
            recognizer,
        )
    except RuntimeError as exc:
        print(f"[ERROR] {exc}")
        return 2

    plaintext = embedding.tobytes()

    aesgcm = AESGCM(key)

    nonce = np.random.bytes(12)
    aad = build_aad(external_id)

    ciphertext = aesgcm.encrypt(
        nonce,
        plaintext,
        aad,
    )

    try:
        with sqlite3.connect(DB_PATH) as connection:
            connection.execute("PRAGMA foreign_keys = ON;")

            connection.execute(
                """
                INSERT OR IGNORE INTO users (
                    external_id,
                    active
                )
                VALUES (?, 1)
                """,
                (external_id,),
            )

            user_id = connection.execute(
                """
                SELECT user_id
                FROM users
                WHERE external_id = ?
                """,
                (external_id,),
            ).fetchone()[0]

            cursor = connection.execute(
                """
                INSERT INTO biometric_templates (
                    user_id,
                    ciphertext,
                    nonce,
                    model_version,
                    algorithm_version,
                    active
                )
                VALUES (?, ?, ?, ?, ?, 1)
                """,
                (
                    user_id,
                    ciphertext,
                    nonce,
                    MODEL_VERSION,
                    ALGORITHM_VERSION,
                ),
            )

            template_id = cursor.lastrowid

            row = connection.execute(
                """
                SELECT
                    ciphertext,
                    nonce,
                    model_version,
                    algorithm_version
                FROM biometric_templates
                WHERE template_id = ?
                """,
                (template_id,),
            ).fetchone()

    except sqlite3.Error as exc:
        print(f"[ERROR] SQLite: {exc}")
        return 3

    stored_ciphertext = row[0]
    stored_nonce = row[1]
    stored_model_version = row[2]
    stored_algorithm_version = row[3]

    stored_aad = (
        f"{external_id}|"
        f"{stored_model_version}|"
        f"{stored_algorithm_version}"
    ).encode("utf-8")

    try:
        recovered_plaintext = aesgcm.decrypt(
            stored_nonce,
            stored_ciphertext,
            stored_aad,
        )
    except Exception as exc:
        print(f"[ERROR] Falló autenticación/descifrado: {exc}")
        return 4

    recovered_embedding = np.frombuffer(
        recovered_plaintext,
        dtype=np.float32,
    )

    same_bytes = plaintext == recovered_plaintext

    same_array = np.array_equal(
        embedding,
        recovered_embedding,
    )

    print(f"[OK] Template almacenado: {template_id}")
    print(f"[OK] Ciphertext almacenado: {len(ciphertext)} bytes")
    print(f"[OK] Nonce: {len(nonce)} bytes")
    print(f"[OK] Embedding recuperado: {recovered_embedding.size} dimensiones")
    print(f"[OK] Igualdad de bytes: {same_bytes}")
    print(f"[OK] Igualdad de arrays: {same_array}")
    print("[SEGURIDAD] K_bio no mostrada.")
    print("[SEGURIDAD] Embedding no mostrado.")
    print("[SEGURIDAD] Plaintext biométrico no persistido.")

    if not same_bytes or not same_array:
        print("[ERROR] Falló el round-trip biométrico.")
        return 5

    print("[RESULTADO] Round-trip AES-256-GCM + SQLite: PASS")

    return 0


if __name__ == "__main__":
    sys.exit(main())
