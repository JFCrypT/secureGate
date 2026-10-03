from dataclasses import dataclass
from datetime import datetime
from os import environ
from secrets import token_hex
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from urllib.parse import urlencode
import json


class TelegramConfigurationError(RuntimeError):
    pass


class TelegramDeliveryError(RuntimeError):
    pass


@dataclass(frozen=True)
class TelegramConfig:
    bot_token: str
    chat_id: str
    timeout_seconds: float = 10.0

    @classmethod
    def from_environment(cls):
        bot_token = environ.get(
            "TELEGRAM_BOT_TOKEN",
            "",
        ).strip()
        chat_id = environ.get(
            "TELEGRAM_CHAT_ID",
            "",
        ).strip()

        if not bot_token and not chat_id:
            return None

        if not bot_token or not chat_id:
            raise TelegramConfigurationError(
                "TELEGRAM_BOT_TOKEN y TELEGRAM_CHAT_ID "
                "deben configurarse juntos."
            )

        return cls(
            bot_token=bot_token,
            chat_id=chat_id,
        )


def _multipart_field(boundary, name, value):
    return (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="{name}"\r\n'
        "\r\n"
        f"{value}\r\n"
    ).encode("utf-8")


def _multipart_file(
    boundary,
    name,
    filename,
    content_type,
    content,
):
    header = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="{name}"; '
        f'filename="{filename}"\r\n'
        f"Content-Type: {content_type}\r\n"
        "\r\n"
    ).encode("utf-8")

    return header + content + b"\r\n"


class TelegramNotifier:
    def __init__(self, config):
        self.config = config

    @classmethod
    def from_environment(cls):
        config = TelegramConfig.from_environment()

        if config is None:
            return None

        return cls(config)

    def send_message(self, text):
        """Alerts must still be delivered when no camera capture is available."""
        body = urlencode({
            "chat_id": self.config.chat_id,
            "text": text,
        }).encode("utf-8")
        return self._send("sendMessage", body, "application/x-www-form-urlencoded")

    def send_photo(self, image, caption, captured_at=None):
        import cv2

        encoded, jpeg = cv2.imencode(
            ".jpg",
            image,
            [cv2.IMWRITE_JPEG_QUALITY, 90],
        )

        if not encoded:
            raise TelegramDeliveryError(
                "No se pudo codificar la captura como JPEG."
            )

        if captured_at is None:
            captured_at = datetime.now()

        filename = (
            "securegate_"
            f"{captured_at.strftime('%Y%m%d_%H%M%S')}"
            ".jpg"
        )
        boundary = f"securegate-{token_hex(16)}"
        body = b"".join(
            [
                _multipart_field(
                    boundary,
                    "chat_id",
                    self.config.chat_id,
                ),
                _multipart_field(
                    boundary,
                    "caption",
                    caption,
                ),
                _multipart_file(
                    boundary,
                    "photo",
                    filename,
                    "image/jpeg",
                    jpeg.tobytes(),
                ),
                f"--{boundary}--\r\n".encode("ascii"),
            ]
        )

        return self._send(
            "sendPhoto", body, f"multipart/form-data; boundary={boundary}"
        )

    def send_document(self, content, filename, caption=""):
        """Envía un archivo (usado para logs que exceden el límite de texto)."""
        if isinstance(content, str):
            content = content.encode("utf-8")
        boundary = f"securegate-{token_hex(16)}"
        parts = [
            _multipart_field(
                boundary,
                "chat_id",
                self.config.chat_id,
            ),
            _multipart_file(
                boundary,
                "document",
                filename,
                "text/plain; charset=utf-8",
                content,
            ),
        ]
        if caption:
            parts.append(_multipart_field(boundary, "caption", caption[:1024]))
        parts.append(f"--{boundary}--\r\n".encode("ascii"))
        return self._send(
            "sendDocument", b"".join(parts), f"multipart/form-data; boundary={boundary}"
        )

    def get_updates(self, offset=None, timeout=0):
        """Polling para comandos (solo se usa para /logs)."""
        params = {"timeout": int(timeout), "allowed_updates": '["message"]'}
        if offset is not None:
            params["offset"] = int(offset)
        request = Request(
            (
                "https://api.telegram.org/bot"
                f"{self.config.bot_token}/getUpdates?{urlencode(params)}"
            ),
            headers={"User-Agent": "secureGate/1.0"},
            method="GET",
        )
        try:
            with urlopen(
                request,
                timeout=self.config.timeout_seconds + int(timeout),
            ) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raise TelegramDeliveryError(
                "Telegram rechazó la consulta " f"(HTTP {exc.code})."
            ) from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise TelegramDeliveryError(
                "No se pudo conectar con Telegram."
            ) from exc
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise TelegramDeliveryError(
                "Telegram devolvió una respuesta inválida."
            ) from exc
        if not isinstance(payload, dict) or not payload.get("ok"):
            raise TelegramDeliveryError("Telegram no confirmó la consulta.")
        result = payload.get("result", [])
        return result if isinstance(result, list) else []

    def _send(self, method, body, content_type):
        request = Request(
            (
                "https://api.telegram.org/bot"
                f"{self.config.bot_token}/{method}"
            ),
            data=body,
            headers={
                "Content-Type": content_type,
                "Content-Length": str(len(body)),
                "User-Agent": "secureGate/1.0",
            },
            method="POST",
        )

        try:
            with urlopen(
                request,
                timeout=self.config.timeout_seconds,
            ) as response:
                payload = json.loads(
                    response.read().decode("utf-8")
                )
        except HTTPError as exc:
            raise TelegramDeliveryError(
                "Telegram rechazó el envío "
                f"(HTTP {exc.code})."
            ) from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise TelegramDeliveryError(
                "No se pudo conectar con Telegram."
            ) from exc
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise TelegramDeliveryError(
                "Telegram devolvió una respuesta inválida."
            ) from exc

        if not isinstance(payload, dict) or not payload.get("ok"):
            raise TelegramDeliveryError(
                "Telegram no confirmó el envío."
            )

        return payload
