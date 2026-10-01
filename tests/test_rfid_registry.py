from pathlib import Path
from contextlib import contextmanager
import sqlite3
import sys
import tempfile
import unittest

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR / "raspberry"))

from init_db import SCHEMA as BIOMETRIC_SCHEMA
from securegate.rfid.registry import CardRegistry, normalize_uid


class RegistryTests(unittest.TestCase):
    @contextmanager
    def connection(self):
        connection = sqlite3.connect(self.database)
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.database = Path(self.temp.name) / "test.db"
        self.key = Path(self.temp.name) / "key"
        self.key.write_bytes(b"x" * 32)
        with self.connection() as connection:
            connection.executescript(BIOMETRIC_SCHEMA)
            connection.execute("INSERT INTO users(external_id) VALUES ('user_001')")
            connection.execute("""INSERT INTO biometric_templates
                (user_id, ciphertext, nonce, model_version, algorithm_version)
                VALUES (1, X'1234', X'ABCD', 'model', 'algorithm')""")
        self.registry = CardRegistry(self.database, self.key)

    def test_uid_canonicalization_preserves_leading_zeros(self):
        self.assertEqual(normalize_uid("00:ab:02:03"), "00AB0203")
        self.assertEqual(normalize_uid([0, 171, 2, 3]), "00AB0203")
        self.assertEqual(normalize_uid("04 01 02 03 04 05 06"), "04010203040506")

    def test_enroll_same_user_keeps_biometrics_unchanged(self):
        self.registry.enroll("user_001", "00AB0203")
        self.assertEqual(self.registry.authorize("00:AB:02:03"), "user_001")
        with self.connection() as connection:
            self.assertEqual(connection.execute("SELECT ciphertext FROM biometric_templates").fetchone()[0], b"\x12\x34")
            row = connection.execute("SELECT uid_digest FROM rfid_credentials").fetchone()[0]
            self.assertEqual(len(row), 64)
            self.assertNotIn("00AB0203", row)

    def test_unknown_card_denied_and_no_automatic_enrollment(self):
        self.assertIsNone(self.registry.authorize("00AB0203"))
        with self.connection() as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM rfid_credentials").fetchone()[0], 0)

    def test_new_rfid_only_user_and_multiple_cards(self):
        self.registry.enroll("user_002", "00AB0203")
        self.registry.enroll("user_002", "04010203040506")
        self.assertEqual(self.registry.authorize("04010203040506"), "user_002")
        with self.connection() as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM biometric_templates").fetchone()[0], 1)

    def test_revoke_and_explicit_reenrollment(self):
        self.registry.enroll("user_001", "00AB0203")
        self.assertTrue(self.registry.revoke("00AB0203"))
        self.assertIsNone(self.registry.authorize("00AB0203"))
        self.registry.enroll("user_001", "00AB0203")
        self.assertEqual(self.registry.authorize("00AB0203"), "user_001")

    def test_card_cannot_be_silently_transferred(self):
        self.registry.enroll("user_001", "00AB0203")
        with self.assertRaises(ValueError):
            self.registry.enroll("user_002", "00AB0203")
        self.assertEqual(self.registry.authorize("00AB0203"), "user_001")

    def test_inactive_user_denied_and_not_reactivated(self):
        self.registry.enroll("user_001", "00AB0203")
        with self.connection() as connection:
            connection.execute("UPDATE users SET active = 0 WHERE user_id = 1")
        self.assertIsNone(self.registry.authorize("00AB0203"))
        with self.assertRaises(ValueError):
            self.registry.enroll("user_001", "00AB0203")

    def test_invalid_uids_rejected(self):
        for uid in ("", "123", "abcdefgh", "01" * 10, "12';DROP TABLE users"):
            with self.subTest(uid=uid), self.assertRaises(ValueError):
                normalize_uid(uid)

    def test_wrong_key_does_not_authorize_cards(self):
        self.registry.enroll("user_001", "00AB0203")
        other_key = Path(self.temp.name) / "other_key"
        other_key.write_bytes(b"y" * 32)
        other = CardRegistry(self.database, other_key)
        self.assertIsNone(other.authorize("00AB0203"))

    def test_bad_key_and_missing_database_fail(self):
        self.key.write_bytes(b"short")
        with self.assertRaises(ValueError):
            CardRegistry(self.database, self.key)
        with self.assertRaises(ValueError):
            CardRegistry(Path(self.temp.name) / "absent.db", self.key)


if __name__ == "__main__":
    unittest.main()
