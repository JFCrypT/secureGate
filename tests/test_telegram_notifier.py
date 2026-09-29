from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
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
)


class FakeResponse:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def read(self):
        return json.dumps({"ok": True}).encode("utf-8")


class TelegramNotifierTests(unittest.TestCase):
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
