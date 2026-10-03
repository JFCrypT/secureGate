"""Login de operadores, sesión, roles y CSRF.

La API de secureGate no tiene login de personas: lo agrega el front. El rate
limit vive en memoria, por eso uvicorn corre con un solo worker.
"""

from collections import deque
from pathlib import Path
from secrets import compare_digest, token_urlsafe
import json
import logging
import os
import re
import time

import bcrypt
from fastapi import Depends, HTTPException, Request

from app import labels


logger = logging.getLogger("securegate.front.auth")

ROLES = ("admin", "viewer")
USERNAME_RE = re.compile(r"[a-z0-9_.-]{2,32}")
MAX_PASSWORD_BYTES = 72  # límite de bcrypt
MIN_PASSWORD_LENGTH = 8


class NotAuthenticated(Exception):
    pass


# --- Operadores -------------------------------------------------------------

def hash_password(password, rounds=12):
    data = password.encode("utf-8")
    if len(data) > MAX_PASSWORD_BYTES:
        raise ValueError("La contraseña no puede superar los 72 bytes.")
    return bcrypt.hashpw(data, bcrypt.gensalt(rounds)).decode("ascii")


def _check(password, hashed):
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("ascii"))
    except ValueError:
        return False


class OperatorStore:
    """Archivo JSON `{"usuarios":[{"usuario","hash","rol","activo"}]}`.

    Se relee cuando cambia en disco, así `cli.py` no exige reiniciar el front.
    """

    def __init__(self, path):
        self.path = Path(path)
        self._stamp = None
        self._operators = {}
        self._dummy_hash = None

    def all(self):
        try:
            stat = self.path.stat()
        except OSError:
            self._stamp, self._operators = None, {}
            return self._operators
        stamp = (stat.st_mtime_ns, stat.st_size)
        if stamp != self._stamp:
            self._operators = self._read()
            self._stamp = stamp
        return self._operators

    def _read(self):
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            entries = data["usuarios"]
        except (OSError, ValueError, KeyError, TypeError):
            logger.error("No se pudo leer el archivo de operadores (FRONT_OPERATORS_FILE).")
            return {}
        operators = {}
        for entry in entries:
            if (
                isinstance(entry, dict)
                and isinstance(entry.get("usuario"), str)
                and isinstance(entry.get("hash"), str)
                and entry.get("rol") in ROLES
            ):
                operators[entry["usuario"]] = entry
        return operators

    def get_active(self, username):
        operator = self.all().get(username)
        if operator and operator.get("activo", True):
            return operator
        return None

    def verify(self, username, password):
        operator = self.get_active(username)
        if operator is None:
            # Mismo costo que un login real, para no delatar qué usuarios existen.
            if self._dummy_hash is None:
                self._dummy_hash = hash_password(token_urlsafe(16))
            _check(password, self._dummy_hash)
            return None
        return operator if _check(password, operator["hash"]) else None


def read_operators_file(path):
    path = Path(path)
    if not path.exists():
        return {"usuarios": []}
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        return {"usuarios": []}  # archivo recién creado con los permisos correctos
    data = json.loads(text)
    if not isinstance(data, dict) or not isinstance(data.get("usuarios"), list):
        raise ValueError("El archivo de operadores no tiene el formato esperado.")
    return data


def write_operators_file(path, data):
    """Escritura con permisos 600; atómica si el directorio lo permite."""
    path = Path(path)
    text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    temporary = path.with_name(path.name + ".tmp")
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    except PermissionError:
        # Directorio de root (p. ej. /etc/securegate) con el archivo ya creado
        # a nombre del usuario del servicio: se escribe en el lugar.
        path.write_text(text, encoding="utf-8")
        return
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(text)
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


# --- Rate limit de login ----------------------------------------------------

class LoginRateLimiter:
    """5 intentos fallidos por IP en 5 minutos → bloqueo de 5 minutos."""

    def __init__(self, max_failures=5, window=300.0, block=300.0, clock=time.monotonic):
        self.max_failures = max_failures
        self.window = window
        self.block = block
        self.clock = clock
        self._failures = {}
        self._blocked_until = {}

    def blocked_seconds(self, ip):
        remaining = self._blocked_until.get(ip, 0) - self.clock()
        if remaining <= 0:
            self._blocked_until.pop(ip, None)
            return 0
        return remaining

    def register_failure(self, ip):
        now = self.clock()
        failures = self._failures.setdefault(ip, deque())
        failures.append(now)
        while failures and now - failures[0] > self.window:
            failures.popleft()
        if len(failures) >= self.max_failures:
            self._blocked_until[ip] = now + self.block
            del self._failures[ip]
        self._prune(now)

    def reset(self, ip):
        self._failures.pop(ip, None)

    def _prune(self, now):
        if len(self._failures) > 10000:
            self._failures = {
                ip: items for ip, items in self._failures.items()
                if items and now - items[-1] <= self.window
            }


def client_ip(request):
    # IP del socket: el front se sirve directo, sin proxy ni X-Forwarded-For.
    return request.client.host if request.client else "desconocida"


# --- Sesión y dependencias --------------------------------------------------

def csrf_token(request):
    token = request.session.get("csrf")
    if not token:
        token = token_urlsafe(32)
        request.session["csrf"] = token
    return token


def start_session(request, operator):
    settings = request.app.state.settings
    request.session.clear()
    request.session["usuario"] = operator["usuario"]
    request.session["exp"] = int(time.time()) + settings.session_hours * 3600
    request.session["csrf"] = token_urlsafe(32)


def current_operator(request):
    username = request.session.get("usuario")
    expires = request.session.get("exp", 0)
    if not username or not isinstance(expires, int) or expires <= time.time():
        return None
    # Se revalida en cada pedido: deshabilitar un operador corta su sesión.
    operator = request.app.state.operators.get_active(username)
    if operator is None:
        return None
    return {
        "usuario": operator["usuario"],
        "rol": operator["rol"],
        "rol_label": labels.operator_role(operator["rol"]),
        "is_admin": operator["rol"] == "admin",
    }


async def page_context(request: Request):
    """Deja en `request.state` lo que usa `render` (operador y token CSRF)."""
    request.state.csrf_token = csrf_token(request)
    request.state.operator = current_operator(request)


async def require_login(request: Request, _=Depends(page_context)):
    if request.state.operator is None:
        raise NotAuthenticated()
    return request.state.operator


async def require_admin(operator=Depends(require_login)):
    if not operator["is_admin"]:
        raise HTTPException(status_code=403, detail="Esta acción es sólo para administradores.")
    return operator


async def verify_csrf(request: Request):
    expected = request.session.get("csrf")
    sent = request.headers.get("X-CSRF-Token")
    if not sent:
        form = await request.form()
        sent = form.get("csrf_token")
    if not expected or not isinstance(sent, str) or not compare_digest(sent, expected):
        raise HTTPException(status_code=403, detail="Token CSRF inválido o ausente. Recargá la página.")


def flash(request, text, kind="ok"):
    # Se reasigna la lista: mutarla en el lugar no marca la sesión como modificada.
    request.session["flash"] = [*request.session.get("flash", []), {"kind": kind, "text": text}]
