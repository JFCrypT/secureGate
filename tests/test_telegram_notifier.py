from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs
from urllib.error import HTTPError
from unittest.mock import patch
import json
import os
import sys
import unittest

import numpy as np


ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR / "raspberry"))

from securegate.alerts.telegram import (
    TelegramConfigurationError,
    TelegramNotifier,
    TelegramConfig,
    TelegramDeliveryError,
)


class FakeResponse:
    def __init__(self, payload=None):
        self.payload = {"ok": True} if payload is None else payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


class TelegramNotifierTests(unittest.TestCase):
    @patch("securegate.alerts.telegram.urlopen")
    def test_text_without_photo_and_negative_response(self, urlopen):
        notifier = TelegramNotifier(TelegramConfig("synthetic-token", "123"))
        urlopen.return_value = FakeResponse()
        notifier.send_message("Tres intentos fallidos")
        request = urlopen.call_args.args[0]
        self.assertTrue(request.full_url.endswith("/sendMessage"))
        self.assertEqual(parse_qs(request.data.decode())["text"], ["Tres intentos fallidos"])
        for invalid_payload in ({"ok": False}, []):
            urlopen.return_value = FakeResponse(invalid_payload)
            with self.assertRaises(TelegramDeliveryError):
                notifier.send_message("alerta")

    @patch("securegate.alerts.telegram.urlopen")
    def test_http_errors_hide_token(self, urlopen):
        notifier = TelegramNotifier(TelegramConfig("synthetic-secret", "123"))
        urlopen.side_effect = HTTPError("https://api.telegram.org/botsynthetic-secret", 401, "Unauthorized", {}, None)
        with self.assertRaises(TelegramDeliveryError) as raised:
            notifier.send_message("alerta")
        self.assertNotIn("synthetic-secret", str(raised.exception))
        self.assertIn("401", str(raised.exception))

    @patch("securegate.alerts.telegram.urlopen")
    def test_timeout_is_controlled(self, urlopen):
        urlopen.side_effect = TimeoutError()
        notifier = TelegramNotifier(TelegramConfig("synthetic", "123"))
        with self.assertRaises(TelegramDeliveryError):
            notifier.send_message("alerta")

    @patch.dict(os.environ, {}, clear=True)
    def test_missing_environment_disables_notifier(self):
        self.assertIsNone(
            TelegramNotifier.from_environment()
        )

    @patch.dict(
        os.environ,
        {"TELEGRAM_BOT_TOKEN": "only-token"},
        clear=True,
    )
    def test_partial_environment_is_rejected(self):
        with self.assertRaises(TelegramConfigurationError):
            TelegramNotifier.from_environment()

    @patch("securegate.alerts.telegram.urlopen")
    @patch.dict(
        os.environ,
        {
            "TELEGRAM_BOT_TOKEN": "test-token",
            "TELEGRAM_CHAT_ID": "123456",
        },
        clear=True,
    )
    def test_sends_caption_and_jpeg_as_multipart(
        self,
        mocked_urlopen,
    ):
        mocked_urlopen.return_value = FakeResponse()
        notifier = TelegramNotifier.from_environment()
        image = np.zeros((16, 16, 3), dtype=np.uint8)
        fake_cv2 = SimpleNamespace(
            IMWRITE_JPEG_QUALITY=1,
            imencode=lambda extension, frame, options: (
                True,
                np.array([255, 216, 255, 217], dtype=np.uint8),
            ),
        )

        with patch.dict(sys.modules, {"cv2": fake_cv2}):
            payload = notifier.send_photo(
                image,
                "ALERTA de prueba",
                captured_at=datetime(
                    2026,
                    9,
                    28,
                    21,
                    5,
                    7,
                ),
            )

        self.assertTrue(payload["ok"])
        request = mocked_urlopen.call_args.args[0]
        body = request.data
        self.assertIn(b"123456", body)
        self.assertIn("ALERTA de prueba".encode("utf-8"), body)
        self.assertIn(
            b"securegate_20260928_210507.jpg",
            body,
        )
        self.assertIn(b"Content-Type: image/jpeg", body)


if __name__ == "__main__":
    unittest.main()
