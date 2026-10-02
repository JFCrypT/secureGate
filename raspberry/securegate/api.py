"""API REST para el frontend de secureGate.

La API expone metadatos y registros, nunca UID, claves ni embeddings.
"""

from datetime import date
from pathlib import Path
from secrets import compare_digest
from typing import List, Optional
import sqlite3

from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field

from securegate.access_log import AccessLogRepository
from securegate.rfid.enrollment import (
    EnrollmentBusy,
    EnrollmentConflict,
    EnrollmentNotFound,
    RFIDEnrollmentRepository,
)
from securegate.rfid.registry import DEFAULT_DB
from securegate.runtime_status import RuntimeStatusRepository
from securegate.users import (
    CredentialNotFound,
    UserAlreadyExists,
    UserNotFound,
    UserRepository,
)


class UserCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    external_id: str = Field(
        min_length=6,
        max_length=64,
        pattern=r"^user_[A-Za-z0-9_-]+$",
        examples=["user_005"],
    )
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


def create_app(database=DEFAULT_DB, api_token=None, cors_origins=()):
    database = Path(database)
    if not isinstance(api_token, str) or len(api_token) < 32:
        raise ValueError("SECUREGATE_API_TOKEN debe tener al menos 32 caracteres.")

    users = UserRepository(database)
    events = AccessLogRepository(database)
    enrollments = RFIDEnrollmentRepository(database)
    runtime_status = RuntimeStatusRepository(database)
    app = FastAPI(
        title="secureGate Backend API",
        version="1.0.0",
        description=(
            "API del prototipo. No expone UID de tarjetas, claves ni datos "
            "biométricos. Los GPIO pertenecen al runtime de acceso."
        ),
    )

    origins = [origin.strip() for origin in cors_origins if origin.strip()]
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=False,
            allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
            allow_headers=["Authorization", "Content-Type"],
        )

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

    @app.get("/health", tags=["sistema"])
    def health():
        try:
            users.list()
        except (OSError, ValueError, sqlite3.Error):
            raise HTTPException(status_code=503, detail="Base de datos no disponible.")
        return {"status": "ok", "database": "ok", "hardware": "runtime-separado"}

    @app.get(
        "/api/v1/status",
        response_model=BackendStatusResponse,
        dependencies=[Depends(require_token)],
        tags=["sistema"],
    )
    def backend_status():
        return {
            "api": "ok",
            "database": "ok",
            "runtime": runtime_status.get(),
            "users": users.summary(),
            "access_events": events.summary(),
        }

    @app.get(
        "/api/v1/users",
        response_model=List[UserResponse],
        dependencies=[Depends(require_token)],
        tags=["usuarios"],
    )
    def list_users():
        return users.list()

    @app.get(
        "/api/v1/users/{external_id}",
        response_model=UserResponse,
        dependencies=[Depends(require_token)],
        tags=["usuarios"],
    )
    def get_user(external_id: str):
        try:
            return users.get(external_id)
        except (ValueError, UserNotFound) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post(
        "/api/v1/users",
        response_model=UserResponse,
        status_code=status.HTTP_201_CREATED,
        dependencies=[Depends(require_token)],
        tags=["usuarios"],
    )
    def create_user(payload: UserCreate):
        try:
            return users.create(
                payload.external_id,
                payload.first_name,
                payload.last_name,
                payload.role,
            )
        except UserAlreadyExists as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.patch(
        "/api/v1/users/{external_id}",
        response_model=UserResponse,
        dependencies=[Depends(require_token)],
        tags=["usuarios"],
    )
    def update_user(external_id: str, payload: UserUpdate):
        try:
            changes = payload.model_dump(exclude_unset=True)
            if not changes:
                raise HTTPException(status_code=422, detail="Enviar al menos un campo.")
            return users.update(external_id, changes)
        except UserNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.delete(
        "/api/v1/users/{external_id}/rfid",
        response_model=UserResponse,
        dependencies=[Depends(require_token)],
        tags=["usuarios"],
    )
    def revoke_rfid(external_id: str):
        try:
            return users.revoke_rfid(external_id)
        except (UserNotFound, CredentialNotFound, ValueError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.delete(
        "/api/v1/users/{external_id}/face",
        response_model=UserResponse,
        dependencies=[Depends(require_token)],
        tags=["usuarios"],
    )
    def revoke_face(external_id: str):
        try:
            return users.revoke_face(external_id)
        except (UserNotFound, CredentialNotFound, ValueError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post(
        "/api/v1/users/{external_id}/rfid-enrollments",
        response_model=RFIDEnrollmentResponse,
        status_code=status.HTTP_201_CREATED,
        dependencies=[Depends(require_token)],
        tags=["rfid"],
    )
    def create_rfid_enrollment(
        external_id: str,
        payload: RFIDEnrollmentCreate,
    ):
        try:
            return enrollments.create(external_id, payload.timeout_seconds)
        except UserNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (EnrollmentBusy, EnrollmentConflict) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get(
        "/api/v1/rfid-enrollments/{request_id}",
        response_model=RFIDEnrollmentResponse,
        dependencies=[Depends(require_token)],
        tags=["rfid"],
    )
    def get_rfid_enrollment(request_id: int):
        try:
            return enrollments.get(request_id)
        except EnrollmentNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.delete(
        "/api/v1/rfid-enrollments/{request_id}",
        response_model=RFIDEnrollmentResponse,
        dependencies=[Depends(require_token)],
        tags=["rfid"],
    )
    def cancel_rfid_enrollment(request_id: int):
        try:
            return enrollments.cancel(request_id)
        except EnrollmentNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get(
        "/api/v1/access-events",
        response_model=List[AccessEventResponse],
        dependencies=[Depends(require_token)],
        tags=["registros"],
    )
    def list_access_events(
        limit: int = Query(50, ge=1, le=500),
        offset: int = Query(0, ge=0),
        day: Optional[date] = None,
        method: Optional[str] = Query(None, max_length=32),
        granted: Optional[bool] = None,
    ):
        return events.list(
            limit=limit,
            offset=offset,
            date_prefix=day.isoformat() if day else None,
            method=method,
            granted=granted,
        )

    @app.get(
        "/api/v1/access-events/summary",
        response_model=AccessSummaryResponse,
        dependencies=[Depends(require_token)],
        tags=["registros"],
    )
    def access_summary(day: Optional[date] = None):
        return events.summary(day.isoformat() if day else None)

    return app
