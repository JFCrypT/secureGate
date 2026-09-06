#!/usr/bin/env python3

from pathlib import Path
import argparse
import sqlite3
import sys


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = ROOT_DIR / "data" / "db" / "securegate.db"


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY AUTOINCREMENT,
    external_id TEXT NOT NULL UNIQUE,
    active INTEGER NOT NULL DEFAULT 1
        CHECK (active IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS biometric_templates (
    template_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,

    ciphertext BLOB NOT NULL,
    nonce BLOB NOT NULL,

    model_version TEXT NOT NULL,
    algorithm_version TEXT NOT NULL,

    active INTEGER NOT NULL DEFAULT 1
        CHECK (active IN (0, 1)),

    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (user_id)
        REFERENCES users(user_id)
        ON UPDATE CASCADE
        ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_biometric_templates_user_id
ON biometric_templates(user_id);

CREATE INDEX IF NOT EXISTS idx_biometric_templates_active
ON biometric_templates(active);
"""


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Inicializa la base SQLite de secureGate."
    )

    parser.add_argument(
        "--database",
        type=Path,
        default=DEFAULT_DB_PATH,
        help="Ruta del archivo SQLite.",
    )

    args = parser.parse_args()

    db_path = args.database.expanduser().resolve()

    db_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    print("[secureGate] Inicialización de SQLite")
    print(f"[INFO] Base: {db_path}")

    try:
        with sqlite3.connect(db_path) as connection:
            connection.execute("PRAGMA foreign_keys = ON;")

            foreign_keys = connection.execute(
                "PRAGMA foreign_keys;"
            ).fetchone()[0]

            if foreign_keys != 1:
                raise RuntimeError(
                    "No se pudieron activar las foreign keys."
                )

            connection.executescript(SCHEMA)
            connection.commit()

    except (sqlite3.Error, RuntimeError) as exc:
        print(f"[ERROR] No se pudo inicializar SQLite: {exc}")
        return 1

    print("[OK] Foreign keys activadas")
    print("[OK] Tabla users disponible")
    print("[OK] Tabla biometric_templates disponible")
    print("[OK] Índices creados/verificados")
    print("[SEGURIDAD] No se insertaron datos biométricos.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
