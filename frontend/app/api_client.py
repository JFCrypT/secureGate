"""Cliente de la API secureGate. Es el ÚNICO módulo que la llama.

El token Bearer vive sólo acá: no se loguea ni se devuelve en errores.
"""

import logging
import re
import time

import httpx


logger = logging.getLogger("securegate.front.api")

TIMEOUT_SECONDS = 3.0
USERS_CACHE_SECONDS = 10.0
PAGE_MAX = 500
EXTERNAL_ID_RE = re.compile(r"user_[A-Za-z0-9_-]+")


class ApiError(Exception):
    """Base de los errores de la API; `message` es apto para mostrar."""

    message = "Error al consultar la API."

    def __init__(self, message=None):
        super().__init__(message or self.message)
        if message:
            self.message = message


class ApiUnavailable(ApiError):
    message = "API no disponible"


class ApiConfigError(ApiError):
    """401: el token del front no coincide con el de la API."""

    message = "Error de configuración del servidor"


class ApiBackendError(ApiError):
    """500 o 503: la API real devuelve 500 si falla SQLite en /api/v1/*."""

    message = "Base de datos no disponible"


class ApiNotFound(ApiError):
    message = "No encontrado"


class ApiConflict(ApiError):
    message = "La operación entra en conflicto con el estado actual."


class ApiValidation(ApiError):
    """422. `fields` mapea campo → mensaje; `errors` son los mensajes sueltos."""

    message = "Datos inválidos."

    def __init__(self, errors=(), fields=None):
        self.errors = list(errors)
        self.fields = dict(fields or {})
        texts = self.errors + [f"{k}: {v}" for k, v in self.fields.items()]
        super().__init__("; ".join(texts) or self.message)


def valid_external_id(external_id):
    return isinstance(external_id, str) and bool(EXTERNAL_ID_RE.fullmatch(external_id))


def _detail(response):
    try:
        return response.json().get("detail")
    except (ValueError, AttributeError):
        return None


def _validation_error(detail):
    if isinstance(detail, list):
        errors, fields = [], {}
        for item in detail:
            if not isinstance(item, dict):
                errors.append(str(item))
                continue
            message = str(item.get("msg", "Valor inválido."))
            location = [str(part) for part in item.get("loc", ()) if part != "body"]
            if location:
                fields[".".join(location)] = message
            else:
                errors.append(message)
        return ApiValidation(errors, fields)
    return ApiValidation([str(detail)] if detail else [])


class SecureGateClient:
    def __init__(self, base_url, token, transport=None, clock=time.monotonic):
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._transport = transport
        self._clock = clock
        self._users_cache = None

    async def _request(self, method, path, *, params=None, json=None):
        try:
            async with httpx.AsyncClient(
                base_url=self._base_url,
                timeout=TIMEOUT_SECONDS,
                transport=self._transport,
                headers={"Authorization": f"Bearer {self._token}"},
            ) as client:
                response = await client.request(method, path, params=params, json=json)
        except httpx.HTTPError as exc:
            # Sin str(exc) de httpx: puede incluir la URL, nunca el token, pero
            # igual alcanza con el tipo para diagnosticar.
            logger.warning("API no disponible (%s %s): %s", method, path, type(exc).__name__)
            raise ApiUnavailable() from None

        code = response.status_code
        if code < 300:
            return response.json()
        detail = _detail(response)
        if code == 401:
            logger.error(
                "La API rechazó el token del front (401 en %s %s). "
                "Revisar SECUREGATE_API_TOKEN.", method, path,
            )
            raise ApiConfigError()
        if code == 404:
            raise ApiNotFound(str(detail) if detail else None)
        if code == 409:
            raise ApiConflict(str(detail) if detail else None)
        if code == 422:
            raise _validation_error(detail)
        logger.error("La API respondió %s en %s %s.", code, method, path)
        raise ApiBackendError()

    # --- Sistema -----------------------------------------------------------

    async def health(self):
        return await self._request("GET", "/health")

    async def status(self):
        return await self._request("GET", "/api/v1/status")

    # --- Usuarios ----------------------------------------------------------

    def invalidate_users(self):
        self._users_cache = None

    async def list_users(self, fresh=False):
        """Lista de usuarios, cacheada 10 s para armar nombres en cada evento."""
        now = self._clock()
        if not fresh and self._users_cache and now - self._users_cache[0] < USERS_CACHE_SECONDS:
            return self._users_cache[1]
        users = await self._request("GET", "/api/v1/users")
        self._users_cache = (now, users)
        return users

    async def users_by_id(self):
        return {user["external_id"]: user for user in await self.list_users()}

    async def get_user(self, external_id):
        # La API da 404 en GET y 422 en PATCH para un ID mal formado; acá es
        # siempre "no encontrado" y no se hace la llamada.
        if not valid_external_id(external_id):
            raise ApiNotFound("Usuario inexistente.")
        return await self._request("GET", f"/api/v1/users/{external_id}")

    async def create_user(self, external_id, first_name=None, last_name=None, role=None):
        body = {"external_id": external_id}
        for name, value in (("first_name", first_name), ("last_name", last_name), ("role", role)):
            if value is not None:
                body[name] = value
        try:
            return await self._request("POST", "/api/v1/users", json=body)
        finally:
            self.invalidate_users()

    async def update_user(self, external_id, changes):
        """`changes` admite first_name, last_name, role (None borra el campo) y active."""
        if not valid_external_id(external_id):
            raise ApiNotFound("Usuario inexistente.")
        body = dict(changes)
        # En la API real {"active": null} desactiva al usuario: nunca se manda.
        if "active" in body and not isinstance(body["active"], bool):
            raise ValueError("active debe ser booleano.")
        try:
            return await self._request("PATCH", f"/api/v1/users/{external_id}", json=body)
        finally:
            self.invalidate_users()

    async def revoke_rfid(self, external_id):
        return await self._revoke(external_id, "rfid")

    async def revoke_face(self, external_id):
        return await self._revoke(external_id, "face")

    async def _revoke(self, external_id, credential):
        if not valid_external_id(external_id):
            raise ApiNotFound("Usuario inexistente.")
        try:
            return await self._request("DELETE", f"/api/v1/users/{external_id}/{credential}")
        finally:
            self.invalidate_users()

    # --- Enrolamiento RFID -------------------------------------------------

    async def create_enrollment(self, external_id, timeout_seconds=60):
        if not valid_external_id(external_id):
            raise ApiNotFound("Usuario inexistente.")
        return await self._request(
            "POST",
            f"/api/v1/users/{external_id}/rfid-enrollments",
            json={"timeout_seconds": timeout_seconds},
        )

    async def get_enrollment(self, request_id):
        return await self._request("GET", f"/api/v1/rfid-enrollments/{int(request_id)}")

    async def cancel_enrollment(self, request_id):
        return await self._request("DELETE", f"/api/v1/rfid-enrollments/{int(request_id)}")

    # --- Eventos de acceso -------------------------------------------------

    async def list_events(self, limit=50, offset=0, day=None, method=None, granted=None):
        params = {"limit": limit, "offset": offset}
        if day:
            params["day"] = day if isinstance(day, str) else day.isoformat()
        if method:
            params["method"] = method
        if granted is not None:
            params["granted"] = "true" if granted else "false"
        return await self._request("GET", "/api/v1/access-events", params=params)

    async def events_for_days(self, days, cap, method=None, granted=None):
        """Todos los eventos de cada día (la API sólo filtra por día).

        Devuelve (eventos, truncado). Pagina de a 500 hasta agotar cada día o
        llegar a `cap`.
        """
        events = []
        for day in days:
            offset = 0
            while True:
                page = await self.list_events(
                    limit=PAGE_MAX, offset=offset, day=day, method=method, granted=granted
                )
                events.extend(page)
                if len(events) >= cap:
                    return events[:cap], True
                if len(page) < PAGE_MAX:
                    break
                offset += PAGE_MAX
        return events, False

    async def summary(self, day=None):
        params = {}
        if day:
            params["day"] = day if isinstance(day, str) else day.isoformat()
        return await self._request("GET", "/api/v1/access-events/summary", params=params)
