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
user_004 → 5 templates
```

Total:

```text
20 templates cifrados
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
user_004
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
cd ~/secureGate
source .venv/bin/activate

python raspberry/runtime_recognize_espcam.py \
  http://192.168.1.95/capture
```

Ese comando inicia el prototipo funcional.


## Comandos de operación y mantenimiento

### Enrolar un nuevo usuario — sólo en notebook

Crear la carpeta local:

```text
data/enrollment/user_###/
```

con al menos 5 fotografías y ejecutar:

```bash
cd ~/secureGate

python admin/enroll_user.py \
  user_### \
  data/enrollment/user_###
```

Ejemplo:

```bash
python admin/enroll_user.py \
  user_005 \
  data/enrollment/user_005
```

Verificar:

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

### Transferir la base actualizada a Raspberry Pi

Después de enrolar usuarios, copiar manualmente:

```text
data/db/securegate.db
```

Ejemplo:

```bash
scp data/db/securegate.db \
  usuario@raspberrypi:~/secureGate/data/db/
```

`K_bio` debe existir también en:

```text
local/keys/k_bio
```

y debe ser exactamente la misma clave con la que se cifró la base.

Si la Raspberry ya posee la `K_bio` correcta, no hace falta copiarla otra vez.

Las fotografías de enrolamiento no se transfieren.

### Preparar Raspberry Pi

```bash
cd ~/secureGate
git pull
source .venv/bin/activate
python -m pip install -r requirements.txt
./scripts/download_models.sh
```

### Ejecutar Prototipo v1

```bash
python raspberry/runtime_recognize_espcam.py \
  http://192.168.1.95/capture
```

El runtime queda activo continuamente hasta `Ctrl+C`.

## Fuera del alcance

- RFID.
- GPIO.
- Relé.
- Reed switch.
- Detección de anomalías.
- IA local.
- Frontend.
- Integración final Raspberry Pi 4.
