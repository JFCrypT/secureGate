# contrato.md — Frontend secureGate ↔ API secureGate

> **Versión:** 1.1 · basada en el commit `d71050b` ("Integra backend, RFID, logs y control de acceso") y en `docs/API_FRONTEND.md`.
> **Fuente de verdad del backend:** `raspberry/securegate/api.py` y `http://127.0.0.1:8000/openapi.json`. Si difieren de este documento, gana el código del backend y este contrato se actualiza por PR.
> **Cambio de alcance (v1.1):** el front se sirve directo en `0.0.0.0:8080`, sin nginx; no se modifica nada de la Raspberry; el mock usa el puerto 8100; F8 es sólo documentación.

---

## 1. Arquitectura y red

```
Cualquier dispositivo de la red local de prueba
        │  HTTP :8080   →  http://IP_PI:8080/dashboard/
        ▼
Front (FastAPI + Jinja + HTMX) en la Raspberry Pi, 0.0.0.0:8080   ← NUESTRO
        │ Bearer token (sólo server-side)
        ▼
127.0.0.1:8000   API secureGate  ← NO ES NUESTRA
        │
SQLite + runtime_access (GPIO, RC522, ESP-CAM)
```

| Servicio | Escucha en | Accesible desde la red | Dueño |
|---|---|---|---|
| Front | `0.0.0.0:8080` | **Sí** (`http://IP_PI:8080/dashboard/`) | Nosotros |
| API secureGate | lo que defina el backend (puerto 8000) | No depende de nosotros | Backend |

Reglas de red:
- **No modificamos nada de la Raspberry.** Ni nginx, ni ufw, ni la IP, ni el servicio o la configuración de la API, ni CORS. El front es un proceso más que se suma; todo lo demás sigue igual con o sin él. Las sugerencias opcionales (nginx, IP fija, no exponer el 8000) están en `PEDIDOS_BACKEND.md`, sección "Recomendaciones para integración".
- **El front se sirve directo:** `uvicorn app.main:app --host 0.0.0.0 --port 8080`, sin `--proxy-headers` y **con un solo worker** (sin `--workers`; ver §3). `GET /` redirige a `/dashboard/`.
- **El front llama a la API por loopback** (`http://127.0.0.1:8000` en la Pi). Como el navegador nunca llama a la API, el front **no necesita CORS**.
- **IP de la Pi:** se usa el marcador `IP_PI` en docs y ejemplos. Nunca es `192.168.1.95`, que es la ESP-CAM.
- **HTTP plano** es aceptable sólo en la red local controlada, igual que la API. Por eso el login de operadores, el CSRF y el rate limit de §3 son **obligatorios**, y la cookie de sesión va sin `Secure`. Si se agrega HTTPS más adelante, la cookie pasa a `Secure`.
- **Ningún archivo del repo contiene la contraseña del Wi-Fi.** La red se configura en la Pi, fuera de Git.

---

## 2. Configuración del front (`frontend/.env`, fuera de Git)

| Variable | Ejemplo | Uso |
|---|---|---|
| `SECUREGATE_API_URL` | `http://127.0.0.1:8100` (desarrollo, mock) · `http://127.0.0.1:8000` (en la Pi) | Base de la API |
| `SECUREGATE_API_TOKEN` | *(≥ 32 caracteres, el mismo que la API)* | Bearer token; nunca sale del servidor |
| `FRONT_SESSION_SECRET` | *(≥ 32 caracteres aleatorios)* | Firma de la cookie de sesión |
| `FRONT_OPERATORS_FILE` | `/etc/securegate/frontend-operators.json` | Operadores con hash bcrypt (permisos `600`) |
| `FRONT_BASE_PATH` | `/dashboard` | Prefijo de todas las rutas |
| `FRONT_TIMEZONE` | `America/Argentina/Buenos_Aires` | Zona para mostrar fechas |
| `FRONT_POLL_REALTIME_MS` | `2000` | Polling del acceso en tiempo real |
| `FRONT_POLL_STATUS_MS` | `5000` | Polling del estado del sistema |
| `FRONT_SESSION_HOURS` | `8` | Duración de la sesión |

`config.py` valida todo al arrancar: si falta el token o tiene menos de 32 caracteres, el front **no arranca** y muestra un error claro sin imprimir el valor.

---

## 3. Autenticación de operadores (la resuelve el front)

La API no tiene login de personas, sólo un token de administración. El front agrega uno propio:

- **Roles:**
  - `admin`: hace todo.
  - `viewer`: ve el dashboard, el historial, las alertas y los reportes (incluido el CSV), pero no crea, edita ni revoca nada y no enrola.
- **Archivo de operadores:** `FRONT_OPERATORS_FILE` es un JSON de la forma `{"usuarios":[{"usuario":"admin","hash":"$2b$...","rol":"admin","activo":true}]}`. Se administra con `cli.py add-user|disable-user|set-password` y nunca se commitea.
- **Sesión:** una cookie firmada, `HttpOnly` y `SameSite=Lax`, que vence a las `FRONT_SESSION_HOURS` horas. Al cerrar sesión se limpia.
- **CSRF:** cada formulario y cada POST, PATCH o DELETE de HTMX lleva un token CSRF de sesión (header `X-CSRF-Token`). Si falta o no coincide, devuelve 403.
- **Rate limit de login:** 5 intentos fallidos por IP cada 5 minutos; después, bloqueo de 5 minutos. La IP es la del socket (`request.client.host`): no hay proxy delante, así que no se usa `X-Forwarded-For`.
- **Un solo worker.** El rate limit y las cachés del BFF (lista de usuarios, último estado conocido) viven en la memoria del proceso: uvicorn corre **sin `--workers`**. Con más de un worker el límite de intentos se multiplicaría y la caché quedaría inconsistente.
- Login, CSRF y rate limit son **obligatorios**: el front está expuesto directamente a la red local de prueba.
- Cualquier ruta sin sesión redirige a `/dashboard/login`.

---

## 4. Contrato de la API que consumimos (tal como está hoy)

Todas las rutas `/api/v1/*` requieren `Authorization: Bearer <SECUREGATE_API_TOKEN>`. Los errores llegan en formato FastAPI: `{"detail": "texto"}`; en un 422 de validación, `detail` es una lista.

### 4.1 Sistema

**`GET /health`** (público)
- `200 {"status":"ok","database":"ok","hardware":"runtime-separado"}`
- `503`: la base no está disponible.

**`GET /api/v1/status`**
```json
{
  "api": "ok",
  "database": "ok",
  "runtime": {
    "online": true,
    "status": "running",
    "methods": "both",
    "door_mode": "simulate",
    "updated_at": "2026-10-03T17:00:05+00:00"
  },
  "users":         { "total": 5, "active": 4, "with_face": 4, "with_rfid": 3, "with_both": 2 },
  "access_events": { "total": 120, "granted": 90, "denied": 30, "restricted": 6, "door_errors": 1 }
}
```

Valores posibles en `runtime`:
- `status`: `running`, `stopped` o `unknown`.
- `methods`: `both`, `face`, `rfid` o `null`.
- `door_mode`: `simulate`, `gpio` o `null`.
- `updated_at`: viene en **UTC**.
- `online`: lo calcula la API; es `true` si el status es `running` y el heartbeat tiene 15 s o menos.

### 4.2 Usuarios

Forma de `UserResponse`:
```json
{
  "external_id": "user_005", "first_name": "Ana", "last_name": "Pérez", "role": "docente",
  "active": true, "created_at": "2026-10-02 14:00:00",
  "has_face": false, "biometric_templates": 0, "has_rfid": false
}
```
`created_at` viene **sin zona horaria**; se interpreta como UTC (ver §9).

| Método | Ruta | Body | Respuestas |
|---|---|---|---|
| GET | `/api/v1/users` | — | `200 [UserResponse]` (sin paginado) |
| GET | `/api/v1/users/{external_id}` | — | `200` · `404` |
| POST | `/api/v1/users` | `{"external_id","first_name"?,"last_name"?,"role"?}` | `201` · `409` duplicado · `422` |
| PATCH | `/api/v1/users/{external_id}` | uno o más de `first_name`, `last_name`, `role`, `active` | `200` · `404` · `422` (body vacío o inválido) |
| DELETE | `/api/v1/users/{external_id}/rfid` | — | `200 UserResponse` · `404` (no existe o no tiene tarjeta activa) |
| DELETE | `/api/v1/users/{external_id}/face` | — | `200 UserResponse` · `404` (no existe o no tiene rostro activo) |

Validaciones de la API que el front replica del lado del cliente:
- `external_id` tiene que cumplir `^user_[A-Za-z0-9_-]+$`, con 6 a 64 caracteres.
- `first_name` y `last_name` van de 1 a 100 caracteres; `role` de 1 a 50.
- **No se aceptan campos extra**: la API usa `extra=forbid`, así que cualquier campo de más da 422.

### 4.3 Enrolamiento RFID

| Método | Ruta | Body | Respuestas |
|---|---|---|---|
| POST | `/api/v1/users/{external_id}/rfid-enrollments` | `{"timeout_seconds":60}` (de 10 a 300) | `201 Enrollment` · `404` usuario · `409` · `422` |
| GET | `/api/v1/rfid-enrollments/{request_id}` | — | `200 Enrollment` · `404` |
| DELETE | `/api/v1/rfid-enrollments/{request_id}` | — | `200 Enrollment` (queda `cancelled`) · `404` (no existe o ya no está pendiente) |

```json
{ "request_id": 3, "external_id": "user_005", "status": "pending",
  "created_at": "2026-10-02T17:00:00+00:00", "expires_at": "2026-10-02T17:01:00+00:00",
  "finished_at": null, "error_code": null }
```

Valores posibles:
- `status`: `pending`, `completed`, `cancelled`, `failed` o `expired`.
- `error_code` conocido: `card_unavailable`, cuando la tarjeta no se pudo asociar.

Casos de 409 en el POST, con su `detail`:
- "El usuario está deshabilitado."
- "El usuario ya posee una tarjeta activa; revocarla primero."
- "Ya existe otra solicitud de enrolamiento pendiente." Hay un solo lector, así que sólo puede haber una solicitud pendiente a la vez.

### 4.4 Eventos de acceso

**`GET /api/v1/access-events`**

Parámetros:
- `limit`: de 1 a 500, por defecto 50.
- `offset`: desde 0.
- `day`: fecha local en formato `AAAA-MM-DD`.
- `method`: `RFID` o `facial`.
- `granted`: `true` o `false`.

Responde `200 [AccessEvent]`, ordenado del más nuevo al más viejo. **No incluye el total.**
```json
{ "event_id": 12, "occurred_at": "2026-10-02T22:15:00-03:00", "method": "RFID",
  "external_id": "user_005", "granted": true, "restricted_time": true,
  "alert_reasons": ["Intento de ingreso fuera de horario"], "door_status": "simulated" }
```

Valores posibles:
- `external_id`: `null` cuando la persona no fue identificada.
- `door_status`: `opened`, `simulated`, `not_requested` o `error`.
- `occurred_at`: viene con offset local.

**`GET /api/v1/access-events/summary?day=AAAA-MM-DD`**
- `200 {"total","granted","denied","restricted","door_errors"}`.
- Sin el parámetro `day`, devuelve el total histórico.

### 4.5 Cómo responde el front a los errores de la API

| Situación | Qué hace el front |
|---|---|
| Conexión rechazada o timeout de 3 s | Banner **"API no disponible"**; el dashboard muestra la API caída. Es un estado **distinto** de "runtime OFFLINE" |
| `401` de la API | Es un error de configuración del token, **no** del operador: muestra "Error de configuración del servidor", lo registra en el log sin el token y no desloguea al operador |
| `404` | "No encontrado" con el contexto (usuario, solicitud, credencial) |
| `409` | Muestra el `detail` de la API, que ya viene en español |
| `422` | Errores por campo cuando `detail` es una lista; si es texto, se muestra tal cual |
| `503` | "Base de datos no disponible" |

---

## 5. Etiquetas (centralizadas en `labels.py`)

| Dato de la API | Se muestra |
|---|---|
| `runtime.online = true` | **ONLINE** (verde) |
| `runtime.online = false` | **OFFLINE** (rojo), con el `status` debajo: `running` (heartbeat vencido), `stopped` o `unknown` |
| `methods`: `both` / `face` / `rfid` / `null` | "Biometría + RFID" / "Biometría" / "RFID" / "Sin datos" |
| `door_mode`: `simulate` / `gpio` / `null` | "Simulación" (ámbar) / "GPIO (puerta real)" / "Sin datos" |
| `method`: `RFID` / `facial` / otro | "RFID" / "Biometría" / el valor crudo |
| `granted`: `true` / `false` | **AUTORIZADO** (verde) / **NO AUTORIZADO** (rojo) |
| `external_id = null` | "Desconocido" |
| `door_status`: `opened` | "Abierta" |
| `door_status`: `simulated` | "Simulada — sin apertura física" |
| `door_status`: `not_requested` | "Sin apertura" |
| `door_status`: `error` | "Error de puerta" (rojo) |
| `role = null`, nombre `null` | "—" |

**Alertas.** La API las devuelve como texto, así que se mapean a códigos internos **sólo en `labels.py`**:

| Texto exacto de la API | Código interno | Etiqueta |
|---|---|---|
| `Tres intentos de ingreso fallidos consecutivos` | `CONSECUTIVE_FAILURES` | Rechazos consecutivos |
| `Intento de ingreso fuera de horario` | `RESTRICTED_TIME` | Fuera de horario |
| cualquier otro texto | `OTHER` | Se muestra el texto crudo |

Además, `restricted_time = true` marca "Fuera de horario" en el evento aunque `alert_reasons` venga vacío, porque la alerta tiene cooldown y no se repite.

**Nombres.** El front arma "Nombre Apellido (user_005)" cruzando `external_id` con `GET /users`. Esa lista se cachea 10 s en el BFF y se invalida después de cada alta o edición.

---

## 6. Pantallas y comportamiento

Todas las rutas van bajo `FRONT_BASE_PATH` (`/dashboard`). Las rutas `partials/*` devuelven fragmentos HTML para HTMX. El diseño es mobile first: tiene que verse bien desde 360 px de ancho.

### 6.1 Dashboard — `GET /dashboard/` (admin y viewer)

**Estado general.** Se consulta `GET /api/v1/status` cada `FRONT_POLL_STATUS_MS` mediante `partials/estado`. Muestra:
- ONLINE u OFFLINE;
- el último heartbeat en hora local y como "hace N s";
- el modo de acceso activo;
- el modo de puerta, con un banner ámbar permanente cuando es `simulate`;
- los contadores de usuarios y de eventos.

**Último acceso y acceso en tiempo real.** Se consulta `GET /access-events?limit=1` cada `FRONT_POLL_REALTIME_MS` mediante `partials/tiempo-real`. Muestra:
- el usuario identificado o "Desconocido";
- el método (Biometría o RFID);
- AUTORIZADO o NO AUTORIZADO;
- la fecha y hora;
- el estado de la puerta;
- las alertas.

Si cambia el `event_id`, la tarjeta se resalta 3 s. Además se listan los últimos 10 eventos.

**Alertas recientes.** Resumen de las alertas de las últimas 24 h (ver §6.5).

Si la API no responde, se muestran los últimos datos con la marca "desactualizado".

### 6.2 Usuarios — `/dashboard/usuarios` (escritura sólo admin)

**Listado.** Muestra nombre, apellido, rol, `external_id`, estado activo, rostro (sí/no y cantidad de templates) y tarjeta (sí/no). Se puede buscar por nombre o ID y filtrar por activo, con rostro o con tarjeta; ambos filtros se aplican en el BFF.

**Alta** (`/usuarios/nuevo`):
- Campos: nombre, apellido y rol.
- El `external_id` lo genera el BFF: toma el máximo `user_(\d+)` existente, le suma 1 y lo rellena a 3 dígitos (`user_006`). Si la API responde 409, recalcula y reintenta hasta 3 veces.
- Al terminar, ofrece "Asociar tarjeta ahora", que lleva a §6.3.

**Detalle** (`/usuarios/{external_id}`):
- **Editar** nombre, apellido y rol con `PATCH`.
- **Activar o desactivar** con `PATCH {"active":...}` y una confirmación que explica que se conservan las credenciales pero deja de autorizar.
- **Credenciales asociadas:** se muestra sólo si tiene rostro (y cuántos templates) y si tiene tarjeta. **Nunca se muestra el UID.**
- **Revocar tarjeta** y **revocar rostro**, con confirmación.
- **Alta facial:** no hay endpoint, así que se muestra el texto "El registro facial se realiza en el puesto de enrolamiento local" sin ningún botón.
- **Últimos 20 accesos** de ese usuario. Como la API no filtra por usuario, el BFF recorre los eventos recientes (como máximo 5 páginas de 500) y los filtra; si no completa los 20, lo indica.

### 6.3 Enrolamiento RFID — `/dashboard/usuarios/{external_id}/rfid` (sólo admin)

1. **Validaciones previas.**
   - Si el usuario está inactivo, se bloquea con "Activá el usuario primero".
   - Si ya tiene tarjeta, se bloquea con "Revocá la tarjeta actual primero".
   - Si el runtime está OFFLINE, o si `methods` es `face`, se muestra la advertencia "El lector RFID no está activo; la solicitud va a expirar". Igual se permite continuar.
2. **Iniciar.** `POST …/rfid-enrollments {"timeout_seconds":60}`. Si responde 409 porque hay otra solicitud pendiente, muestra el `detail` y ofrece reintentar.
3. **Espera.** Pantalla "Acercá la tarjeta al lector" con una cuenta regresiva calculada a partir de `expires_at`. Hace polling de `GET /rfid-enrollments/{id}` cada 1 s y tiene un botón **Cancelar** que llama a `DELETE`.
4. **Resultado** según el estado:

   | Estado | Mensaje |
   |---|---|
   | `completed` | "Tarjeta asociada a Nombre Apellido" (y se recarga el usuario, que pasa a `has_rfid`) |
   | `failed` + `card_unavailable` | "No se pudo asociar la tarjeta. Puede que ya pertenezca a otro usuario." |
   | `expired` | "No se detectó ninguna tarjeta a tiempo." |
   | `cancelled` | "Solicitud cancelada." |

5. Si el operador cierra la pantalla con una solicitud `pending`, la solicitud expira sola. Al volver a entrar, el front no la retoma.
6. **En ningún momento se muestra ni se registra el UID.**

### 6.4 Historial — `/dashboard/historial` (admin y viewer)

**Columnas:** fecha y hora, usuario (o "Desconocido"), método, resultado, fuera de horario, estado de la puerta y alertas generadas.

**Filtros que se mandan a la API:**
- `day`;
- `method`;
- `granted`.

**Filtros que aplica el BFF** sobre las páginas que trae:
- usuario;
- sólo fuera de horario;
- sólo con alertas;
- sólo con error de puerta.

**Paginado:**
- trae `limit=50` y usa `offset`;
- como la API no devuelve el total, se muestra "Siguiente" mientras la página venga llena y no se muestra "página X de Y".

### 6.5 Estado y alertas — `/dashboard/alertas` (admin y viewer)

Se calculan a partir de los eventos del período elegido (24 h o 7 días; por defecto 24 h):

| Alerta | Regla |
|---|---|
| Error de puerta | `door_status = "error"` |
| Rechazos consecutivos | `alert_reasons` contiene `CONSECUTIVE_FAILURES` |
| Intentos fuera de horario | `restricted_time = true` |

Además se muestra el estado actual: un banner si el runtime está OFFLINE, si la API no responde o si la puerta está en modo simulación.

Cada alerta enlaza al evento correspondiente en el historial.

### 6.6 Reportes — `/dashboard/reportes` (admin y viewer)

**Rango:** `desde` y `hasta`, de 31 días como máximo y por defecto los últimos 7 días.

**Cómo se obtienen los datos.** Como la API sólo filtra por día, el BFF pide `day` por cada fecha del rango y pagina de a 500 hasta agotar cada día. Hay un tope de 20.000 eventos por reporte; si se pasa, avisa.

**Contenido:**
- autorizados contra rechazados (totales y porcentaje);
- por usuario (autorizados y rechazados de cada uno);
- por método;
- por fecha (una fila por día, con un gráfico de barras hecho en CSS o SVG, sin librerías externas).

**Exportar CSV.** `GET /dashboard/reportes/export.csv?desde=&hasta=&...` usa los mismos filtros y el mismo tope.

| Aspecto | Valor |
|---|---|
| Codificación | UTF-8 con BOM |
| Separador | `;` |
| Nombre del archivo | `accesos_AAAA-MM-DD_AAAA-MM-DD.csv` |
| Columnas | `fecha_hora;usuario_id;nombre;apellido;rol;metodo;resultado;fuera_de_horario;estado_puerta;alertas` |
| Formato de valores | Fecha en hora local; resultado `AUTORIZADO`/`NO AUTORIZADO`; alertas separadas por ` \| ` |
| Datos excluidos | Nunca UID ni datos biométricos |

---

## 7. Desarrollo sin Raspberry: `dev/mock_api.py`

Es una API falsa con **los mismos endpoints, campos, códigos de error y validaciones** que §4, con datos en memoria.

- Escucha en **`127.0.0.1:8100`** (configurable con `MOCK_PORT`), **nunca en 8000**, para no pisar ni confundirse con la API real.
- Es **sólo para desarrollo y tests**: nunca se instala ni se corre en la Pi.
- **No importa nada de `raspberry/`**: los modelos y los textos de `detail` están copiados en el archivo, así el front se instala y se testea sin las dependencias del backend.

Tiene que incluir:
- unos 6 usuarios con combinaciones distintas: con rostro, con tarjeta, inactivo, sin nombre;
- un generador que agrega un evento aleatorio cada 5 s, cubriendo todos los `door_status`, desconocidos, fuera de horario y alertas;
- un heartbeat que se puede apagar con `?offline=1` en `/mock/control`;
- enrolamiento RFID que pasa a `completed` a los 5 s, o a `failed`/`expired` según `/mock/control`;
- el mismo token Bearer por variable de entorno.

---

## 8. Despliegue en la Raspberry (fase F8: sólo documentación)

El front **no modifica la Raspberry**: F8 entrega documentación y un ejemplo de unit, con marcadores y sin secretos. Quien integra decide si los instala.

- `deploy/INSTALACION.md`: crear el venv, instalar dependencias, armar `/etc/securegate/frontend.env` (con `SECUREGATE_API_URL=http://127.0.0.1:8000`), crear operadores con `cli.py`, arrancar y verificar.
- `deploy/securegate-frontend.service.example`:
  - `User=USUARIO_RPI` y `WorkingDirectory=/home/USUARIO_RPI/secureGate/frontend`;
  - `EnvironmentFile=/etc/securegate/frontend.env`;
  - `ExecStart=.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8080` (sin `--proxy-headers` y **sin `--workers`**: un solo proceso);
  - `Restart=on-failure`, `NoNewPrivileges=true`, `PrivateTmp=true`;
  - `After=securegate-api.service`.

**Verificación desde otra máquina de la red:**
- `http://IP_PI:8080/dashboard/` → pantalla de login.
- `http://IP_PI:8080/` → redirige a `/dashboard/`.

---

## 9. Fechas

- Todo se muestra en `FRONT_TIMEZONE` con el formato `dd/mm/aaaa HH:MM:SS`.
- `occurred_at`: viene con offset y se convierte a la zona del front.
- `updated_at`, `expires_at` y `created_at` de los enrolamientos: vienen en UTC con offset y se convierten.
- `created_at` de los usuarios: viene sin offset y **se asume UTC**, porque SQLite usa `CURRENT_TIMESTAMP`. Si el backend lo cambia, sólo se toca `timefmt.py`.
- El "hace N s" se calcula del lado del servidor del front con el reloj de la Pi, que tiene que tener NTP activo.

---

## 10. Pedidos al backend (`PEDIDOS_BACKEND.md`)

El front funciona sin estos cambios usando los fallbacks indicados. Si el backend los implementa, sólo se cambian `api_client.py`, `labels.py` o `reports.py`.

| # | Pedido | Fallback actual |
|---|---|---|
| B1 | Parámetros `from` y `to` en `/access-events` y `/summary` | Un request por día (§6.6) |
| B2 | Filtro `external_id` en `/access-events` | Filtrado en el BFF sobre páginas recientes (§6.2) |
| B3 | Total de resultados (header `X-Total-Count` o un objeto `{items,total}`) | Paginado con "Siguiente" (§6.4) |
| B4 | Códigos estables en las alertas (`CONSECUTIVE_FAILURES`, `RESTRICTED_TIME`) | Mapeo por texto exacto (§5) |
| B5 | Contador actual de rechazos consecutivos en `/status` | Sólo se ve cuando se dispara la alerta |
| B6 | `created_at` de usuarios con zona horaria | Se asume UTC (§9) |
| B7 | Alta facial desde la API | Texto informativo, sin botón (§6.2) |

`PEDIDOS_BACKEND.md` tiene además:
- **Diferencias encontradas con la API real** (D1, D2, …): comportamientos de `api.py` que no coinciden con §4 y cómo se adaptó el front.
- **Recomendaciones para integración** (opcionales, no las aplica el front): poner nginx delante, fijar la IP de la Pi, no exponer el puerto 8000 a la red.

---

## 11. Checklist de aceptación (en la Pi, desde otro dispositivo)

- [ ] Desde una PC y un celular de la red, `http://IP_PI:8080/dashboard/` abre el login; sin login, todas las rutas redirigen.
- [ ] Desde otro equipo, `http://IP_PI:8080/dashboard/` muestra el login.
- [ ] Con el runtime corriendo se ve ONLINE con un heartbeat de menos de 15 s; al detenerlo pasa a OFFLINE en unos 20 s como máximo.
- [ ] El modo de acceso y el modo de puerta coinciden con `SECUREGATE_METHODS` y `SECUREGATE_DOOR_MODE`; en `simulate` se ve el banner ámbar.
- [ ] Un acceso con tarjeta o rostro aparece en tiempo real en menos de 3 s, con usuario, método, resultado, fecha y estado de la puerta.
- [ ] Una persona no identificada aparece como "Desconocido / NO AUTORIZADO".
- [ ] Alta de un usuario, asociación de tarjeta con espera y confirmación, y luego acceso autorizado con esa tarjeta. **En ningún paso aparece el UID**, ni en la pantalla, ni en el CSV, ni en los logs del front.
- [ ] Una tarjeta que ya pertenece a otro usuario da `failed` con el mensaje correcto.
- [ ] Un enrolamiento sin pasar tarjeta da `expired`; con Cancelar da `cancelled`.
- [ ] Al desactivar un usuario se rechazan sus accesos; al reactivarlo vuelve a entrar sin re-enrolar.
- [ ] Al revocar la tarjeta, `has_rfid` pasa a false y se puede asociar otra.
- [ ] Tres rechazos seguidos generan la alerta "Rechazos consecutivos" en el historial y en Alertas; un intento fuera de horario queda marcado.
- [ ] Los reportes de 7 días cuadran con los totales de `/summary` por día; el CSV abre bien en Excel con acentos.
- [ ] Un `viewer` no ve ni puede llamar acciones de escritura (403 directo por URL).
- [ ] Con la API detenida, el front muestra "API no disponible" y no se cae; al levantarla se recupera solo.
- [ ] `git grep` del repo no encuentra tokens, hashes de operadores ni la contraseña del Wi-Fi.
