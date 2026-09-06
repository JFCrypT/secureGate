#!/usr/bin/env python3

from pathlib import Path
from itertools import combinations
from time import perf_counter
import argparse
import sys

import cv2
import numpy as np


ROOT_DIR = Path(__file__).resolve().parents[1]
MODEL_DIR = ROOT_DIR / "models"

YUNET_MODEL = MODEL_DIR / "face_detection_yunet_2023mar.onnx"
SFACE_MODEL = MODEL_DIR / "face_recognition_sface_2021dec.onnx"

VALID_EXTENSIONS = {".jpg", ".jpeg", ".png"}


def extract_embedding(image_path, recognizer):
    image = cv2.imread(str(image_path))

    if image is None:
        raise RuntimeError(f"No se pudo leer {image_path.name}")

    height, width = image.shape[:2]

    detector = cv2.FaceDetectorYN.create(
        str(YUNET_MODEL),
        "",
        (width, height),
        0.7,
        0.3,
        5000,
    )

    _, faces = detector.detect(image)

    if faces is None or len(faces) == 0:
        raise RuntimeError(
            f"No se detectó ningún rostro en {image_path.name}"
        )

    if len(faces) != 1:
        raise RuntimeError(
            f"Se detectaron {len(faces)} rostros en "
            f"{image_path.name}; se requiere exactamente uno"
        )

    aligned = recognizer.alignCrop(image, faces[0])
    embedding = recognizer.feature(aligned)

    return np.asarray(
        embedding,
        dtype=np.float32,
    ).reshape(1, -1)


def main():
    parser = argparse.ArgumentParser(
        description="Valida un conjunto de capturas para enrolamiento."
    )
    parser.add_argument(
        "directory",
        type=Path,
        help="Directorio con imágenes de una misma persona",
    )

    args = parser.parse_args()

    directory = args.directory.expanduser().resolve()

    if not directory.is_dir():
        print(f"[ERROR] Directorio inexistente: {directory}")
        return 1

    images = sorted(
        path
        for path in directory.iterdir()
        if path.is_file()
        and path.suffix.lower() in VALID_EXTENSIONS
    )

    if len(images) < 5:
        print(
            "[ERROR] Se requieren al menos 5 imágenes "
            "para esta prueba de enrolamiento."
        )
        return 1

    recognizer = cv2.FaceRecognizerSF.create(
        str(SFACE_MODEL),
        "",
    )

    print("[secureGate] Validación de enrolamiento")
    print(f"[INFO] Directorio: {directory}")
    print(f"[INFO] Imágenes encontradas: {len(images)}")
    print()

    embeddings = []

    start = perf_counter()

    for index, image_path in enumerate(images, start=1):
        try:
            embedding = extract_embedding(
                image_path,
                recognizer,
            )
        except RuntimeError as exc:
            print(f"[ERROR] {exc}")
            return 2

        embeddings.append(
            (image_path.name, embedding)
        )

        print(
            f"[OK] {index:02d}/{len(images):02d} "
            f"{image_path.name}"
        )

    extraction_end = perf_counter()

    cosine_scores = []
    l2_scores = []

    print()
    print("[secureGate] Comparaciones intrausuario")

    for (name1, emb1), (name2, emb2) in combinations(
        embeddings,
        2,
    ):
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

        cosine_scores.append(cosine)
        l2_scores.append(l2)

        print(
            f"{name1} <-> {name2} | "
            f"cos={cosine:.6f} | "
            f"L2={l2:.6f}"
        )

    end = perf_counter()

    cosine_scores = np.asarray(cosine_scores)
    l2_scores = np.asarray(l2_scores)

    print()
    print("[secureGate] Resumen intrausuario")

    print(
        f"[COSENO] mínimo : "
        f"{cosine_scores.min():.6f}"
    )
    print(
        f"[COSENO] máximo : "
        f"{cosine_scores.max():.6f}"
    )
    print(
        f"[COSENO] media  : "
        f"{cosine_scores.mean():.6f}"
    )

    print(
        f"[L2] mínimo     : "
        f"{l2_scores.min():.6f}"
    )
    print(
        f"[L2] máximo     : "
        f"{l2_scores.max():.6f}"
    )
    print(
        f"[L2] media      : "
        f"{l2_scores.mean():.6f}"
    )

    print()
    print(
        f"[TIEMPO] Extracción: "
        f"{(extraction_end - start) * 1000:.2f} ms"
    )
    print(
        f"[TIEMPO] Total: "
        f"{(end - start) * 1000:.2f} ms"
    )

    print()
    print(
        "[SEGURIDAD] Los embeddings permanecieron "
        "únicamente en memoria RAM."
    )
    print(
        "[SEGURIDAD] No se almacenaron templates "
        "biométricos en disco."
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
