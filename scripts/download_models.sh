#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODEL_DIR="${ROOT_DIR}/models"

YUNET_FILE="face_detection_yunet_2023mar.onnx"
SFACE_FILE="face_recognition_sface_2021dec.onnx"

YUNET_URL="https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/${YUNET_FILE}"
SFACE_URL="https://github.com/opencv/opencv_zoo/raw/main/models/face_recognition_sface/${SFACE_FILE}"

YUNET_SHA256="8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4"
SFACE_SHA256="0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79"

mkdir -p "${MODEL_DIR}"

echo "[secureGate] Descargando YuNet..."
curl --fail --location \
    "${YUNET_URL}" \
    --output "${MODEL_DIR}/${YUNET_FILE}"

echo "[secureGate] Verificando YuNet..."
echo "${YUNET_SHA256}  ${MODEL_DIR}/${YUNET_FILE}" | sha256sum --check

echo "[secureGate] Descargando SFace..."
curl --fail --location \
    "${SFACE_URL}" \
    --output "${MODEL_DIR}/${SFACE_FILE}"

echo "[secureGate] Verificando SFace..."
echo "${SFACE_SHA256}  ${MODEL_DIR}/${SFACE_FILE}" | sha256sum --check

echo
echo "[secureGate] Modelos descargados y verificados correctamente."
