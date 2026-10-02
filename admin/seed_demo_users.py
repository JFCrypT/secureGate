#!/usr/bin/env python3
"""Crea los 20 usuarios del prototipo sin inventar credenciales físicas."""

from pathlib import Path
import argparse
import sys


ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR / "raspberry"))

from securegate.rfid.registry import DEFAULT_DB
from securegate.users import UserAlreadyExists, UserRepository


def demo_users():
    """Devuelve usuarios y el tipo de credencial que se debe enrolar."""
    users = []
    for number in range(1, 11):
        users.append(
            {
                "external_id": f"user_rfid_{number:02d}",
                "first_name": "Demo",
                "last_name": f"RFID {number:02d}",
                "role": "prototipo",
                "credential_plan": "RFID",
            }
        )
    for number in range(1, 11):
        users.append(
            {
                "external_id": f"user_both_{number:02d}",
                "first_name": "Demo",
                "last_name": f"Ambos {number:02d}",
                "role": "prototipo",
                "credential_plan": "RFID + facial",
            }
        )
    return users


def seed(database):
    repository = UserRepository(database)
    created = []
    existing = []
    for user in demo_users():
        try:
            repository.create(
                user["external_id"],
                user["first_name"],
                user["last_name"],
                user["role"],
            )
        except UserAlreadyExists:
            existing.append(user)
        else:
            created.append(user)
    return created, existing


def main():
    parser = argparse.ArgumentParser(
        description="Crea 10 usuarios RFID y 10 usuarios RFID + facial."
    )
    parser.add_argument("--database", type=Path, default=DEFAULT_DB)
    args = parser.parse_args()

    try:
        created, existing = seed(args.database.expanduser().resolve())
    except (OSError, ValueError) as exc:
        print(f"[ERROR] {exc}")
        return 1

    print(f"[OK] Usuarios nuevos: {len(created)}")
    print(f"[INFO] Usuarios que ya existían: {len(existing)}")
    print("[PENDIENTE] Presentar una tarjeta real para cada usuario.")
    print("[PENDIENTE] Enrolar rostro sólo para user_both_01 a user_both_10.")
    print("[SEGURIDAD] No se generaron UID ni datos biométricos ficticios.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
