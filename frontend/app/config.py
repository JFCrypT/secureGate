"""Configuración del front: se lee del entorno y se valida al arrancar.

Los mensajes de error nombran la variable, nunca su valor.
"""

from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import os


FRONTEND_DIR = Path(__file__).resolve().parent.parent
MIN_SECRET_LENGTH = 32
PLACEHOLDER_PREFIX = "REEMPLAZAR"


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class Settings:
    api_url: str
    api_token: str
    session_secret: str
    operators_file: Path
    base_path: str = "/dashboard"
    timezone: str = "America/Argentina/Buenos_Aires"
    poll_realtime_ms: int = 2000
    poll_status_ms: int = 5000
    session_hours: int = 8

    @property
    def tz(self):
        return ZoneInfo(self.timezone)

    def __repr__(self):
        # El token y el secreto no deben aparecer en logs ni tracebacks.
        return f"Settings(api_url={self.api_url!r}, base_path={self.base_path!r})"


def load_env_file(path=FRONTEND_DIR / ".env", environ=os.environ):
    """Carga `frontend/.env` si existe, sin pisar variables ya definidas."""
    path = Path(path)
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        environ.setdefault(name.strip(), value)


def _secret(environ, name, errors):
    value = environ.get(name, "").strip()
    if not value:
        errors.append(f"{name} no está definida.")
    elif value.startswith(PLACEHOLDER_PREFIX):
        errors.append(f"{name} todavía tiene el marcador de ejemplo.")
    elif len(value) < MIN_SECRET_LENGTH:
        errors.append(f"{name} debe tener al menos {MIN_SECRET_LENGTH} caracteres.")
    return value


def _integer(environ, name, default, minimum, maximum, errors):
    raw = environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        errors.append(f"{name} debe ser un número entero.")
        return default
    if not minimum <= value <= maximum:
        errors.append(f"{name} debe estar entre {minimum} y {maximum}.")
    return value


def load_settings(environ=os.environ):
    errors = []

    api_url = environ.get("SECUREGATE_API_URL", "").strip().rstrip("/")
    if not api_url.startswith(("http://", "https://")):
        errors.append("SECUREGATE_API_URL debe ser una URL http(s) de la API.")

    api_token = _secret(environ, "SECUREGATE_API_TOKEN", errors)
    session_secret = _secret(environ, "FRONT_SESSION_SECRET", errors)

    operators_file = environ.get("FRONT_OPERATORS_FILE", "").strip()
    if not operators_file:
        errors.append("FRONT_OPERATORS_FILE no está definida.")

    base_path = environ.get("FRONT_BASE_PATH", "/dashboard").strip().rstrip("/")
    if not base_path.startswith("/") or len(base_path) < 2:
        errors.append("FRONT_BASE_PATH debe empezar con / (por ejemplo /dashboard).")

    timezone = environ.get("FRONT_TIMEZONE", "").strip() or Settings.timezone
    try:
        ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, ValueError):
        errors.append("FRONT_TIMEZONE no es una zona horaria válida.")

    poll_realtime = _integer(environ, "FRONT_POLL_REALTIME_MS", 2000, 500, 60000, errors)
    poll_status = _integer(environ, "FRONT_POLL_STATUS_MS", 5000, 500, 60000, errors)
    session_hours = _integer(environ, "FRONT_SESSION_HOURS", 8, 1, 72, errors)

    if errors:
        raise ConfigError(
            "Configuración inválida del front:\n- " + "\n- ".join(errors)
        )
    return Settings(
        api_url=api_url,
        api_token=api_token,
        session_secret=session_secret,
        operators_file=Path(operators_file),
        base_path=base_path,
        timezone=timezone,
        poll_realtime_ms=poll_realtime,
        poll_status_ms=poll_status,
        session_hours=session_hours,
    )
