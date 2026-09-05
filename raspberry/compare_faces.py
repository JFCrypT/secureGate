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


def extract_embedding(image_path, recognizer):
    image = cv2.imread(str(image_path))

    if image is None:
        raise RuntimeError(f"No se pudo leer la imagen: {image_path}")

    height, width = image.shape[:2]

    detector = cv2.FaceDetectorYN.create(
        str(YUNET_MODEL),
        "",
        (width, height),
        0.9,
        0.3,
        5000,
    )

    _, faces = detector.detect(image)

    if faces is None or len(faces) == 0:
        raise RuntimeError(f"No se detectó ningún rostro en: {image_path}")

    if len(faces) != 1:
        raise RuntimeError(
            f"Se detectaron {len(faces)} rostros en {image_path}; "
            "se requiere exactamente uno."
        )

    aligned = recognizer.alignCrop(image, faces[0])
    embedding = recognizer.feature(aligned)

    return np.asarray(
        embedding,
        dtype=np.float32
    ).reshape(1, -1)


def main():
    parser = argparse.ArgumentParser(
        description="Compara dos rostros mediante SFace."
    )

    parser.add_argument("image1", type=Path)
    parser.add_argument("image2", type=Path)

    args = parser.parse_args()

    image1 = args.image1.expanduser().resolve()
    image2 = args.image2.expanduser().resolve()

    if not image1.is_file():
        print(f"[ERROR] Imagen no encontrada: {image1}")
        return 1

    if not image2.is_file():
        print(f"[ERROR] Imagen no encontrada: {image2}")
        return 1

    recognizer = cv2.FaceRecognizerSF.create(
        str(SFACE_MODEL),
        "",
    )

    print("[secureGate] Comparación facial")
    print(f"[IMAGEN 1] {image1.name}")
    print(f"[IMAGEN 2] {image2.name}")

    t0 = perf_counter()

    try:
        embedding1 = extract_embedding(image1, recognizer)
        embedding2 = extract_embedding(image2, recognizer)
    except RuntimeError as exc:
        print(f"[ERROR] {exc}")
        return 2

    t1 = perf_counter()

    cosine_score = recognizer.match(
        embedding1,
        embedding2,
        cv2.FaceRecognizerSF_FR_COSINE,
    )

    l2_score = recognizer.match(
        embedding1,
        embedding2,
        cv2.FaceRecognizerSF_FR_NORM_L2,
    )

    print(f"[INFO] Dimensión embedding: {embedding1.size}")
    print(f"[RESULTADO] Similitud coseno: {cosine_score:.6f}")
    print(f"[RESULTADO] Distancia L2: {l2_score:.6f}")
    print(f"[TIEMPO] Extracción total: {(t1 - t0) * 1000:.2f} ms")
    print("[SEGURIDAD] Embeddings no mostrados en consola.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
