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

## Logs

El Prototipo v1 muestra resultados y eventos por consola, pero no implementa todavía un sistema de logs persistentes.

La definición, almacenamiento, análisis y eventual protección de logs de accesos, rechazos, anomalías y eventos del sistema corresponde al **GRUPO 3 — Detección de anomalías, alertas, logs e investigación de IA local**.

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



## Flujo completo de incorporación y uso de un usuario biométrico

### 1. Alta de un usuario

El alta se realiza únicamente en el entorno ADMIN/notebook.

Cada usuario se identifica de forma pseudonimizada:

```text
user_001
user_002
user_003
user_004
...
```

Las fotografías se colocan en una carpeta local:

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
python admin/enroll_user.py \
  user_### \
  data/enrollment/user_###
```

El script procesa todas las imágenes y agrega el nuevo usuario sin modificar los templates de usuarios ya existentes.

### 2. Vectorización de la imagen

Cada fotografía pasa por el mismo pipeline facial:

```text
imagen
↓
normalización de tamaño
↓
lado mayor máximo = 800 px
↓
YuNet
↓
detección del rostro
↓
alineación
↓
SFace
↓
embedding facial
```

SFace genera un embedding de:

```text
128 componentes
```

Conceptualmente:

```text
[e1, e2, e3, ..., e128]
```

Cada componente es un valor real que representa características del rostro dentro del espacio de embeddings del modelo.

No se almacena la fotografía como parte del runtime biométrico de la Raspberry.

### 3. Cifrado del embedding

El embedding se convierte a bytes y se cifra antes de almacenarse:

```text
embedding 128D
↓
serialización float32
↓
AES-256-GCM
↓
ciphertext
↓
SQLite
```

La clave utilizada es:

```text
K_bio
```

`K_bio`:

- es única y global para la base biométrica de esta instancia;
- tiene 256 bits;
- no es una clave por usuario;
- no identifica personas;
- permanece fuera de SQLite;
- permanece fuera de Git.

Cada template utiliza un nonce GCM único.

SQLite almacena el ciphertext y la metadata necesaria, nunca el embedding en claro.

### 4. Qué ocurre cuando se reconoce una persona

La ESP-CAM no realiza reconocimiento.

Su función es únicamente:

```text
ESP-CAM
↓
captura JPEG
↓
/capture
```

El runtime solicita frames a la ESP-CAM de forma continua.

Para cada frame válido:

```text
frame
↓
YuNet
↓
alineación
↓
SFace
↓
embedding_query de 128 componentes
```

El nuevo `embedding_query` no se guarda en SQLite.

### 5. Descifrado de templates durante el matching

Al iniciar el runtime se cargan los templates biométricos activos desde SQLite.

Para cada template:

```text
SQLite
↓
ciphertext + nonce
↓
AES-256-GCM con K_bio
↓
embedding enrolado
↓
RAM
```

El embedding se descifra temporalmente en memoria RAM para poder compararlo con el `embedding_query`.

El proceso de matching utiliza similitud coseno:

```text
embedding_query
vs.
embedding enrolado
↓
score
```

El runtime evalúa todos los templates activos y selecciona la mejor coincidencia.

Los embeddings descifrados no se vuelven a escribir en claro en disco.

### 6. Decisión biométrica

El threshold del prototipo es:

```text
0.45
```

Para reducir falsos rechazos por una captura desfavorable, el runtime utiliza una regla temporal:

```text
3 frames válidos
↓
si al menos 2 de 3
identifican al mismo usuario
con score >= 0.45
↓
USUARIO VÁLIDO
```

En caso contrario:

```text
USUARIO NO AUTORIZADO
```

### 7. Loop de reconocimiento

El runtime permanece ejecutándose continuamente hasta que el operador lo detiene con `Ctrl+C`.

Conceptualmente:

```text
while True:
    pedir frame a ESP-CAM

    si no hay rostro:
        continuar

    generar embedding_query

    comparar contra templates activos

    acumular resultados de 3 frames

    aplicar regla 2-de-3

    imprimir resultado

    continuar esperando
```

No es necesario reiniciar ni liberar la ESP-CAM después de cada usuario.

La cámara permanece activa y disponible para la siguiente captura.

### 8. Flujo resumido completo

```text
ENROLAMIENTO OFFLINE

fotos user_###
↓
YuNet
↓
SFace
↓
5 embeddings × 128D
↓
AES-256-GCM con K_bio
↓
securegate.db


RECONOCIMIENTO EN VIVO

ESP-CAM
↓
JPEG
↓
YuNet
↓
SFace
↓
embedding_query 128D
↓
descifrado temporal de templates con K_bio
↓
matching 1:N
↓
3 frames
↓
regla 2-de-3
↓
USUARIO VÁLIDO / NO AUTORIZADO
```

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

Desarrollo del prototipo sobre Raspberry Pi 3. Reconocimiento facial con YuNet + SFace, embeddings, enrolamiento offline, AES-256-GCM, SQLite, `K_bio`, firmware ESP-CAM y ciberseguridad del prototipo.

### GRUPO 2 — Sensores y actuadores

GPIO, relé, cerradura electromagnética, LED, buzzer y Reed switch. Lógica física de apertura, cierre, señalización y monitoreo.

### GRUPO 3 — Detección de anomalías, alertas, logs e investigación de IA local

Definición de eventos y comportamientos normales, sospechosos y críticos; generación de alertas; implementación y análisis de logs de accesos y eventos; reglas determinísticas; evaluación de Isolation Forest e investigación sobre necesidad y factibilidad de un LLM local en Raspberry Pi 4. La IA local es opcional y nunca decide apertura.

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
