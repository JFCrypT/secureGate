# Prototipo v1

## Objetivo

Validar el pipeline de reconocimiento facial sobre Raspberry Pi 3 utilizando una ESP-CAM como sensor de imagen.

## Pipeline

ESP-CAM
→ Raspberry Pi 3
→ YuNet
→ alineación facial
→ SFace
→ embedding biométrico

## Modelos

- Detector facial: YuNet.
- Reconocimiento / embeddings: SFace.
- Framework: OpenCV DNN.
- Matching previsto: similitud coseno.

## Alcance inicial

Esta primera prueba valida exclusivamente:

- recepción de imagen;
- detección facial;
- landmarks;
- alineación;
- extracción del embedding;
- rendimiento sobre Raspberry Pi 3.

Todavía no incluye:

- enrolamiento persistente;
- SQLite;
- AES-256-GCM;
- gestión de claves;
- relé;
- RFID;
- detección de anomalías;
- LLM.

## Seguridad

Los modelos no se versionan en Git.

Los binarios ONNX se descargan desde OpenCV Zoo y se valida su hash SHA-256 antes de utilizarlos.

No se almacenarán fotografías ni datos biométricos reales en el repositorio.
