from contextlib import closing
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "raspberry"))

from init_db import SCHEMA
from securegate.rfid.registry import CardRegistry
from securegate.users import (
    CredentialNotFound,
    UserAlreadyExists,
    UserNotFound,
    UserRepository,
)


class UserRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.database = Path(self.temp.name) / "securegate.db"
        self.key = Path(self.temp.name) / "k_rfid"
        self.key.write_bytes(b"k" * 32)
        with closing(sqlite3.connect(self.database)) as connection:
            connection.executescript(SCHEMA)
        self.repository = UserRepository(self.database)

    def test_create_list_disable_and_missing_user(self):
        created = self.repository.create("user_001")
        self.assertTrue(created["active"])
        self.assertFalse(created["has_face"])
        self.assertFalse(created["has_rfid"])
        with self.assertRaises(UserAlreadyExists):
            self.repository.create("user_001")
        disabled = self.repository.set_active("user_001", False)
        self.assertFalse(disabled["active"])
        with self.assertRaises(UserNotFound):
            self.repository.get("user_999")

    def test_reports_only_credential_presence_not_secrets(self):
        self.repository.create("user_001")
        with sqlite3.connect(self.database) as connection:
            connection.execute(
                """INSERT INTO biometric_templates
                   (user_id, ciphertext, nonce, model_version, algorithm_version)
                   VALUES (1, X'1234', X'5678', 'model', 'algorithm')"""
            )
        registry = CardRegistry(self.database, self.key)
        registry.enroll("user_001", "01020304")
        user = self.repository.get("user_001")
        self.assertTrue(user["has_face"])
        self.assertTrue(user["has_rfid"])
        self.assertEqual(user["biometric_templates"], 1)
        self.assertNotIn("ciphertext", user)
        self.assertNotIn("uid", user)
        self.assertFalse(self.repository.revoke_rfid("user_001")["has_rfid"])
        self.assertFalse(self.repository.revoke_face("user_001")["has_face"])
        with self.assertRaises(CredentialNotFound):
            self.repository.revoke_face("user_001")


if __name__ == "__main__":
    unittest.main()
