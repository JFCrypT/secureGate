#!/usr/bin/env python3

from pathlib import Path
from time import perf_counter
import argparse
import sys

import cv2
import numpy as np

ROOT_DIR = Path(__file__).resolve().parents[1]
MODEL_DIR = ROOT_DIR / "models"

YUNET_MODEL = MODEL_DIR / "face_detection_yunet_2023mar.onnx"
SFACE_MODEL = MODEL_DIR / "face_recognition_sface_2021dec.onnx"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("image", type=Path)
    args = parser.parse_args()

    image_path = args.image.expanduser().resolve()

    if not image_path.is_file():
        print(f"[ERROR] Imagen no encontrada: {image_path}")
        return 1

    image = cv2.imread(str(image_path))

    if image is None:
        print(f"[ERROR] No se pudo leer: {image_path}")
        return 1

    height, width = image.shape[:2]

    print("[secureGate] Prueba facial sobre imagen estática")
    print(f"[secureGate] OpenCV: {cv2.__version__}")
    print(f"[secureGate] Imagen: {image_path.name}")
    print(f"[secureGate] Resolución: {width}x{height}")

    detector = cv2.FaceDetectorYN.create(
        str(YUNET_MODEL),
        "",
        (width, height),
        0.9,
        0.3,
        5000,
    )

    recognizer = cv2.FaceRecognizerSF.create(
        str(SFACE_MODEL),
        "",
    )

    t0 = perf_counter()
    _, faces = detector.detect(image)
    t1 = perf_counter()

    detection_ms = (t1 - t0) * 1000

    if faces is None or len(faces) == 0:
        print("[RESULTADO] No se detectaron rostros")
        print(f"[TIEMPO] Detección: {detection_ms:.2f} ms")
        return 2

    print(f"[RESULTADO] Rostros detectados: {len(faces)}")
    print(f"[TIEMPO] Detección: {detection_ms:.2f} ms")

    if len(faces) != 1:
        print("[AVISO] La prueba requiere exactamente un rostro.")
        return 3

    face = faces[0]

    t2 = perf_counter()
    aligned = recognizer.alignCrop(image, face)
    t3 = perf_counter()

    embedding = recognizer.feature(aligned)
    t4 = perf_counter()

    embedding = np.asarray(
        embedding,
        dtype=np.float32
    ).reshape(-1)

    print("[OK] Rostro alineado")
    print("[OK] Embedding generado")
    print(f"[INFO] Dimensión embedding: {embedding.size}")
    print(f"[INFO] Norma L2: {np.linalg.norm(embedding):.6f}")

    print(f"[TIEMPO] Alineación: {(t3 - t2) * 1000:.2f} ms")
    print(f"[TIEMPO] Embedding: {(t4 - t3) * 1000:.2f} ms")
    print(f"[TIEMPO] Total pipeline: {(t4 - t0) * 1000:.2f} ms")

    print("[SEGURIDAD] Embedding no mostrado en consola.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
