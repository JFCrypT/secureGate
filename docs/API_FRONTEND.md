# API para el equipo de frontend

Esta API es el puente entre la interfaz y el backend de secureGate. El frontend
no debe abrir SQLite, manejar GPIO ni recibir UID, claves o embeddings.

## Alcance actual

Disponible:

- comprobar que API y base respondan;
- crear, listar, consultar, activar y desactivar usuarios pseudonimizados;
- guardar opcionalmente nombre, apellido y rol para mostrar en la interfaz;
- saber si un usuario tiene rostro o RFID, sin exponer la credencial;
- consultar registros de acceso con filtros y paginación;
- obtener resúmenes diarios;
- revocar una tarjeta o biometría sin exponer/borrar sus datos;
- documentación OpenAPI automática.

Pendiente hasta integrar actuadores:

- orden remota de apertura;
- estado físico de puerta/Reed;
- alta facial desde el navegador;
- otros campos personales que el equipo todavía pueda definir.

## Instalación

Dentro del entorno virtual de la Raspberry:

```bash
python -m pip install -r requirements-api.txt
python raspberry/init_db.py
```

Para ejecutar también las pruebas del backend, instalar
`requirements-test.txt` en el entorno de desarrollo.

Generar un token de administración:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Guardar el resultado fuera de Git y cargarlo en la terminal:

```bash
read -r -s -p "Token API: " SECUREGATE_API_TOKEN
export SECUREGATE_API_TOKEN
echo
```

Si el frontend se ejecuta, por ejemplo, en `http://localhost:3000`:

```bash
export SECUREGATE_CORS_ORIGINS="http://localhost:3000"
```

Iniciar sólo para la misma Raspberry:

```bash
python raspberry/backend_api.py
```

Para exponerla a otros equipos de la red local:

```bash
python raspberry/backend_api.py --host 0.0.0.0 --port 8000
```

Limitar ese puerto a la red del laboratorio. HTTP con Bearer token es aceptable
sólo para el prototipo en una red controlada; una instalación real necesita
HTTPS, firewall y rotación de credenciales.

Documentación interactiva:

```text
http://IP_DE_LA_RASPBERRY:8000/docs
```

Contrato OpenAPI para generar clientes:

```text
http://IP_DE_LA_RASPBERRY:8000/openapi.json
```

## Autenticación

`GET /health` es público. Todas las rutas `/api/v1/*` requieren:

```http
Authorization: Bearer TOKEN_CONFIGURADO
```

No guardar el token dentro del código JavaScript público. El despliegue final
debe acordar dónde se autentica el operador; este Bearer token es una protección
administrativa mínima para el prototipo.

## Endpoints

| Método | Ruta | Uso |
|---|---|---|
| `GET` | `/health` | Estado de API y SQLite |
| `GET` | `/api/v1/status` | Totales para el tablero |
| `GET` | `/api/v1/users` | Listar usuarios |
| `GET` | `/api/v1/users/{external_id}` | Consultar un usuario |
| `POST` | `/api/v1/users` | Crear usuario pseudonimizado |
| `PATCH` | `/api/v1/users/{external_id}` | Activar/desactivar usuario |
| `DELETE` | `/api/v1/users/{external_id}/rfid` | Revocar tarjeta activa |
| `DELETE` | `/api/v1/users/{external_id}/face` | Desactivar templates faciales |
| `POST` | `/api/v1/users/{external_id}/rfid-enrollments` | Solicitar lectura de tarjeta |
| `GET` | `/api/v1/rfid-enrollments/{request_id}` | Consultar alta RFID |
| `DELETE` | `/api/v1/rfid-enrollments/{request_id}` | Cancelar alta RFID |
| `GET` | `/api/v1/access-events` | Consultar registros |
| `GET` | `/api/v1/access-events/summary` | Resumen de registros |

### Crear usuario

Petición:

```http
POST /api/v1/users
Content-Type: application/json
Authorization: Bearer TOKEN_CONFIGURADO

{
  "external_id":"user_005",
  "first_name":"Ana",
  "last_name":"Pérez",
  "role":"docente"
}
```

Respuesta `201`:

```json
{
  "external_id": "user_005",
  "first_name": "Ana",
  "last_name": "Pérez",
  "role": "docente",
  "active": true,
  "created_at": "2026-10-02 14:00:00",
  "has_face": false,
  "biometric_templates": 0,
  "has_rfid": false
}
```

Crear un usuario no registra automáticamente rostro ni tarjeta. Esas altas se
hacen mediante los flujos locales controlados.

### Desactivar usuario

```http
PATCH /api/v1/users/user_005
Content-Type: application/json
Authorization: Bearer TOKEN_CONFIGURADO

{"active":false}
```

La tarjeta y los templates se conservan, pero el usuario deja de autorizar
ingresos. Esto permite rehabilitarlo sin destruir evidencias o credenciales.

### Revocar credenciales

```text
DELETE /api/v1/users/user_005/rfid
DELETE /api/v1/users/user_005/face
```

La API nunca recibe ni devuelve el UID, las fotografías, los embeddings o las
claves. La revocación cambia el estado de la credencial, sin borrarla. La tarjeta
debe presentarse físicamente en el RC522; el alta facial continúa siendo un
procedimiento local controlado.

### Asociar tarjeta desde el frontend

El frontend no accede al RC522. Crea una solicitud temporal:

```http
POST /api/v1/users/user_005/rfid-enrollments
Content-Type: application/json
Authorization: Bearer TOKEN_CONFIGURADO

{"timeout_seconds":60}
```

Respuesta:

```json
{
  "request_id": 3,
  "external_id": "user_005",
  "status": "pending",
  "created_at": "2026-10-02T17:00:00+00:00",
  "expires_at": "2026-10-02T17:01:00+00:00",
  "finished_at": null,
  "error_code": null
}
```

El runtime que controla el RC522 toma la próxima tarjeta, guarda su HMAC y marca
la solicitud `completed`. El frontend consulta periódicamente:

```text
GET /api/v1/rfid-enrollments/3
```

Estados posibles: `pending`, `completed`, `cancelled`, `failed` y `expired`.
Sólo puede existir una solicitud pendiente porque hay un único lector. El
runtime debe ejecutarse con `--methods rfid` o `--methods both`.

### Consultar registros

Parámetros opcionales:

- `limit`: 1 a 500;
- `offset`: paginación;
- `day`: fecha local `AAAA-MM-DD`;
- `method`: por ejemplo `RFID` o `facial`;
- `granted`: `true` o `false`.

Ejemplo:

```text
GET /api/v1/access-events?day=2026-10-02&granted=true&limit=50
```

Respuesta:

```json
[
  {
    "event_id": 12,
    "occurred_at": "2026-10-02T22:15:00-03:00",
    "method": "RFID",
    "external_id": "user_005",
    "granted": true,
    "restricted_time": true,
    "alert_reasons": ["Intento de ingreso fuera de horario"],
    "door_status": "simulated"
  }
]
```

### Ejemplo JavaScript

```javascript
const response = await fetch("http://IP_RASPBERRY:8000/api/v1/users", {
  headers: {
    Authorization: `Bearer ${token}`,
  },
});

if (!response.ok) {
  throw new Error(`API secureGate: ${response.status}`);
}

const users = await response.json();
```

## Códigos esperados

| Código | Significado |
|---:|---|
| `200` | Consulta/modificación correcta |
| `201` | Usuario creado |
| `401` | Token ausente o incorrecto |
| `404` | Usuario inexistente |
| `409` | Usuario duplicado |
| `422` | JSON o parámetros inválidos |
| `503` | Base no disponible |

## Reglas de integración

1. El frontend usa únicamente la API.
2. El runtime de RFID/rostro es el único que decide autorización.
3. Telegram nunca decide la apertura.
4. El proceso que controle el relé y RC522 debe ser único.
5. Nunca incluir UID, fotografías, base, `k_bio`, `k_rfid` o tokens en Git.
6. No presentar `door_status=simulated` como una apertura física.
