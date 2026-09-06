#!/usr/bin/env python3

from pathlib import Path
import argparse
import secrets
import sqlite3
import sys

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

MODEL_VERSION = "sface_2021dec"
ALGORITHM_VERSION = "AES-256-GCM-v1"

VALID_EXTENSIONS = {".jpg", ".jpeg", ".png"}


def build_aad(external_id):
    return (
        f"{external_id}|"
        f"{MODEL_VERSION}|"
        f"{ALGORITHM_VERSION}"
    ).encode("utf-8")


def main():
    parser = argparse.ArgumentParser(
        description="Enrolamiento biométrico offline de secureGate."
    )

    parser.add_argument(
        "user",
        help="Identificador pseudonimizado, por ejemplo user_002.",
    )

    parser.add_argument(
        "directory",
        type=Path,
        help="Directorio con fotografías del usuario.",
    )

    args = parser.parse_args()

    external_id = args.user.strip()
    directory = args.directory.expanduser().resolve()

    if not external_id.startswith("user_"):
        print(
            "[ERROR] Utilizar identificadores pseudonimizados "
            "del tipo user_001."
        )
        return 1

    if not directory.is_dir():
        print(f"[ERROR] Directorio inexistente: {directory}")
        return 1

    if not DB_PATH.is_file():
        print(f"[ERROR] Base inexistente: {DB_PATH}")
        return 1

    if not K_BIO_PATH.is_file():
        print(f"[ERROR] K_bio inexistente: {K_BIO_PATH}")
        return 1

    key = K_BIO_PATH.read_bytes()

    if len(key) != 32:
        print("[ERROR] K_bio debe tener exactamente 32 bytes.")
        return 1

    images = sorted(
        path
        for path in directory.iterdir()
        if path.is_file()
        and path.suffix.lower() in VALID_EXTENSIONS
    )

    if len(images) < 5:
        print(
            "[ERROR] Se requieren al menos 5 fotografías "
            "válidas para enrolamiento."
        )
        return 1

    recognizer = create_recognizer()

    print("[secureGate] Enrolamiento biométrico offline")
    print(f"[INFO] Usuario: {external_id}")
    print(f"[INFO] Imágenes: {len(images)}")
    print()

    embeddings = []

    for index, image_path in enumerate(images, start=1):
        try:
            embedding = extract_embedding(
                image_path,
                recognizer,
            )
        except RuntimeError as exc:
            print(f"[ERROR] {exc}")
            return 2

        embeddings.append(embedding)

        print(
            f"[OK] {index:02d}/{len(images):02d} "
            f"{image_path.name} "
            f"→ embedding {embedding.size}D"
        )

    aesgcm = AESGCM(key)
    aad = build_aad(external_id)

    try:
        with sqlite3.connect(DB_PATH) as connection:
            connection.execute(
                "PRAGMA foreign_keys = ON;"
            )

            existing = connection.execute(
                """
                SELECT user_id
                FROM users
                WHERE external_id = ?
                """,
                (external_id,),
            ).fetchone()

            if existing is not None:
                template_count = connection.execute(
                    """
                    SELECT COUNT(*)
                    FROM biometric_templates
                    WHERE user_id = ?
                    AND active = 1
                    """,
                    (existing[0],),
                ).fetchone()[0]

                if template_count > 0:
                    print(
                        f"[ERROR] {external_id} ya posee "
                        f"{template_count} templates activos."
                    )
                    print(
                        "[SEGURIDAD] No se modifica el enrolamiento "
                        "existente automáticamente."
                    )
                    return 3

                user_id = existing[0]

            else:
                cursor = connection.execute(
                    """
                    INSERT INTO users (
                        external_id,
                        active
                    )
                    VALUES (?, 1)
                    """,
                    (external_id,),
                )

                user_id = cursor.lastrowid

            for embedding in embeddings:
                plaintext = embedding.tobytes()
                nonce = secrets.token_bytes(12)

                ciphertext = aesgcm.encrypt(
                    nonce,
                    plaintext,
                    aad,
                )

                connection.execute(
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

            connection.commit()

    except sqlite3.Error as exc:
        print(f"[ERROR] SQLite: {exc}")
        return 4

    print()
    print("[RESULTADO] Enrolamiento completado")
    print(f"[OK] Usuario: {external_id}")
    print(f"[OK] Templates almacenados: {len(embeddings)}")
    print("[OK] Templates protegidos con AES-256-GCM")
    print("[OK] Nonce único generado para cada template")
    print("[SEGURIDAD] K_bio no mostrada.")
    print("[SEGURIDAD] Embeddings no mostrados.")
    print("[SEGURIDAD] Embeddings plaintext no persistidos.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
