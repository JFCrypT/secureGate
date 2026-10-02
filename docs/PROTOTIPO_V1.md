# PROTOTIPO V1 — Registro histórico de biometría y ciberseguridad

## Estado del documento

Este documento conserva la **línea base histórica del Prototipo V1**, correspondiente a la etapa en la que secureGate validó el acceso únicamente por biometría facial sobre Raspberry Pi 3 + ESP32-CAM.

La versión actual del proyecto evolucionó posteriormente e incorpora RFID, Telegram, logs persistentes, API REST, heartbeat y control de puerta en modo simulado/GPIO. El estado general vigente se documenta en `README.md`.

## Objetivo original

Validar un prototipo funcional de control de acceso biométrico con Raspberry Pi 3 y ESP32-CAM.

Salida original:

```text
[ACCESO] USUARIO VÁLIDO: user_00#
```

o:

```text
[ACCESO] USUARIO NO AUTORIZADO
```

En esta etapa V1 no se utilizaban RFID, relé ni cerradura.

## Arquitectura V1

```text
ADMIN / NOTEBOOK
│
├── fotos
├── YuNet
├── SFace
├── embeddings
├── AES-256-GCM
└── securegate.db
        │
        ▼
Raspberry Pi 3
│
├── securegate.db
├── K_bio
├── YuNet/SFace
└── runtime biométrico
        │
        ▼
ESP32-CAM
192.168.1.95
/capture
```

## Pipeline biométrico

```text
imagen
↓
normalización ≤ 800 px
↓
YuNet
↓
detección y alineación
↓
SFace
↓
embedding de 128 componentes
```

Parámetros validados:

```text
OpenCV = 4.11.0
YuNet threshold = 0.7
SFace embedding = 128D
Métrica = similitud coseno
Threshold = 0.45
Regla de consenso = 2 de 3 frames
```

## Base biométrica validada

```text
user_001 → 5 templates
user_002 → 5 templates
user_003 → 5 templates
user_004 → 5 templates
```

Total:

```text
20 templates cifrados activos
```

## Enrolamiento biométrico

El alta se realiza offline en notebook/equipo administrativo:

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

El enrolamiento es incremental.

## Protección de embeddings

Cada imagen produce un embedding de 128 componentes:

```text
[e1, e2, ..., e128]
```

El embedding se serializa y cifra:

```text
embedding 128D
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

```text
local/keys/k_bio
```

Características:

- 256 bits;
- global para la base biométrica;
- fuera de SQLite;
- fuera de Git;
- transferida manualmente a la Raspberry.

Cada template utiliza un nonce GCM único.

Los embeddings cifrados se almacenan en disco. Los embeddings descifrados existen únicamente de forma temporal en RAM durante el matching.

## Reconocimiento en vivo V1

La ESP32-CAM entrega JPEG mediante:

```text
http://192.168.1.95/capture
```

Para cada frame:

```text
JPEG
↓
YuNet
↓
alineación
↓
SFace
↓
embedding_query 128D
↓
comparación 1:N
↓
similitud coseno
```

El `embedding_query` no se almacena en SQLite.

## Regla de consenso 2-de-3

```text
3 frames válidos
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

## Loop de reconocimiento

Conceptualmente:

```text
while True:
    capturar frame
    detectar rostro
    generar embedding_query
    comparar contra templates
    acumular 3 resultados
    aplicar consenso 2-de-3
    imprimir decisión
    continuar
```

La ESP32-CAM permanece activa; no se reinicia después de cada reconocimiento.

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

Resultado validado:

```text
Embedding: 128 dimensiones
Ciphertext: 528 bytes
Nonce: 12 bytes
Igualdad de bytes: True
Igualdad de arrays: True
PASS
```

## Validación biométrica offline

La calibración original del threshold se realizó con tres usuarios:

```text
3 usuarios
5 imágenes por usuario
15 muestras
30 comparaciones genuinas
75 impostoras
105 totales
```

Resultados:

```text
genuino mínimo  = 0.540249
impostor máximo = 0.329046
margen          = 0.211203
```

No se observó solapamiento en ese conjunto experimental.

## Validación en vivo documentada

Ejemplos con `user_001`:

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

Una persona no enrolada fue rechazada consistentemente durante las pruebas documentadas de esta etapa.

## Ejecución histórica del V1

```bash
python raspberry/runtime_recognize_espcam.py \
  http://192.168.1.95/capture
```

Este runtime biométrico continúa disponible por compatibilidad y para pruebas aisladas.

La operación integrada actual utiliza:

```bash
python raspberry/runtime_access.py \
  http://192.168.1.95/capture
```

## Transferencia biométrica

Desde el equipo administrativo se transfieren:

```text
data/db/securegate.db
local/keys/k_bio
```

No se necesitan fotografías de enrolamiento en la Raspberry.

## Evolución posterior al V1

Después de validar este prototipo se incorporaron, sin reemplazar el núcleo biométrico:

- RFID RC522 por SPI;
- protección de UID mediante HMAC-SHA-256;
- `K_rfid` separada de `K_bio`;
- runtime unificado facial OR RFID;
- alertas Telegram;
- registro persistente `access_events`;
- API REST para frontend;
- solicitudes de enrolamiento RFID desde backend;
- heartbeat del runtime;
- control de puerta en modo simulado y driver GPIO configurable;
- tests automatizados.

Estas funcionalidades corresponden a la versión integrada actual y se documentan en `README.md`.

## Alcance que quedó fuera de la etapa V1

En la etapa V1 todavía no se habían implementado:

- RFID;
- control GPIO/relé;
- logs persistentes;
- API REST;
- frontend;
- Reed switch;
- detección avanzada de anomalías;
- IA local;
- integración final sobre Raspberry Pi 4.

Algunas de estas funciones ya están implementadas actualmente; por eso esta sección describe únicamente el alcance histórico del V1.
