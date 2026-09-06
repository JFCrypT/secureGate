#!/usr/bin/env python3

from pathlib import Path
import argparse
import os
import secrets
import sys


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_KEY_PATH = ROOT_DIR / "local" / "keys" / "k_bio"
KEY_SIZE_BYTES = 32


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Genera la clave biométrica K_bio de secureGate."
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_KEY_PATH,
        help="Ruta de salida de K_bio.",
    )

    args = parser.parse_args()

    key_path = args.output.expanduser().resolve()

    if key_path.exists():
        print(f"[ERROR] La clave ya existe: {key_path}")
        print("[SEGURIDAD] No se sobrescribe una K_bio existente.")
        return 1

    key_path.parent.mkdir(
        parents=True,
        exist_ok=True,
        mode=0o700,
    )

    key = secrets.token_bytes(KEY_SIZE_BYTES)

    try:
        key_path.write_bytes(key)
        os.chmod(key_path, 0o600)
    except OSError as exc:
        print(f"[ERROR] No se pudo crear K_bio: {exc}")
        return 2

    print("[secureGate] Generación de K_bio")
    print(f"[OK] Ruta: {key_path}")
    print(f"[OK] Tamaño: {KEY_SIZE_BYTES} bytes / 256 bits")
    print("[OK] Permisos solicitados: 600")
    print("[SEGURIDAD] El contenido de la clave no se muestra.")
    print("[SEGURIDAD] K_bio no debe almacenarse en Git.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
