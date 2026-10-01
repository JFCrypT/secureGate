#!/usr/bin/env python3
"""Local card enrollment/revocation; never writes card sectors."""

from pathlib import Path
from contextlib import closing
import argparse
import os
import secrets
import sqlite3
import sys
import time

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR / "raspberry"))

from securegate.rfid.registry import CardRegistry, DEFAULT_DB, DEFAULT_KEY
from securegate.rfid.reader import RC522Reader


def scan(reader, timeout=30):
    deadline = time.monotonic() + timeout
    print("[INFO] Acercar UNA tarjeta al RC522 (máximo 30 segundos).")
    while time.monotonic() < deadline:
        uid = reader.poll()
        if uid:
            return uid
        time.sleep(0.1)
    raise RuntimeError("No se leyó ninguna tarjeta. Revisar SPI y compatibilidad.")


def main():
    parser = argparse.ArgumentParser(description="Administrar tarjetas RFID de secureGate.")
    parser.add_argument("--database", type=Path, default=DEFAULT_DB)
    parser.add_argument("--key", type=Path, default=DEFAULT_KEY)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("init", help="Crear k_rfid si no existe y añadir tabla RFID.")
    subparsers.add_parser("scan", help="Ver UID para diagnóstico local.")
    enroll = subparsers.add_parser("enroll", help="Registrar tarjeta para un usuario.")
    enroll.add_argument("user")
    enroll.add_argument("--uid", help="UID hexadecimal; si falta se lee del RC522.")
    revoke = subparsers.add_parser("revoke", help="Deshabilitar tarjeta sin borrarla.")
    revoke.add_argument("--uid", help="Si falta se lee del RC522.")
    args = parser.parse_args()
    try:
        if args.command == "init":
            if not args.database.is_file():
                raise ValueError("Ejecutar raspberry/init_db.py antes de inicializar RFID.")
            if not args.key.exists():
                with closing(sqlite3.connect(args.database)) as connection:
                    exists = connection.execute(
                        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='rfid_credentials'"
                    ).fetchone()
                    if exists and connection.execute(
                        "SELECT COUNT(*) FROM rfid_credentials"
                    ).fetchone()[0]:
                        raise ValueError(
                            "Hay tarjetas registradas y falta k_rfid. Restaurar la clave "
                            "original; no se crea otra que invalide esas tarjetas."
                        )
            args.key.parent.mkdir(parents=True, exist_ok=True)
            try:
                descriptor = os.open(args.key, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            except FileExistsError:
                print("[INFO] Se conserva la k_rfid existente.")
            else:
                with os.fdopen(descriptor, "wb") as key_file:
                    key_file.write(secrets.token_bytes(32))
            CardRegistry(args.database, args.key)
            print("[OK] Tabla RFID lista. La base biométrica permanece intacta.")
            return 0
        if args.command == "scan":
            with RC522Reader() as reader:
                uid = scan(reader)
            print(f"[DIAGNÓSTICO LOCAL] UID: {uid}. No publicarlo en Git.")
            return 0
        registry = CardRegistry(args.database, args.key)
        uid = args.uid
        if uid is None:
            with RC522Reader() as reader:
                uid = scan(reader)
        if args.command == "enroll":
            registry.enroll(args.user, uid)
            print(f"[OK] Tarjeta habilitada para {args.user}.")
        else:
            if not registry.revoke(uid):
                raise ValueError("La tarjeta no está registrada.")
            print("[OK] Tarjeta deshabilitada.")
        return 0
    except (ValueError, OSError, RuntimeError, sqlite3.Error) as exc:
        print(f"[ERROR] {exc}")
        return 1
    except KeyboardInterrupt:
        print("\n[INFO] Operación cancelada.")
        return 130


if __name__ == "__main__":
    sys.exit(main())
