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

El proyecto utiliza una separación explícita entre:

- entorno de desarrollo y análisis;
- repositorio Git;
- hardware objetivo.

La estrategia adoptada es:

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
├── generación de resultados
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

La notebook se utiliza como entorno principal de desarrollo porque permite:

- iterar más rápido;
- procesar datasets más grandes;
- realizar comparaciones masivas;
- calcular métricas;
- generar gráficos;
- calibrar thresholds;
- ejecutar tests;
- documentar cambios.

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

Por lo tanto, sólo se versionan:

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

La notebook mantiene, por ejemplo:

```text
data/
└── enrollment/
    └── personaA/
        ├── 01.jpg
        ├── 02.jpg
        ├── 03.jpg
        ├── 04.jpg
        └── 05.jpg
```

Cuando sea necesario validar el mismo conjunto en la Raspberry Pi 3, las imágenes se transfieren manualmente mediante:

- `scp`;
- pendrive;
- red local;
- otro mecanismo controlado.

Ejemplo conceptual:

```bash
scp -r data/enrollment/personaA \
  jfcrypt@raspberrypi:~/Documents/Proyectos/secureGate/data/enrollment/
```

Estas fotografías siguen siendo archivos locales y continúan excluidas de Git en ambos equipos.

---

## Sincronización de código entre notebook y Raspberry

El flujo normal de trabajo es:

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

La Raspberry Pi recibe por Git únicamente:

- código;
- scripts;
- tests;
- README;
- documentación;
- archivos de configuración no sensibles.

Los datos biométricos no forman parte de este flujo.

---

## Modelos faciales

Los modelos YuNet y SFace tampoco se versionan.

Cada equipo los reconstruye localmente mediante:

```bash
./scripts/download_models.sh
```

El script:

- descarga los modelos;
- verifica integridad con SHA-256;
- evita depender de binarios versionados en el repositorio.

---

## Pipeline facial

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

### YuNet

Modelo utilizado:

```text
face_detection_yunet_2023mar.onnx
```

Funciones:

- localizar rostros;
- obtener landmarks;
- permitir alineación;
- preparar la entrada para reconocimiento.

### SFace

Modelo utilizado:

```text
face_recognition_sface_2021dec.onnx
```

El embedding generado en el prototipo tiene:

```text
128 dimensiones
```

El reconocimiento no compara imágenes directamente.

Compara embeddings faciales.

---

## Threshold de detección de YuNet

El threshold inicial era:

```text
score_threshold = 0.9
```

Ese valor resultó demasiado restrictivo para capturas reales de enrolamiento.

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

El modelo ya viene entrenado.

Agregar un usuario consiste en un proceso de:

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

con pequeñas variaciones de:

- posición;
- orientación;
- expresión;
- iluminación.

---

## Estructura de enrolamiento experimental

Durante las pruebas iniciales se utiliza:

```text
data/
└── enrollment/
    └── personaA/
        ├── 01.jpg
        ├── 02.jpg
        ├── 03.jpg
        ├── 04.jpg
        └── 05.jpg
```

Las capturas representan:

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

No se requieren poses extremas.

El objetivo es representar variaciones naturales que una persona puede presentar al acercarse al sistema.

Formatos admitidos:

```text
.jpg
.jpeg
.png
```

---

## Uso de fotografías durante el desarrollo

Las fotografías actuales son material experimental.

Se utilizan para:

- validar YuNet;
- validar SFace;
- medir similitud intrausuario;
- medir similitud interusuario;
- calibrar thresholds;
- probar robustez.

Estas imágenes:

```text
NO se versionan
NO se suben a GitHub
NO forman parte del repositorio público
```

En producción, el objetivo es que el enrolamiento en vivo genere embeddings y que las imágenes se descarten después del procesamiento, salvo necesidad específica y aprobada.

---

## Validación intrausuario inicial

Se realizó una primera prueba con cinco capturas de una misma persona.

Se obtuvieron:

```text
10 comparaciones intrausuario
```

Resultados de similitud coseno:

```text
mínimo : 0.576052
máximo : 0.819145
media  : 0.685984
```

Resultados de distancia L2:

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

Sin embargo, estos casos aislados no son suficientes para fijar el threshold operativo.

El siguiente paso es obtener distribuciones interusuario con más personas y más muestras.

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

## Protección de biometría

```text
datos en reposo
→ cifrados

datos en tránsito
→ protegidos

datos en uso
→ plaintext temporal en RAM
```

Formulación del proyecto:

> Los datos biométricos se almacenan cifrados en reposo y sólo se descifran temporalmente en memoria volátil durante el proceso de matching.

Se analizarán:

- minimización de copias;
- archivos temporales;
- swap;
- core dumps;
- zeroization cuando sea viable;
- permisos de proceso;
- mínimo privilegio.

---

## Fotografías

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

Podrán utilizarse temporalmente durante:

- desarrollo;
- calibración;
- debugging;
- pruebas.

---

# Base de datos

Se utilizará SQLite.

Arquitectura lógica prevista:

```text
SQLite
│
├── users
│
├── biometric_templates
│
├── access_events
└── security_events
```

### users

```text
user_id
identificador
estado
fecha_alta
activo
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

### access_events

```text
timestamp
user_id
resultado
distancia
score
motivo
```

### security_events

```text
timestamp
tipo
severidad
metadata
```

---

# Gestión de claves

Los secretos criptográficos no deben almacenarse dentro de SQLite.

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

La primera implementación podrá utilizar almacenamiento protegido por Linux.

Posteriormente se evaluarán:

- TPM 2.0;
- Secure Element;
- almacenamiento respaldado por hardware.

---

# Seguridad ESP-CAM ↔ Raspberry Pi

No se confiará únicamente en IP conocida y LAN local.

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

Alternativas a evaluar:

- TLS/HTTPS;
- autenticación HMAC por dispositivo;
- TLS + identidad de dispositivo.

HMAC por sí solo proporciona autenticación e integridad, pero no confidencialidad.

---

# Anti-replay

Se prevé utilizar:

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

Reconocer una identidad no equivale a demostrar presencia física real.

Debe distinguirse:

```text
reconocimiento facial
```

de:

```text
presentation attack detection
```

Un atacante podría intentar utilizar:

- fotografía;
- pantalla;
- video;
- máscara.

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

Este mecanismo protege el UID almacenado.

No evita por sí mismo la clonación de tarjetas con UID estático.

Ese riesgo se documentará como riesgo residual.

---

# Logs tamper-evident

Se prevé implementar:

```text
MAC_0 = valor inicial

MAC_n =
HMAC(
    K_log,
    MAC_(n-1) || canonical(event_n)
)
```

La propiedad buscada es:

```text
tamper-evident
```

y no:

```text
tamper-proof
```

---

# Detección de anomalías

No se utilizará un LLM como detector primario.

```text
eventos
   │
   ├── reglas determinísticas
   │
   └── Machine Learning
           ↓
    Isolation Forest
```

Isolation Forest es actualmente el candidato principal.

---

# Reglas de seguridad

Ejemplos:

```text
N intentos fallidos
→ alerta

MAC inválido
→ rechazo

nonce repetido
→ rechazo

dispositivo desconocido
→ rechazo

puerta abierta demasiado tiempo
→ alerta
```

Las reglas determinísticas tendrán prioridad sobre cualquier modelo ML.

---

# Inteligencia Artificial local

Un LLM local podrá utilizarse posteriormente para:

- explicar eventos;
- resumir actividad;
- generar reportes;
- responder consultas estructuradas.

El LLM no participará en decisiones de apertura.

```text
sensor
↓
autenticación
↓
autorización
↓
actuación
↓
registro
↓
detección de anomalías
↓
interpretación IA
```

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
- backups;
- filesystem de sólo lectura donde resulte viable.

---

# Seguridad de credenciales

Las credenciales administrativas nunca deberán almacenarse en documentación o código.

Si existe autenticación mediante contraseña:

```text
NO:
AES(password)

SÍ:
Argon2id(password)
```

Alternativas posibles:

- scrypt;
- bcrypt.

---

# Sensor de puerta

Se propone incorporar posteriormente un:

```text
Reed switch
```

para medir el estado físico real de la puerta.

```text
imán próximo
→ CLOSED

imán alejado
→ OPEN
```

Permitirá registrar:

```text
t_open
t_close
duración
```

y detectar:

```text
puerta abierta demasiado tiempo
```

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

Esta separación es conceptual. No implica necesariamente utilizar microservicios.

---

# Concurrencia

Una tarea lenta no debe bloquear:

- lectura de sensores;
- reconocimiento;
- decisión de acceso;
- GPIO;
- relé;
- buzzer.

Se evaluarán:

- threading;
- multiprocessing;
- asyncio;
- procesos independientes;
- colas;
- systemd.

---

# Fail-safe y fail-secure

Deberá analizarse el comportamiento ante:

- reboot;
- caída de cámara;
- caída de RFID;
- fallo de SQLite;
- ausencia de clave;
- fallo de ML;
- fallo de LLM;
- pérdida de Wi-Fi;
- corte de energía.

La decisión:

```text
fail-safe
vs.
fail-secure
```

dependerá también de:

- seguridad física;
- evacuación;
- normativa institucional.

---

# Seguridad física

El proyecto también considerará:

- acceso físico a Raspberry;
- extracción de SD;
- USB;
- relé;
- cableado;
- cerradura;
- GPIO;
- reset;
- alimentación;
- manipulación de sensores;
- extracción de firmware.

---

# Criptografía

Se utilizarán exclusivamente primitivas estándar y bibliotecas maduras.

- Cifrado autenticado: AES-GCM.
- Alternativa evaluable: ChaCha20-Poly1305.
- HMAC: HMAC-SHA-256.
- KDF: HKDF.
- Password hashing: Argon2id.
- Aleatoriedad: CSPRNG del sistema operativo.

No utilizar:

- AES-ECB;
- criptografía propia;
- claves hardcodeadas;
- reutilización de nonces GCM;
- PRNG no criptográfico;
- secretos versionados.

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
│       └── personaA/
│           ├── 01.jpg
│           ├── 02.jpg
│           ├── 03.jpg
│           ├── 04.jpg
│           └── 05.jpg
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

# Instalación inicial

```bash
python3 -m venv .venv
source .venv/bin/activate

python -m pip install --upgrade pip
python -m pip install -r requirements.txt

./scripts/download_models.sh

python raspberry/check_models.py
```

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
  data/enrollment/personaA
```

---

# Seguridad del repositorio

Este repositorio es público.

No se deben versionar:

- contraseñas;
- claves SSH;
- claves AES;
- claves HMAC;
- Wi-Fi;
- `.env`;
- bases SQLite reales;
- embeddings;
- fotografías;
- capturas;
- información biométrica;
- certificados privados;
- tokens;
- secretos.

---

# Fases generales

1. Inventario y arquitectura.
2. Threat Model.
3. Arquitectura de seguridad.
4. Plan de migración.
5. PoC.
6. Testing.
7. Integración con Raspberry Pi 4.
8. Detección de anomalías.
9. IA local.
10. Hardening final.
11. Documentación.

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

# Flujo conceptual final

```text
SENSORES
   ↓
AUTENTICACIÓN
   ↓
AUTORIZACIÓN
   ↓
ACTUACIÓN
   ↓
AUDITORÍA
   ↓
DETECCIÓN DE ANOMALÍAS
   ↓
INTERPRETACIÓN IA
```

Transversalmente:

```text
CRIPTOGRAFÍA
+
GESTIÓN DE CLAVES
+
HARDENING
+
MONITOREO
```

---

# Estado actual del desarrollo

Actualmente se encuentra validado:

```text
OpenCV 4.11.0
+
YuNet
+
SFace
```

en Xubuntu y en Raspberry Pi 3.

También se encuentra validado:

- carga de YuNet;
- carga de SFace;
- detección de rostro;
- alineación;
- generación de embedding de 128 dimensiones;
- comparación mediante similitud coseno;
- comparación mediante distancia L2;
- validación intrausuario con cinco capturas;
- ajuste de YuNet a `score_threshold = 0.7`;
- separación entre entorno de desarrollo y hardware objetivo;
- transferencia manual de datos biométricos fuera de Git.

El siguiente hito es obtener distribuciones interusuario para comenzar a determinar el threshold operativo de SFace.

---

# Uso académico

El proyecto se desarrolla con fines académicos y experimentales asociados al sistema de ingreso al Laboratorio de Mecatrónica de la Facultad de Ingeniería del Ejército.

Las licencias de bibliotecas y modelos de terceros deberán respetarse individualmente.
