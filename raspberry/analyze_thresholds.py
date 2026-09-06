#!/usr/bin/env python3

from pathlib import Path
from itertools import combinations
import argparse
import sys

import cv2
import numpy as np


ROOT_DIR = Path(__file__).resolve().parents[1]
MODEL_DIR = ROOT_DIR / "models"

YUNET_MODEL = MODEL_DIR / "face_detection_yunet_2023mar.onnx"
SFACE_MODEL = MODEL_DIR / "face_recognition_sface_2021dec.onnx"

VALID_EXTENSIONS = {".jpg", ".jpeg", ".png"}
YUNET_THRESHOLD = 0.7


def extract_embedding(image_path, recognizer):
    image = cv2.imread(str(image_path))

    if image is None:
        raise RuntimeError(f"No se pudo leer {image_path}")

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
            f"No se detectó ningún rostro en {image_path}"
        )

    if len(faces) != 1:
        raise RuntimeError(
            f"Se detectaron {len(faces)} rostros en {image_path}; "
            "se requiere exactamente uno"
        )

    aligned = recognizer.alignCrop(image, faces[0])
    embedding = recognizer.feature(aligned)

    return np.asarray(
        embedding,
        dtype=np.float32,
    ).reshape(1, -1)


def describe(name, values):
    values = np.asarray(values, dtype=np.float64)

    print(f"[{name}] cantidad : {values.size}")
    print(f"[{name}] mínimo   : {values.min():.6f}")
    print(f"[{name}] máximo   : {values.max():.6f}")
    print(f"[{name}] media    : {values.mean():.6f}")
    print(f"[{name}] mediana  : {np.median(values):.6f}")


def main():
    parser = argparse.ArgumentParser(
        description="Analiza scores genuinos e impostores."
    )
    parser.add_argument(
        "directory",
        type=Path,
        help="Directorio raíz de enrolamiento",
    )

    args = parser.parse_args()
    root = args.directory.expanduser().resolve()

    if not root.is_dir():
        print(f"[ERROR] Directorio inexistente: {root}")
        return 1

    recognizer = cv2.FaceRecognizerSF.create(
        str(SFACE_MODEL),
        "",
    )

    samples = []

    person_dirs = sorted(
        path for path in root.iterdir()
        if path.is_dir()
    )

    if len(person_dirs) < 2:
        print("[ERROR] Se requieren al menos dos personas.")
        return 1

    print("[secureGate] Extracción de embeddings")
    print()

    for person_dir in person_dirs:
        images = sorted(
            path
            for path in person_dir.iterdir()
            if path.is_file()
            and path.suffix.lower() in VALID_EXTENSIONS
        )

        if len(images) < 2:
            print(
                f"[ERROR] {person_dir.name} necesita "
                "al menos dos imágenes."
            )
            return 1

        for image_path in images:
            try:
                embedding = extract_embedding(
                    image_path,
                    recognizer,
                )
            except RuntimeError as exc:
                print(f"[ERROR] {exc}")
                return 2

            samples.append(
                (person_dir.name, image_path.name, embedding)
            )

            print(
                f"[OK] {person_dir.name}/{image_path.name}"
            )

    genuine_cosine = []
    impostor_cosine = []

    genuine_l2 = []
    impostor_l2 = []

    print()
    print("[secureGate] Comparaciones")

    for sample1, sample2 in combinations(samples, 2):
        person1, image1, emb1 = sample1
        person2, image2, emb2 = sample2

        cosine = recognizer.match(
            emb1,
            emb2,
            cv2.FaceRecognizerSF_FR_COSINE,
        )

        l2 = recognizer.match(
            emb1,
            emb2,
            cv2.FaceRecognizerSF_FR_NORM_L2,
        )

        if person1 == person2:
            genuine_cosine.append(cosine)
            genuine_l2.append(l2)
        else:
            impostor_cosine.append(cosine)
            impostor_l2.append(l2)

    if not genuine_cosine or not impostor_cosine:
        print("[ERROR] No se obtuvieron ambos tipos de comparación.")
        return 3

    print()
    print("[secureGate] SIMILITUD COSENO")
    print()

    describe("GENUINAS", genuine_cosine)
    print()
    describe("IMPOSTORAS", impostor_cosine)

    print()
    print("[secureGate] DISTANCIA L2")
    print()

    describe("GENUINAS", genuine_l2)
    print()
    describe("IMPOSTORAS", impostor_l2)

    min_genuine_cos = min(genuine_cosine)
    max_impostor_cos = max(impostor_cosine)

    max_genuine_l2 = max(genuine_l2)
    min_impostor_l2 = min(impostor_l2)

    print()
    print("[secureGate] Separación observada")

    print(
        f"[COSENO] genuino mínimo   : "
        f"{min_genuine_cos:.6f}"
    )

    print(
        f"[COSENO] impostor máximo  : "
        f"{max_impostor_cos:.6f}"
    )

    print(
        f"[COSENO] margen observado : "
        f"{min_genuine_cos - max_impostor_cos:.6f}"
    )

    print()

    print(
        f"[L2] genuino máximo       : "
        f"{max_genuine_l2:.6f}"
    )

    print(
        f"[L2] impostor mínimo      : "
        f"{min_impostor_l2:.6f}"
    )

    print(
        f"[L2] margen observado     : "
        f"{min_impostor_l2 - max_genuine_l2:.6f}"
    )

    print()
    print(
        "[IMPORTANTE] Estos resultados no fijan todavía "
        "un threshold de producción."
    )

    print(
        "[SEGURIDAD] Los embeddings permanecieron "
        "únicamente en memoria RAM."
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
