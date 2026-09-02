#!/usr/bin/env python3

from pathlib import Path
import sys

import cv2


ROOT_DIR = Path(__file__).resolve().parents[1]
MODEL_DIR = ROOT_DIR / "models"

YUNET_MODEL = MODEL_DIR / "face_detection_yunet_2023mar.onnx"
SFACE_MODEL = MODEL_DIR / "face_recognition_sface_2021dec.onnx"


def main() -> int:
    print("[secureGate] Verificación de modelos faciales")
    print(f"[secureGate] OpenCV: {cv2.__version__}")

    for model in (YUNET_MODEL, SFACE_MODEL):
        if not model.is_file():
            print(f"[ERROR] Modelo no encontrado: {model}")
            return 1

        size_mb = model.stat().st_size / (1024 * 1024)
        print(f"[OK] {model.name}: {size_mb:.2f} MiB")

    try:
        detector = cv2.FaceDetectorYN.create(
            str(YUNET_MODEL),
            "",
            (320, 320),
            0.9,
            0.3,
            5000,
        )
        print("[OK] YuNet inicializado correctamente")
    except Exception as exc:
        print(f"[ERROR] No se pudo inicializar YuNet: {exc}")
        return 1

    try:
        recognizer = cv2.FaceRecognizerSF.create(
            str(SFACE_MODEL),
            "",
        )
        print("[OK] SFace inicializado correctamente")
    except Exception as exc:
        print(f"[ERROR] No se pudo inicializar SFace: {exc}")
        return 1

    if detector is None or recognizer is None:
        print("[ERROR] OpenCV devolvió una instancia inválida")
        return 1

    print("[secureGate] YuNet + SFace disponibles")
    return 0


if __name__ == "__main__":
    sys.exit(main())
