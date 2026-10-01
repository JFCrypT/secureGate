"""RFID allowlist; UIDs are pseudonymized with a dedicated HMAC key."""

from pathlib import Path
from contextlib import contextmanager
import hashlib
import hmac
import re
import sqlite3


ROOT_DIR = Path(__file__).resolve().parents[3]
DEFAULT_DB = ROOT_DIR / "data" / "db" / "securegate.db"
DEFAULT_KEY = ROOT_DIR / "local" / "keys" / "k_rfid"
SCHEMA = """
CREATE TABLE IF NOT EXISTS rfid_credentials (
    credential_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE RESTRICT,
    uid_digest TEXT NOT NULL UNIQUE,
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_rfid_user ON rfid_credentials(user_id);
"""


def normalize_uid(uid):
    if isinstance(uid, (bytes, list, tuple)):
        uid = bytes(uid).hex()
    if not isinstance(uid, str):
        raise ValueError("UID esperado como bytes o hexadecimal.")
    value = re.sub(r"[\s:-]", "", uid).upper()
    if len(value) not in (8, 14) or not re.fullmatch(r"[0-9A-F]+", value):
        raise ValueError("El RC522 admite aquí UIDs hexadecimales de 4 o 7 bytes.")
    return value


class CardRegistry:
    def __init__(self, database=DEFAULT_DB, key_path=DEFAULT_KEY):
        self.database = Path(database)
        if not self.database.is_file():
            raise ValueError("Base inexistente. Ejecutar raspberry/init_db.py primero.")
        self.key = Path(key_path).read_bytes()
        if len(self.key) != 32:
            raise ValueError("k_rfid debe tener exactamente 32 bytes.")
        with self._connect() as connection:
            connection.execute("SELECT user_id FROM users LIMIT 1")
            connection.executescript(SCHEMA)

    @contextmanager
    def _connect(self):
        connection = sqlite3.connect(self.database, timeout=5)
        try:
            connection.execute("PRAGMA foreign_keys = ON")
            with connection:
                yield connection
        finally:
            connection.close()

    def digest(self, uid):
        canonical = normalize_uid(uid)
        return hmac.new(self.key, canonical.encode("ascii"), hashlib.sha256).hexdigest()

    def authorize(self, uid):
        with self._connect() as connection:
            row = connection.execute(
                """SELECT u.external_id FROM rfid_credentials c
                   JOIN users u ON u.user_id = c.user_id
                   WHERE c.uid_digest = ? AND c.active = 1 AND u.active = 1""",
                (self.digest(uid),),
            ).fetchone()
        return row[0] if row else None

    def enroll(self, external_id, uid):
        if not re.fullmatch(r"user_[A-Za-z0-9_-]+", external_id):
            raise ValueError("Usar un identificador pseudonimizado como user_001.")
        with self._connect() as connection:
            # RFID-only users need no biometric templates. Never reactivate a
            # disabled user implicitly or transfer an existing card to someone else.
            connection.execute(
                "INSERT OR IGNORE INTO users(external_id, active) VALUES (?, 1)",
                (external_id,),
            )
            user_id, active = connection.execute(
                "SELECT user_id, active FROM users WHERE external_id = ?",
                (external_id,),
            ).fetchone()
            if not active:
                raise ValueError("El usuario está deshabilitado.")
            digest = self.digest(uid)
            existing = connection.execute(
                "SELECT user_id FROM rfid_credentials WHERE uid_digest = ?", (digest,),
            ).fetchone()
            if existing and existing[0] != user_id:
                raise ValueError("La tarjeta ya pertenece a otro usuario.")
            connection.execute(
                """INSERT INTO rfid_credentials(user_id, uid_digest, active)
                   VALUES (?, ?, 1)
                   ON CONFLICT(uid_digest) DO UPDATE SET active = 1""",
                (user_id, digest),
            )

    def revoke(self, uid):
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE rfid_credentials SET active = 0 WHERE uid_digest = ?",
                (self.digest(uid),),
            )
            return cursor.rowcount > 0
