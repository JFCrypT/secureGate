#!/usr/bin/env python3
"""Informe simple de accesos para operar sin frontend."""

from pathlib import Path
import argparse
import csv
import sqlite3
import sys


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT_DIR / "data" / "db" / "securegate.db"


def load_rows(database, limit, date_prefix=None):
    where = ""
    parameters = []
    if date_prefix:
        where = "WHERE occurred_at LIKE ?"
        parameters.append(f"{date_prefix}%")
    parameters.append(limit)
    with sqlite3.connect(database) as connection:
        return connection.execute(
            f"""SELECT event_id, occurred_at, method,
                       COALESCE(external_id, '-'),
                       CASE granted WHEN 1 THEN 'SI' ELSE 'NO' END,
                       CASE restricted_time WHEN 1 THEN 'SI' ELSE 'NO' END,
                       door_status, alert_reasons
                FROM access_events
                {where}
                ORDER BY event_id DESC
                LIMIT ?""",
            parameters,
        ).fetchall()


def print_summary(rows):
    total = len(rows)
    granted = sum(row[4] == "SI" for row in rows)
    restricted = sum(row[5] == "SI" for row in rows)
    print(f"[RESUMEN] Eventos mostrados: {total}")
    print(f"[RESUMEN] Autorizados: {granted}; rechazados: {total - granted}")
    print(f"[RESUMEN] Fuera de horario: {restricted}")
    print()
    print("ID | FECHA/HORA | MÉTODO | USUARIO | AUTORIZADO | FUERA HORARIO | PUERTA | ALERTA")
    for row in rows:
        print(" | ".join(str(value) if value != "" else "-" for value in row))


def export_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow([
            "event_id", "occurred_at", "method", "external_id", "granted",
            "restricted_time", "door_status", "alert_reasons",
        ])
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description="Consultar registros de secureGate.")
    parser.add_argument("--database", type=Path, default=DEFAULT_DB)
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--date", help="Filtrar por fecha local AAAA-MM-DD.")
    parser.add_argument("--csv", type=Path, help="Exportar los registros mostrados.")
    args = parser.parse_args()
    if args.limit < 1 or args.limit > 10000:
        parser.error("--limit debe estar entre 1 y 10000.")
    if not args.database.is_file():
        print("[ERROR] Base inexistente. Ejecutar raspberry/init_db.py primero.")
        return 1
    try:
        rows = load_rows(args.database, args.limit, args.date)
    except sqlite3.Error as exc:
        print(f"[ERROR] No se pudieron consultar los registros: {exc}")
        return 1
    print_summary(rows)
    if args.csv:
        export_csv(args.csv, rows)
        print(f"\n[OK] CSV generado: {args.csv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
