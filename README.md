# secureGate

Sistema de control de acceso seguro para el ingreso al **Laboratorio de Mecatrónica de la Facultad de Ingeniería del Ejército**.

`secureGate` tiene como objetivo evolucionar un sistema de cerradura electrónica existente hacia una arquitectura de control de acceso con mayor nivel de ciberseguridad, incorporando reconocimiento facial, RFID, protección criptográfica de datos sensibles, autenticación de dispositivos, auditoría, detección de anomalías y, eventualmente, inteligencia artificial local.

El proyecto se desarrolla de forma incremental y preservando la compatibilidad con la infraestructura existente.

---

## Estado del proyecto

El proyecto se encuentra actualmente en una primera etapa de implementación experimental.

Se distinguen dos arquitecturas:

1. **Prototipo v1**
   - Raspberry Pi 3.
   - ESP-CAM.
   - Reconocimiento facial.
   - Apertura mediante relé.
   - Sin RFID.

2. **Arquitectura final prevista**
   - Raspberry Pi 4 existente en el laboratorio.
   - Reconocimiento facial.
   - RFID.
   - Acceso por biometría **o** por tarjeta.
   - SQLite.
   - Relé.
   - Cerradura electromagnética.
   - LED.
   - Buzzer.
   - Sensor de estado de puerta.
   - Detección de anomalías.
   - IA local opcional.

El prototipo permite validar progresivamente la arquitectura antes de integrarla al sistema real.

---

## Objetivo general

Diseñar e implementar un sistema de control de acceso físico seguro que combine:

- sistemas embebidos;
- reconocimiento facial;
- RFID;
- criptografía aplicada;
- protección de datos biométricos;
- seguridad de comunicaciones;
- hardening Linux;
- auditoría;
- detección de anomalías;
- inteligencia artificial local.

La arquitectura debe preservar:

- simplicidad;
- compatibilidad;
- auditabilidad;
- ejecución local;
- mínimo privilegio;
- bajo costo.

---

## Restricción de compatibilidad

La futura integración con el sistema del laboratorio deberá preservar la infraestructura legacy.

No se deberán:

- modificar las tarjetas RFID existentes;
- reemitir tarjetas;
- cambiar el padrón de usuarios autorizados;
- requerir reenrolamiento masivo;
- modificar autorizaciones vigentes sin necesidad.

El hardening se implementará sobre la infraestructura existente.

---

## Mecanismos de ingreso de la versión final

La arquitectura final **no utiliza 2FA obligatorio**.

Los mecanismos de ingreso serán independientes:

```text
Reconocimiento facial
        O
Tarjeta RFID
```

Por lo tanto:

```text
biometría válida
→ acceso

O

RFID autorizado
→ acceso
```

La tarjeta podrá utilizarse como mecanismo alternativo cuando el reconocimiento facial no funcione o no esté disponible.

Esto implica que el riesgo de clonación de tarjetas RFID deberá considerarse explícitamente dentro del modelo de amenazas.

---

# Prototipo v1

La primera implementación se realiza sobre una **Raspberry Pi 3** utilizada previamente como plataforma de laboratorio.

El prototipo utiliza exclusivamente reconocimiento facial.

RFID no forma parte de esta primera etapa.

La arquitectura es:

```text
                  ┌────────────────────┐
                  │      ESP-CAM       │
                  │  sensor de imagen  │
                  └─────────┬──────────┘
                            │
                            │ imagen
                            ▼
                  ┌────────────────────┐
                  │   Raspberry Pi 3   │
                  │                    │
                  │ YuNet              │
                  │ SFace              │
                  │ reconocimiento     │
                  │ autorización       │
                  │ SQLite             │
                  │ criptografía       │
                  │ auditoría          │
                  └─────────┬──────────┘
                            │
                           GPIO
                            │
                            ▼
                      ┌──────────┐
                      │   RELÉ   │
                      └────┬─────┘
                           │
                           ▼
                    apertura de puerta
```

La ESP-CAM funciona exclusivamente como sensor óptico/cámara.

Toda la lógica principal reside en la Raspberry Pi 3.

---

# Flujo de trabajo de desarrollo

La estrategia adoptada separa el entorno de desarrollo del hardware objetivo.

```text
NOTEBOOK / XUBUNTU
│
├── desarrollo Python
├── pruebas con imágenes
├── enrolamiento experimental
├── comparación intrausuario
├── comparación interusuario
├── calibración de thresholds
├── análisis estadístico
├── tests
├── documentación
└── git push
        │
        ▼
      GitHub
        │
        ▼
Raspberry Pi 3
│
├── git pull
├── descarga local de modelos
├── validación funcional
├── benchmark ARM
├── ESP-CAM
├── GPIO
├── relé
├── temperatura
├── memoria
└── hardening
```

Regla práctica:

```text
Todo lo que no dependa del hardware
→ notebook

Todo lo que dependa del hardware
→ Raspberry Pi
```

La notebook se utiliza como entorno principal de desarrollo, análisis y calibración.

La Raspberry Pi 3 se utiliza principalmente para validar:

- compatibilidad ARM;
- latencia real;
- consumo de RAM;
- uso de swap;
- CPU;
- temperatura;
- ESP-CAM;
- comunicaciones;
- GPIO;
- relé;
- servicios Linux;
- hardening.

---

# Política de Git y datos locales

El repositorio GitHub es público.

Sólo se versionan:

```text
código
scripts
tests
README
documentación
configuración no secreta
requirements
```

No se versionan:

```text
fotografías
embeddings
bases SQLite reales
claves
secrets
capturas
datos biométricos
modelos descargados
```

El `.gitignore` excluye:

```text
data/
captures/
images/
embeddings/
models/
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

---

## Transferencia manual de fotografías

Las fotografías de enrolamiento y prueba se mantienen localmente.

No se suben a GitHub.

Cuando sea necesario validar el mismo conjunto en la Raspberry Pi 3, las imágenes se transfieren manualmente mediante:

- `scp`;
- pendrive;
- red local;
- otro mecanismo controlado.

Ejemplo:

```bash
scp -r data/enrollment/user_001 \
  jfcrypt@raspberrypi:~/Documents/Proyectos/secureGate/data/enrollment/
```

Estas fotografías siguen siendo archivos locales y continúan excluidas de Git en ambos equipos.

---

## Sincronización de código entre notebook y Raspberry

```text
Notebook
   ↓
desarrollo
   ↓
tests
   ↓
git commit
   ↓
git push
   ↓
GitHub
   ↓
git pull
   ↓
Raspberry Pi 3
```

La Raspberry Pi recibe por Git únicamente código, scripts, tests, documentación y configuración no sensible.

---

# Modelos faciales

Los modelos YuNet y SFace no se versionan.

Cada equipo los reconstruye localmente mediante:

```bash
./scripts/download_models.sh
```

El script descarga los modelos y verifica su integridad mediante SHA-256.

Detector:

```text
YuNet
face_detection_yunet_2023mar.onnx
```

Extractor:

```text
SFace
face_recognition_sface_2021dec.onnx
```

Framework:

```text
OpenCV DNN
```

Versión inicial validada:

```text
OpenCV 4.11.0
```

---

# Pipeline facial

```text
ESP-CAM
   ↓
imagen
   ↓
YuNet
   ↓
detección facial
   ↓
landmarks
   ↓
alineación
   ↓
SFace
   ↓
embedding facial
   ↓
comparación
   ↓
autorización
```

El embedding generado por SFace en el prototipo tiene:

```text
128 dimensiones
```

---

## Threshold de detección de YuNet

El threshold inicial:

```text
score_threshold = 0.9
```

resultó demasiado restrictivo para algunas capturas reales de enrolamiento.

El prototipo utiliza actualmente:

```text
score_threshold = 0.7
```

Este threshold responde únicamente a:

```text
¿hay un rostro detectable?
```

No debe confundirse con el futuro threshold biométrico de SFace:

```text
¿el rostro corresponde a un usuario enrolado?
```

---

# Enrolamiento de usuarios

El sistema no reentrena SFace para cada persona.

Agregar un usuario consiste en realizar un proceso de:

```text
enrolamiento biométrico
```

El método principal final será enrolamiento en vivo mediante ESP-CAM.

Flujo previsto:

```text
usuario
   ↓
ESP-CAM
   ↓
varias capturas
   ↓
YuNet
   ↓
alineación
   ↓
SFace
   ↓
varios embeddings
   ↓
validación
   ↓
cifrado
   ↓
SQLite
```

Inicialmente se prevé obtener aproximadamente:

```text
5 a 10 muestras válidas por usuario
```

con pequeñas variaciones de posición, orientación, expresión e iluminación.

---

## Convención pseudonimizada de usuarios

Para datasets, pruebas y documentación técnica se utiliza una convención neutral:

```text
user_001
user_002
user_003
...
```

Los nombres reales no deben incorporarse a:

- rutas;
- logs técnicos;
- capturas;
- documentación pública;
- datasets de prueba.

Esto separa la identidad real del identificador técnico utilizado durante desarrollo y validación.

---

## Estructura de enrolamiento experimental

```text
data/
└── enrollment/
    ├── user_001/
    │   ├── 01.jpg
    │   ├── 02.jpg
    │   ├── 03.jpg
    │   ├── 04.jpg
    │   └── 05.jpg
    │
    ├── user_002/
    │   └── ...
    │
    └── user_003/
        └── ...
```

Para cada usuario:

```text
01.jpg
→ rostro frontal
→ expresión neutra
→ iluminación normal

02.jpg
→ leve giro hacia la izquierda

03.jpg
→ leve giro hacia la derecha

04.jpg
→ pequeña variación de expresión

05.jpg
→ pequeña variación de iluminación o posición
```

Formatos admitidos:

```text
.jpg
.jpeg
.png
```

`data/` está excluido de Git.

---

## Validación intrausuario inicial

Se realizó una primera prueba con cinco capturas de un mismo usuario.

Se obtuvieron:

```text
10 comparaciones intrausuario
```

Similitud coseno:

```text
mínimo : 0.576052
máximo : 0.819145
media  : 0.685984
```

Distancia L2:

```text
mínimo : 0.601423
máximo : 0.920813
media  : 0.785822
```

Peor caso intrausuario observado:

```text
02.jpg ↔ 04.jpg

coseno = 0.576052
L2     = 0.920813
```

Durante esta etapa:

- los embeddings permanecieron únicamente en RAM;
- no se almacenaron templates biométricos en disco;
- no se definió todavía un threshold operativo de reconocimiento.

---

## Comparación facial inicial

Prueba genuina:

```text
misma persona:
coseno = 0.565232
L2     = 0.932489
```

Prueba impostora:

```text
persona distinta:
coseno = 0.009471
L2     = 1.407501
```

La separación observada valida el funcionamiento básico de SFace.

---

# Análisis de thresholds biométricos

Se implementó:

```text
raspberry/analyze_thresholds.py
```

Su objetivo es procesar múltiples usuarios y separar las comparaciones en:

```text
GENUINAS
→ imágenes del mismo usuario

IMPOSTORAS
→ imágenes de usuarios distintos
```

El script calcula:

- cantidad de comparaciones;
- mínimo;
- máximo;
- media;
- mediana;
- margen observado entre genuinos e impostores;
- resultados mediante similitud coseno;
- resultados mediante distancia L2.

Ejecución prevista:

```bash
python raspberry/analyze_thresholds.py \
  data/enrollment
```

## Estado de la calibración multiusuario

```text
IMPLEMENTACIÓN DEL SCRIPT
→ COMPLETADA

CALIBRACIÓN MULTIUSUARIO
→ PENDIENTE
```

La prueba multiusuario queda pendiente por falta temporal de personas/muestras suficientes.

No se fijará un threshold de producción hasta contar con una cantidad adecuada de comparaciones genuinas e impostoras.

---

# Datos biométricos

Los embeddings faciales son considerados datos sensibles.

No deben almacenarse en claro.

No se utilizará:

```text
SHA-256(embedding)
```

porque dos capturas del mismo rostro no generan necesariamente un embedding idéntico.

La estrategia prevista es:

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

La clave:

```text
K_bio
```

se almacenará fuera de SQLite.

---

# Próximo hito — Secure Biometric Storage

El siguiente bloque de desarrollo es:

```text
P1 — Secure Biometric Storage
```

Objetivo:

```text
embedding
   ↓
serialización
   ↓
AES-256-GCM
   ↓
SQLite
   ↓
lectura
   ↓
descifrado temporal en RAM
   ↓
verificación
```

Decisiones preliminares ya aceptadas:

- AES-256-GCM para protección de embeddings;
- SQLite como almacenamiento;
- `K_bio` fuera de SQLite;
- fotografías no persistentes por defecto;
- embeddings no impresos;
- metadata mínima;
- separación entre datos y secretos.

---

## Esquema lógico mínimo previsto

### users

```text
user_id
identificador
estado
created_at
active
```

### biometric_templates

```text
template_id
user_id
ciphertext
nonce
model_version
algorithm_version
created_at
active
```

El esquema definitivo se congelará antes de implementar la persistencia.

---

## Estrategia preliminar para K_bio

`K_bio` deberá:

- generarse mediante CSPRNG;
- residir fuera de SQLite;
- no versionarse;
- no imprimirse;
- tener permisos restrictivos;
- ser accesible únicamente por el servicio autorizado.

Primera opción a evaluar para el prototipo:

```text
almacenamiento protegido por Linux
```

Evolución futura:

```text
TPM 2.0
Secure Element
```

---

## Round-trip criptográfico obligatorio

La primera prueba de almacenamiento seguro deberá demostrar:

```text
embedding original
      ↓
serialización
      ↓
AES-256-GCM encrypt
      ↓
SQLite
      ↓
lectura
      ↓
AES-256-GCM decrypt
      ↓
embedding recuperado
      ↓
comparación exacta con original
```

Esta prueba debe validar:

- confidencialidad;
- integridad;
- formato;
- persistencia;
- recuperación;
- metadata.

Todavía no implica decisión de apertura de puerta.

---

# Protección de biometría

```text
datos en reposo
→ cifrados

datos en tránsito
→ protegidos

datos en uso
→ plaintext temporal en RAM
```

Los datos biométricos se almacenan cifrados en reposo y sólo se descifran temporalmente en memoria volátil durante el proceso de matching.

Se analizarán:

- minimización de copias;
- archivos temporales;
- swap;
- core dumps;
- zeroization cuando sea viable;
- permisos de proceso;
- mínimo privilegio.

---

# Fotografías

Por defecto, las fotografías originales no se almacenarán permanentemente.

```text
imagen
   ↓
detección
   ↓
embedding
   ↓
descartar imagen
```

Durante desarrollo podrán utilizarse temporalmente para:

- calibración;
- debugging;
- validación;
- pruebas.

---

# Gestión de claves

Las claves previstas incluyen:

```text
K_bio
→ cifrado biométrico

K_rfid
→ protección de UID RFID

K_log
→ integridad de logs

K_device
→ autenticación entre dispositivos
```

Las claves se separarán por función.

No se utilizará una única clave para todo el sistema.

---

# Seguridad ESP-CAM ↔ Raspberry Pi

La comunicación deberá evolucionar hacia un canal:

```text
autenticado
+
íntegro
+
protegido contra replay
+
preferentemente cifrado
```

Alternativas:

- TLS/HTTPS;
- autenticación HMAC por dispositivo;
- TLS + identidad de dispositivo.

---

# Anti-replay

Campos candidatos:

```text
device_id
timestamp
counter
nonce
payload
MAC
```

La Raspberry deberá detectar y rechazar:

- nonces repetidos;
- contadores antiguos;
- timestamps fuera de ventana;
- mensajes alterados;
- dispositivos desconocidos.

---

# Reconocimiento facial y spoofing

El reconocimiento facial no equivale a liveness.

Debe distinguirse entre:

```text
reconocimiento facial
```

y:

```text
presentation attack detection
```

La detección de liveness / anti-spoofing será una etapa posterior.

---

# RFID — versión final

RFID no forma parte del prototipo v1.

En la integración futura:

```text
tarjeta existente
   ↓
UID
   ↓
HMAC-SHA-256(K_rfid, UID)
   ↓
token determinístico
   ↓
SQLite
   ↓
autorización
```

El HMAC protege el UID almacenado, pero no elimina el riesgo de clonación de tarjetas con UID estático.

---

# Logs tamper-evident

Arquitectura prevista:

```text
MAC_0 = valor inicial

MAC_n =
HMAC(
    K_log,
    MAC_(n-1) || canonical(event_n)
)
```

La propiedad buscada es `tamper-evident`.

---

# Detección de anomalías

Arquitectura prevista:

```text
eventos
   │
   ├── reglas determinísticas
   │
   └── Machine Learning
           ↓
    Isolation Forest
```

Isolation Forest es el candidato principal actual.

---

# Inteligencia Artificial local

Un LLM local podrá utilizarse posteriormente para:

- explicar eventos;
- resumir actividad;
- generar reportes;
- responder consultas estructuradas.

El LLM no participará en decisiones de apertura.

---

# Hardening Linux

Se analizarán:

- usuario dedicado;
- mínimo privilegio;
- permisos Unix;
- grupos GPIO;
- autenticación SSH mediante clave;
- deshabilitación de root remoto;
- firewall;
- reducción de servicios;
- actualizaciones;
- journald;
- fail2ban cuando corresponda;
- protección de secretos;
- core dumps;
- swap;
- watchdog;
- systemd sandboxing;
- AppArmor;
- backups.

---

# Sensor de puerta

Se propone incorporar posteriormente un Reed switch para medir:

```text
OPEN
CLOSED
t_open
t_close
duración
```

y detectar aperturas prolongadas.

---

# Arquitectura final prevista

```text
                    ┌─────────────────────┐
                    │       ESP-CAM       │
                    │  sensor de imagen   │
                    │ reconocimiento/capt.│
                    └──────────┬──────────┘
                               │
                         TLS / HMAC
                    nonce / timestamp /
                         sequence
                               │
                               ▼
┌─────────────────┐    ┌─────────────────────────┐
│  LECTOR RFID    │───►│     RASPBERRY PI 4      │
│                 │    │                         │
│ UID existente   │    │ access_service          │
└─────────────────┘    │ security_service        │
                       │ biometric matching      │
┌─────────────────┐    │ SQLite                  │
│ SENSOR REED     │───►│ anomaly_service         │
│ puerta          │    │ LLM opcional            │
└─────────────────┘    └───────────┬─────────────┘
                                   │
                                  GPIO
                                   │
                                   ▼
                           ┌──────────────┐
                           │     RELÉ     │
                           └──────┬───────┘
                                  │
                                  ▼
                           ┌──────────────┐
                           │ ELECTROIMÁN  │
                           │  CERRADURA   │
                           └──────────────┘
```

Salidas adicionales:

```text
LED verde/rojo
Buzzer
```

---

# Storage final previsto

```text
SQLite
│
├── RFID
│   └── HMAC(K_rfid, UID)
│
├── Biometría
│   └── AES-256-GCM(embedding)
│
├── Logs
│   └── HMAC encadenado
│
└── Metadata
```

Claves:

```text
FUERA DE SQLITE
      ↓
almacenamiento protegido
      ↓
eventualmente TPM / Secure Element
```

---

# Arquitectura de software conceptual

```text
Raspberry Pi
│
├── access_service
│   ├── RFID
│   ├── biometría
│   ├── autorización
│   ├── GPIO
│   └── control cerradura
│
├── database_service
│   └── SQLite
│
├── security_service
│   ├── crypto
│   ├── key management
│   ├── anti-replay
│   └── audit
│
├── anomaly_service
│   ├── reglas
│   └── Isolation Forest
│
└── llm_service
    ├── explicación
    ├── resumen
    └── consultas
```

La separación es conceptual y no implica microservicios obligatorios.

---

# Estructura actual

```text
secureGate/
│
├── README.md
├── requirements.txt
│
├── data/
│   └── enrollment/
│       ├── user_001/
│       │   ├── 01.jpg
│       │   ├── 02.jpg
│       │   ├── 03.jpg
│       │   ├── 04.jpg
│       │   └── 05.jpg
│       ├── user_002/
│       └── user_003/
│
├── docs/
│   └── PROTOTIPO_V1.md
│
├── esp32cam/
│   └── README.md
│
├── models/
│   ├── YuNet
│   └── SFace
│
├── raspberry/
│   ├── README.md
│   ├── check_models.py
│   ├── test_image.py
│   ├── compare_faces.py
│   ├── validate_enrollment.py
│   ├── analyze_thresholds.py
│   │
│   └── securegate/
│       └── vision/
│
├── scripts/
│   └── download_models.sh
│
└── tests/
```

`data/` y `models/` se encuentran excluidos de Git.

---

# Pruebas disponibles

## Verificación de modelos

```bash
python raspberry/check_models.py
```

## Imagen estática

```bash
python raspberry/test_image.py \
  data/test/rostro.png
```

## Comparación de rostros

```bash
python raspberry/compare_faces.py \
  data/test/rostro.png \
  data/test/personaA_2.png
```

## Validación de enrolamiento

```bash
python raspberry/validate_enrollment.py \
  data/enrollment/user_001
```

## Análisis multiusuario

```bash
python raspberry/analyze_thresholds.py \
  data/enrollment
```

---

# Estado actual del desarrollo

Actualmente se encuentra validado:

- OpenCV 4.11.0;
- YuNet;
- SFace;
- carga de modelos en Xubuntu;
- carga de modelos en Raspberry Pi 3;
- detección facial;
- alineación;
- embeddings de 128 dimensiones;
- similitud coseno;
- distancia L2;
- validación intrausuario;
- `score_threshold = 0.7` para YuNet;
- script de análisis multiusuario;
- flujo notebook → GitHub → Raspberry Pi;
- transferencia manual de datos biométricos;
- pseudonimización mediante `user_001`, `user_002`, etc.

Pendiente:

- completar dataset multiusuario;
- ejecutar comparaciones genuinas e impostoras a mayor escala;
- calibrar threshold de SFace;
- implementar almacenamiento biométrico seguro;
- integrar ESP-CAM;
- controlar relé;
- incorporar SQLite;
- hardening de comunicaciones;
- logs;
- detección de anomalías;
- IA local.

---

# Próximo paso

El próximo bloque de desarrollo es:

```text
P1 — Secure Biometric Storage
```

Antes de implementar se deberá congelar:

1. esquema SQLite mínimo;
2. representación serializada del embedding;
3. ubicación y permisos de `K_bio`;
4. metadata asociada;
5. procedimiento de round-trip;
6. tratamiento de errores criptográficos;
7. estrategia de rotación futura.

---

# Principios de diseño

```text
SEGURIDAD
+
SIMPLICIDAD
+
AUDITABILIDAD
+
COMPATIBILIDAD
+
BAJO COSTO
+
EJECUCIÓN LOCAL
```

Se evitarán:

- complejidad innecesaria;
- microservicios por moda;
- blockchain;
- criptografía experimental;
- cloud innecesario;
- IA generativa en decisiones críticas.

---

# Uso académico

El proyecto se desarrolla con fines académicos y experimentales asociados al sistema de ingreso al Laboratorio de Mecatrónica de la Facultad de Ingeniería del Ejército.

Las licencias de bibliotecas y modelos de terceros deberán respetarse individualmente.
