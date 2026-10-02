#!/usr/bin/env python3
"""Arranque de la API para el frontend."""

from pathlib import Path
import argparse
import os
import sqlite3
import sys


sys.path.insert(0, str(Path(__file__).resolve().parent))

from securegate.rfid.registry import DEFAULT_DB


def main():
    parser = argparse.ArgumentParser(description="API REST de secureGate.")
    parser.add_argument("--database", type=Path, default=DEFAULT_DB)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    token = os.environ.get("SECUREGATE_API_TOKEN", "")
    if len(token) < 32:
        print(
            "[ERROR] Definir SECUREGATE_API_TOKEN con al menos 32 caracteres. "
            "No se inicia una API administrativa sin autenticación."
        )
        return 1
    if not args.database.is_file():
        print("[ERROR] Base inexistente. Ejecutar raspberry/init_db.py primero.")
        return 1
    if not 1 <= args.port <= 65535:
        parser.error("--port debe estar entre 1 y 65535.")

    cors_origins = [
        origin
        for origin in os.environ.get("SECUREGATE_CORS_ORIGINS", "").split(",")
        if origin.strip()
    ]
    try:
        import uvicorn
        from securegate.api import create_app
        app = create_app(args.database, token, cors_origins)
    except ImportError:
        print("[ERROR] Instalar requirements-api.txt dentro del entorno virtual.")
        return 1
    except (OSError, ValueError, sqlite3.Error) as exc:
        print(f"[ERROR] No se pudo iniciar la API: {exc}")
        return 1

    print(f"[INFO] API: http://{args.host}:{args.port}")
    print(f"[INFO] Documentación: http://{args.host}:{args.port}/docs")
    if args.host == "0.0.0.0":
        print("[ADVERTENCIA] Limitar el acceso a la red local y utilizar firewall.")
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    return 0


if __name__ == "__main__":
    sys.exit(main())
