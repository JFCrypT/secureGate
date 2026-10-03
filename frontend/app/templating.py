"""Plantillas Jinja2 y helper de render compartido por todas las rutas."""

from pathlib import Path

from fastapi.templating import Jinja2Templates


APP_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(APP_DIR / "templates"))


def render(request, name, context=None, status_code=200, headers=None):
    settings = request.app.state.settings
    data = {
        "base": settings.base_path,
        "poll_realtime_ms": settings.poll_realtime_ms,
        "poll_status_ms": settings.poll_status_ms,
        "operator": getattr(request.state, "operator", None),
        "csrf_token": getattr(request.state, "csrf_token", ""),
        "flashes": [],
    }
    # Los avisos se consumen al mostrar una página, no en los parciales de polling.
    if not name.startswith("partials/") and "session" in request.scope:
        data["flashes"] = request.session.pop("flash", [])
    data.update(context or {})
    return templates.TemplateResponse(
        request, name, data, status_code=status_code, headers=headers
    )
