"""Historial de accesos con filtros y paginado."""

from datetime import date
from urllib.parse import urlencode

from fastapi import APIRouter, Request

from app import labels
from app.api_client import PAGE_MAX
from app.templating import render


router = APIRouter(prefix="/historial")

PAGE_SIZE = 50
EVENT_SEARCH_PAGES = 5
UNKNOWN = "desconocido"
RESULTS = {"autorizado": True, "rechazado": False}


def parse_day(value):
    try:
        return date.fromisoformat(value).isoformat() if value else None
    except ValueError:
        return None


def bff_filter(event, usuario, fuera_horario, con_alertas, error_puerta):
    """Filtros que la API no ofrece; se aplican sobre la página que trajo."""
    if usuario == UNKNOWN and event["external_id"] is not None:
        return False
    if usuario and usuario != UNKNOWN and event["external_id"] != usuario:
        return False
    if fuera_horario and not event["restricted_time"]:
        return False
    if con_alertas and not event["alert_reasons"]:
        return False
    if error_puerta and event["door_status"] != labels.DOOR_ERROR:
        return False
    return True


async def find_event(api, event_id, day):
    for page_number in range(EVENT_SEARCH_PAGES):
        page = await api.list_events(limit=PAGE_MAX, offset=page_number * PAGE_MAX, day=day)
        for event in page:
            if event["event_id"] == event_id:
                return event
        if len(page) < PAGE_MAX or (page and page[-1]["event_id"] < event_id and not day):
            break
    return None


@router.get("")
async def historial(
    request: Request, dia: str = "", metodo: str = "", resultado: str = "", usuario: str = "",
    fuera_horario: str = "", con_alertas: str = "", error_puerta: str = "",
    offset: int = 0, evento: int | None = None,
):
    api = request.app.state.api
    tz = request.app.state.settings.tz
    base = f"{request.app.state.settings.base_path}/historial"
    day = parse_day(dia)
    method = metodo if metodo in labels.ACCESS_METHODS else None
    granted = RESULTS.get(resultado)
    offset = max(0, offset)
    users = await api.users_by_id()

    filters = {
        "dia": day or "", "metodo": method or "", "resultado": resultado if granted is not None else "",
        "usuario": usuario if usuario == UNKNOWN or usuario in users else "",
        "fuera_horario": "1" if fuera_horario else "", "con_alertas": "1" if con_alertas else "",
        "error_puerta": "1" if error_puerta else "",
    }
    context = {
        "section": "historial", "filtros": filters, "dia_invalido": bool(dia) and day is None,
        "metodos": labels.ACCESS_METHODS, "unknown": UNKNOWN, "unknown_label": labels.UNKNOWN_USER,
        "usuarios": [(external_id, labels.user_label(external_id, users)) for external_id in sorted(users)],
        "todo_url": f"{base}?{urlencode({'dia': day})}" if day else base,
    }

    if evento is not None:
        # Enlace desde una alerta: se muestra ese evento puntual.
        found = await find_event(api, evento, day)
        context.update({
            "evento_buscado": evento,
            "eventos": [labels.event_view(found, users, tz)] if found else [],
        })
        return render(request, "historial.html", context, status_code=200 if found else 404)

    page = await api.list_events(limit=PAGE_SIZE, offset=offset, day=day, method=method, granted=granted)
    shown = [
        labels.event_view(event, users, tz) for event in page
        if bff_filter(event, filters["usuario"], filters["fuera_horario"],
                      filters["con_alertas"], filters["error_puerta"])
    ]

    def link(new_offset):
        query = {name: value for name, value in filters.items() if value}
        if new_offset:
            query["offset"] = new_offset
        return f"{base}?{urlencode(query)}" if query else base

    context.update({
        "eventos": shown,
        "traidos": len(page),
        "desde": offset + 1,
        "hasta": offset + len(page),
        "filtro_bff": any(filters[name] for name in ("usuario", "fuera_horario", "con_alertas", "error_puerta")),
        # La API no devuelve el total: hay "Siguiente" mientras la página venga llena.
        "siguiente": link(offset + PAGE_SIZE) if len(page) == PAGE_SIZE else None,
        "anterior": link(max(0, offset - PAGE_SIZE)) if offset > 0 else None,
    })
    return render(request, "historial.html", context)
