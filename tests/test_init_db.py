from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "raspberry"))

from init_db import apply_migrations


class DatabaseMigrationTests(unittest.TestCase):
    def test_adds_profile_columns_without_losing_legacy_user(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "legacy.db"
            with sqlite3.connect(database) as connection:
                connection.execute(
                    """CREATE TABLE users (
                        user_id INTEGER PRIMARY KEY,
                        external_id TEXT NOT NULL UNIQUE,
                        active INTEGER NOT NULL,
                        created_at TEXT NOT NULL
                    )"""
                )
                connection.execute(
                    """INSERT INTO users
                       (external_id, active, created_at)
                       VALUES ('user_001', 1, CURRENT_TIMESTAMP)"""
                )
                apply_migrations(connection)
                columns = {
                    row[1] for row in connection.execute("PRAGMA table_info(users)")
                }
                user = connection.execute(
                    "SELECT external_id, active FROM users"
                ).fetchone()
            self.assertTrue({"first_name", "last_name", "role"}.issubset(columns))
            self.assertEqual(user, ("user_001", 1))


if __name__ == "__main__":
    unittest.main()
