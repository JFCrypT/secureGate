# Puesta en marcha final de secureGate en Raspberry Pi 3

Este documento describe el procedimiento para dejar la Raspberry Pi 3 preparada para la demostración integral de secureGate.

El alcance actual incluye:

- identificación biométrica mediante YuNet + SFace;
- identificación alternativa mediante RFID RC522;
- autorización por biometría OR RFID;
- base SQLite;
- embeddings protegidos con AES-256-GCM;
- UID RFID protegido mediante HMAC-SHA-256;
- logs de acceso;
- alertas Telegram;
- backend REST;
- frontend web;
- heartbeat del runtime;
- control de puerta en modo `simulate`.

La actuación física de la cerradura mediante GPIO/relé queda prevista en software, pero su integración definitiva se realizará posteriormente en coordinación con el Director del Laboratorio.

## 1. Estado previo requerido

Deben estar encendidos o conectados:

- AP `jfcrypt-lab`;
- Raspberry Pi 3;
- ESP32-CAM;
- RC522.

Direcciones previstas:

    Raspberry Pi 3: 192.168.1.40
    ESP32-CAM:      192.168.1.95

## 2. Cableado RC522

Con la Raspberry Pi apagada:

    RC522       Raspberry Pi 3
    --------------------------------
    3.3V   ->   Pin 1
    GND    ->   Pin 6
    MOSI   ->   Pin 19 / GPIO10
    MISO   ->   Pin 21 / GPIO9
    RST    ->   Pin 22 / GPIO25
    SCK    ->   Pin 23 / GPIO11
    SDA/SS ->   Pin 24 / GPIO8 / CE0
    IRQ    ->   sin conectar

El RC522 debe alimentarse exclusivamente con 3,3 V.

Nunca conectarlo a 5 V.

## 3. Actualizar secureGate en la Raspberry Pi

    cd ~/secureGate

    git status
    git pull origin main

    git --no-pager log --oneline -5

Se deben observar los commits recientes correspondientes a:

- frontend;
- scripts start/stop;
- integración de Telegram;
- documentación final.

## 4. Preparar sistema y entorno Python

    cd ~/secureGate

    sudo apt update

    sudo apt install -y \
      python3-venv \
      python3-dev \
      build-essential \
      sqlite3 \
      curl

Crear el entorno si todavía no existe:

    [ -d .venv ] || python3 -m venv .venv

Activarlo:

    source .venv/bin/activate

Actualizar pip:

    python -m pip install -U pip

Instalar dependencias:

    python -m pip install \
      -r requirements.txt \
      -r requirements-rfid.txt \
      -r requirements-api.txt \
      -r requirements-test.txt

## 5. Habilitar SPI

Ejecutar:

    sudo raspi-config

Seleccionar:

    Interface Options
    -> SPI
    -> Enable

Agregar el usuario a los grupos correspondientes:

    sudo usermod -aG spi,gpio "$USER"

Reiniciar:

    sudo reboot

Luego verificar:

    ls -l /dev/spidev0.0

Debe existir el dispositivo SPI0.

## 6. Verificar red

Comprobar configuración IP:

    ip -4 addr
    ip route

Comprobar comunicación con la ESP32-CAM:

    ping -c 3 192.168.1.95

Probar captura:

    curl -f \
      http://192.168.1.95/capture \
      -o /tmp/securegate_capture.jpg

Verificar el archivo:

    file /tmp/securegate_capture.jpg

También verificar salida a Internet para Telegram:

    curl -I https://api.telegram.org

## 7. Copiar los datos privados definitivos

Copiar manualmente desde el equipo administrativo hacia la Raspberry Pi:

    data/db/securegate.db
    local/keys/k_bio
    local/keys/k_rfid
    local/securegate.env

Significado:

    securegate.db  -> biometría final de user_001...user_009
    K_bio          -> clave de protección biométrica
    K_rfid         -> clave HMAC de RFID
    securegate.env -> configuración privada de Telegram

No copiar desde el equipo de desarrollo:

    frontend/.env
    frontend/operators.json

Estos archivos se generan directamente en la Raspberry Pi.

Aplicar permisos:

    cd ~/secureGate

    chmod 600 local/keys/k_bio
    chmod 600 local/keys/k_rfid
    chmod 600 local/securegate.env

Verificar:

    ls -l \
      data/db/securegate.db \
      local/keys/k_bio \
      local/keys/k_rfid \
      local/securegate.env

## 8. Crear backup de la DB

Antes de enrolar RFID:

    cd ~/secureGate

    cp data/db/securegate.db \
       data/db/securegate_backup_pre_rfid.db

Una vez enroladas las tarjetas, la base de la Raspberry pasa a ser la base operativa principal.

No sobrescribirla posteriormente con una copia antigua del equipo administrativo.

## 9. Migrar/inicializar la DB

Activar entorno:

    source .venv/bin/activate

Ejecutar:

    python raspberry/init_db.py

Este proceso crea o actualiza las estructuras necesarias sin eliminar los datos biométricos.

## 10. Verificar usuarios biométricos

Ejecutar:

    sqlite3 data/db/securegate.db \
    'SELECT u.external_id, COUNT(t.template_id)
     FROM users u
     LEFT JOIN biometric_templates t
       ON t.user_id = u.user_id
      AND t.active = 1
     GROUP BY u.user_id
     ORDER BY u.external_id;'

Resultado esperado:

    user_001|5
    user_002|5
    user_003|5
    user_004|5
    user_005|5
    user_006|5
    user_007|5
    user_008|5
    user_009|5

## 11. Verificar modelos biométricos

Ejecutar:

    python raspberry/check_models.py

Si faltan los modelos:

    ./scripts/download_models.sh

Volver a verificar:

    python raspberry/check_models.py

## 12. Inicializar RFID

Ejecutar:

    python admin/manage_rfid.py init

`K_rfid` ya debe existir porque fue transferida desde el equipo administrativo.

No debe regenerarse una vez que existan credenciales RFID enroladas.

## 13. Comprobar RC522

Ejecutar:

    python admin/manage_rfid.py scan

Acercar una tarjeta al lector.

El programa debe detectar correctamente el dispositivo RFID.

## 14. Enrolar las dos tarjetas

Ejemplo:

    python admin/manage_rfid.py enroll user_001

Luego:

    python admin/manage_rfid.py enroll user_002

Acercar la tarjeta correspondiente cuando el programa lo solicite.

Estado esperado:

    user_001 -> biometría + RFID
    user_002 -> biometría + RFID
    user_003 -> biometría
    user_004 -> biometría
    user_005 -> biometría
    user_006 -> biometría
    user_007 -> biometría
    user_008 -> biometría
    user_009 -> biometría

No se crean archivos RFID equivalentes a las fotografías biométricas.

El flujo es:

    UID
    -> HMAC-SHA-256(K_rfid, UID)
    -> uid_digest
    -> securegate.db
    -> rfid_credentials

El UID no se almacena en claro.

## 15. Verificar credenciales RFID

Ejecutar:

    sqlite3 data/db/securegate.db \
    'SELECT u.external_id, COUNT(r.credential_id)
     FROM users u
     LEFT JOIN rfid_credentials r
       ON r.user_id = u.user_id
      AND r.active = 1
     GROUP BY u.user_id
     ORDER BY u.external_id;'

Resultado esperado:

    user_001|1
    user_002|1
    user_003|0
    user_004|0
    user_005|0
    user_006|0
    user_007|0
    user_008|0
    user_009|0

## 16. Probar RFID de forma aislada

Ejecutar:

    python raspberry/runtime_access.py \
      --methods rfid \
      --door-mode simulate

Probar:

    tarjeta user_001 -> AUTORIZADO
    tarjeta user_002 -> AUTORIZADO
    tarjeta desconocida -> RECHAZADO

Finalizar con:

    Ctrl+C

## 17. Probar biometría de forma aislada

Ejecutar:

    python raspberry/runtime_access.py \
      http://192.168.1.95/capture \
      --methods face \
      --door-mode simulate

Probar:

    usuario enrolado -> AUTORIZADO
    persona no enrolada -> RECHAZADO

Finalizar con:

    Ctrl+C

## 18. Preparar frontend

El frontend utiliza un entorno virtual independiente del backend.

Ejecutar:

    cd ~/secureGate/frontend

    [ -d .venv ] || python3 -m venv .venv

    source .venv/bin/activate

    python -m pip install -U pip

    python -m pip install \
      -r requirements.txt \
      -r requirements-dev.txt

## 19. Crear frontend/.env propio de la Raspberry

Ejecutar:

    cd ~/secureGate/frontend

    cp --update=none .env.example .env 2>/dev/null || true

Generar secretos:

    TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"

    SESSION_SECRET="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"

Actualizar `.env`:

    python - <<PY
    from pathlib import Path

    p = Path(".env")
    s = p.read_text() if p.exists() else ""

    values = {
        "SECUREGATE_API_URL": "http://127.0.0.1:8000",
        "SECUREGATE_API_TOKEN": "$TOKEN",
        "FRONT_SESSION_SECRET": "$SESSION_SECRET",
    }

    lines = s.splitlines()

    for key, value in values.items():
        found = False
        for i, line in enumerate(lines):
            if line.startswith(key + "="):
                lines[i] = f"{key}={value}"
                found = True
                break

        if not found:
            lines.append(f"{key}={value}")

    p.write_text("\n".join(lines) + "\n")
    PY

Proteger el archivo:

    chmod 600 .env

Limpiar variables temporales:

    unset TOKEN SESSION_SECRET

## 20. Crear administrador del dashboard

Dentro de `frontend/`:

    source .venv/bin/activate

    python cli.py add-user admin --role admin

Ingresar la contraseña solicitada.

El archivo:

    frontend/operators.json

queda almacenado localmente y fuera de Git.

## 21. Verificar configuración Telegram

Desde la raíz:

    cd ~/secureGate

Verificar sin mostrar secretos:

    grep -q '^TELEGRAM_BOT_TOKEN=' local/securegate.env \
      && echo "[OK] Telegram token presente"

    grep -q '^TELEGRAM_CHAT_ID=' local/securegate.env \
      && echo "[OK] Telegram chat presente"

No utilizar:

    cat local/securegate.env

porque expondría el token.

## 22. Prueba manual del sistema completo

Antes de iniciar:

    cd ~/secureGate

    ./scripts/stop_securegate.sh

Luego:

    ./scripts/start_securegate.sh

Este script inicia:

    runtime_access.py -> biometría OR RFID
    backend_api.py    -> 127.0.0.1:8000
    frontend          -> 0.0.0.0:8080
    Telegram          -> cargado desde local/securegate.env
    door-mode         -> simulate

## 23. Verificar procesos

Ejecutar:

    ps aux | \
      grep -E 'runtime_access|backend_api|uvicorn' | \
      grep -v grep

Deben observarse tres procesos:

- runtime;
- backend;
- frontend.

## 24. Revisar logs

Ejecutar:

    cd ~/secureGate

    echo "===== RUNTIME ====="
    tail -n 40 local/logs/runtime.log

    echo
    echo "===== BACKEND ====="
    tail -n 20 local/logs/backend.log

    echo
    echo "===== FRONTEND ====="
    tail -n 20 local/logs/frontend.log

En el runtime se espera observar:

    Métodos: both
    Puerta en simulación
    Telegram habilitado

No deben existir errores de inicialización del RC522.

## 25. Verificar API

Ejecutar:

    curl http://127.0.0.1:8000/health

La API debe responder correctamente.

## 26. Abrir dashboard

Desde cualquier equipo conectado a `jfcrypt-lab`:

    http://192.168.1.40:8080/dashboard/

Estado esperado:

    ONLINE
    heartbeat reciente
    modo de acceso: both
    modo de puerta: simulate

    total usuarios: 9
    con rostro: 9
    con tarjeta: 2
    con ambos: 2

## 27. Prueba funcional final

Ejecutar la demostración en este orden:

1. `user_001` por rostro
   -> AUTORIZADO

2. `user_001` por RFID
   -> AUTORIZADO

3. `user_002` por RFID
   -> AUTORIZADO

4. Persona no enrolada
   -> RECHAZADO

5. Tarjeta no enrolada
   -> RECHAZADO

6. Tarjeta no enrolada tres veces
   -> retirar entre intentos
   -> alerta Telegram

7. Verificar Historial.

8. Verificar Alertas.

9. Verificar Reportes.

10. Confirmar que la puerta figure como:

    SIMULADA — sin apertura física

El modo `simulate` ejecuta toda la lógica de autorización, registro y actuación lógica sin energizar ningún GPIO.

## 28. Prueba de Telegram

Utilizar una tarjeta no enrolada:

    intento 1
    -> retirar

    intento 2
    -> retirar

    intento 3

Al alcanzar el umbral de rechazos consecutivos debe llegar una alerta al chat Telegram configurado.

Luego realizar un acceso válido para comprobar que el contador de rechazos se reinicia.

Telegram no participa de la decisión de autorización ni de la actuación física.

## 29. Configurar inicio automático con cron

Realizar este paso únicamente después de validar manualmente todo el sistema.

Primero detener secureGate:

    cd ~/secureGate

    ./scripts/stop_securegate.sh

Agregar un único `@reboot`:

    (
      crontab -l 2>/dev/null |
        grep -v 'secureGate/scripts/start_securegate.sh'

      echo "@reboot sleep 20 && $HOME/secureGate/scripts/start_securegate.sh"
    ) | crontab -

Verificar:

    crontab -l

Debe aparecer:

    @reboot sleep 20 && /home/USUARIO/secureGate/scripts/start_securegate.sh

## 30. Validar el arranque automático

Reiniciar:

    sudo reboot

Esperar aproximadamente 30 a 60 segundos.

Desde otro equipo de `jfcrypt-lab`, abrir:

    http://192.168.1.40:8080/dashboard/

El dashboard debe mostrar:

    ONLINE

Para verificar por SSH:

    cd ~/secureGate

    ps aux | \
      grep -E 'runtime_access|backend_api|uvicorn' | \
      grep -v grep

    tail -n 30 local/logs/runtime.log

## 31. Estado final esperado

La Raspberry Pi 3 queda ejecutando:

    Raspberry Pi 3
    192.168.1.40
    |
    +-- runtime_access.py
    |   |
    |   +-- YuNet
    |   +-- SFace
    |   +-- ESP32-CAM 192.168.1.95
    |   +-- RC522
    |   +-- biometría OR RFID
    |   +-- Telegram
    |   +-- access_events
    |   +-- heartbeat
    |   +-- door-mode simulate
    |
    +-- backend_api.py :8000
    |
    +-- frontend :8080
        |
        +-- /dashboard/

En cada reinicio:

    Raspberry Pi 3 arranca
    -> espera 20 segundos
    -> start_securegate.sh
    -> runtime + backend + frontend
    -> heartbeat
    -> dashboard ONLINE

## 32. Integración física futura de puerta

La actuación física ya está prevista en software mediante:

    --door-mode gpio
    --relay-pin <GPIO_BCM>
    --relay-active high|low
    --door-open-seconds <segundos>

La demostración actual utiliza:

    --door-mode simulate

Por lo tanto:

- se realiza la decisión de acceso;
- se registra la orden lógica de apertura;
- se actualizan logs y frontend;
- no se energiza ningún GPIO.

La definición del GPIO, módulo de relé, polaridad, alimentación y tiempo definitivo de apertura queda como trabajo futuro en coordinación con el Director del Laboratorio y según la infraestructura instalada.
