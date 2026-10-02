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
    first_name TEXT,
    last_name TEXT,
    role TEXT,
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

CREATE TABLE IF NOT EXISTS access_events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    occurred_at TEXT NOT NULL,
    method TEXT NOT NULL,
    external_id TEXT,
    granted INTEGER NOT NULL
        CHECK (granted IN (0, 1)),
    restricted_time INTEGER NOT NULL
        CHECK (restricted_time IN (0, 1)),
    alert_reasons TEXT NOT NULL DEFAULT '',
    door_status TEXT NOT NULL
        CHECK (door_status IN ('opened', 'simulated', 'not_requested', 'error')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_access_events_occurred_at
ON access_events(occurred_at);

CREATE INDEX IF NOT EXISTS idx_access_events_external_id
ON access_events(external_id);

CREATE TABLE IF NOT EXISTS rfid_enrollment_requests (
    request_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    status TEXT NOT NULL
        CHECK (status IN ('pending', 'completed', 'cancelled', 'failed', 'expired')),
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    finished_at TEXT,
    error_code TEXT,
    FOREIGN KEY (user_id)
        REFERENCES users(user_id)
        ON UPDATE CASCADE
        ON DELETE RESTRICT
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_rfid_enrollment_one_pending
ON rfid_enrollment_requests(status) WHERE status = 'pending';

CREATE INDEX IF NOT EXISTS idx_rfid_enrollment_user
ON rfid_enrollment_requests(user_id);

CREATE TABLE IF NOT EXISTS runtime_status (
    runtime_name TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    methods TEXT NOT NULL,
    door_mode TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


USER_PROFILE_COLUMNS = {
    "first_name": "TEXT",
    "last_name": "TEXT",
    "role": "TEXT",
}


def apply_migrations(connection):
    """Añade columnas nuevas sin borrar bases creadas por versiones anteriores."""
    existing = {
        row[1] for row in connection.execute("PRAGMA table_info(users)").fetchall()
    }
    for name, column_type in USER_PROFILE_COLUMNS.items():
        if name not in existing:
            connection.execute(f"ALTER TABLE users ADD COLUMN {name} {column_type}")


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
            journal_mode = connection.execute("PRAGMA journal_mode = WAL;").fetchone()[0]
            connection.execute("PRAGMA busy_timeout = 5000;")

            foreign_keys = connection.execute(
                "PRAGMA foreign_keys;"
            ).fetchone()[0]

            if foreign_keys != 1:
                raise RuntimeError(
                    "No se pudieron activar las foreign keys."
                )

            if journal_mode.lower() != "wal":
                raise RuntimeError("No se pudo activar el modo WAL de SQLite.")

            connection.executescript(SCHEMA)
            apply_migrations(connection)
            connection.commit()

    except (sqlite3.Error, RuntimeError) as exc:
        print(f"[ERROR] No se pudo inicializar SQLite: {exc}")
        return 1

    print("[OK] Foreign keys activadas")
    print("[OK] SQLite WAL activado para acceso concurrente")
    print("[OK] Tabla users disponible")
    print("[OK] Perfil opcional de usuarios actualizado")
    print("[OK] Tabla biometric_templates disponible")
    print("[OK] Tabla access_events disponible")
    print("[OK] Solicitudes de enrolamiento RFID disponibles")
    print("[OK] Estado del runtime disponible")
    print("[OK] Índices creados/verificados")
    print("[SEGURIDAD] No se insertaron datos biométricos.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
