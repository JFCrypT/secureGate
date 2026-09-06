# secureGate

Sistema de control de acceso seguro para el ingreso al **Laboratorio de Mecatrónica de la Facultad de Ingeniería del Ejército**.

## Estado actual

El **Prototipo v1** se encuentra funcional en notebook/Xubuntu y preparado para validación final sobre Raspberry Pi 3.

Incluye:
- ESP-CAM como sensor óptico.
- YuNet para detección facial.
- SFace para extracción de embeddings.
- Enrolamiento offline.
- SQLite.
- Embeddings cifrados con AES-256-GCM.
- `K_bio` global para la base biométrica.
- Identificación 1:N.
- Runtime continuo.
- Regla temporal 2-de-3 frames.
- Salida por consola:
  - `USUARIO VÁLIDO: user_00#`
  - `USUARIO NO AUTORIZADO`

No incluye GPIO, relé, RFID, Reed switch, detección de anomalías, IA local ni frontend.

## Arquitectura del prototipo

```text
NOTEBOOK / ADMIN
│
├── fotos
├── YuNet + SFace
├── embeddings
├── validación
├── AES-256-GCM
└── securegate.db
        │
        │ transferencia manual
        ▼
Raspberry Pi 3
│
├── securegate.db
├── K_bio
├── modelos YuNet/SFace
└── runtime continuo
        │
        ▼
ESP-CAM
192.168.1.95
/capture
```

La Raspberry Pi 3 no necesita fotografías de enrolamiento.

## ESP-CAM

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
→ captura JPEG
```

Resolución validada:

```text
640x480
```

La ESP-CAM sólo captura y entrega imágenes. La biometría se procesa en notebook/Raspberry.

## Pipeline facial

```text
frame
↓
normalización
↓
lado mayor máximo = 800 px
↓
YuNet
↓
alineación
↓
SFace
↓
embedding 128D
```

Parámetros del prototipo:

```text
OpenCV = 4.11.0
YuNet threshold = 0.7
Métrica SFace = similitud coseno
Threshold SFace = 0.45
Regla temporal = 2 de 3 frames
```

## Enrolamiento

Usuarios pseudonimizados:

```text
user_001
user_002
user_003
```

Estado actual:

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

El enrolamiento es incremental y no sobrescribe automáticamente usuarios existentes.

## Seguridad biométrica

Los embeddings no se almacenan en claro.

```text
embedding
↓
AES-256-GCM
↓
SQLite
```

`K_bio`:
- 256 bits.
- Global para la base biométrica.
- Fuera de SQLite.
- Fuera de Git.
- Ruta local: `local/keys/k_bio`.
- Se transfiere manualmente a Raspberry Pi.

Cada template usa un nonce GCM único.

## Validación criptográfica

Round-trip:

```text
embedding
→ cifrado
→ SQLite
→ lectura
→ descifrado
→ embedding recuperado
```

Resultado:

```text
Embedding: 128 dimensiones
Ciphertext: 528 bytes
Nonce: 12 bytes
Igualdad de bytes: True
Igualdad de arrays: True
PASS
```

## Validación biométrica offline

La calibración de threshold documentada a continuación se realizó antes de incorporar `user_004`, por lo que corresponde al conjunto experimental original:

```text
3 usuarios
5 imágenes por usuario
15 muestras
30 comparaciones genuinas
75 impostoras
105 totales
```

Coseno:

```text
genuino mínimo  = 0.540249
impostor máximo = 0.329046
margen          = 0.211203
```

No se observó solapamiento en este conjunto experimental.

## Runtime continuo

Archivo:

```text
raspberry/runtime_recognize_espcam.py
```

Ejecución:

```bash
python raspberry/runtime_recognize_espcam.py \
  http://192.168.1.95/capture
```

Lógica:

```text
capturar 3 frames válidos
↓
si al menos 2 identifican al mismo usuario
con score >= 0.45
↓
USUARIO VÁLIDO

caso contrario
↓
USUARIO NO AUTORIZADO
```

## Validación en vivo

Prueba con `user_001`:

```text
0.391301
0.586555
0.581802
→ 2/3
→ USUARIO VÁLIDO

0.634341
0.564879
0.600887
→ 3/3
→ USUARIO VÁLIDO

0.525558
0.470321
0.557747
→ 3/3
→ USUARIO VÁLIDO

0.532937
0.496281
0.489149
→ 3/3
→ USUARIO VÁLIDO
```

Una persona no enrolada fue rechazada consistentemente.

Pendiente de validación presencial:

```text
user_002
user_003
user_004
```

## Política de Git

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
```

## Despliegue sobre Raspberry Pi 3

En Raspberry Pi 3:

```bash
cd ~/secureGate
git pull
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Los modelos deben estar disponibles localmente:

```bash
./scripts/download_models.sh
```

Transferencia manual desde notebook:

```text
data/db/securegate.db
local/keys/k_bio
```

No se transfieren fotografías.

Una vez preparado:

```bash
python raspberry/runtime_recognize_espcam.py \
  http://192.168.1.95/capture
```

Ese comando inicia el prototipo funcional.


## Comandos de utilidad

### Enrolar un usuario nuevo

Las fotografías se preparan únicamente en el entorno ADMIN/notebook.

Convención:

```text
user_001
user_002
user_003
user_004
user_005
...
```

Para agregar un nuevo usuario, crear su carpeta local con al menos 5 fotografías:

```text
data/enrollment/user_###/
├── 01.jpg
├── 02.jpg
├── 03.jpg
├── 04.jpg
└── 05.jpg
```

Comando general:

```bash
cd ~/secureGate

python admin/enroll_user.py \
  user_### \
  data/enrollment/user_###
```

Ejemplo para `user_005`:

```bash
python admin/enroll_user.py \
  user_005 \
  data/enrollment/user_005
```

El enrolamiento es incremental: agregar `user_004` no modifica los templates existentes de `user_001`, `user_002` o `user_003`.

Verificación de templates activos:

```bash
sqlite3 data/db/securegate.db \
'SELECT u.external_id, COUNT(t.template_id) AS templates
 FROM users u
 LEFT JOIN biometric_templates t
   ON t.user_id = u.user_id
  AND t.active = 1
 GROUP BY u.user_id
 ORDER BY u.external_id;'
```

### Analizar thresholds biométricos

```bash
python raspberry/analyze_thresholds.py \
  data/enrollment
```

### Validar una imagen local contra la base

```bash
python raspberry/runtime_recognize_image.py \
  /ruta/a/imagen.jpg
```

### Ejecutar secureGate con ESP-CAM

En notebook o Raspberry Pi:

```bash
cd ~/secureGate
source .venv/bin/activate

python raspberry/runtime_recognize_espcam.py \
  http://192.168.1.95/capture
```

El proceso queda activo hasta `Ctrl+C`.

### Archivos que deben transferirse manualmente a Raspberry Pi

Después de enrolar o modificar usuarios en la notebook, la base biométrica actualizada debe copiarse manualmente:

```text
data/db/securegate.db
```

También debe existir en la Raspberry la misma clave:

```text
local/keys/k_bio
```

`K_bio` se copia manualmente una vez por instalación, o nuevamente sólo si se reemplaza/rota de forma deliberada.

Ejemplo desde notebook:

```bash
scp data/db/securegate.db \
  usuario@raspberrypi:~/secureGate/data/db/

scp local/keys/k_bio \
  usuario@raspberrypi:~/secureGate/local/keys/
```

Las fotografías de enrolamiento NO se transfieren a Raspberry Pi.

El código se actualiza mediante Git:

```bash
git pull
```

Los modelos YuNet/SFace tampoco se transfieren necesariamente a mano; pueden descargarse localmente en Raspberry mediante:

```bash
./scripts/download_models.sh
```

Por lo tanto, para actualizar usuarios normalmente basta con transferir:

```text
securegate.db
```

Si la Raspberry ya posee la misma `K_bio`, no es necesario volver a copiar la clave.

## Organización por grupos

### GRUPO 1 — Prototipo v1: biometría y ciberseguridad

Desarrollo del prototipo sobre Raspberry Pi 3. Reconocimiento facial con YuNet + SFace, embeddings, enrolamiento offline, AES-256-GCM, SQLite, `K_bio`, firmware ESP-CAM y ciberseguridad del prototipo. El alcance termina en el prototipo funcional.

### GRUPO 2 — Sensores y actuadores

GPIO, relé, cerradura electromagnética, LED, buzzer y Reed switch. Lógica física de apertura, cierre, señalización y monitoreo.

### GRUPO 3 — Detección de anomalías, alertas e investigación de IA local

Reglas determinísticas, evaluación de Isolation Forest e investigación sobre necesidad y factibilidad de un LLM local en Raspberry Pi 4. La IA local es opcional y nunca decide apertura.

### GRUPO 4 — Frontend

Desarrollo de la interfaz de usuario de la solución final.

### GRUPO 5 — Integración final sobre Raspberry Pi 4 y RFID legacy

Porteo del prototipo a Raspberry Pi 4, integración RFID legacy preservando tarjetas y autorizaciones, e integración final de los subsistemas.

## Fuera del alcance del Prototipo v1

- GPIO.
- Relé.
- RFID.
- Reed switch.
- Detección de anomalías.
- Isolation Forest.
- IA local.
- Frontend.
- Integración final en Raspberry Pi 4.
