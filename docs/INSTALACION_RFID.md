# Instalación RC522 en Raspberry Pi 3 — secureGate

## Objetivo

Configurar el lector RFID RC522 sobre Raspberry Pi 3 para utilizarlo como método alternativo de acceso en secureGate.

La lógica del sistema es:

```text
rostro válido OR tarjeta RFID válida
→ acceso autorizado
```

RFID no funciona como segundo factor obligatorio.

## Hardware

- Raspberry Pi 3B
- Módulo RFID RC522
- Tarjeta o llavero compatible con 13,56 MHz / ISO 14443-A
- Cables Dupont

## Cableado RC522 → Raspberry Pi 3B

Con la Raspberry Pi apagada, conectar:

| RC522 | Pin físico RPi3 | GPIO / señal |
|---|---:|---|
| 3.3V | 1 | 3.3 V |
| RST | 22 | GPIO25 |
| GND | 6 | GND |
| IRQ | — | No conectar |
| MISO | 21 | GPIO9 / SPI0 MISO |
| MOSI | 19 | GPIO10 / SPI0 MOSI |
| SCK | 23 | GPIO11 / SPI0 SCLK |
| SDA / SS | 24 | GPIO8 / SPI0 CE0 |

**Importante:** el RC522 trabaja a 3,3 V. No conectarlo a 5 V.

## Referencia rápida del conector GPIO de Raspberry Pi 3B

Mirando la placa con USB/Ethernet hacia la derecha y el conector GPIO en la parte superior:

```text
  3V3  (1)  (2)  5V
GPIO2  (3)  (4)  5V
GPIO3  (5)  (6)  GND
GPIO4  (7)  (8)  GPIO14
  GND  (9) (10)  GPIO15
GPIO17 (11) (12) GPIO18
GPIO27 (13) (14) GND
GPIO22 (15) (16) GPIO23
  3V3 (17) (18) GPIO24
GPIO10 (19) (20) GND
 GPIO9 (21) (22) GPIO25
GPIO11 (23) (24) GPIO8
  GND (25) (26) GPIO7
GPIO0  (27) (28) GPIO1
GPIO5  (29) (30) GND
GPIO6  (31) (32) GPIO12
GPIO13 (33) (34) GND
GPIO19 (35) (36) GPIO16
GPIO26 (37) (38) GPIO20
  GND (39) (40) GPIO21
```

Para el RC522, los pines usados son:

```text
1  → 3.3V
6  → GND
19 → MOSI
21 → MISO
22 → RST
23 → SCK
24 → SDA / SS
```

## Habilitar SPI

Ejecutar:

```bash
sudo raspi-config
```

Luego:

```text
Interface Options
→ SPI
→ Enable
```

Reiniciar si se solicita.

Verificar:

```bash
ls -l /dev/spidev0.0
```

Si aparece el dispositivo, SPI está habilitado.

## Actualizar secureGate en la Raspberry Pi 3

```bash
cd ~/secureGate

git pull origin main

source .venv/bin/activate

python -m pip install -r requirements.txt \
  -r requirements-rfid.txt \
  -r requirements-api.txt
```

## Base de datos biométrica

Antes de iniciar RFID, copiar a la Raspberry Pi la base biométrica final:

```text
data/db/securegate.db
```

y la clave biométrica:

```text
local/keys/k_bio
```

Se recomienda realizar un backup antes de continuar:

```bash
cp data/db/securegate.db \
  data/db/securegate_backup_pre_rfid.db
```

Luego ejecutar:

```bash
python raspberry/init_db.py
```

Este comando migra/inicializa la estructura necesaria sin eliminar los usuarios ni los templates biométricos existentes.

## Inicializar RFID

Ejecutar:

```bash
python admin/manage_rfid.py init
```

Este proceso prepara la funcionalidad RFID y utiliza la clave:

```text
local/keys/k_rfid
```

`K_rfid` debe mantenerse fuera de Git y es independiente de `K_bio`.

## Enrolar tarjetas RFID

Para enrolar una tarjeta:

```bash
python admin/manage_rfid.py enroll user_001
```

El programa espera que se acerque la tarjeta al RC522.

Para una segunda tarjeta:

```bash
python admin/manage_rfid.py enroll user_002
```

No se almacenan archivos RFID equivalentes a las fotografías biométricas.

El flujo es:

```text
tarjeta
↓
RC522 lee UID
↓
normalización
↓
HMAC-SHA-256(K_rfid, UID)
↓
uid_digest
↓
securegate.db
↓
tabla rfid_credentials
```

El UID no se guarda en claro.

## Verificar credenciales RFID

```bash
sqlite3 data/db/securegate.db \
'SELECT u.external_id, COUNT(r.credential_id)
 FROM users u
 LEFT JOIN rfid_credentials r
   ON r.user_id = u.user_id
  AND r.active = 1
 GROUP BY u.user_id
 ORDER BY u.external_id;'
```

## Probar sólo RFID

```bash
python raspberry/runtime_access.py --methods rfid
```

## Probar sistema completo

```bash
python raspberry/runtime_access.py \
  http://192.168.1.95/capture
```

Con ese comando quedan habilitados ambos métodos:

```text
biometría OR RFID
```

## Notas de seguridad

- No alimentar RC522 con 5 V.
- No almacenar UID RFID en claro.
- Mantener `K_rfid` fuera de SQLite y Git.
- Mantener `K_rfid` separada de `K_bio`.
- No exponer UID desde frontend.
- No sobrescribir la base operativa de la Raspberry con una copia antigua después de enrolar RFID.
- El modo de puerta permanece en simulación por defecto hasta validar el relé físicamente.

## Puesta en marcha integral

Para la instalación completa sobre Raspberry Pi 3, incluyendo biometría,
RFID, Telegram, backend, frontend, logs, prueba funcional y arranque
automático mediante cron, consultar:

[PUESTA_EN_MARCHA_RPI3.md](PUESTA_EN_MARCHA_RPI3.md)
