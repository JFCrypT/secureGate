from datetime import datetime, time as clock_time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


DEFAULT_TIMEZONE = "America/Argentina/Buenos_Aires"


def load_timezone(name=DEFAULT_TIMEZONE):
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(
            f"Zona horaria desconocida: {name}"
        ) from exc


def is_restricted_time(moment):
    """Return True when an access attempt occurs outside allowed hours."""
    if not isinstance(moment, datetime):
        raise TypeError("moment debe ser un datetime.")

    if moment.tzinfo is None or moment.utcoffset() is None:
        raise ValueError(
            "moment debe incluir una zona horaria."
        )

    local_clock = moment.timetz().replace(tzinfo=None)

    if moment.weekday() < 5:
        return (
            local_clock >= clock_time(21, 0)
            or local_clock < clock_time(6, 0)
        )

    return (
        local_clock >= clock_time(17, 0)
        or local_clock < clock_time(9, 0)
    )
