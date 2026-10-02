# secureGate

Sistema de control de acceso seguro desarrollado actualmente sobre **hardware propio**, con proyección a una implementación final en el Laboratorio de Mecatrónica.

## Estado actual

La versión integrada actual reúne en una misma solución:

- ESP32-CAM como sensor óptico.
- YuNet para detección facial.
- SFace para extracción de embeddings faciales.
- Embeddings de 128 componentes.
- Enrolamiento biométrico offline.
- SQLite como base de datos común.
- Templates biométricos cifrados con AES-256-GCM.
- `K_bio` separada de la base de datos y de Git.
- Acceso alternativo mediante RFID RC522.
- UID RFID no almacenado en claro.
- `HMAC-SHA-256(K_rfid, UID)`.
- `K_rfid` independiente de `K_bio`.
- Runtime unificado: **biometría OR RFID**.
- Regla de consenso biométrica 2-de-3 frames.
- Alertas por Telegram.
- Registro persistente de eventos de acceso.
- API REST para frontend.
- Heartbeat del runtime.
- Control de puerta en modo simulado y driver GPIO configurable.
- Tests automatizados.

La actuación física mediante relé está implementada en software, pero permanece en **modo simulado por defecto** hasta validar eléctricamente módulo, GPIO y polaridad. El Reed switch y la interfaz web visual continúan pendientes. La investigación de IA local sigue siendo opcional.

## Arquitectura general

```text
                         INTERNET
                            │
                            ▼
                  TP-Link Router / AP
                      192.168.1.1
                            │
              ┌─────────────┴─────────────┐
              │                           │
            Wi-Fi                       LAN/Wi-Fi
              │                           │
              ▼                           ▼
       ESP32-CAM                     Raspberry Pi 3B
       192.168.1.95                  192.168.1.40
       - OV2640                      - secureGate
       - /capture                    - YuNet + SFace
       - JPEG HTTP                   - SQLite
              │                      - RFID RC522
              └──── HTTP /capture ──►- Telegram
                                     - API REST
                                     - logs
                                     - decisión de acceso
                                     - control de puerta
                                          │
                                          ▼
                                  relé / cerradura
                                  (simulado por defecto)
```

El RC522 se conecta directamente a la Raspberry Pi mediante SPI. La ESP32-CAM queda dedicada a captura de imagen.

## Flujo de acceso

```text
Usuario
  │
  ├── rostro ──► ESP32-CAM ──► YuNet + SFace ──► matching biométrico
  │
  └── tarjeta ─► RC522 ──────► HMAC UID ───────► lookup RFID
                                      │
                         BIOMETRÍA OR RFID
                                      │
                                      ▼
                           ACCESO AUTORIZADO
                                      │
                     ┌────────────────┼───────────────┐
                     │                │               │
                     ▼                ▼               ▼
                 puerta/relé       logs          Telegram
                                     │
                                     ▼
                                  API REST
                                     │
                                     ▼
                                  frontend
```

No es 2FA: basta un rostro autorizado **o** una tarjeta RFID autorizada.

## Base de datos

La base operativa es:

```text
data/db/securegate.db
```

La biometría y RFID se almacenan en tablas distintas dentro de la misma base.

Tablas principales:

```text
users
biometric_templates
rfid_credentials
access_events
rfid_enrollment_requests
runtime_status
```

`rfid_credentials` se crea al inicializar el módulo RFID mediante `CardRegistry` / `admin/manage_rfid.py`.

La tabla `users` funciona como identidad común. Un mismo `user_0##` puede tener biometría, RFID o ambas.

## Biometría

### Pipeline

```text
imagen
↓
normalización
↓
YuNet
↓
detección y alineación
↓
SFace
↓
embedding 128D
```

Parámetros actuales:

```text
OpenCV = 4.11.0
YuNet threshold = 0.7
SFace = similitud coseno
Threshold = 0.45
Regla de consenso = 2 de 3 frames
```

### Enrolamiento

Las fotografías se procesan únicamente en el equipo administrativo.

Estructura:

```text
data/enrollment/user_###/
├── 01.jpg
├── 02.jpg
├── 03.jpg
├── 04.jpg
└── 05.jpg
```

Comando:

```bash
python admin/enroll_user.py \
  user_### \
  data/enrollment/user_###
```

Estado biométrico validado:

```text
user_001 → 5 templates
user_002 → 5 templates
user_003 → 5 templates
user_004 → 5 templates
```

Total:

```text
20 templates activos
```

Las fotografías de enrolamiento no son necesarias en la Raspberry Pi de operación.

### Protección criptográfica

Cada embedding de 128 componentes se serializa y cifra:

```text
embedding
↓
float32 → bytes
↓
AES-256-GCM
↓
ciphertext
↓
SQLite
```

`K_bio`:

- 256 bits;
- global para la base biométrica;
- almacenada localmente;
- fuera de SQLite;
- fuera de Git;
- ruta local: `local/keys/k_bio`.

Cada template usa un nonce GCM único. Los embeddings se descifran únicamente de forma temporal en RAM durante el matching y no se persisten en claro.

## RFID RC522

El RC522 se conecta a la Raspberry Pi por SPI:

```text
RC522        Raspberry Pi
-------------------------------
3.3V    →    Pin 1
RST     →    Pin 22 / GPIO25
GND     →    Pin 6
IRQ     →    sin conectar
MISO    →    Pin 21 / GPIO9
MOSI    →    Pin 19 / GPIO10
SCK     →    Pin 23 / GPIO11
SDA/CS  →    Pin 24 / GPIO8 / CE0
```

**Nunca alimentar el RC522 con 5 V.**

Inicialización:

```bash
python admin/manage_rfid.py init
```

Enrolamiento:

```bash
python admin/manage_rfid.py enroll user_001
```

El UID no se almacena en claro:

```text
UID
↓
HMAC-SHA-256(K_rfid, UID)
↓
uid_digest
↓
rfid_credentials
```

`K_rfid` se almacena localmente en:

```text
local/keys/k_rfid
```

y debe mantenerse fuera de Git.

Un usuario puede tener una o más credenciales RFID activas.

## Runtime unificado

Comando principal:

```bash
python raspberry/runtime_access.py \
  http://192.168.1.95/capture
```

Métodos disponibles:

```text
both
face
rfid
```

Ejemplos:

```bash
python raspberry/runtime_access.py \
  http://192.168.1.95/capture \
  --methods face
```

```bash
python raspberry/runtime_access.py \
  --methods rfid
```

El runtime ejecuta workers independientes para biometría y RFID y unifica ambos en una decisión común de acceso.

Las fallas técnicas de cámara, visión, RFID o base de datos no deben convertirse automáticamente en rechazos de credenciales.

## Regla de consenso biométrica

Se capturan tres frames válidos:

```text
frame 1
frame 2
frame 3
↓
2 o más identifican al mismo usuario
con score >= 0.45
↓
USUARIO VÁLIDO
```

Caso contrario:

```text
USUARIO NO AUTORIZADO
```

## Control de puerta

Por seguridad, el modo por defecto es:

```text
simulate
```

Una credencial válida genera la decisión y registra el evento, pero no energiza GPIO.

El modo físico requiere configurar explícitamente:

```bash
python raspberry/runtime_access.py \
  --methods rfid \
  --door-mode gpio \
  --relay-pin PIN_BCM_CONFIRMADO \
  --relay-active high \
  --door-open-seconds 3
```

No habilitar este modo hasta validar el módulo de relé, el GPIO BCM elegido y su polaridad.

## Logs y auditoría

Cada intento procesado por el runtime unificado puede registrarse en:

```text
access_events
```

Incluye, entre otros:

- timestamp;
- método de autenticación;
- usuario pseudonimizado;
- autorizado / rechazado;
- horario restringido;
- motivos de alerta;
- resultado de puerta.

Consulta:

```bash
python admin/access_report.py --limit 50
```

Exportación CSV:

```bash
python admin/access_report.py \
  --date 2026-10-01 \
  --csv informe.csv
```

La detección avanzada de anomalías continúa siendo una etapa posterior.

## Alertas por Telegram

El runtime puede generar alertas por:

- intento fuera de horario;
- múltiples rechazos consecutivos.

Horarios restringidos actuales:

```text
Lunes a viernes: 21:00 a 05:59
Sábados y domingos: 17:00 a 08:59
```

Configuración local:

```bash
export TELEGRAM_BOT_TOKEN="token_del_bot"
export TELEGRAM_CHAT_ID="id_del_chat"
```

Los secretos de Telegram no deben almacenarse en Git.

Para eventos RFID, si corresponde una alerta, el runtime puede solicitar una captura adicional a la ESP32-CAM. Si la fotografía falla, la alerta de texto continúa.

Telegram nunca decide la apertura de la puerta.

## Backend REST para frontend

El frontend no accede directamente a SQLite, GPIO, UID, claves ni embeddings.

Instalación:

```bash
python -m pip install -r requirements-api.txt
```

Generar token:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Ejecutar:

```bash
export SECUREGATE_API_TOKEN="TOKEN_GENERADO"
python raspberry/backend_api.py
```

Documentación OpenAPI:

```text
http://127.0.0.1:8000/docs
```

Funciones disponibles:

- estado general;
- usuarios;
- alta y activación/desactivación de usuarios;
- consulta de credenciales disponibles por usuario;
- revocación de RFID o biometría;
- solicitud de enrolamiento RFID;
- eventos de acceso;
- resumen de eventos;
- heartbeat del runtime.

La interfaz web visual todavía no forma parte de esta versión.

## Estado del runtime

La tabla:

```text
runtime_status
```

permite al backend conocer:

- si el runtime está ejecutándose;
- métodos habilitados;
- modo de puerta;
- última actualización / heartbeat.

## Seguridad

### Pseudonimización

Los usuarios operativos se representan como:

```text
user_001
user_002
...
```

### Separación de claves

```text
K_bio  ≠  K_rfid
```

No se reutiliza la misma clave para biometría y RFID.

### Política de Git

No se versionan:

```text
data/
models/
local/
captures/
images/
embeddings/
*.db
*.sqlite
*.sqlite3
.env
.env.*
*.key
*.pem
secrets/
config/local/
esp32cam/include/network_secrets.hpp
esp32cam/.pio/
```

### Mínima exposición de datos

- fotografías de enrolamiento fuera de la Raspberry de operación;
- embeddings cifrados en disco;
- embeddings descifrados sólo temporalmente en RAM;
- UID RFID no almacenado en claro;
- claves fuera de SQLite y Git;
- frontend sin acceso directo a secretos, UID o embeddings.

## ESP32-CAM

Firmware desarrollado con PlatformIO.

IP reservada por DHCP:

```text
192.168.1.95
```

Endpoints:

```text
/
→ healthcheck

/capture
→ JPEG
```

Resolución validada:

```text
640x480
```

Actualmente `/capture` usa HTTP dentro de la LAN. HTTPS/TLS queda como hardening posterior.

## Red de prueba

```text
Red LAN:       192.168.1.0/24
Gateway/AP:    192.168.1.1
Raspberry Pi:  192.168.1.40
ESP32-CAM:     192.168.1.95
```

Las IP de Raspberry Pi y ESP32-CAM se mantienen mediante reservas DHCP.

La autenticación local puede continuar dentro de la LAN sin Internet. La salida a Internet se utiliza para servicios externos como Telegram.

## Inicialización de una instalación

```bash
cd ~/secureGate
source .venv/bin/activate

python -m pip install -r requirements.txt \
  -r requirements-rfid.txt \
  -r requirements-api.txt

python raspberry/init_db.py
./scripts/download_models.sh
```

Para desarrollo/tests:

```bash
python -m pip install -r requirements-test.txt
python -m pytest -q
```

## Transferencia de datos biométricos

El enrolamiento facial se realiza en el equipo administrativo.

A la Raspberry se transfiere:

```text
data/db/securegate.db
local/keys/k_bio
```

Si `K_bio` ya existe y no fue rotada, sólo debe actualizarse la DB.

Una vez que se comienzan a enrolar tarjetas RFID en la Raspberry, esa copia de `securegate.db` contiene también las credenciales RFID. Evitar sobrescribirla con una copia antigua del equipo administrativo.

## Documentación

- [Prototipo V1 biométrico — registro histórico](docs/PROTOTIPO_V1.md)
- [Instalación RFID](docs/INSTALACION_RFID.md)
- [Guía rápida RFID](docs/RFID_GUIA_RAPIDA.md)
- [API para frontend](docs/API_FRONTEND.md)
- [Despliegue Raspberry Pi 4](docs/DESPLIEGUE_RPI4.md)

## Pendientes

- validación física completa del RC522;
- validación eléctrica y mecánica del relé/cerradura;
- Reed switch para estado real de puerta en implementación final;
- frontend visual;
- evaluación de detección avanzada de anomalías;
- evaluación de necesidad y factibilidad de IA local;
- hardening adicional de red y TLS/HTTPS para despliegue final.
