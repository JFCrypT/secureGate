# PROTOTIPO V1 — Reconocimiento facial seguro sobre Raspberry Pi 3

## Objetivo

Construir un prototipo funcional de control de acceso biométrico utilizando Raspberry Pi 3, ESP-CAM, YuNet, SFace, SQLite, AES-256-GCM y relé.

El prototipo valida únicamente acceso por reconocimiento facial. RFID queda fuera de esta versión y se integrará posteriormente en la Raspberry Pi 4 del sistema real.

## Arquitectura

```text
NOTEBOOK / ADMIN
│
├── fotos de usuarios
├── generación de embeddings
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
├── YuNet
├── SFace
├── runtime de reconocimiento
└── GPIO
     │
     ▼
    RELÉ
```

La Raspberry Pi 3 no necesita fotografías de enrolamiento.

## Enrolamiento offline

Los usuarios se enrolan fuera del sistema de producción.

Convención:

```text
user_001
user_002
user_003
```

Cada usuario dispone inicialmente de 5 capturas:

```text
01.jpg → frontal
02.jpg → leve giro izquierda
03.jpg → leve giro derecha
04.jpg → variación de expresión
05.jpg → variación de iluminación/posición
```

Pipeline:

```text
foto
↓
normalización ≤ 800 px
↓
YuNet
↓
SFace
↓
embedding 128D
↓
AES-256-GCM
↓
SQLite
```

## Datos biométricos

Los embeddings no se almacenan en claro.

`K_bio` es:

- global para la base biométrica;
- de 256 bits;
- interna al sistema;
- independiente de la identidad del usuario;
- almacenada en `local/keys/k_bio`;
- excluida de Git;
- transferida manualmente a Raspberry Pi.

Cada template usa un nonce GCM único.

## Estado de la base

```text
user_001 → 5 templates
user_002 → 5 templates
user_003 → 5 templates
```

Total:

```text
15 templates cifrados
```

## Parámetros congelados

```text
OpenCV = 4.11.0
YuNet = face_detection_yunet_2023mar.onnx
SFace = face_recognition_sface_2021dec.onnx
Embedding = 128 dimensiones
Normalización = lado mayor máximo 800 px
YuNet threshold = 0.7
Métrica SFace = similitud coseno
Threshold SFace = 0.45
```

## Validación multiusuario

```text
3 usuarios
5 imágenes por usuario
15 muestras
30 comparaciones genuinas
75 comparaciones impostoras
105 totales
```

Coseno:

```text
genuino mínimo  = 0.540249
impostor máximo = 0.329046
margen           = 0.211203
```

L2:

```text
genuino máximo  = 0.958907
impostor mínimo = 1.158408
margen           = 0.199501
```

No se observó solapamiento en este conjunto experimental.

Para el prototipo:

```text
cosine threshold = 0.45
```

## Validación del almacenamiento seguro

```text
embedding
→ cifrado
→ SQLite
→ lectura
→ descifrado
→ reconstrucción
```

Resultado:

```text
Ciphertext: 528 bytes
Nonce: 12 bytes
Embedding recuperado: 128D
Igualdad bytes: True
Igualdad arrays: True

PASS
```

## Runtime de identificación

```text
imagen_query
↓
YuNet + SFace
↓
embedding_query
↓
templates cifrados
↓
decrypt temporal
↓
matching
↓
mejor score
↓
threshold 0.45
```

Salida esperada:

```text
[ACCESO] USUARIO VÁLIDO: user_001
```

o:

```text
[ACCESO] USUARIO NO AUTORIZADO
```

Prueba impostora:

```text
score = 0.270803
→ NO AUTORIZADO
```

Prueba genuina independiente de `user_001`:

```text
score = 0.599675
threshold = 0.45
→ USUARIO VÁLIDO
```

## Seguridad

- fotos fuera de Git;
- DB real fuera de Git;
- K_bio fuera de Git;
- embeddings cifrados;
- embeddings no impresos;
- plaintext no persistido;
- pseudonimización de usuarios;
- separación ADMIN / RUNTIME;
- Raspberry sin fotos de enrolamiento.

## Próximo paso inmediato

Integrar ESP-CAM.

```text
usuario frente a ESP-CAM
↓
frame en vivo
↓
Raspberry Pi 3
↓
YuNet + SFace
↓
DB cifrada
↓
print de resultado
```

Salida esperada:

```text
[ACCESO] USUARIO VÁLIDO: user_001
```

Después:

```text
USUARIO VÁLIDO
↓
GPIO
↓
RELÉ
```

## Fuera del alcance de v1

Todavía no se incluye:

- RFID;
- Reed switch;
- anomaly detection;
- Isolation Forest;
- LLM local;
- integración completa con Raspberry Pi 4;
- hardening final;
- logs tamper-evident completos.
