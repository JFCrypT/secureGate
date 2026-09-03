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

La arquitectura debe preservar simplicidad, compatibilidad, auditabilidad, ejecución local, mínimo privilegio y bajo costo.

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

## Prototipo v1

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

YuNet se utiliza como detector facial.

Modelo inicial:

```text
face_detection_yunet_2023mar.onnx
```

### SFace

SFace se utiliza para generar embeddings faciales.

Modelo inicial:

```text
face_recognition_sface_2021dec.onnx
```

El reconocimiento no compara imágenes directamente: compara el embedding generado durante un intento de acceso con los embeddings previamente enrolados.

---

## Enrolamiento de usuarios

El sistema no reentrena SFace para cada persona. El modelo ya se encuentra entrenado.

El método principal será enrolamiento en vivo mediante ESP-CAM:

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

Inicialmente se prevé obtener aproximadamente **5 a 10 muestras válidas por usuario**, con pequeñas variaciones de posición, orientación, expresión e iluminación.

Las fotografías existentes podrán utilizarse posteriormente para migración, pruebas o recuperación, pero no constituyen el método preferido de enrolamiento.

---

## Datos biométricos

Los embeddings faciales son considerados datos sensibles y no deben almacenarse en claro.

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

La clave `K_bio` se almacenará fuera de SQLite.

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

Podrán utilizarse temporalmente durante desarrollo, calibración, debugging y pruebas.

---

## Base de datos

Se utilizará SQLite.

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

Ejemplos conceptuales:

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

## Gestión de claves

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

La primera implementación podrá utilizar almacenamiento protegido por Linux. Posteriormente se evaluarán TPM 2.0 y Secure Element.

---

## Seguridad ESP-CAM ↔ Raspberry Pi

No se confiará únicamente en IP conocida y LAN local.

La comunicación deberá evolucionar hacia un canal autenticado, íntegro, protegido contra replay y preferentemente cifrado.

Alternativas a evaluar:

- TLS/HTTPS;
- autenticación HMAC por dispositivo;
- TLS + identidad de dispositivo.

HMAC por sí solo proporciona autenticación e integridad, pero no confidencialidad.

---

## Anti-replay

Se prevé utilizar campos como:

```text
device_id
timestamp
counter
nonce
payload
MAC
```

La Raspberry deberá detectar y rechazar nonces repetidos, contadores antiguos, timestamps fuera de ventana, mensajes alterados y dispositivos desconocidos.

---

## Reconocimiento facial y spoofing

Reconocer una identidad no equivale a demostrar presencia física real.

Debe distinguirse entre reconocimiento facial y presentation attack detection.

Un atacante podría intentar utilizar:

- fotografía;
- pantalla;
- video;
- máscara.

La detección de liveness / anti-spoofing será una etapa posterior.

---

## RFID — versión final

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

Este mecanismo protege el UID almacenado, pero no evita por sí mismo la clonación de tarjetas con UID estático.

---

## Logs tamper-evident

Se prevé implementar integridad verificable de logs mediante una cadena HMAC:

```text
MAC_0 = valor inicial

MAC_n =
HMAC(
    K_log,
    MAC_(n-1) || canonical(event_n)
)
```

La propiedad buscada es `tamper-evident`, no `tamper-proof`.

---

## Detección de anomalías

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

## Reglas de seguridad

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

## Inteligencia Artificial local

Un LLM local podrá utilizarse posteriormente para explicar eventos, resumir actividad, generar reportes y responder consultas sobre datos previamente estructurados.

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

La cerradura deberá seguir funcionando aunque el LLM o el detector ML estén fuera de servicio.

---

## Hardening Linux

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

## Seguridad de credenciales

Las credenciales administrativas nunca deberán almacenarse en documentación o código.

Si existe autenticación mediante contraseña:

```text
NO:
AES(password)

SÍ:
Argon2id(password)
```

Alternativas posibles: scrypt y bcrypt.

---

## Sensor de puerta

Se propone incorporar posteriormente un Reed switch para medir el estado físico real de la puerta.

```text
imán próximo
→ CLOSED

imán alejado
→ OPEN
```

Permitirá registrar `t_open`, `t_close`, duración y detectar una puerta abierta demasiado tiempo.

---

## Arquitectura final prevista

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

## Storage final previsto

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

## Arquitectura de software conceptual

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

## Concurrencia

Una tarea lenta no debe bloquear lectura de sensores, reconocimiento, decisión de acceso, GPIO, relé ni buzzer.

Se evaluarán:

- threading;
- multiprocessing;
- asyncio;
- procesos independientes;
- colas;
- systemd.

---

## Fail-safe y fail-secure

Deberá analizarse el comportamiento ante reboot, caída de cámara, caída de RFID, fallo de SQLite, ausencia de clave, fallo de ML, fallo de LLM, pérdida de Wi-Fi y corte de energía.

La decisión `fail-safe` vs. `fail-secure` dependerá también de seguridad física, evacuación y normativa institucional.

---

## Seguridad física

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

## Criptografía

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

## Modelos faciales

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

Versión inicial:

```text
OpenCV 4.11.0
```

---

## Modelos no versionados

Los modelos ONNX no se incluyen en Git.

Se descargan mediante:

```bash
./scripts/download_models.sh
```

El script verifica su integridad mediante SHA-256.

---

## Estructura actual

```text
secureGate/
│
├── README.md
├── requirements.txt
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
│   │
│   └── securegate/
│       └── vision/
│
├── scripts/
│   └── download_models.sh
│
└── tests/
```

`models/` se encuentra excluido de Git.

---

## Instalación inicial

```bash
python3 -m venv .venv
source .venv/bin/activate

python -m pip install --upgrade pip
python -m pip install -r requirements.txt

./scripts/download_models.sh

python raspberry/check_models.py
```

Salida esperada:

```text
[OK] YuNet inicializado correctamente
[OK] SFace inicializado correctamente
[secureGate] YuNet + SFace disponibles
```

---

## Seguridad del repositorio

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

## Fases generales

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

## Principios de diseño

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

Se evitarán complejidad innecesaria, microservicios por moda, blockchain, criptografía experimental, cloud innecesario e IA generativa en decisiones críticas.

---

## Flujo conceptual final

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

## Estado actual del desarrollo

Actualmente se encuentra validado en el entorno de desarrollo Xubuntu:

```text
OpenCV 4.11.0
+
YuNet
+
SFace
```

Los modelos:

```text
face_detection_yunet_2023mar.onnx
face_recognition_sface_2021dec.onnx
```

se cargan correctamente.

El siguiente hito es validar el mismo pipeline sobre Raspberry Pi 3 y posteriormente realizar:

```text
imagen estática
→ detección
→ alineación
→ embedding
→ benchmark
```

antes de conectar la ESP-CAM.

---

## Uso académico

El proyecto se desarrolla con fines académicos y experimentales asociados al sistema de ingreso al Laboratorio de Mecatrónica de la Facultad de Ingeniería del Ejército.

Las licencias de bibliotecas y modelos de terceros deberán respetarse individualmente.
