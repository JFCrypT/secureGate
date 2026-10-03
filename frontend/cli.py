"""Administración de operadores del front (hash bcrypt, archivo con permisos 600).

    python cli.py add-user admin --role admin
    python cli.py add-user guardia --role viewer
    python cli.py set-password guardia
    python cli.py disable-user guardia
    python cli.py enable-user guardia
    python cli.py list

El archivo es FRONT_OPERATORS_FILE (del entorno o de frontend/.env), o --file.
"""

from getpass import getpass
import argparse
import os
import sys

from app import auth
from app.config import load_env_file


def ask_password(from_stdin=False):
    if from_stdin:
        password = sys.stdin.readline().rstrip("\n")
    else:
        password = getpass("Contraseña: ")
        if getpass("Repetir contraseña: ") != password:
            raise SystemExit("Las contraseñas no coinciden.")
    if len(password) < auth.MIN_PASSWORD_LENGTH:
        raise SystemExit(f"La contraseña debe tener al menos {auth.MIN_PASSWORD_LENGTH} caracteres.")
    if len(password.encode("utf-8")) > auth.MAX_PASSWORD_BYTES:
        raise SystemExit("La contraseña no puede superar los 72 bytes.")
    return password


def find(data, username):
    for entry in data["usuarios"]:
        if entry.get("usuario") == username:
            return entry
    raise SystemExit(f"No existe el operador {username}.")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Operadores del front secureGate")
    parser.add_argument("--file", help="archivo de operadores (por defecto FRONT_OPERATORS_FILE)")
    commands = parser.add_subparsers(dest="command", required=True)
    add = commands.add_parser("add-user", help="crear un operador")
    add.add_argument("usuario")
    add.add_argument("--role", choices=auth.ROLES, required=True)
    add.add_argument("--password-stdin", action="store_true", help="leer la contraseña de stdin")
    password = commands.add_parser("set-password", help="cambiar la contraseña")
    password.add_argument("usuario")
    password.add_argument("--password-stdin", action="store_true")
    for name, text in (("disable-user", "deshabilitar"), ("enable-user", "habilitar")):
        commands.add_parser(name, help=f"{text} un operador").add_argument("usuario")
    commands.add_parser("list", help="listar operadores (sin hashes)")
    args = parser.parse_args(argv)

    load_env_file()
    path = args.file or os.environ.get("FRONT_OPERATORS_FILE")
    if not path:
        raise SystemExit("Definir FRONT_OPERATORS_FILE o usar --file.")
    try:
        data = auth.read_operators_file(path)
    except ValueError as exc:
        raise SystemExit(str(exc))

    if args.command == "list":
        for entry in data["usuarios"]:
            state = "activo" if entry.get("activo", True) else "deshabilitado"
            print(f"{entry.get('usuario')}\t{entry.get('rol')}\t{state}")
        return 0

    username = args.usuario.strip().lower()
    if args.command == "add-user":
        if not auth.USERNAME_RE.fullmatch(username):
            raise SystemExit("Usuario inválido: 2 a 32 caracteres entre a-z, 0-9, punto, guion y guion bajo.")
        if any(entry.get("usuario") == username for entry in data["usuarios"]):
            raise SystemExit(f"El operador {username} ya existe.")
        data["usuarios"].append({
            "usuario": username,
            "hash": auth.hash_password(ask_password(args.password_stdin)),
            "rol": args.role,
            "activo": True,
        })
        message = f"Operador {username} creado con rol {args.role}."
    elif args.command == "set-password":
        find(data, username)["hash"] = auth.hash_password(ask_password(args.password_stdin))
        message = f"Contraseña de {username} actualizada."
    else:
        active = args.command == "enable-user"
        find(data, username)["activo"] = active
        message = f"Operador {username} {'habilitado' if active else 'deshabilitado'}."

    auth.write_operators_file(path, data)
    print(message)
    return 0


if __name__ == "__main__":
    sys.exit(main())
