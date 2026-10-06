"""Comandos Telegram entrantes (polling getUpdates). Solo /logs."""

from __future__ import annotations

MAX_MESSAGE_CHARS = 4000
DEFAULT_LOG_LINES = 50
MAX_LOG_LINES = 200


def parse_command(text):
    """Devuelve (comando, argumento) o (None, None) si no es comando."""
    if not isinstance(text, str):
        return None, None
    cleaned = text.strip()
    if not cleaned.startswith("/"):
        return None, None
    token = cleaned.split(None, 1)
    name = token[0].split("@")[0].lower()
    arg = token[1].strip() if len(token) > 1 else ""
    return name, arg


def parse_limit(arg, default=DEFAULT_LOG_LINES):
    try:
        value = int(str(arg).strip())
    except (ValueError, TypeError):
        return default
    return max(1, min(MAX_LOG_LINES, value))


def is_authorized(update, expected_chat_id):
    try:
        return str(update["message"]["chat"]["id"]) == str(expected_chat_id)
    except (KeyError, TypeError):
        return False


def extract_message(update):
    try:
        message = update["message"]
        return message.get("text", ""), message.get("message_id")
    except (KeyError, TypeError, AttributeError):
        return "", None


def build_logs_text(daily_logger, access_log=None, limit=DEFAULT_LOG_LINES, moment=None):
    """Texto del log del día (00:00 hasta ahora) + resumen SQLite."""
    limit = max(1, min(MAX_LOG_LINES, int(limit)))
    lines, total = daily_logger.read_today(limit=limit, moment=moment)
    label = daily_logger.today_label(moment=moment)
    header = f"📋 Log secureGate {label} (00:00 hasta ahora)"
    if total == 0:
        body = "Sin eventos registrados hoy."
    elif total > len(lines):
        body = "\n".join(lines)
        body = f"(mostrando últimas {len(lines)} de {total} líneas)\n{body}"
    else:
        body = "\n".join(lines)

    summary_line = ""
    if access_log is not None:
        try:
            summary = access_log.summary(date_prefix=label)
            summary_line = (
                f"\nResumen DB: total={summary.get('total', 0)} "
                f"autorizados={summary.get('granted', 0)} "
                f"rechazados={summary.get('denied', 0)} "
                f"fuera_horario={summary.get('restricted', 0)}"
            )
        except Exception:
            summary_line = "\nResumen DB no disponible."
    text = f"{header}\n{body}{summary_line}"
    if len(text) > MAX_MESSAGE_CHARS:
        # Recorta por el final (lo más reciente es lo importante).
        truncated = text[-MAX_MESSAGE_CHARS:]
        cut = truncated.find("\n")
        if cut > 0:
            truncated = truncated[cut + 1 :]
        text = f"{header}\n(recortado, ver archivo adjunto)\n{truncated}{summary_line}"
    return text


def should_send_as_document(text):
    return len(text) >= MAX_MESSAGE_CHARS
