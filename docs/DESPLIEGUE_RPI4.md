# Despliegue del backend en Raspberry Pi 4

Esta guía instala el prototipo con dos procesos:

1. `securegate-runtime`: RC522, rostro, Telegram, registros y relé.
2. `securegate-api`: puente JSON para el frontend.

Ambos comparten SQLite en modo WAL. Sólo el runtime utiliza RC522 y GPIO.

## 1. Preparar el sistema

```bash
sudo apt update
sudo apt install -y python3-venv python3-dev build-essential
cd ~/secureGate
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt -r requirements-rfid.txt -r requirements-api.txt
python raspberry/init_db.py
python admin/manage_rfid.py init
python admin/seed_demo_users.py
```

El último comando es opcional y prepara la demostración: crea diez usuarios
`user_rfid_01` a `user_rfid_10` y diez usuarios `user_both_01` a
`user_both_10`. Es idempotente, por lo que puede repetirse sin duplicarlos.
No inventa tarjetas ni rostros: cada credencial debe enrolarse con el RC522 o
la cámara reales.

Habilitar SPI desde `sudo raspi-config`, reiniciar y verificar:

```bash
ls /dev/spidev0.0
```

El usuario del servicio debe pertenecer a `spi` y `gpio`.

## 2. Configuración privada

Copiar `deploy/securegate.env.example` fuera del repositorio:

```bash
sudo install -d -m 700 /etc/securegate
sudo install -m 600 deploy/securegate.env.example /etc/securegate/securegate.env
sudo nano /etc/securegate/securegate.env
```

Reemplazar IP de ESP-CAM, token Telegram, chat, token API y origen del frontend.
Generar el token API con:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Mantener inicialmente:

```text
SECUREGATE_DOOR_MODE=simulate
```

Para el módulo FE-SRY de la demostración, después de validar la conexión física:

```text
SECUREGATE_DOOR_MODE=gpio
SECUREGATE_RELAY_PIN=5
SECUREGATE_RELAY_ACTIVE=high
SECUREGATE_DOOR_OPEN_SECONDS=3
```

`GPIO5` corresponde al pin físico 29. El relé se alimenta con 5 V externos y
comparte GND con Raspberry; sus contactos `NC/COM/NO` quedan libres porque el LED
representa la apertura. Nunca aplicar 5 V al GPIO.

## 3. Probar manualmente antes de crear servicios

En una terminal:

```bash
set -a
source /etc/securegate/securegate.env
set +a
python raspberry/runtime_access.py
```

En otra terminal con el mismo entorno:

```bash
python raspberry/backend_api.py --host 0.0.0.0 --port 8000
```

Comprobar:

```text
http://IP_RASPBERRY:8000/health
http://IP_RASPBERRY:8000/docs
```

## 4. Servicios automáticos

Los archivos de `deploy/systemd/*.example` contienen `USUARIO_RPI`. Reemplazar
ese marcador por el usuario y ajustar `/home/USUARIO_RPI/secureGate` si la ruta
es diferente. Después copiar los archivos ya editados:

```bash
sudo cp deploy/systemd/securegate-api.service.example /etc/systemd/system/securegate-api.service
sudo cp deploy/systemd/securegate-runtime.service.example /etc/systemd/system/securegate-runtime.service
sudo systemctl daemon-reload
sudo systemctl enable --now securegate-api securegate-runtime
```

Consultar estado y logs:

```bash
systemctl status securegate-api securegate-runtime
journalctl -u securegate-api -u securegate-runtime -f
```

## 5. Flujo de alta desde frontend

1. Frontend crea el usuario mediante `POST /api/v1/users`.
2. Frontend crea `POST /api/v1/users/{id}/rfid-enrollments`.
3. Runtime debe estar activo en modo `rfid` o `both`.
4. El operador acerca una tarjeta antes del vencimiento.
5. Runtime guarda únicamente el HMAC del UID y marca la solicitud `completed`.
6. Frontend consulta `GET /api/v1/rfid-enrollments/{request_id}`.

Una sola solicitud puede estar pendiente, porque existe un solo lector. Si la
tarjeta pertenece a otro usuario, el pedido termina en `failed`. El UID nunca se
envía al navegador.

## 6. Prueba de aceptación

- `/api/v1/status` informa runtime `online`.
- Tarjeta registrada autoriza y genera un registro.
- Rostro registrado autoriza sin tarjeta.
- Usuario desactivado no autoriza.
- Fuera de horario autoriza pero genera Telegram y registro restringido.
- Tres rechazos consecutivos generan alerta.
- Cámara desconectada no impide RFID.
- Tarjeta retirada y presentada nuevamente produce un nuevo intento.
- En modo GPIO el LED del relé se activa tres segundos.

No declarar validación física hasta completar estas pruebas en la Raspberry.
