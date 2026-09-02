# Raspberry Pi

Código ejecutado en la Raspberry Pi para el procesamiento y control de secureGate.

## Prototipo v1

Pipeline inicial:

ESP-CAM
→ Raspberry Pi 3
→ YuNet
→ SFace
→ detección facial
→ generación de embedding

En esta primera etapa no se incorporan todavía:

- SQLite;
- cifrado biométrico;
- control del relé;
- detección de anomalías;
- LLM.
