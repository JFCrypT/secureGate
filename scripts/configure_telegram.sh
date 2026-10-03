#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$ROOT_DIR/local/securegate.env"

mkdir -p "$ROOT_DIR/local"

echo "[secureGate] Configuración de Telegram"
echo

read -r -s -p "TELEGRAM_BOT_TOKEN: " TOKEN
echo

echo "[INFO] Verificando bot..."

BOT_INFO="$(curl -fsS "https://api.telegram.org/bot${TOKEN}/getMe")"

BOT_NAME="$(
    printf '%s' "$BOT_INFO" |
    python -c 'import sys,json; d=json.load(sys.stdin); print(d["result"]["username"] if d.get("ok") else "")'
)"

if [ -z "$BOT_NAME" ]; then
    echo "[ERROR] Token inválido."
    exit 1
fi

echo "[OK] Bot verificado: @$BOT_NAME"
echo
echo "Abrí Telegram y enviá un mensaje a @$BOT_NAME"
echo "por ejemplo: hola"
echo
read -r -p "Cuando lo hayas enviado, presioná ENTER..."

UPDATES="$(curl -fsS "https://api.telegram.org/bot${TOKEN}/getUpdates")"

CHAT_ID="$(
    printf '%s' "$UPDATES" |
    python -c '
import sys,json
d=json.load(sys.stdin)
ids=[]
for u in d.get("result", []):
    for key in ("message","edited_message","channel_post","edited_channel_post"):
        m=u.get(key)
        if m and m.get("chat", {}).get("id") is not None:
            ids.append(str(m["chat"]["id"]))
print(ids[-1] if ids else "")
'
)"

if [ -z "$CHAT_ID" ]; then
    echo "[ERROR] No se encontró CHAT_ID."
    exit 1
fi

printf 'TELEGRAM_BOT_TOKEN=%s\nTELEGRAM_CHAT_ID=%s\n' \
    "$TOKEN" "$CHAT_ID" > "$ENV_FILE"

chmod 600 "$ENV_FILE"

echo "[INFO] Enviando mensaje de prueba..."

curl -fsS \
    -X POST \
    "https://api.telegram.org/bot${TOKEN}/sendMessage" \
    -d "chat_id=${CHAT_ID}" \
    --data-urlencode "text=[secureGate] Telegram configurado correctamente." \
    >/dev/null

unset TOKEN CHAT_ID BOT_INFO UPDATES BOT_NAME

echo
echo "[OK] Telegram configurado."
echo "[OK] Archivo local: $ENV_FILE"
echo "[SEGURIDAD] Token y chat ID no se almacenan en Git."
