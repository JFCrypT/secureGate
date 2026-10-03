"""Reportes: rango de fechas, agregaciones y exportación CSV."""

from datetime import date, timedelta
import csv
import io

from app import labels, timefmt


MAX_DAYS = 31
DEFAULT_DAYS = 7
MAX_EVENTS = 20000

CSV_COLUMNS = (
    "fecha_hora", "usuario_id", "nombre", "apellido", "rol", "metodo",
    "resultado", "fuera_de_horario", "estado_puerta", "alertas",
)
CSV_ALERT_SEPARATOR = " | "
FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")

CHART_WIDTH = 640
CHART_HEIGHT = 166
CHART_LABELS = 26  # alto reservado para las fechas


def parse_range(desde, hasta, today):
    """Devuelve (inicio, fin, error). Sin parámetros: los últimos 7 días."""
    try:
        end = date.fromisoformat(hasta) if hasta else today
        start = date.fromisoformat(desde) if desde else end - timedelta(days=DEFAULT_DAYS - 1)
    except ValueError:
        return None, None, "Las fechas no son válidas."
    if start > end:
        return start, end, "La fecha «desde» no puede ser posterior a «hasta»."
    if (end - start).days + 1 > MAX_DAYS:
        return start, end, f"El rango no puede superar los {MAX_DAYS} días."
    return start, end, None


def days_between(start, end):
    return [start + timedelta(days=n) for n in range((end - start).days + 1)]


def _percent(part, total):
    return round(part * 100 / total, 1) if total else 0.0


def _bucket(label):
    return {"label": label, "granted": 0, "denied": 0, "total": 0}


def _count(bucket, event):
    bucket["granted" if event["granted"] else "denied"] += 1
    bucket["total"] += 1


def aggregate(events, users, days):
    totals = _bucket("Total")
    by_user, by_method = {}, {}
    by_day = {day.isoformat(): _bucket(day.strftime("%d/%m")) for day in days}
    for event in events:
        _count(totals, event)
        user = event["external_id"]
        _count(by_user.setdefault(user, _bucket(labels.user_label(user, users))), event)
        method = event["method"]
        _count(by_method.setdefault(method, _bucket(labels.method_label(method))), event)
        day = timefmt.api_day(event["occurred_at"])
        if day in by_day:
            _count(by_day[day], event)
    totals["granted_pct"] = _percent(totals["granted"], totals["total"])
    totals["denied_pct"] = _percent(totals["denied"], totals["total"])
    order = lambda bucket: (-bucket["total"], bucket["label"])
    return {
        "totals": totals,
        "by_user": sorted(by_user.values(), key=order),
        "by_method": sorted(by_method.values(), key=order),
        "by_day": [dict(bucket, day=day) for day, bucket in by_day.items()],
    }


def chart(by_day):
    """Geometría de un gráfico de barras apiladas (SVG, sin librerías)."""
    if not by_day:
        return None
    peak = max(bucket["total"] for bucket in by_day) or 1
    slot = CHART_WIDTH / len(by_day)
    width = round(slot * 0.7, 1)
    plot = CHART_HEIGHT - CHART_LABELS
    label_every = max(1, -(-len(by_day) // 10))
    bars = []
    for index, bucket in enumerate(by_day):
        granted = round(bucket["granted"] * plot / peak, 1)
        denied = round(bucket["denied"] * plot / peak, 1)
        x = round(index * slot + slot * 0.15, 1)
        bars.append({
            "x": x, "width": width,
            "granted_y": round(plot - granted, 1), "granted_h": granted,
            "denied_y": round(plot - granted - denied, 1), "denied_h": denied,
            "label": bucket["label"] if index % label_every == 0 else "",
            "label_x": round(x + width / 2, 1),
            "title": f"{bucket['label']}: {bucket['granted']} autorizados, {bucket['denied']} rechazados",
        })
    return {"width": CHART_WIDTH, "height": CHART_HEIGHT, "label_y": CHART_HEIGHT - 6,
            "peak": peak, "bars": bars}


def _cell(value):
    """Texto para una celda. Neutraliza fórmulas: los nombres los carga un operador."""
    text = "" if value is None else str(value)
    return "'" + text if text.startswith(FORMULA_PREFIXES) else text


def build_csv(events, users, tz):
    """CSV en UTF-8 con BOM y separador `;`, apto para Excel. Sin UID ni biometría."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";", lineterminator="\r\n")
    writer.writerow(CSV_COLUMNS)
    for event in sorted(events, key=lambda item: item["event_id"]):
        user = users.get(event["external_id"]) or {}
        writer.writerow([_cell(value) for value in (
            timefmt.format_local(event["occurred_at"], tz),
            event["external_id"],
            user.get("first_name"),
            user.get("last_name"),
            user.get("role"),
            labels.method_label(event["method"]),
            labels.GRANTED if event["granted"] else labels.DENIED,
            "SI" if event["restricted_time"] else "NO",
            labels.door_label(event["door_status"]),
            CSV_ALERT_SEPARATOR.join(alert["label"] for alert in labels.event_alerts(event)),
        )])
    return ("﻿" + buffer.getvalue()).encode("utf-8")


def csv_filename(start, end):
    return f"accesos_{start.isoformat()}_{end.isoformat()}.csv"
