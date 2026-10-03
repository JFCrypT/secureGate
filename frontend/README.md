# secureGate — dashboard web (front)

Dashboard del sistema de control de acceso secureGate. Es un BFF en FastAPI + Jinja2 + HTMX
que consume la API REST de secureGate y agrega login de operadores.

- **Contrato:** [`contrato.md`](contrato.md) (fuente de verdad).
- **Diferencias con la API real y pedidos al backend:** [`PEDIDOS_BACKEND.md`](PEDIDOS_BACKEND.md).
- **Instalación en la Raspberry Pi:** [`deploy/INSTALACION.md`](deploy/INSTALACION.md).

```
navegador (PC / celular)  ──HTTP :8080──▶  front (este proyecto)  ──Bearer──▶  API secureGate
```

El navegador nunca habla con la API ni ve el token. El front no escribe en SQLite,
no toca GPIO ni el lector, y no modifica nada de la Raspberry.

## Desarrollo en tu compu (sin Raspberry)

Requiere Python 3.11 o superior.

```bash
cd frontend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt

cp .env.example .env
# Editar .env: poner un valor aleatorio de 32+ caracteres en SECUREGATE_API_TOKEN
# y otro en FRONT_SESSION_SECRET:
python -c "import secrets; print(secrets.token_urlsafe(32))"

python cli.py add-user admin --role admin       # pide la contraseña
python cli.py add-user guardia --role viewer
```

En dos terminales:

```bash
python dev/mock_api.py                                    # API falsa en 127.0.0.1:8100
uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload  # front
```

Abrir `http://127.0.0.1:8080/dashboard/`.

`.env.example` apunta `SECUREGATE_API_URL` al mock (`http://127.0.0.1:8100`).
**En la Pi va `http://127.0.0.1:8000`**, que es la API real.

### Probar desde el celular

Con el celular en la misma red que la compu:

```bash
ip -4 addr show | grep inet        # buscar la IP de la compu en la red local
```

y abrir `http://IP_DE_LA_COMPU:8080/dashboard/`. Si no carga, revisar el firewall de la compu (puerto 8080).

### La API falsa

`dev/mock_api.py` tiene los mismos endpoints, campos, códigos y mensajes que la API real,
con datos en memoria y un evento nuevo cada 5 s. Es **sólo para desarrollo y tests**:
escucha en `127.0.0.1:8100` (`MOCK_PORT`), nunca en 8000, no se instala en la Pi y no
importa nada de `raspberry/`. Usa el token de `.env`.

Se maneja con `/mock/control`:

```bash
curl "http://127.0.0.1:8100/mock/control?offline=1"        # heartbeat vencido → OFFLINE
curl "http://127.0.0.1:8100/mock/control?offline=stopped"  # runtime detenido
curl "http://127.0.0.1:8100/mock/control?offline=0"        # vuelve a ONLINE
curl "http://127.0.0.1:8100/mock/control?enroll=failed"    # el enrolamiento falla (tarjeta de otro)
curl "http://127.0.0.1:8100/mock/control?enroll=expired"   # nadie pasa la tarjeta
curl "http://127.0.0.1:8100/mock/control?enroll=completed&enroll_seconds=5"
curl "http://127.0.0.1:8100/mock/control?door_mode=gpio"   # o simulate
curl "http://127.0.0.1:8100/mock/control?methods=face"     # both | face | rfid
curl "http://127.0.0.1:8100/mock/control?db_down=true"     # la API responde 500/503
curl "http://127.0.0.1:8100/mock/control?event=true"       # agrega un evento ya
```

`MOCK_EVENT_SECONDS=0 python dev/mock_api.py` apaga el generador de eventos.

## Tests

```bash
pytest -q
```

Cubren el flujo feliz y los errores (API caída, 401 del token, 404, 409, 422, 500/503),
los permisos (`viewer` → 403) y el CSRF. No necesitan red ni el backend instalado.

## Configuración

Variables de entorno (o `frontend/.env` en desarrollo; el entorno tiene prioridad):

| Variable | Por defecto | Uso |
|---|---|---|
| `SECUREGATE_API_URL` | — | Base de la API (`http://127.0.0.1:8100` mock, `http://127.0.0.1:8000` en la Pi) |
| `SECUREGATE_API_TOKEN` | — | Bearer token, 32+ caracteres; nunca sale del servidor |
| `FRONT_SESSION_SECRET` | — | Firma de la cookie de sesión, 32+ caracteres |
| `FRONT_OPERATORS_FILE` | — | JSON de operadores con hash bcrypt (lo administra `cli.py`) |
| `FRONT_BASE_PATH` | `/dashboard` | Prefijo de las rutas |
| `FRONT_TIMEZONE` | `America/Argentina/Buenos_Aires` | Zona para mostrar fechas (igual que la del runtime) |
| `FRONT_POLL_REALTIME_MS` | `2000` | Polling del acceso en tiempo real |
| `FRONT_POLL_STATUS_MS` | `5000` | Polling del estado del sistema |
| `FRONT_SESSION_HOURS` | `8` | Duración de la sesión |

Si la configuración es inválida el front no arranca y nombra la variable, sin mostrar su valor.

## Qué hay en cada pantalla

| Ruta | Rol | Contenido |
|---|---|---|
| `/dashboard/` | admin, viewer | Estado del runtime, último acceso en tiempo real, últimos 10, alertas de 24 h |
| `/dashboard/usuarios` | admin, viewer (lectura) | Listado con búsqueda y filtros; alta, edición, activar/desactivar y revocación sólo admin |
| `/dashboard/usuarios/{id}/rfid` | admin | Enrolamiento de tarjeta con espera, cuenta regresiva y cancelación |
| `/dashboard/historial` | admin, viewer | Registros con filtros y paginado |
| `/dashboard/alertas` | admin, viewer | Estado actual y alertas de 24 h o 7 días |
| `/dashboard/reportes` | admin, viewer | Totales, por usuario, por método, por fecha y exportación CSV |

## Estructura

```
app/
  main.py         create_app, middlewares, manejo de errores
  config.py       variables de entorno, validadas al arrancar
  api_client.py   ÚNICO lugar que llama a la API secureGate
  labels.py       ÚNICO lugar con etiquetas y mapeo de alertas
  timefmt.py      fechas → zona del front
  auth.py         operadores, sesión, roles, CSRF, rate limit
  reports.py      agregaciones y CSV
  routes/         una por pantalla + parciales HTMX
  templates/      Jinja2
  static/         htmx vendorizado, app.css, app.js (sin CDNs)
cli.py            operadores
dev/mock_api.py   API falsa (sólo desarrollo)
deploy/           INSTALACION.md y ejemplo de unit systemd
tests/
```

## Límites conocidos

- **Un solo worker de uvicorn** (sin `--workers`): el rate limit de login y las cachés viven en memoria.
- HTTP plano, cookie sin `Secure`: pensado para la red local controlada.
- La API no filtra por usuario ni por rango y no devuelve totales: el front lo resuelve
  con los fallbacks de `PEDIDOS_BACKEND.md` (paginado con "Siguiente", un pedido por día en reportes).
- El alta facial no tiene endpoint: se hace en el puesto de enrolamiento local.
