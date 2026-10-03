"""API falsa de secureGate para desarrollar y testear el front sin Raspberry.

SÓLO desarrollo y tests: nunca se instala ni se corre en la Pi. Escucha en
127.0.0.1:8100 (MOCK_PORT), nunca en 8000.

No importa nada de `raspberry/`: los modelos, las validaciones y los textos de
`detail` están copiados de `raspberry/securegate/` (api.py, users.py,
rfid/enrollment.py, runtime_status.py, access_log.py, access.py). Si la API
real cambia, hay que actualizar este archivo a mano.

Uso:
    python dev/mock_api.py
    curl "http://127.0.0.1:8100/mock/control?offline=1"
"""

from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from secrets import compare_digest
from typing import List, Optional
from zoneinfo import ZoneInfo
import asyncio
import os
import random
import re

from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.responses import PlainTextResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field


DEFAULT_PORT = 8100
LOCAL_TZ = ZoneInfo("America/Argentina/Buenos_Aires")
EXTERNAL_ID_PATTERN = re.compile(r"user_[A-Za-z0-9_-]+")
ONLINE_SECONDS = 15

# Textos idénticos a los de la API real.
INVALID_ID = "Usar un identificador pseudonimizado como user_001."
USER_NOT_FOUND = "Usuario inexistente."
USER_EXISTS = "El usuario ya existe."
NO_RFID = "El usuario no posee una tarjeta activa."
NO_FACE = "El usuario no posee biometría activa."
ALERT_FAILURES = "Tres intentos de ingreso fallidos consecutivos"
ALERT_SCHEDULE = "Intento de ingreso fuera de horario"


# --- Modelos (copia de raspberry/securegate/api.py) -------------------------

class UserCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    external_id: str = Field(min_length=6, max_length=64, pattern=r"^user_[A-Za-z0-9_-]+$")
    first_name: Optional[str] = Field(None, min_length=1, max_length=100)
    last_name: Optional[str] = Field(None, min_length=1, max_length=100)
    role: Optional[str] = Field(None, min_length=1, max_length=50)


class UserUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    first_name: Optional[str] = Field(None, min_length=1, max_length=100)
    last_name: Optional[str] = Field(None, min_length=1, max_length=100)
    role: Optional[str] = Field(None, min_length=1, max_length=50)
    active: Optional[bool] = None


class UserResponse(BaseModel):
    external_id: str
    first_name: Optional[str]
    last_name: Optional[str]
    role: Optional[str]
    active: bool
    created_at: str
    has_face: bool
    biometric_templates: int
    has_rfid: bool


class AccessEventResponse(BaseModel):
    event_id: int
    occurred_at: str
    method: str
    external_id: Optional[str]
    granted: bool
    restricted_time: bool
    alert_reasons: List[str]
    door_status: str


class AccessSummaryResponse(BaseModel):
    total: int
    granted: int
    denied: int
    restricted: int
    door_errors: int


class UserSummaryResponse(BaseModel):
    total: int
    active: int
    with_face: int
    with_rfid: int
    with_both: int


class RuntimeInfoResponse(BaseModel):
    online: bool
    status: str
    methods: Optional[str]
    door_mode: Optional[str]
    updated_at: Optional[str]


class BackendStatusResponse(BaseModel):
    api: str
    database: str
    runtime: RuntimeInfoResponse
    users: UserSummaryResponse
    access_events: AccessSummaryResponse


class RFIDEnrollmentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    timeout_seconds: int = Field(60, ge=10, le=300)


class RFIDEnrollmentResponse(BaseModel):
    request_id: int
    external_id: str
    status: str
    created_at: str
    expires_at: str
    finished_at: Optional[str]
    error_code: Optional[str]


# --- Estado en memoria ------------------------------------------------------

def _user(external_id, first_name, last_name, role, active, templates, has_rfid):
    return {
        "external_id": external_id, "first_name": first_name, "last_name": last_name,
        "role": role, "active": active, "created_at": "2026-09-01 12:00:00",
        "biometric_templates": templates, "has_rfid": has_rfid,
    }


class MockState:
    def __init__(self, clock=None, seed=7):
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.rng = random.Random(seed)
        self.users = [
            _user("user_001", "Ana", "Pérez", "docente", True, 2, True),
            _user("user_002", "Bruno", "Gómez", "alumno", True, 1, False),
            _user("user_003", "Carla", "Díaz", "no docente", True, 0, True),
            _user("user_004", "Diego", "López", "alumno", False, 1, True),
            _user("user_005", None, None, None, True, 0, False),
            _user("user_006", "Elena", "Ruiz", "docente", True, 0, False),
        ]
        self.events = []
        self.enrollments = []
        self.failures = 0
        # Lo que se maneja desde /mock/control.
        self.offline = "0"          # "0", "1" (heartbeat vencido), "stopped", "unknown"
        self.enroll = "completed"   # "completed", "failed", "expired"
        self.enroll_seconds = 5.0
        self.db_down = False
        self.methods = "both"
        self.door_mode = "simulate"
        self._seed_events()

    def now(self):
        return self.clock().astimezone(timezone.utc)

    # Usuarios

    def find_user(self, external_id):
        for user in self.users:
            if user["external_id"] == external_id:
                return user
        return None

    @staticmethod
    def serialize_user(user):
        return {
            "external_id": user["external_id"],
            "first_name": user["first_name"],
            "last_name": user["last_name"],
            "role": user["role"],
            "active": user["active"],
            "created_at": user["created_at"],
            "has_face": user["biometric_templates"] > 0,
            "biometric_templates": user["biometric_templates"],
            "has_rfid": user["has_rfid"],
        }

    def list_users(self):
        ordered = sorted(self.users, key=lambda user: user["external_id"])
        return [self.serialize_user(user) for user in ordered]

    # Eventos

    def add_event(self, moment=None, historical=False):
        moment = (moment or self.now()).astimezone(LOCAL_TZ)
        rng = self.rng
        method = rng.choice(("RFID", "facial"))
        roll = rng.random()
        if roll < 0.25:
            user, granted = None, False
        else:
            candidates = [
                u for u in self.users
                if (u["has_rfid"] if method == "RFID" else u["biometric_templates"] > 0)
            ]
            chosen = rng.choice(candidates) if candidates else None
            user = chosen["external_id"] if chosen else None
            granted = bool(chosen and chosen["active"])
        restricted = moment.hour < 7 or moment.hour >= 22 or rng.random() < 0.1
        self.failures = 0 if granted else self.failures + 1
        reasons = []
        if not granted and self.failures % 3 == 0:
            reasons.append(ALERT_FAILURES)
        # La alerta de horario tiene cooldown en el runtime real: a veces el
        # evento queda con restricted_time=true y sin texto de alerta.
        if restricted and rng.random() < 0.5:
            reasons.append(ALERT_SCHEDULE)
        if not granted:
            door = "not_requested"
        elif rng.random() < 0.08:
            door = "error"
        elif historical:
            door = rng.choice(("simulated", "simulated", "opened"))
        else:
            door = "simulated" if self.door_mode == "simulate" else "opened"
        event = {
            "event_id": len(self.events) + 1,
            "occurred_at": moment.isoformat(timespec="seconds"),
            "method": method,
            "external_id": user,
            "granted": granted,
            "restricted_time": restricted,
            "alert_reasons": reasons,
            "door_status": door,
        }
        self.events.append(event)
        return event

    def _seed_events(self):
        now = self.now()
        offsets = sorted(
            (self.rng.uniform(60, 7 * 86400) for _ in range(80)), reverse=True
        )
        for offset in offsets:
            self.add_event(now - timedelta(seconds=offset), historical=True)

    def list_events(self, limit, offset, date_prefix, method, granted):
        rows = [
            event for event in reversed(self.events)
            if (not date_prefix or event["occurred_at"].startswith(date_prefix))
            and (not method or event["method"] == method)
            and (granted is None or event["granted"] == granted)
        ]
        return rows[offset:offset + limit]

    def summary(self, date_prefix=None):
        rows = [
            event for event in self.events
            if not date_prefix or event["occurred_at"].startswith(date_prefix)
        ]
        return {
            "total": len(rows),
            "granted": sum(event["granted"] for event in rows),
            "denied": sum(not event["granted"] for event in rows),
            "restricted": sum(event["restricted_time"] for event in rows),
            "door_errors": sum(event["door_status"] == "error" for event in rows),
        }

    # Runtime

    def runtime(self):
        if self.offline == "unknown":
            return {"online": False, "status": "unknown", "methods": None,
                    "door_mode": None, "updated_at": None}
        now = self.now()
        if self.offline == "1":
            updated, state = now - timedelta(seconds=90), "running"
        elif self.offline == "stopped":
            updated, state = now - timedelta(seconds=90), "stopped"
        else:
            updated, state = now, "running"
        age = (now - updated).total_seconds()
        return {
            "online": state == "running" and 0 <= age <= ONLINE_SECONDS,
            "status": state,
            "methods": self.methods,
            "door_mode": self.door_mode,
            "updated_at": updated.isoformat(timespec="seconds"),
        }

    def reader_active(self):
        return self.offline == "0" and self.methods in ("both", "rfid")

    # Enrolamiento

    def advance_enrollments(self):
        """Simula al runtime leyendo la tarjeta y la caducidad perezosa de la API."""
        now = self.now()
        for request in self.enrollments:
            if request["status"] != "pending":
                continue
            created = datetime.fromisoformat(request["created_at"])
            expires = datetime.fromisoformat(request["expires_at"])
            ready = (now - created).total_seconds() >= self.enroll_seconds
            if ready and now < expires and self.reader_active() and self.enroll != "expired":
                request["finished_at"] = now.isoformat(timespec="seconds")
                if self.enroll == "failed":
                    request["status"] = "failed"
                    request["error_code"] = "card_unavailable"
                else:
                    request["status"] = "completed"
                    self.find_user(request["external_id"])["has_rfid"] = True
            elif expires <= now:
                request["status"] = "expired"
                request["finished_at"] = now.isoformat(timespec="seconds")

    def find_enrollment(self, request_id):
        for request in self.enrollments:
            if request["request_id"] == request_id:
                return request
        return None


def valid_id(external_id):
    return bool(EXTERNAL_ID_PATTERN.fullmatch(external_id))


# --- Aplicación -------------------------------------------------------------

def create_mock_app(api_token, event_seconds=0.0, clock=None):
    if not isinstance(api_token, str) or len(api_token) < 32:
        raise ValueError("SECUREGATE_API_TOKEN debe tener al menos 32 caracteres.")

    state = MockState(clock=clock)

    async def generator():
        while True:
            await asyncio.sleep(event_seconds)
            state.add_event()

    @asynccontextmanager
    async def lifespan(app):
        task = asyncio.create_task(generator()) if event_seconds > 0 else None
        yield
        if task:
            task.cancel()

    app = FastAPI(title="secureGate MOCK API (sólo desarrollo)", lifespan=lifespan)
    app.state.mock = state
    bearer = HTTPBearer(auto_error=False)

    def require_token(
        credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer),
    ):
        valid = (
            credentials is not None
            and credentials.scheme.lower() == "bearer"
            and compare_digest(credentials.credentials, api_token)
        )
        if not valid:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token de API inválido o ausente.",
                headers={"WWW-Authenticate": "Bearer"},
            )

    class DatabaseDown(Exception):
        pass

    def database():
        # La API real no atrapa sqlite3.Error en /api/v1/*: responde 500.
        if state.db_down:
            raise DatabaseDown()

    @app.exception_handler(DatabaseDown)
    async def database_down(request, exc):
        return PlainTextResponse("Internal Server Error", status_code=500)

    protected = [Depends(require_token), Depends(database)]

    @app.get("/health")
    def health():
        if state.db_down:
            raise HTTPException(status_code=503, detail="Base de datos no disponible.")
        return {"status": "ok", "database": "ok", "hardware": "runtime-separado"}

    @app.get("/api/v1/status", response_model=BackendStatusResponse, dependencies=protected)
    def backend_status():
        users = state.list_users()
        return {
            "api": "ok",
            "database": "ok",
            "runtime": state.runtime(),
            "users": {
                "total": len(users),
                "active": sum(u["active"] for u in users),
                "with_face": sum(u["has_face"] for u in users),
                "with_rfid": sum(u["has_rfid"] for u in users),
                "with_both": sum(u["has_face"] and u["has_rfid"] for u in users),
            },
            "access_events": state.summary(),
        }

    @app.get("/api/v1/users", response_model=List[UserResponse], dependencies=protected)
    def list_users():
        return state.list_users()

    @app.get("/api/v1/users/{external_id}", response_model=UserResponse, dependencies=protected)
    def get_user(external_id: str):
        if not valid_id(external_id):
            raise HTTPException(status_code=404, detail=INVALID_ID)
        user = state.find_user(external_id)
        if user is None:
            raise HTTPException(status_code=404, detail=USER_NOT_FOUND)
        return state.serialize_user(user)

    @app.post("/api/v1/users", response_model=UserResponse, status_code=201, dependencies=protected)
    def create_user(payload: UserCreate):
        if state.find_user(payload.external_id):
            raise HTTPException(status_code=409, detail=USER_EXISTS)
        user = _user(
            payload.external_id, payload.first_name, payload.last_name,
            payload.role, True, 0, False,
        )
        user["created_at"] = state.now().strftime("%Y-%m-%d %H:%M:%S")
        state.users.append(user)
        return state.serialize_user(user)

    @app.patch("/api/v1/users/{external_id}", response_model=UserResponse, dependencies=protected)
    def update_user(external_id: str, payload: UserUpdate):
        changes = payload.model_dump(exclude_unset=True)
        if not changes:
            raise HTTPException(status_code=422, detail="Enviar al menos un campo.")
        if not valid_id(external_id):
            raise HTTPException(status_code=422, detail=INVALID_ID)
        user = state.find_user(external_id)
        if user is None:
            raise HTTPException(status_code=404, detail=USER_NOT_FOUND)
        if "active" in changes:
            # Igual que la API real: {"active": null} termina desactivando.
            changes["active"] = bool(changes["active"])
        user.update(changes)
        return state.serialize_user(user)

    @app.delete("/api/v1/users/{external_id}/rfid", response_model=UserResponse, dependencies=protected)
    def revoke_rfid(external_id: str):
        if not valid_id(external_id):
            raise HTTPException(status_code=404, detail=INVALID_ID)
        user = state.find_user(external_id)
        if user is None:
            raise HTTPException(status_code=404, detail=USER_NOT_FOUND)
        if not user["has_rfid"]:
            raise HTTPException(status_code=404, detail=NO_RFID)
        user["has_rfid"] = False
        return state.serialize_user(user)

    @app.delete("/api/v1/users/{external_id}/face", response_model=UserResponse, dependencies=protected)
    def revoke_face(external_id: str):
        if not valid_id(external_id):
            raise HTTPException(status_code=404, detail=INVALID_ID)
        user = state.find_user(external_id)
        if user is None:
            raise HTTPException(status_code=404, detail=USER_NOT_FOUND)
        if user["biometric_templates"] == 0:
            raise HTTPException(status_code=404, detail=NO_FACE)
        user["biometric_templates"] = 0
        return state.serialize_user(user)

    @app.post(
        "/api/v1/users/{external_id}/rfid-enrollments",
        response_model=RFIDEnrollmentResponse, status_code=201, dependencies=protected,
    )
    def create_rfid_enrollment(external_id: str, payload: RFIDEnrollmentCreate):
        if not valid_id(external_id):
            raise HTTPException(status_code=422, detail=INVALID_ID)
        state.advance_enrollments()
        user = state.find_user(external_id)
        if user is None:
            raise HTTPException(status_code=404, detail=USER_NOT_FOUND)
        if not user["active"]:
            raise HTTPException(status_code=409, detail="El usuario está deshabilitado.")
        if user["has_rfid"]:
            raise HTTPException(
                status_code=409,
                detail="El usuario ya posee una tarjeta activa; revocarla primero.",
            )
        if any(request["status"] == "pending" for request in state.enrollments):
            raise HTTPException(
                status_code=409,
                detail="Ya existe otra solicitud de enrolamiento pendiente.",
            )
        now = state.now()
        request = {
            "request_id": len(state.enrollments) + 1,
            "external_id": external_id,
            "status": "pending",
            "created_at": now.isoformat(timespec="seconds"),
            "expires_at": (now + timedelta(seconds=payload.timeout_seconds)).isoformat(timespec="seconds"),
            "finished_at": None,
            "error_code": None,
        }
        state.enrollments.append(request)
        return request

    @app.get(
        "/api/v1/rfid-enrollments/{request_id}",
        response_model=RFIDEnrollmentResponse, dependencies=protected,
    )
    def get_rfid_enrollment(request_id: int):
        state.advance_enrollments()
        request = state.find_enrollment(request_id)
        if request is None:
            raise HTTPException(status_code=404, detail="Solicitud inexistente.")
        return request

    @app.delete(
        "/api/v1/rfid-enrollments/{request_id}",
        response_model=RFIDEnrollmentResponse, dependencies=protected,
    )
    def cancel_rfid_enrollment(request_id: int):
        # Como la API real, cancelar no caduca antes: sólo exige "pending".
        request = state.find_enrollment(request_id)
        if request is None or request["status"] != "pending":
            raise HTTPException(status_code=404, detail="La solicitud no está pendiente.")
        request["status"] = "cancelled"
        request["finished_at"] = state.now().isoformat(timespec="seconds")
        return request

    @app.get(
        "/api/v1/access-events",
        response_model=List[AccessEventResponse], dependencies=protected,
    )
    def list_access_events(
        limit: int = Query(50, ge=1, le=500),
        offset: int = Query(0, ge=0),
        day: Optional[date] = None,
        method: Optional[str] = Query(None, max_length=32),
        granted: Optional[bool] = None,
    ):
        return state.list_events(
            limit, offset, day.isoformat() if day else None, method, granted
        )

    @app.get(
        "/api/v1/access-events/summary",
        response_model=AccessSummaryResponse, dependencies=protected,
    )
    def access_summary(day: Optional[date] = None):
        return state.summary(day.isoformat() if day else None)

    # --- Control del mock (no existe en la API real) ------------------------

    @app.get("/mock/control")
    def control(
        offline: Optional[str] = Query(None, pattern="^(0|1|stopped|unknown)$"),
        enroll: Optional[str] = Query(None, pattern="^(completed|failed|expired)$"),
        enroll_seconds: Optional[float] = Query(None, ge=0, le=300),
        db_down: Optional[bool] = None,
        methods: Optional[str] = Query(None, pattern="^(both|face|rfid)$"),
        door_mode: Optional[str] = Query(None, pattern="^(simulate|gpio)$"),
        event: Optional[bool] = None,
    ):
        if offline is not None:
            state.offline = offline
        if enroll is not None:
            state.enroll = enroll
        if enroll_seconds is not None:
            state.enroll_seconds = enroll_seconds
        if db_down is not None:
            state.db_down = db_down
        if methods is not None:
            state.methods = methods
        if door_mode is not None:
            state.door_mode = door_mode
        if event:
            state.add_event()
        return {
            "offline": state.offline, "enroll": state.enroll,
            "enroll_seconds": state.enroll_seconds, "db_down": state.db_down,
            "methods": state.methods, "door_mode": state.door_mode,
            "events": len(state.events),
        }

    return app


def _env_from_file(name):
    """Lee una variable de frontend/.env para compartir el token con el front."""
    path = Path(__file__).resolve().parent.parent / ".env"
    if not path.is_file():
        return ""
    for line in path.read_text(encoding="utf-8").splitlines():
        key, _, value = line.strip().partition("=")
        if key.strip() == name:
            return value.strip().strip("\"'")
    return ""


def main():
    import uvicorn

    port = int(os.environ.get("MOCK_PORT", DEFAULT_PORT))
    if port == 8000:
        raise SystemExit("El mock no usa el puerto 8000: es el de la API real.")
    token = os.environ.get("SECUREGATE_API_TOKEN") or _env_from_file("SECUREGATE_API_TOKEN")
    if len(token) < 32:
        raise SystemExit(
            "Definir SECUREGATE_API_TOKEN (32 caracteres o más) en el entorno "
            "o en frontend/.env: tiene que ser el mismo que usa el front."
        )
    event_seconds = float(os.environ.get("MOCK_EVENT_SECONDS", "5"))
    app = create_mock_app(token, event_seconds=event_seconds)
    print(f"[MOCK] API falsa de secureGate en http://127.0.0.1:{port} (sólo desarrollo)")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()
