#!/usr/bin/env bash

set -e

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FRONT_DIR="$ROOT_DIR/frontend"
LOG_DIR="$ROOT_DIR/local/logs"

BACKEND_PY="$ROOT_DIR/.venv/bin/python"
FRONT_UVICORN="$FRONT_DIR/.venv/bin/uvicorn"
FRONT_ENV="$FRONT_DIR/.env"

ESP_CAM_URL="http://192.168.1.95/capture"

mkdir -p "$LOG_DIR"

SECUREGATE_ENV="$ROOT_DIR/local/securegate.env"

# Configuración local privada: Telegram y futuras variables del runtime.
if [ -f "$SECUREGATE_ENV" ]; then
    set -a
    source "$SECUREGATE_ENV"
    set +a
    echo "[OK] Configuración local cargada."
else
    echo "[ADVERTENCIA] No existe local/securegate.env; Telegram quedará deshabilitado."
fi


[ -x "$BACKEND_PY" ] || {
    echo "[ERROR] No existe $BACKEND_PY"
    exit 1
}

[ -x "$FRONT_UVICORN" ] || {
    echo "[ERROR] No existe $FRONT_UVICORN"
    exit 1
}

[ -f "$FRONT_ENV" ] || {
    echo "[ERROR] No existe $FRONT_ENV"
    exit 1
}

SECUREGATE_API_TOKEN="$(sed -n 's/^SECUREGATE_API_TOKEN=//p' "$FRONT_ENV" | head -n 1)"

[ -n "$SECUREGATE_API_TOKEN" ] || {
    echo "[ERROR] SECUREGATE_API_TOKEN no está configurado."
    exit 1
}

export SECUREGATE_API_TOKEN

# ============================================================
# 1. Runtime principal: biometría OR RFID
# ============================================================

cd "$ROOT_DIR"

nohup "$BACKEND_PY" raspberry/runtime_access.py \
    "$ESP_CAM_URL" \
    --methods both \
    --door-mode simulate \
    > "$LOG_DIR/runtime.log" 2>&1 &

echo $! > "$LOG_DIR/runtime.pid"

# ============================================================
# 2. Backend API
# ============================================================

nohup "$BACKEND_PY" raspberry/backend_api.py \
    > "$LOG_DIR/backend.log" 2>&1 &

echo $! > "$LOG_DIR/backend.pid"

sleep 3

# ============================================================
# 3. Frontend
# ============================================================

cd "$FRONT_DIR"

nohup "$FRONT_UVICORN" app.main:app \
    --host 0.0.0.0 \
    --port 8080 \
    > "$LOG_DIR/frontend.log" 2>&1 &

echo $! > "$LOG_DIR/frontend.pid"

echo "[OK] secureGate iniciado"
echo "[OK] Runtime: biometría OR RFID"
echo "[OK] Backend API: 127.0.0.1:8000"
echo "[OK] Frontend: 0.0.0.0:8080"
