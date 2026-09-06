# PROTOTIPO V1 — Biometría y ciberseguridad

## Objetivo

Validar un prototipo funcional de control de acceso biométrico con Raspberry Pi 3 y ESP-CAM.

Salida:

```text
[ACCESO] USUARIO VÁLIDO: user_00#
```

o:

```text
[ACCESO] USUARIO NO AUTORIZADO
```

GPIO, relé y cerradura quedan fuera del prototipo.

## Arquitectura

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
└── runtime continuo
        │
        ▼
ESP-CAM
192.168.1.95
/capture
```

## Parámetros

```text
OpenCV = 4.11.0
YuNet threshold = 0.7
Normalización máxima = 800 px
SFace embedding = 128D
Métrica = similitud coseno
Threshold = 0.45
Regla temporal = 2 de 3 frames
```

## Base biométrica

```text
user_001 → 5 templates
user_002 → 5 templates
user_003 → 5 templates
```

Total:

```text
15 templates cifrados
```

## K_bio

```text
local/keys/k_bio
```

- 256 bits.
- Global para la base biométrica.
- Fuera de SQLite.
- Fuera de Git.
- Transferencia manual a Raspberry Pi.

## ESP-CAM

IP:

```text
192.168.1.95
```

Endpoint:

```text
http://192.168.1.95/capture
```

Captura validada:

```text
JPEG 640x480
```

## Runtime

```bash
python raspberry/runtime_recognize_espcam.py \
  http://192.168.1.95/capture
```

El proceso permanece activo hasta `Ctrl+C`.

## Regla 2-de-3

```text
2 o más coincidencias
del mismo usuario
con score >= 0.45
→ USUARIO VÁLIDO

caso contrario
→ USUARIO NO AUTORIZADO
```

## Validación

Offline:

```text
30 comparaciones genuinas
75 impostoras
105 totales

genuino mínimo  = 0.540249
impostor máximo = 0.329046
```

Runtime en vivo con `user_001`:

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

Pendiente para demostración:

```text
user_002
user_003
```

## Despliegue en Raspberry Pi 3

Después de `git pull`, copiar manualmente:

```text
data/db/securegate.db
local/keys/k_bio
```

No se necesitan fotografías.

Luego:

```bash
cd ~/Documents/Proyectos/secureGate
source .venv/bin/activate

python raspberry/runtime_recognize_espcam.py \
  http://192.168.1.95/capture
```

Ese comando inicia el prototipo funcional.

## Fuera del alcance

- RFID.
- GPIO.
- Relé.
- Reed switch.
- Detección de anomalías.
- IA local.
- Frontend.
- Integración final Raspberry Pi 4.
