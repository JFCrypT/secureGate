# secureGate

Sistema de control de acceso seguro desarrollado actualmente sobre **hardware propio**, con posibilidad de implementación final en el **Laboratorio de Mecatrónica de la Facultad de Ingeniería del Ejército**.

## Estado actual

El sistema se encuentra funcional en notebook/Xubuntu y preparado para integración y validación sobre Raspberry Pi 3, que se mantiene como SBC objetivo también para una eventual implementación final en laboratorio.

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
- Regla de consenso 2-de-3 frames.
- Salida por consola:
  - `USUARIO VÁLIDO: user_00#`
  - `USUARIO NO AUTORIZADO`
- Alertas por Telegram fuera del horario permitido, con hora y fotografía.
- Acceso alternativo por tarjeta RC522 registrada (SPI, Raspberry Pi 3).
- Alerta por tres rechazos consecutivos, combinando reconocimiento facial y RFID.
- Control de puerta con modo simulado seguro y driver GPIO configurable.
- Registro persistente de accesos y exportación de informes CSV desde SQLite.
- API REST protegida para usuarios y registros, con documentación OpenAPI.
- Alta RFID solicitada desde frontend sin exponer el UID al navegador.
- Heartbeat para que el tablero informe si el runtime está realmente activo.

La actuación GPIO está implementada pero todavía requiere confirmar el módulo,
pin y polaridad del relé antes de habilitarla físicamente. No incluye Reed switch,
IA local ni frontend.

## Acceso facial O RFID y tres intentos fallidos

Ver [guía rápida para el equipo](docs/RFID_GUIA_RAPIDA.md) y
[instructivo completo RC522](docs/INSTALACION_RFID.md) para cableado,
dependencias, alta/revocación de tarjetas y prueba final. La placa RC522 requiere
3,3 V y SPI0. No se escribe en las tarjetas; las credenciales se vinculan con los
usuarios existentes y se guardan mediante HMAC con una clave local separada.

```bash
python raspberry/runtime_access.py http://192.168.1.95/capture
```

El comando habilita ambos métodos: basta rostro válido **o** tarjeta registrada.
El comando anterior `runtime_recognize_espcam.py` sigue disponible en modo facial.
Se suman globalmente los rechazos de ambos métodos; un acceso válido reinicia el
contador. Se alerta en el tercero, sexto, noveno... incluso dentro del horario
permitido. Una tarjeta/rostro sostenido no genera intentos repetidos: retirarlo
antes de volver a presentar. Las fallas técnicas no cuentan como rechazos.

La alerta horaria se aplica a ambos métodos. Si no se obtiene la fotografía se
envía texto para no perder el aviso. Por seguridad, el runtime comienza con la
puerta en modo simulado. La apertura física se habilita explícitamente cuando
se haya validado el relé; el Reed todavía está pendiente.

## Control de puerta y registros

Sin indicar opciones de relé, una credencial válida muestra la orden pero no
activa GPIO:

```bash
python raspberry/runtime_access.py --methods rfid
```

Los intentos se guardan en `access_events`, incluyendo fecha con zona horaria,
método, usuario pseudonimizado, autorización, horario restringido, alerta y
resultado de puerta. Se pueden consultar y exportar sin frontend:

```bash
python admin/access_report.py --limit 50
python admin/access_report.py --date 2026-10-01 --csv informe.csv
```

El modo físico exige indicar el GPIO en numeración BCM y la polaridad confirmada:

```bash
python raspberry/runtime_access.py --methods rfid \
  --door-mode gpio \
  --relay-pin PIN_BCM_CONFIRMADO \
  --relay-active high \
  --door-open-seconds 3
```

No usar ese comando hasta verificar el módulo. El GPIO entrega 3,3 V; los 5 V
del relé y los 12 V de la cerradura no deben ingresar al GPIO.

## Backend para el frontend

La interfaz no debe acceder directamente a SQLite, GPIO, UID ni embeddings. La
API REST permite trabajar con usuarios y registros mediante JSON:

```bash
python -m pip install -r requirements-api.txt
python -c "import secrets; print(secrets.token_urlsafe(32))"
export SECUREGATE_API_TOKEN="TOKEN_GENERADO"
python raspberry/backend_api.py
```

La documentación interactiva queda en `http://127.0.0.1:8000/docs`. Para usar
otro equipo de la red y configurar CORS, seguir [API_FRONTEND.md](docs/API_FRONTEND.md).
No se expone todavía apertura remota: el GPIO debe tener un único propietario.
La plataforma SBC definida para la solución actual y para una eventual implementación final en laboratorio es **Raspberry Pi 3**.

Para preparar los veinte usuarios del prototipo sin crear credenciales falsas:

```bash
python admin/seed_demo_users.py
```

## Alertas por Telegram fuera de horario

El runtime puede avisar a un chat de Telegram cuando detecta un intento de ingreso en estos horarios:

```text
Lunes a viernes: 21:00 a 05:59
Sábados y domingos: 17:00 a 08:59
```

Cada alerta incluye:

- aviso de ingreso fuera de horario;
- fecha y hora local;
- resultado del reconocimiento;
- fotografía capturada por la ESP-CAM.

La zona horaria predeterminada es `America/Argentina/Buenos_Aires`. Puede cambiarse con `SECUREGATE_TIMEZONE` o con la opción `--timezone`.

### Configuración segura

Crear un bot con `@BotFather`, iniciar una conversación con el bot y definir las variables sólo en la Raspberry Pi:

```bash
export TELEGRAM_BOT_TOKEN="token_del_bot"
export TELEGRAM_CHAT_ID="id_del_chat"
```

El token y el identificador del chat no deben agregarse al repositorio. Si ambas variables faltan, el reconocimiento continúa y muestra que las alertas están deshabilitadas. Si sólo una está definida, el runtime se detiene para advertir la configuración incompleta.

Cada presentación produce un intento. Para evitar alertas horarias repetidas en nuevas presentaciones, se aplica una espera de 60 segundos por método/resultado. No suprime la alerta de tres fallos. Puede ajustarse, por ejemplo:

```bash
python raspberry/runtime_recognize_espcam.py \
  http://192.168.1.95/capture \
  --alert-cooldown 120
```

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
Regla de consenso = 2 de 3 frames
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

Las decisiones del runtime unificado se almacenan en la tabla `access_events`.
El comando `admin/access_report.py` permite obtener un informe por consola o CSV.
La detección avanzada de anomalías y el análisis de eventos continúa
correspondiendo al **GRUPO 3 — Detección de anomalías, alertas, logs e
investigación de IA local**.

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

Recomendación para las 5 fotografías de enrolamiento:

```text
01.jpg → rostro frontal
02.jpg → leve giro hacia la izquierda
03.jpg → leve giro hacia la derecha
04.jpg → frontal con ligera variación de altura/ángulo
05.jpg → frontal con ligera variación de expresión o posición
```

Condiciones recomendadas:

- rostro completo visible;
- buena iluminación;
- evitar perfiles extremos;
- evitar imágenes desenfocadas;
- una sola persona por imagen;
- mantener variaciones moderadas respecto de la posición frontal.

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

Recomendación para las 5 fotografías de enrolamiento:

```text
01.jpg → rostro frontal
02.jpg → leve giro hacia la izquierda
03.jpg → leve giro hacia la derecha
04.jpg → frontal con ligera variación de altura/ángulo
05.jpg → frontal con ligera variación de expresión o posición
```

Condiciones recomendadas:

- rostro completo visible;
- buena iluminación;
- evitar perfiles extremos;
- evitar imágenes desenfocadas;
- una sola persona por imagen;
- mantener variaciones moderadas respecto de la posición frontal.

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

Definición de eventos y comportamientos normales, sospechosos y críticos; generación de alertas; implementación y análisis de logs de accesos y eventos; reglas determinísticas; evaluación de Isolation Forest e investigación sobre necesidad y factibilidad de un LLM local en Raspberry Pi 3. La IA local es opcional y nunca decide apertura.

### GRUPO 4 — Frontend

Desarrollo de la interfaz de usuario de la solución final.

### GRUPO 5 — Integración final sobre Raspberry Pi 3 y RFID

Integración final de los subsistemas sobre Raspberry Pi 3, incluyendo RFID RC522, actuadores, frontend y validación sobre hardware propio. Si posteriormente se instala en el Laboratorio de Mecatrónica, se mantiene Raspberry Pi 3 como SBC objetivo.

## Fuera del alcance del Prototipo v1

- GPIO.
- Relé.
- RFID legacy y autenticación criptográfica de tarjetas (RC522 por UID incluido).
- Reed switch.
- Detección de anomalías.
- Isolation Forest.
- IA local.
- Frontend.
- Integración final de todos los subsistemas sobre Raspberry Pi 3.
