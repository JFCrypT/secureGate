"""Operaciones de usuarios para el backend y la API."""

from contextlib import contextmanager
from pathlib import Path
import re
import sqlite3

from securegate.rfid.registry import DEFAULT_DB


EXTERNAL_ID_PATTERN = re.compile(r"user_[A-Za-z0-9_-]+")


class UserAlreadyExists(ValueError):
    pass


class UserNotFound(ValueError):
    pass


class CredentialNotFound(ValueError):
    pass


def validate_external_id(external_id):
    if not isinstance(external_id, str) or not EXTERNAL_ID_PATTERN.fullmatch(external_id):
        raise ValueError("Usar un identificador pseudonimizado como user_001.")
    return external_id


class UserRepository:
    def __init__(self, database=DEFAULT_DB):
        self.database = Path(database)
        if not self.database.is_file():
            raise ValueError("Base inexistente. Ejecutar raspberry/init_db.py primero.")
        with self._connect() as connection:
            connection.execute("SELECT user_id FROM users LIMIT 1")

    @contextmanager
    def _connect(self):
        connection = sqlite3.connect(self.database, timeout=5)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA busy_timeout = 5000")
            with connection:
                yield connection
        finally:
            connection.close()

    @staticmethod
    def _has_rfid_table(connection):
        return connection.execute(
            """SELECT 1 FROM sqlite_master
               WHERE type = 'table' AND name = 'rfid_credentials'"""
        ).fetchone() is not None

    @staticmethod
    def _serialize(row, has_rfid=False):
        template_count = int(row["biometric_templates"])
        return {
            "external_id": row["external_id"],
            "first_name": row["first_name"],
            "last_name": row["last_name"],
            "role": row["role"],
            "active": bool(row["active"]),
            "created_at": row["created_at"],
            "has_face": template_count > 0,
            "biometric_templates": template_count,
            "has_rfid": bool(has_rfid),
        }

    def list(self):
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT u.user_id, u.external_id, u.first_name,
                          u.last_name, u.role, u.active, u.created_at,
                          SUM(CASE WHEN t.active = 1 THEN 1 ELSE 0 END)
                              AS biometric_templates
                   FROM users u
                   LEFT JOIN biometric_templates t ON t.user_id = u.user_id
                   GROUP BY u.user_id
                   ORDER BY u.external_id"""
            ).fetchall()
            rfid_users = set()
            if self._has_rfid_table(connection):
                rfid_users = {
                    row[0]
                    for row in connection.execute(
                        "SELECT user_id FROM rfid_credentials WHERE active = 1"
                    ).fetchall()
                }
        return [self._serialize(row, row["user_id"] in rfid_users) for row in rows]

    def summary(self):
        users = self.list()
        return {
            "total": len(users),
            "active": sum(user["active"] for user in users),
            "with_face": sum(user["has_face"] for user in users),
            "with_rfid": sum(user["has_rfid"] for user in users),
            "with_both": sum(
                user["has_face"] and user["has_rfid"] for user in users
            ),
        }

    def get(self, external_id):
        validate_external_id(external_id)
        with self._connect() as connection:
            row = connection.execute(
                """SELECT u.user_id, u.external_id, u.first_name,
                          u.last_name, u.role, u.active, u.created_at,
                          SUM(CASE WHEN t.active = 1 THEN 1 ELSE 0 END)
                              AS biometric_templates
                   FROM users u
                   LEFT JOIN biometric_templates t ON t.user_id = u.user_id
                   WHERE u.external_id = ?
                   GROUP BY u.user_id""",
                (external_id,),
            ).fetchone()
            if row is None:
                raise UserNotFound("Usuario inexistente.")
            has_rfid = False
            if self._has_rfid_table(connection):
                has_rfid = connection.execute(
                    """SELECT 1 FROM rfid_credentials
                       WHERE user_id = ? AND active = 1""",
                    (row["user_id"],),
                ).fetchone() is not None
        return self._serialize(row, has_rfid)

    def create(self, external_id, first_name=None, last_name=None, role=None):
        validate_external_id(external_id)
        try:
            with self._connect() as connection:
                connection.execute(
                    """INSERT INTO users(
                           external_id, first_name, last_name, role, active
                       ) VALUES (?, ?, ?, ?, 1)""",
                    (external_id, first_name, last_name, role),
                )
        except sqlite3.IntegrityError as exc:
            raise UserAlreadyExists("El usuario ya existe.") from exc
        return self.get(external_id)

    def set_active(self, external_id, active):
        return self.update(external_id, {"active": bool(active)})

    def update(self, external_id, changes):
        validate_external_id(external_id)
        allowed = {"first_name", "last_name", "role", "active"}
        if not changes or not set(changes).issubset(allowed):
            raise ValueError("No hay campos válidos para actualizar.")
        normalized = dict(changes)
        if "active" in normalized:
            normalized["active"] = int(bool(normalized["active"]))
        assignments = ", ".join(f"{field} = ?" for field in normalized)
        parameters = [*normalized.values(), external_id]
        with self._connect() as connection:
            cursor = connection.execute(
                f"UPDATE users SET {assignments} WHERE external_id = ?",
                parameters,
            )
            if cursor.rowcount == 0:
                raise UserNotFound("Usuario inexistente.")
        return self.get(external_id)

    def revoke_rfid(self, external_id):
        validate_external_id(external_id)
        with self._connect() as connection:
            row = connection.execute(
                "SELECT user_id FROM users WHERE external_id = ?",
                (external_id,),
            ).fetchone()
            if row is None:
                raise UserNotFound("Usuario inexistente.")
            if not self._has_rfid_table(connection):
                raise CredentialNotFound("El usuario no posee una tarjeta activa.")
            cursor = connection.execute(
                """UPDATE rfid_credentials SET active = 0
                   WHERE user_id = ? AND active = 1""",
                (row["user_id"],),
            )
            if cursor.rowcount == 0:
                raise CredentialNotFound("El usuario no posee una tarjeta activa.")
        return self.get(external_id)

    def revoke_face(self, external_id):
        validate_external_id(external_id)
        with self._connect() as connection:
            row = connection.execute(
                "SELECT user_id FROM users WHERE external_id = ?",
                (external_id,),
            ).fetchone()
            if row is None:
                raise UserNotFound("Usuario inexistente.")
            cursor = connection.execute(
                """UPDATE biometric_templates SET active = 0
                   WHERE user_id = ? AND active = 1""",
                (row["user_id"],),
            )
            if cursor.rowcount == 0:
                raise CredentialNotFound("El usuario no posee biometría activa.")
        return self.get(external_id)
