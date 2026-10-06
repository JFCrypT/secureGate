from pathlib import Path
from unittest.mock import patch
import json
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "raspberry"))

from securegate.alerts.telegram import TelegramConfig, TelegramNotifier


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


class TelegramPollingTests(unittest.TestCase):
    @patch("securegate.alerts.telegram.urlopen")
    def test_get_updates_returns_list(self, urlopen):
        urlopen.return_value = FakeResponse(
            {"ok": True, "result": [{"update_id": 7, "message": {"chat": {"id": 123}, "text": "/logs"}}]}
        )
        notifier = TelegramNotifier(TelegramConfig("token", "123"))
        updates = notifier.get_updates(offset=7, timeout=0)
        self.assertEqual(len(updates), 1)
        request = urlopen.call_args.args[0]
        self.assertIn("getUpdates", request.full_url)
        self.assertIn("offset=7", request.full_url)

    @patch("securegate.alerts.telegram.urlopen")
    def test_send_document_uses_multipart(self, urlopen):
        urlopen.return_value = FakeResponse({"ok": True})
        notifier = TelegramNotifier(TelegramConfig("token", "123"))
        notifier.send_document("linea1\nlinea2", "securegate-2026-10-03.log", caption="Log de hoy")
        request = urlopen.call_args.args[0]
        self.assertTrue(request.full_url.endswith("/sendDocument"))
        self.assertIn(b"securegate-2026-10-03.log", request.data)
        self.assertIn("Log de hoy".encode("utf-8"), request.data)


if __name__ == "__main__":
    unittest.main()
