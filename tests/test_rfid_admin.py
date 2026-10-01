from contextlib import closing, redirect_stdout
from pathlib import Path
from unittest.mock import patch
import io
import sqlite3
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "admin"))
sys.path.insert(0, str(ROOT / "raspberry"))

from init_db import SCHEMA
from manage_rfid import main
from securegate.rfid.registry import CardRegistry


class AdminTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / "test.db"
        self.key = Path(self.temp.name) / "key"
        with closing(sqlite3.connect(self.db)) as connection:
            connection.executescript(SCHEMA)

    def initialize(self):
        with patch.object(sys, "argv", ["manage_rfid.py", "--database", str(self.db), "--key", str(self.key), "init"]), redirect_stdout(io.StringIO()):
            return main()

    def test_init_twice_preserves_key_and_existing_card(self):
        self.assertEqual(self.initialize(), 0)
        original = self.key.read_bytes()
        self.assertEqual(len(original), 32)
        registry = CardRegistry(self.db, self.key)
        registry.enroll("user_001", "01020304")
        self.assertEqual(self.initialize(), 0)
        self.assertEqual(self.key.read_bytes(), original)
        self.assertEqual(CardRegistry(self.db, self.key).authorize("01020304"), "user_001")

    def test_missing_key_with_existing_cards_requires_restore(self):
        self.assertEqual(self.initialize(), 0)
        CardRegistry(self.db, self.key).enroll("user_001", "01020304")
        self.key.unlink()
        self.assertEqual(self.initialize(), 1)
        self.assertFalse(self.key.exists())


if __name__ == "__main__":
    unittest.main()
