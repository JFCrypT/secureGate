"""Reportes por rango de fechas y exportación CSV."""

from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response

from app import labels, reports, timefmt
from app.templating import render


router = APIRouter(prefix="/reportes")

RESULTS = {"autorizado": True, "rechazado": False}


def read_filters(request, desde, hasta, metodo, resultado):
    today = timefmt.today(request.app.state.settings.tz)
    start, end, error = reports.parse_range(desde.strip(), hasta.strip(), today)
    method = metodo if metodo in labels.ACCESS_METHODS else None
    granted = RESULTS.get(resultado)
    return start, end, error, method, granted


async def fetch(request, start, end, method, granted):
    """La API sólo filtra por día: un pedido por fecha, paginando de a 500 (pedido B1)."""
    api = request.app.state.api
    days = reports.days_between(start, end)
    events, truncated = await api.events_for_days(days, reports.MAX_EVENTS, method=method, granted=granted)
    return days, events, truncated, await api.users_by_id()


@router.get("")
async def reportes(request: Request, desde: str = "", hasta: str = "", metodo: str = "", resultado: str = ""):
    start, end, error, method, granted = read_filters(request, desde, hasta, metodo, resultado)
    filters = {
        "desde": start.isoformat() if start else desde, "hasta": end.isoformat() if end else hasta,
        "metodo": method or "", "resultado": resultado if granted is not None else "",
    }
    context = {
        "section": "reportes", "filtros": filters, "error": error, "reporte": None,
        "metodos": labels.ACCESS_METHODS, "max_dias": reports.MAX_DAYS, "tope": reports.MAX_EVENTS,
    }
    if error:
        return render(request, "reportes.html", context, status_code=422)
    days, events, truncated, users = await fetch(request, start, end, method, granted)
    report = reports.aggregate(events, users, days)
    query = urlencode({name: value for name, value in filters.items() if value})
    context.update({
        "reporte": report, "chart": reports.chart(report["by_day"]), "truncado": truncated,
        "csv_url": f"{request.app.state.settings.base_path}/reportes/export.csv?{query}",
    })
    return render(request, "reportes.html", context)


@router.get("/export.csv")
async def exportar(request: Request, desde: str = "", hasta: str = "", metodo: str = "", resultado: str = ""):
    start, end, error, method, granted = read_filters(request, desde, hasta, metodo, resultado)
    if error:
        raise HTTPException(status_code=422, detail=error)
    _, events, truncated, users = await fetch(request, start, end, method, granted)
    headers = {"Content-Disposition": f'attachment; filename="{reports.csv_filename(start, end)}"'}
    if truncated:
        headers["X-Reporte-Truncado"] = str(reports.MAX_EVENTS)
    return Response(
        reports.build_csv(events, users, request.app.state.settings.tz),
        media_type="text/csv; charset=utf-8", headers=headers,
    )
