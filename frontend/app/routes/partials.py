"""Fragmentos HTML para HTMX (polling) y los contextos que comparten con las páginas."""

from fastapi import APIRouter, Request

from app import labels, timefmt
from app.api_client import ApiError
from app.templating import render


router = APIRouter(prefix="/partials")

RECENT_EVENTS = 10


async def estado_context(request):
    """Estado del sistema. Si la API falla, devuelve el último dato conocido."""
    app = request.app
    tz = app.state.settings.tz
    error = None
    try:
        status = await app.state.api.status()
        app.state.last_status = (status, timefmt.now_utc())
    except ApiError as exc:
        error = exc.message
    status, fetched_at = getattr(app.state, "last_status", (None, None))
    context = {"api_error": error, "stale": bool(error and status), "estado": None,
               "stale_label": labels.API_STALE, "simulation_banner": labels.SIMULATION_BANNER}
    if status:
        context["estado"] = {
            "runtime": labels.runtime_view(status["runtime"], tz),
            "users": status["users"],
            "events": status["access_events"],
            "fetched_at": timefmt.format_local(fetched_at, tz),
        }
    return context


async def tiempo_real_context(request):
    """Último acceso y últimos 10 eventos, con el mismo fallback que el estado."""
    app = request.app
    tz = app.state.settings.tz
    error = None
    try:
        events = await app.state.api.list_events(limit=RECENT_EVENTS)
        users = await app.state.api.users_by_id()
        views = [labels.event_view(event, users, tz) for event in events]
        app.state.last_events = (views, timefmt.now_utc())
    except ApiError as exc:
        error = exc.message
    views, fetched_at = getattr(app.state, "last_events", (None, None))
    return {
        "rt_error": error,
        "rt_stale": bool(error and views is not None),
        "eventos": views,
        "ultimo": views[0] if views else None,
        "rt_fetched_at": timefmt.format_local(fetched_at, tz) if fetched_at else None,
        "stale_label": labels.API_STALE,
    }


@router.get("/estado")
async def estado(request: Request):
    return render(request, "partials/estado.html", await estado_context(request))


@router.get("/tiempo-real")
async def tiempo_real(request: Request):
    return render(request, "partials/tiempo_real.html", await tiempo_real_context(request))
