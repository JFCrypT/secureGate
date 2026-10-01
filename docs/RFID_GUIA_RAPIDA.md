# RC522: guía rápida para el equipo

Usar Raspberry Pi 3/4 y Raspberry Pi OS. El módulo debe tener los pines soldados.

1. **Con la Raspberry apagada**, conectar RC522 → pin físico Raspberry:
   SDA→24, SCK→23, MOSI→19, MISO→21, GND→6, RST→22, 3.3V→1.
   IRQ queda libre. **Nunca alimentar a 5 V.**
2. Encender. En `sudo raspi-config`, habilitar **Interface Options → SPI** y
   reiniciar. Comprobar que exista `/dev/spidev0.0`.
3. Descargar la rama `feature/rfid-access-failure-alerts` del fork de Daniel
   (o actualizar `main` una vez fusionada). Dentro de la carpeta del proyecto:

```bash
source .venv/bin/activate
python -m pip install -r requirements.txt -r requirements-rfid.txt
python raspberry/init_db.py
python admin/manage_rfid.py init
```

4. Registrar una tarjeta por vez. El comando espera que acerquen la tarjeta:

```bash
python admin/manage_rfid.py enroll user_001
```

Repetir para cada usuario/llavero. Puede asociarse al usuario que ya tiene rostro.
No se modifica la tarjeta ni se borran usuarios biométricos.

5. Cargar las credenciales Telegram en esa misma terminal y ejecutar:

```bash
read -r -s -p "Token Telegram: " TELEGRAM_BOT_TOKEN
export TELEGRAM_BOT_TOKEN
echo
read -r -p "ID del chat: " TELEGRAM_CHAT_ID
export TELEGRAM_CHAT_ID
python raspberry/runtime_access.py http://192.168.1.95/capture
```

6. Probar rostro válido **o** tarjeta registrada. Probar tres rechazos retirando
   la tarjeta/rostro entre intentos: debe llegar Telegram. Un acceso válido
   reinicia la cuenta. Para aislar RFID: `python raspberry/runtime_access.py
   --methods rfid`. Si falla la foto se envía texto. Detener con Ctrl+C.

Conservar `local/keys/k_rfid` y la base fuera de Git; son necesarias en cada
Raspberry que valide las mismas tarjetas. Los UID pueden clonarse.
El código entrega autorización lógica; el relé/Reed aún corresponde al grupo
de actuadores. Completar la prueba física antes de ponerlo en servicio.

Si falta `.venv`, hay errores de permisos, necesitan revocar una tarjeta o
consultar cómo probar la rama: [instructivo completo](INSTALACION_RFID.md).
