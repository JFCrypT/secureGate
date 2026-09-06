#!/usr/bin/env python3

from pathlib import Path

import cv2
import numpy as np


ROOT_DIR = Path(__file__).resolve().parents[3]
MODEL_DIR = ROOT_DIR / "models"

YUNET_MODEL = MODEL_DIR / "face_detection_yunet_2023mar.onnx"
SFACE_MODEL = MODEL_DIR / "face_recognition_sface_2021dec.onnx"

YUNET_THRESHOLD = 0.7
MAX_IMAGE_DIMENSION = 800


def normalize_image(image, max_dimension=MAX_IMAGE_DIMENSION):
    if image is None:
        raise ValueError("La imagen no puede ser None.")

    height, width = image.shape[:2]
    largest_dimension = max(width, height)

    if largest_dimension <= max_dimension:
        return image

    scale = max_dimension / largest_dimension

    new_width = max(1, int(round(width * scale)))
    new_height = max(1, int(round(height * scale)))

    return cv2.resize(
        image,
        (new_width, new_height),
        interpolation=cv2.INTER_AREA,
    )


def load_image(image_path):
    image = cv2.imread(str(image_path))

    if image is None:
        raise RuntimeError(
            f"No se pudo leer la imagen: {image_path}"
        )

    return normalize_image(image)


def create_recognizer():
    return cv2.FaceRecognizerSF.create(
        str(SFACE_MODEL),
        "",
    )


def extract_embedding_from_image(image, recognizer=None):
    image = normalize_image(image)

    height, width = image.shape[:2]

    detector = cv2.FaceDetectorYN.create(
        str(YUNET_MODEL),
        "",
        (width, height),
        YUNET_THRESHOLD,
        0.3,
        5000,
    )

    _, faces = detector.detect(image)

    if faces is None or len(faces) == 0:
        raise RuntimeError(
            "No se detectó ningún rostro."
        )

    if len(faces) != 1:
        raise RuntimeError(
            f"Se detectaron {len(faces)} rostros; "
            "se requiere exactamente uno."
        )

    if recognizer is None:
        recognizer = create_recognizer()

    aligned = recognizer.alignCrop(
        image,
        faces[0],
    )

    embedding = recognizer.feature(aligned)

    return np.asarray(
        embedding,
        dtype=np.float32,
    ).reshape(-1)


def extract_embedding(image_path, recognizer=None):
    image = load_image(image_path)

    return extract_embedding_from_image(
        image,
        recognizer,
    )
