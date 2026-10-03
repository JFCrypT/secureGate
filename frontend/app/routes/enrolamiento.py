"""Enrolamiento RFID: sólo admin. El UID nunca pasa por el front."""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse

from app import auth, labels
from app.api_client import ApiConflict, ApiError, ApiNotFound, ApiValidation
from app.templating import render


router = APIRouter(dependencies=[Depends(auth.require_admin)])

TIMEOUT_SECONDS = 60


def rfid_url(request, external_id, request_id=None):
    url = f"{request.app.state.settings.base_path}/usuarios/{external_id}/rfid"
    return f"{url}/{request_id}" if request_id is not None else url


async def inicio_response(request, external_id, conflict=None, status_code=200):
    api = request.app.state.api
    tz = request.app.state.settings.tz
    user = labels.user_view(await api.get_user(external_id), tz)
    blocked = None
    if not user["active"]:
        blocked = labels.ACTIVATE_FIRST
    elif user["has_rfid"]:
        blocked = labels.REVOKE_FIRST
    # El aviso del lector es sólo informativo: si no se puede saber, se avisa igual.
    try:
        reader_active = labels.runtime_view((await api.status())["runtime"], tz)["rfid_reader_active"]
    except ApiError:
        reader_active = False
    return render(request, "enrolamiento_inicio.html", {
        "section": "usuarios", "usuario": user, "blocked": blocked, "conflict": conflict,
        "reader_warning": None if reader_active else labels.READER_INACTIVE,
        "timeout": TIMEOUT_SECONDS,
    }, status_code=status_code)


@router.get("/usuarios/{external_id}/rfid")
async def inicio(request: Request, external_id: str):
    # Siempre empieza de cero: una solicitud pendiente anterior no se retoma.
    return await inicio_response(request, external_id)


@router.post("/usuarios/{external_id}/rfid", dependencies=[Depends(auth.verify_csrf)])
async def iniciar(request: Request, external_id: str):
    try:
        enrollment = await request.app.state.api.create_enrollment(external_id, TIMEOUT_SECONDS)
    except (ApiConflict, ApiValidation) as exc:
        return await inicio_response(request, external_id, conflict=exc.message, status_code=409)
    return RedirectResponse(rfid_url(request, external_id, enrollment["request_id"]), status_code=303)


async def espera_context(request, request_id, external_id=None):
    api = request.app.state.api
    enrollment = await api.get_enrollment(request_id)
    if external_id is not None and enrollment["external_id"] != external_id:
        raise ApiNotFound("Solicitud inexistente.")
    if enrollment["status"] == labels.ENROLLMENT_COMPLETED:
        api.invalidate_users()  # el usuario pasa a has_rfid
    users = await api.users_by_id()
    name = labels.full_name(users.get(enrollment["external_id"])) or enrollment["external_id"]
    return {"enrolamiento": labels.enrollment_view(enrollment, name), "poll_error": None}


@router.get("/usuarios/{external_id}/rfid/{request_id}")
async def espera(request: Request, external_id: str, request_id: int):
    context = await espera_context(request, request_id, external_id)
    context["section"] = "usuarios"
    return render(request, "enrolamiento_espera.html", context)


@router.get("/partials/enrolamiento/{request_id}")
async def espera_parcial(request: Request, request_id: int):
    try:
        context = await espera_context(request, request_id)
    except ApiNotFound:
        raise
    except ApiError as exc:
        # Un corte momentáneo no interrumpe la espera: se sigue consultando.
        context = {"enrolamiento": {"request_id": request_id, "pending": True, "title": labels.ENROLLMENT_WAITING,
                                    "remaining": None}, "poll_error": exc.message}
    return render(request, "partials/enrolamiento.html", context)


@router.post("/usuarios/{external_id}/rfid/{request_id}/cancelar", dependencies=[Depends(auth.verify_csrf)])
async def cancelar(request: Request, external_id: str, request_id: int):
    try:
        await request.app.state.api.cancel_enrollment(request_id)
    except ApiNotFound:
        pass  # ya no estaba pendiente: la pantalla muestra en qué quedó
    return RedirectResponse(rfid_url(request, external_id, request_id), status_code=303)
