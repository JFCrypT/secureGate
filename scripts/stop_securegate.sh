#!/usr/bin/env bash

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="$ROOT_DIR/local/logs"

stop_pidfile() {
    name="$1"
    pidfile="$2"

    if [ ! -f "$pidfile" ]; then
        echo "[INFO] $name: no hay PID registrado."
        return
    fi

    pid="$(cat "$pidfile")"

    if kill -0 "$pid" 2>/dev/null; then
        kill "$pid" 2>/dev/null || true

        for _ in 1 2 3 4 5; do
            kill -0 "$pid" 2>/dev/null || break
            sleep 1
        done

        if kill -0 "$pid" 2>/dev/null; then
            echo "[ADVERTENCIA] $name no terminó; enviando SIGKILL."
            kill -9 "$pid" 2>/dev/null || true
        fi

        echo "[OK] $name detenido."
    else
        echo "[INFO] $name ya estaba detenido."
    fi

    rm -f "$pidfile"
}

stop_pidfile "Runtime"  "$LOG_DIR/runtime.pid"
stop_pidfile "Backend"  "$LOG_DIR/backend.pid"
stop_pidfile "Frontend" "$LOG_DIR/frontend.pid"

echo "[OK] secureGate detenido."
