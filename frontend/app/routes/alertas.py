"""Estado y alertas, calculadas a partir de los eventos del período."""

from datetime import timedelta
from urllib.parse import urlencode

from fastapi import APIRouter, Request

from app import labels, timefmt
from app.api_client import ApiError
from app.routes.partials import estado_context
from app.templating import render


router = APIRouter()

PERIODS = {"24h": (timedelta(hours=24), "Últimas 24 h"), "7d": (timedelta(days=7), "Últimos 7 días")}
DEFAULT_PERIOD = "24h"
MAX_EVENTS = 20000
MAX_LISTED = 200

# (clave, etiqueta, regla sobre el evento crudo)
KINDS = (
    ("door_error", labels.DOOR_ERROR_ALERT,
     lambda event: event["door_status"] == labels.DOOR_ERROR),
    ("consecutive", labels.ALERT_LABELS[labels.CONSECUTIVE_FAILURES],
     lambda event: labels.CONSECUTIVE_FAILURES in labels.event_alert_codes(event)),
    ("restricted", "Intentos fuera de horario",
     lambda event: bool(event["restricted_time"])),
)


async def collect_alerts(request, period):
    """Devuelve conteos por tipo y la lista de alertas para el período pedido."""
    api = request.app.state.api
    settings = request.app.state.settings
    tz = settings.tz
    now = timefmt.now_utc()
    since = now - PERIODS[period][0]
    first, last = since.astimezone(tz).date(), now.astimezone(tz).date()
    days = [last - timedelta(days=n) for n in range((last - first).days + 1)]
    events, truncated = await api.events_for_days(days, MAX_EVENTS)
    users = await api.users_by_id()

    counts = {key: 0 for key, _, _ in KINDS}
    items = []
    for event in sorted(events, key=lambda item: item["event_id"], reverse=True):
        moment = timefmt.parse(event["occurred_at"])
        if moment is None or moment < since:
            continue
        view = None
        for key, label, rule in KINDS:
            if not rule(event):
                continue
            counts[key] += 1
            view = view or labels.event_view(event, users, tz)
            query = urlencode({"dia": view["day"], "evento": view["event_id"]})
            items.append({"kind": key, "label": label, "event": view,
                          "url": f"{settings.base_path}/historial?{query}"})
    return {
        "counts": [{"key": key, "label": label, "count": counts[key]} for key, label, _ in KINDS],
        "total": len(items),
        "lista": items[:MAX_LISTED],
        "listed": min(len(items), MAX_LISTED),
        "truncated": truncated,
    }


@router.get("/alertas")
async def alertas(request: Request, periodo: str = DEFAULT_PERIOD):
    period = periodo if periodo in PERIODS else DEFAULT_PERIOD
    context = {
        "section": "alertas", "periodo": period,
        "periodos": [(key, label) for key, (_, label) in PERIODS.items()],
        "periodo_label": PERIODS[period][1],
        "alertas": None, "alertas_error": None,
    }
    context.update(await estado_context(request))
    try:
        context["alertas"] = await collect_alerts(request, period)
    except ApiError as exc:
        context["alertas_error"] = exc.message
    return render(request, "alertas.html", context)


@router.get("/partials/alertas-resumen")
async def alertas_resumen(request: Request):
    context = {"alertas": None, "alertas_error": None, "periodo_label": PERIODS[DEFAULT_PERIOD][1]}
    try:
        context["alertas"] = await collect_alerts(request, DEFAULT_PERIOD)
    except ApiError as exc:
        context["alertas_error"] = exc.message
    return render(request, "partials/alertas_resumen.html", context)
