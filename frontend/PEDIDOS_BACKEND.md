# PEDIDOS_BACKEND.md — lo que el front le pide (o le avisa) al backend

El front **no modifica nada fuera de `frontend/`** y funciona hoy con la API tal como está. Este archivo junta:

1. pedidos de cambios a la API (con el fallback que usa el front mientras tanto);
2. diferencias encontradas entre la API real y `contrato.md` §4;
3. recomendaciones opcionales para quien integre el sistema en la Raspberry.

Comparación hecha contra el commit `d71050b`: `raspberry/securegate/api.py`, `users.py`, `runtime_status.py`, `access_log.py`, `rfid/enrollment.py`, `access.py`, `raspberry/runtime_access.py` y `docs/API_FRONTEND.md`.

---

## 1. Pedidos

| # | Pedido | Fallback actual del front |
|---|---|---|
| B1 | Parámetros `from` y `to` en `/access-events` y `/access-events/summary` | Un request por día (reportes y alertas) |
| B2 | Filtro `external_id` en `/access-events` | Filtrado en el BFF sobre las páginas recientes (máx. 5 × 500) |
| B3 | Total de resultados (header `X-Total-Count` o `{items,total}`) | Paginado con "Siguiente" mientras la página venga llena |
| B4 | Códigos estables en las alertas (`CONSECUTIVE_FAILURES`, `RESTRICTED_TIME`) | Mapeo por texto exacto en `app/labels.py` |
| B5 | Contador actual de rechazos consecutivos en `/status` | Sólo se ve cuando se dispara la alerta |
| B6 | `created_at` de usuarios con zona horaria | Se asume UTC (`app/timefmt.py`) |
| B7 | Alta facial desde la API | Texto informativo, sin botón |
| B8 | Que un fallo de SQLite en `/api/v1/*` responda `503` con `detail` (ver D1) | El front trata 500 y 503 igual |
| B9 | Rechazar `{"active": null}` en `PATCH /users/{id}` con 422 (ver D2) | El front nunca manda `active` nulo |

---

## 2. Diferencias encontradas con la API real

En todos los casos **el front se adaptó a la API real**; el contrato §4 no se cambió.

| # | Qué dice el contrato / la doc | Qué hace la API real | Cómo se adaptó el front |
|---|---|---|---|
| D1 | §4.5: `503` = base no disponible | Sólo `GET /health` devuelve 503. En `/api/v1/*` un `sqlite3.Error` no se atrapa y sale como **500** `Internal Server Error` (texto plano, sin `detail`) | `api_client.py` trata 500 y 503 igual: "Base de datos no disponible" |
| D2 | §4.2: `PATCH` acepta `first_name`, `last_name`, `role`, `active` | `{"active": null}` pasa la validación y **desactiva** al usuario (`int(bool(None))`). `{"first_name": null}` borra el campo; `""` da 422 | El cliente exige `active` booleano. Un campo de texto vacío en el formulario se manda como `null` (es la única forma de borrarlo) |
| D3 | §4.2: `404` si el usuario no existe | Con un ID mal formado: `GET` y `DELETE …/rfid|face` → **404**; `PATCH` y `POST …/rfid-enrollments` → **422** con `detail` de texto. El largo 6–64 sólo se valida en el `POST /users` | El BFF valida `^user_[A-Za-z0-9_-]+$` antes de llamar y responde siempre "no encontrado" |
| D4 | §4.1: ejemplo con `updated_at` siempre presente | Si el runtime nunca corrió: `status="unknown"`, `methods`, `door_mode` y `updated_at` en `null`. Además `online` es `false` si el heartbeat queda "en el futuro" (relojes desfasados) | Se muestra "Sin datos"; el "hace N s" sólo aparece si hay fecha |
| D5 | §4.1: heartbeat ≤ 15 s | El runtime lo escribe cada **5 s**; al detenerse limpio escribe `stopped` | Informativo. El polling de estado (5 s) alcanza |
| D6 | §4.4: `day` es "fecha local" | Es un prefijo de texto sobre `occurred_at`, que se guarda con el offset de `SECUREGATE_TIMEZONE` del runtime. El orden es por `event_id DESC`, no por fecha | `FRONT_TIMEZONE` tiene que coincidir con `SECUREGATE_TIMEZONE`. El día de un evento se toma de los primeros 10 caracteres de `occurred_at` |
| D7 | §4.4: `method` es `RFID` o `facial` | Acepta cualquier texto de hasta 32 caracteres, comparación exacta (distingue mayúsculas) | El front sólo manda `RFID` o `facial` |
| D8 | §4.3: estado `expired` | La caducidad es perezosa: la solicitud pasa a `expired` recién cuando alguien consulta o crea otra. `DELETE` sobre una solicitud vencida pero todavía `pending` la deja `cancelled` | El polling de 1 s dispara la caducidad; el front muestra el estado que devuelva la API |
| D9 | `docs/API_FRONTEND.md` | La doc dice que `PATCH` sólo activa/desactiva, que 404 es "usuario inexistente" y 409 "usuario duplicado"; el código también edita nombre/apellido/rol, da 404 por credencial o solicitud inexistente y 409 en enrolamiento | Gana el código (coincide con el contrato). Sugerencia: actualizar la doc |
| D10 | Contrato v1.0 asumía la API en `127.0.0.1` | `deploy/systemd/securegate-api.service.example` arranca con `--host 0.0.0.0` (el default de `backend_api.py` es `127.0.0.1`) | No se toca. Ver recomendaciones |

Coincide con el contrato (verificado en el código): campos y tipos de todas las respuestas, textos de las alertas (`access.py`), valores de `method` (`RFID`, `facial`), `door_status`, `methods`, `door_mode`, textos de los 409 de enrolamiento y `error_code = card_unavailable`.

---

## 3. Recomendaciones para integración (opcionales)

El front **no aplica ninguna** de estas: no instala nginx, no toca ufw, no cambia la IP ni el servicio o la configuración de la API. Quedan a criterio de quien integre.

- **No exponer el puerto 8000 a la red.** El navegador nunca llama a la API: sólo el front, por loopback. Arrancar la API con `--host 127.0.0.1` (o cerrar el 8000 con firewall) reduce la superficie. Con el front no hace falta `SECUREGATE_CORS_ORIGINS`.
- **IP fija para la Pi** (reserva DHCP en el router), distinta de `192.168.1.95` (ESP-CAM), para que `http://IP_PI:8080/dashboard/` no cambie.
- **nginx delante del front** si se quiere servir en el puerto 80 o agregar HTTPS. En ese caso el front pasaría a `--host 127.0.0.1` con `--proxy-headers --forwarded-allow-ips 127.0.0.1` (para que el rate limit vea la IP real) y la cookie de sesión debería marcarse `Secure`.
- **mDNS (`avahi-daemon`)** para entrar por nombre (`securegate.local`); algunos Android no resuelven `.local`, así que la URL por IP tiene que seguir funcionando.
- **NTP activo en la Pi:** el "hace N s" del heartbeat y la cuenta regresiva del enrolamiento usan el reloj de la Pi.
- **Un solo worker de uvicorn para el front** (sin `--workers`): el rate limit de login y las cachés viven en memoria.
