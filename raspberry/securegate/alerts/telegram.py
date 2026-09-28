from dataclasses import dataclass
from datetime import datetime
from os import environ
from secrets import token_hex
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
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

        request = Request(
            (
                "https://api.telegram.org/bot"
                f"{self.config.bot_token}/sendPhoto"
            ),
            data=body,
            headers={
                "Content-Type": (
                    "multipart/form-data; "
                    f"boundary={boundary}"
                ),
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
        except URLError as exc:
            raise TelegramDeliveryError(
                "No se pudo conectar con Telegram."
            ) from exc
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise TelegramDeliveryError(
                "Telegram devolvió una respuesta inválida."
            ) from exc

        if not payload.get("ok"):
            description = payload.get(
                "description",
                "error sin descripción",
            )
            raise TelegramDeliveryError(
                f"Telegram no confirmó el envío: {description}"
            )

        return payload
