"""Usuarios: listado, alta, detalle, edición, activar/desactivar y revocaciones."""

import re

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse

from app import auth, labels
from app.api_client import PAGE_MAX, ApiConflict, ApiNotFound, ApiValidation
from app.templating import render


router = APIRouter(prefix="/usuarios")
admin_write = [Depends(auth.require_admin), Depends(auth.verify_csrf)]

SEQUENTIAL_ID_RE = re.compile(r"user_(\d+)")
CREATE_ATTEMPTS = 3
RECENT_ACCESSES = 20
RECENT_MAX_PAGES = 5

# Mismos límites que valida la API (contrato §4.2).
FIELDS = (("first_name", "nombre", 100), ("last_name", "apellido", 100), ("role", "rol", 50))
FIELD_NAMES = {api_name: form_name for api_name, form_name, _ in FIELDS}


def clean_fields(nombre, apellido, rol):
    """Devuelve (valores para la API, errores por campo del formulario).

    Un campo vacío viaja como None: en el alta se omite y en la edición borra
    el dato (la API rechaza el texto vacío).
    """
    values, errors = {}, {}
    for (api_name, form_name, limit), raw in zip(FIELDS, (nombre, apellido, rol)):
        text = " ".join(raw.split())
        if len(text) > limit:
            errors[form_name] = f"Máximo {limit} caracteres."
        values[api_name] = text or None
    return values, errors


def api_field_errors(exc):
    """Errores 422 de la API → errores por campo del formulario + generales."""
    errors = {FIELD_NAMES.get(name, name): message for name, message in exc.fields.items()}
    general = list(exc.errors)
    for name in list(errors):
        if name not in FIELD_NAMES.values():
            general.append(f"{name}: {errors.pop(name)}")
    return errors, general


def user_url(request, external_id, suffix=""):
    return f"{request.app.state.settings.base_path}/usuarios/{external_id}{suffix}"


def next_external_id(users):
    numbers = [
        int(match.group(1))
        for user in users
        if (match := SEQUENTIAL_ID_RE.fullmatch(user["external_id"]))
    ]
    return f"user_{max(numbers, default=0) + 1:03d}"


async def recent_accesses(api, external_id):
    """Últimos accesos del usuario. La API no filtra por usuario (pedido B2)."""
    found = []
    for page_number in range(RECENT_MAX_PAGES):
        page = await api.list_events(limit=PAGE_MAX, offset=page_number * PAGE_MAX)
        found.extend(event for event in page if event["external_id"] == external_id)
        if len(found) >= RECENT_ACCESSES:
            return found[:RECENT_ACCESSES], True
        if len(page) < PAGE_MAX:
            return found, True
    return found, False


# --- Listado ----------------------------------------------------------------

def matches(user, q, activo, rostro, tarjeta):
    if q:
        haystack = " ".join(
            str(user.get(name) or "") for name in ("first_name", "last_name", "external_id")
        ).lower()
        if not all(word in haystack for word in q.lower().split()):
            return False
    for value, flag in ((activo, user["active"]), (rostro, user["has_face"]), (tarjeta, user["has_rfid"])):
        if value == "si" and not flag or value == "no" and flag:
            return False
    return True


@router.get("")
async def listado(request: Request, q: str = "", activo: str = "", rostro: str = "", tarjeta: str = ""):
    tz = request.app.state.settings.tz
    users = await request.app.state.api.list_users(fresh=True)
    q = q.strip()
    shown = [labels.user_view(user, tz) for user in users if matches(user, q, activo, rostro, tarjeta)]
    return render(request, "usuarios.html", {
        "section": "usuarios", "usuarios": shown, "total": len(users),
        "filtros": {"q": q, "activo": activo, "rostro": rostro, "tarjeta": tarjeta},
    })


# --- Alta -------------------------------------------------------------------

@router.get("/nuevo", dependencies=[Depends(auth.require_admin)])
async def nuevo_form(request: Request):
    return render(request, "usuario_nuevo.html", {"section": "usuarios", "form": {}, "errors": {}})


@router.post("/nuevo", dependencies=admin_write)
async def nuevo(request: Request, nombre: str = Form(""), apellido: str = Form(""), rol: str = Form("")):
    api = request.app.state.api
    values, errors = clean_fields(nombre, apellido, rol)
    general = []
    if not errors:
        for _ in range(CREATE_ATTEMPTS):
            # El ID lo genera el BFF; si otro operador lo ganó (409), se recalcula.
            external_id = next_external_id(await api.list_users(fresh=True))
            try:
                await api.create_user(external_id, **values)
            except ApiConflict:
                continue
            except ApiValidation as exc:
                errors, general = api_field_errors(exc)
                break
            auth.flash(request, f"Usuario {external_id} creado.")
            return RedirectResponse(user_url(request, external_id, "?creado=1"), status_code=303)
        else:
            general = ["No se pudo generar un identificador libre. Probá de nuevo."]
    return render(request, "usuario_nuevo.html", {
        "section": "usuarios", "errors": errors, "general": general,
        "form": {"nombre": nombre, "apellido": apellido, "rol": rol},
    }, status_code=409 if general and not errors else 422)


# --- Detalle ----------------------------------------------------------------

async def detalle_response(request, external_id, errors=None, general=None, form=None, status_code=200):
    api = request.app.state.api
    tz = request.app.state.settings.tz
    user = await api.get_user(external_id)
    events, complete = await recent_accesses(api, external_id)
    view = labels.user_view(user, tz)
    return render(request, "usuario_detalle.html", {
        "section": "usuarios",
        "usuario": view,
        "form": form or {"nombre": view["raw"]["first_name"], "apellido": view["raw"]["last_name"],
                         "rol": view["raw"]["role"]},
        "errors": errors or {},
        "general": general or [],
        "accesos": [labels.event_view(event, {external_id: user}, tz) for event in events],
        "accesos_completos": complete,
        "accesos_buscados": RECENT_ACCESSES,
        "recien_creado": request.query_params.get("creado") == "1",
        "face_info": labels.FACE_ENROLLMENT_INFO,
    }, status_code=status_code)


@router.get("/{external_id}")
async def detalle(request: Request, external_id: str):
    return await detalle_response(request, external_id)


@router.post("/{external_id}/editar", dependencies=admin_write)
async def editar(request: Request, external_id: str,
                 nombre: str = Form(""), apellido: str = Form(""), rol: str = Form("")):
    values, errors = clean_fields(nombre, apellido, rol)
    general = []
    if not errors:
        try:
            await request.app.state.api.update_user(external_id, values)
        except ApiValidation as exc:
            errors, general = api_field_errors(exc)
        else:
            auth.flash(request, "Datos del usuario actualizados.")
            return RedirectResponse(user_url(request, external_id), status_code=303)
    return await detalle_response(
        request, external_id, errors, general,
        {"nombre": nombre, "apellido": apellido, "rol": rol}, status_code=422,
    )


@router.post("/{external_id}/estado", dependencies=admin_write)
async def cambiar_estado(request: Request, external_id: str, activo: str = Form(...)):
    if activo not in ("si", "no"):
        raise HTTPException(status_code=422, detail="Estado inválido.")
    active = activo == "si"
    await request.app.state.api.update_user(external_id, {"active": active})
    auth.flash(request, "Usuario activado." if active else
               "Usuario desactivado: conserva sus credenciales, pero ya no autoriza ingresos.")
    return RedirectResponse(user_url(request, external_id), status_code=303)


async def _revocar(request, external_id, action, done, context):
    api = request.app.state.api
    await api.get_user(external_id)  # 404 de usuario → página "No encontrado"
    try:
        await action(external_id)
    except ApiNotFound as exc:
        auth.flash(request, f"No encontrado ({context}): {exc.message}", "error")
    else:
        auth.flash(request, done)
    return RedirectResponse(user_url(request, external_id), status_code=303)


@router.post("/{external_id}/tarjeta/revocar", dependencies=admin_write)
async def revocar_tarjeta(request: Request, external_id: str):
    return await _revocar(request, external_id, request.app.state.api.revoke_rfid,
                          "Tarjeta revocada.", "tarjeta")


@router.post("/{external_id}/rostro/revocar", dependencies=admin_write)
async def revocar_rostro(request: Request, external_id: str):
    return await _revocar(request, external_id, request.app.state.api.revoke_face,
                          "Registro facial revocado.", "rostro")
