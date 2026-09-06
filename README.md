# secureGate

Sistema de control de acceso seguro para el ingreso al **Laboratorio de Mecatrónica de la Facultad de Ingeniería del Ejército**.

`secureGate` evoluciona un sistema de cerradura electrónica existente hacia una arquitectura de control de acceso con mayor nivel de ciberseguridad, incorporando biometría facial, RFID, criptografía aplicada, protección de datos sensibles, auditoría, detección de anomalías y, eventualmente, IA local.

## Estado actual

### Prototipo v1

- Raspberry Pi 3 como hardware objetivo.
- ESP-CAM como sensor óptico.
- Reconocimiento facial con YuNet + SFace.
- Enrolamiento offline en notebook/Xubuntu.
- SQLite para almacenamiento biométrico.
- Embeddings cifrados con AES-256-GCM.
- `K_bio` global para la base biométrica, almacenada fuera de SQLite y fuera de Git.
- Identificación 1:N contra templates cifrados.
- Threshold de reconocimiento del prototipo: `0.45`.
- Apertura mediante relé: siguiente etapa.
- RFID: fuera del prototipo v1; se integrará posteriormente en Raspberry Pi 4.

### Arquitectura final prevista

- Raspberry Pi 4 existente en el laboratorio.
- Acceso por reconocimiento facial **o** RFID.
- SQLite.
- Relé.
- Cerradura electromagnética.
- LED.
- Buzzer.
- Reed switch.
- Detección de anomalías.
- IA local opcional.
- Hardening, gestión de claves, comunicaciones seguras y logs protegidos.

## Flujo de trabajo

```text
NOTEBOOK / XUBUNTU
│
├── desarrollo
├── enrolamiento offline
├── generación de embeddings
├── validación biométrica
├── cifrado AES-256-GCM
├── construcción/actualización de securegate.db
└── git push
        │
        ▼
      GitHub
        │
        ▼
RASPBERRY PI
│
├── git pull
├── modelos locales
├── securegate.db transferida manualmente
├── K_bio transferida manualmente
├── ESP-CAM
├── reconocimiento en vivo
├── GPIO
└── relé
```

Regla práctica:

```text
Todo lo que no dependa del hardware
→ notebook

Todo lo que dependa del hardware
→ Raspberry Pi
```

## Separación ADMIN / RUNTIME

### ADMIN — notebook

El enrolamiento y la incorporación de usuarios se realizan fuera del sistema operativo de la puerta.

```text
fotos
↓
YuNet
↓
SFace
↓
embeddings
↓
validación
↓
AES-256-GCM con K_bio
↓
securegate.db
```

Las fotografías de enrolamiento:

- no se suben a GitHub;
- no se transfieren a Raspberry Pi;
- no forman parte del runtime final;
- pueden descartarse una vez generado el material biométrico requerido.

### RUNTIME — Raspberry Pi

La Raspberry recibe:

```text
securegate.db
K_bio
código
modelos YuNet/SFace
```

No necesita fotografías de enrolamiento.

Durante operación:

```text
ESP-CAM
↓
frame temporal
↓
YuNet
↓
SFace
↓
embedding_query
↓
comparación contra templates cifrados
↓
usuario válido / no autorizado
```

## Política de Git y datos sensibles

El repositorio es público.

Se versionan código, scripts, tests, documentación, requirements y configuración no secreta.

No se versionan:

- fotografías;
- embeddings;
- bases SQLite reales;
- claves;
- secretos;
- capturas;
- modelos descargados.

El `.gitignore` contempla:

```text
data/
captures/
images/
embeddings/
models/
local/
*.db
*.sqlite
*.sqlite3
.env
.env.*
*.key
*.pem
secrets/
config/local/
```

`K_bio` permanece dentro del árbol local del proyecto:

```text
secureGate/local/keys/k_bio
```

pero nunca se sube al repositorio.

## Pipeline facial

```text
imagen
↓
normalización
↓
lado mayor máximo = 800 px
↓
YuNet
↓
detección facial
↓
alineación
↓
SFace
↓
embedding 128D
```

Modelos:

```text
YuNet: face_detection_yunet_2023mar.onnx
SFace: face_recognition_sface_2021dec.onnx
OpenCV: 4.11.0
```

Parámetros congelados para el prototipo:

```text
YuNet score_threshold = 0.7
Normalización máxima = 800 px
Métrica SFace = similitud coseno
Threshold SFace = 0.45
```

## Enrolamiento offline

Convención pseudonimizada:

```text
user_001
user_002
user_003
...
```

Estructura experimental:

```text
data/
└── enrollment/
    ├── user_001/
    │   ├── 01.jpg
    │   ├── 02.jpg
    │   ├── 03.jpg
    │   ├── 04.jpg
    │   └── 05.jpg
    ├── user_002/
    │   └── ...
    └── user_003/
        └── ...
```

Criterio inicial:

```text
01.jpg → frontal, expresión neutra
02.jpg → leve giro izquierda
03.jpg → leve giro derecha
04.jpg → pequeña variación de expresión
05.jpg → pequeña variación de iluminación/posición
```

El enrolamiento es incremental. Un usuario nuevo se agrega sin modificar los anteriores. Un usuario ya enrolado no se sobrescribe automáticamente.

## Base biométrica segura

SQLite contiene:

```text
users
biometric_templates
```

Cada template almacena:

```text
user_id
ciphertext
nonce
model_version
algorithm_version
created_at
active
```

Los embeddings no se almacenan en claro.

```text
embedding
↓
serialización
↓
AES-256-GCM
↓
ciphertext
↓
SQLite
```

### K_bio

- 256 bits.
- Global para todos los templates biométricos de esta instancia.
- No es una clave por usuario.
- No participa en la identificación.
- Protege los embeddings en reposo.
- Está fuera de SQLite.
- Está fuera de Git.
- Se transfiere manualmente a Raspberry Pi.
- Cada template usa un nonce GCM único.

## Validación criptográfica

Round-trip validado:

```text
embedding
→ AES-256-GCM
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

Round-trip AES-256-GCM + SQLite: PASS
```

## Validación biométrica multiusuario

Dataset actual:

```text
3 usuarios
5 imágenes por usuario
15 muestras
30 comparaciones genuinas
75 comparaciones impostoras
105 comparaciones totales
```

### Similitud coseno

```text
GENUINAS
mínimo   : 0.540249
máximo   : 0.915049
media    : 0.737737
mediana  : 0.741141

IMPOSTORAS
mínimo   : -0.039285
máximo   : 0.329046
media    : 0.193046
mediana  : 0.205272
```

Margen observado:

```text
genuino mínimo  = 0.540249
impostor máximo = 0.329046
margen           = 0.211203
```

### Distancia L2

```text
GENUINAS
mínimo   : 0.412192
máximo   : 0.958907
media    : 0.712431
mediana  : 0.719186

IMPOSTORAS
mínimo   : 1.158408
máximo   : 1.441725
media    : 1.268722
mediana  : 1.260736
```

Margen observado:

```text
genuino máximo  = 0.958907
impostor mínimo = 1.158408
margen           = 0.199501
```

No se observó solapamiento entre distribuciones genuina e impostora en este conjunto experimental.

Para el prototipo se congela:

```text
SFace cosine threshold = 0.45
```

Este valor es específico del prototipo de laboratorio.

## Estado de enrolamiento actual

```text
user_001 → 5 templates
user_002 → 5 templates
user_003 → 5 templates
```

Total:

```text
15 templates biométricos activos
```

Todos cifrados con AES-256-GCM.

## Runtime de reconocimiento

Se implementó identificación 1:N contra la base cifrada:

```text
imagen_query
↓
YuNet + SFace
↓
embedding_query
↓
cargar templates activos
↓
descifrar temporalmente con K_bio
↓
comparar por similitud coseno
↓
mejor coincidencia
↓
threshold 0.45
```

Salida:

```text
[ACCESO] USUARIO VÁLIDO: user_00#
```

o:

```text
[ACCESO] USUARIO NO AUTORIZADO
```

Pruebas realizadas:

```text
user_001 → reconocido
user_002 → reconocido
user_003 → reconocido
```

Prueba impostora:

```text
mejor coincidencia: user_003
score: 0.270803
threshold: 0.45

→ USUARIO NO AUTORIZADO
```

Prueba genuina independiente de `user_001` con imagen no usada en enrolamiento:

```text
mejor coincidencia: user_001
score: 0.599675
threshold: 0.45

→ USUARIO VÁLIDO
```

## Scripts actuales

```text
scripts/generate_k_bio.py
raspberry/init_db.py
raspberry/check_models.py
raspberry/test_image.py
raspberry/compare_faces.py
raspberry/validate_enrollment.py
raspberry/analyze_thresholds.py
raspberry/test_secure_storage.py
admin/enroll_user.py
raspberry/runtime_recognize_image.py
raspberry/securegate/vision/pipeline.py
```

## Próximo hito

```text
ESP-CAM
↓
frame en vivo
↓
Raspberry Pi 3
↓
YuNet + SFace
↓
securegate.db + K_bio
↓
user_001 / user_002 / user_003
o
USUARIO NO AUTORIZADO
```

Después:

```text
USUARIO VÁLIDO
↓
GPIO
↓
RELÉ
```

## Arquitectura final prevista

```text
                    ┌─────────────────────┐
                    │       ESP-CAM       │
                    │  sensor de imagen   │
                    └──────────┬──────────┘
                               │
                          canal seguro
                               │
                               ▼
┌─────────────────┐    ┌─────────────────────────┐
│  LECTOR RFID    │───►│     RASPBERRY PI 4      │
│ UID existente   │    │                         │
└─────────────────┘    │ biometría               │
                       │ autorización             │
┌─────────────────┐    │ SQLite                  │
│ SENSOR REED     │───►│ anomalías               │
│ puerta          │    │ IA local opcional       │
└─────────────────┘    └───────────┬─────────────┘
                                   │
                                  GPIO
                                   │
                                   ▼
                              ┌────────┐
                              │  RELÉ  │
                              └───┬────┘
                                  │
                                  ▼
                           cerradura electromagnética
```

En la arquitectura final:

```text
biometría válida
O
RFID autorizado
→ acceso
```

No se trata de 2FA obligatorio.

## Principios de seguridad

- datos biométricos cifrados en reposo;
- plaintext biométrico sólo temporal en RAM;
- no almacenar fotos de enrolamiento en Raspberry;
- no subir biometría ni claves a Git;
- claves separadas por función;
- primitivas criptográficas estándar;
- mínimo privilegio;
- comunicaciones autenticadas;
- anti-replay;
- logs protegidos;
- LLM fuera del camino crítico.

## Uso académico

Proyecto desarrollado con fines académicos y experimentales asociados al sistema de ingreso al Laboratorio de Mecatrónica de la Facultad de Ingeniería del Ejército.
