"""Fechas de la API → zona del front, formato dd/mm/aaaa HH:MM:SS (contrato §9)."""

from datetime import datetime, timezone


FORMAT = "%d/%m/%Y %H:%M:%S"
EMPTY = "—"


def parse(value):
    """Texto ISO de la API → datetime con zona. Sin offset se asume UTC.

    Sólo `created_at` de usuarios viene sin offset (SQLite CURRENT_TIMESTAMP).
    """
    if isinstance(value, datetime):
        moment = value
    else:
        try:
            moment = datetime.fromisoformat(str(value))
        except (TypeError, ValueError):
            return None
    if moment.tzinfo is None or moment.utcoffset() is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment


def format_local(value, tz):
    moment = parse(value) if value is not None else None
    return moment.astimezone(tz).strftime(FORMAT) if moment else EMPTY


def now_utc():
    return datetime.now(timezone.utc)


def seconds_since(value, now=None):
    moment = parse(value) if value is not None else None
    if moment is None:
        return None
    return max(0, int(((now or now_utc()) - moment).total_seconds()))


def ago(value, now=None):
    seconds = seconds_since(value, now)
    if seconds is None:
        return None
    if seconds < 120:
        return f"hace {seconds} s"
    if seconds < 7200:
        return f"hace {seconds // 60} min"
    if seconds < 172800:
        return f"hace {seconds // 3600} h"
    return f"hace {seconds // 86400} d"


def seconds_until(value, now=None):
    moment = parse(value) if value is not None else None
    if moment is None:
        return 0
    return max(0, int((moment - (now or now_utc())).total_seconds() + 0.999))


def api_day(occurred_at):
    """Día del evento tal como lo filtra la API: prefijo de texto de `occurred_at`."""
    return str(occurred_at)[:10]


def today(tz, now=None):
    return (now or now_utc()).astimezone(tz).date()
