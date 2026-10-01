# Instalación RC522 y alertas de secureGate

Destino: Raspberry Pi **3 o 4**, Raspberry Pi OS y Python **3.9 a 3.12**.
La placa de la foto es RFID-RC522 V1.33. El chip trabaja con tarjetas ISO/IEC
14443-A de 13,56 MHz. La apariencia de la tarjeta/llavero no confirma su chip:
verificar compatibilidad con `scan`. Este adaptador admite UID de 4 o 7 bytes.
No admite tarjetas de 125 kHz, Pi Pico ni garantiza Raspberry Pi 5.

El resultado es autorización lógica por **rostro O tarjeta registrada**.
No hay driver de relé/cerradura ni Reed en el repositorio original. El grupo de
actuadores debe conectar su apertura a `AccessEvent.granted` en
`raspberry/runtime_access.py`; no anunciar apertura física antes de esa integración.
Telegram no decide ni condiciona la apertura.

## 1. Conectar con la Raspberry apagada y desenchufada

Si el módulo viene sin pines, soldar una tira de 8 pines. Usar cables cortos y
conectar siguiendo los nombres impresos, no la orientación de la foto.
**Alimentar a 3,3 V, nunca a 5 V.** No conectar la cerradura a estos pines.

| Pin del RC522 | Pin físico Raspberry (conector de 40 pines) | Función |
|---|---:|---|
| SDA / SS | 24 | GPIO8, SPI0 CE0 (no I²C) |
| SCK | 23 | GPIO11, reloj SPI |
| MOSI | 19 | GPIO10 |
| MISO | 21 | GPIO9 |
| IRQ | Sin conectar | Se usa consulta periódica |
| GND | 6 | Tierra |
| RST | 22 | GPIO25 |
| 3.3V | 1 | Alimentación de 3,3 V |

El programa utiliza numeración **BCM** internamente (RST=GPIO25); la tabla usa
**pines físicos**. No reservar estos pines para otros sensores o relés.

## 2. Obtener el código

Si ya integraron esta mejora en el proyecto original, dentro de `secureGate`:

```bash
git switch main
git pull --ff-only
```

Para probar la rama antes de integrarla, desde una copia limpia del proyecto:

```bash
git fetch https://github.com/danyto49/secureGate.git feature/rfid-access-failure-alerts
git switch -c prueba-rfid FETCH_HEAD
```

No cambiar de rama si hay cambios locales pendientes sin guardarlos primero.

## 3. Habilitar SPI e instalar

Encender la Raspberry, abrir terminal y ejecutar:

```bash
sudo raspi-config
```

Elegir **Interface Options → SPI → Enable** y reiniciar. Después:

```bash
ls /dev/spidev0.0
cd ~/secureGate
sudo apt update
sudo apt install -y python3-venv python3-dev build-essential
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt -r requirements-rfid.txt
```

Si el entorno `.venv` ya existe, conservarlo y activar el existente.
El usuario del servicio debe pertenecer a `spi` y `gpio`:

```bash
sudo usermod -aG spi,gpio "$USER"
```

Cerrar sesión y volver a entrar si se agregaron grupos. Ejecutar el programa
como usuario normal, no con `sudo python` (se perderían entorno y credenciales).
Para rostro deben estar disponibles los modelos, la base y `k_bio` ya usados
por el prototipo. No hace falta `k_bio` ni modelos en modo sólo RFID.

## 4. Registrar las tarjetas

Detener el runtime antes de abrir el lector para enrolamiento. Hacer copia
protegida de la base existente si ya hay usuarios (fuera de Git).

```bash
python raspberry/init_db.py
python admin/manage_rfid.py init
python admin/manage_rfid.py scan
```

`init_db.py` crea las tablas faltantes, no borra usuarios/templates existentes.
El segundo comando crea `local/keys/k_rfid` sólo si no existe y añade la tabla
RFID. `scan` espera hasta 30 segundos; acercar UNA tarjeta a 1–3 cm.

Registrar la tarjeta blanca para un usuario, acercándola al lector:

```bash
python admin/manage_rfid.py enroll user_001
```

Repetir para el llavero. Puede pertenecer al mismo usuario o a otro:

```bash
python admin/manage_rfid.py enroll user_002
```

Si `user_001` ya tiene rostro enrolado, queda con ambas opciones. Si no existe,
se crea como usuario sólo RFID. No se escriben sectores de la tarjeta ni se
modifican los embeddings existentes. Una tarjeta de otro usuario no se reasigna
automáticamente; un usuario deshabilitado no se reactiva automáticamente.

Para deshabilitar una tarjeta, presentarla cuando lo solicita:

```bash
python admin/manage_rfid.py revoke
```

Los UID no se guardan en claro: se guarda un HMAC con `k_rfid`. Conservar esa
clave, protegerla con permisos `600` y respaldarla de forma segura. Al mover
la base a otra Raspberry debe trasladarse también `k_rfid` por un canal seguro.
No reemplazarla: las tarjetas ya registradas dejarían de coincidir.
No publicar UID, claves, bases, tokens ni fotografías en GitHub.

## 5. Configurar Telegram y ejecutar

El destinatario debe haber iniciado una conversación con el bot o agregado el
bot al grupo privado. Cargar token sin mostrarlo ni dejarlo en el historial:

```bash
read -r -s -p "Token Telegram: " TELEGRAM_BOT_TOKEN
export TELEGRAM_BOT_TOKEN
echo
read -r -p "ID del chat: " TELEGRAM_CHAT_ID
export TELEGRAM_CHAT_ID
python raspberry/runtime_access.py http://192.168.1.95/capture
```

Ese comando habilita **ambos métodos**. La URL debe coincidir con su ESP-CAM.
Para probar RFID sin modelos/cámara:

```bash
python raspberry/runtime_access.py --methods rfid
```

Para rostro solamente (comando anterior compatible):

```bash
python raspberry/runtime_recognize_espcam.py http://192.168.1.95/capture
```

Las variables duran esa sesión. Para instalación permanente, el encargado del
servicio debe cargarlas desde un archivo privado del servicio, no desde Git.
Si faltan ambas, las alertas aparecen sólo en consola. Si falta una, el arranque
falla para evitar una configuración incompleta.

## 6. Comprobar el resultado

1. Una tarjeta registrada debe imprimir `RFID: USUARIO VÁLIDO: user_...`.
2. Un rostro enrolado debe ser aceptado sin exigir tarjeta (regla 2 de 3, 0,45).
3. Una tarjeta desconocida debe producir UN rechazo aunque permanezca encima.
   Retirarla al menos un segundo y volverla a presentar para otro intento.
4. Para otro intento facial, retirarse hasta ver `Rostro retirado; listo para
   otro intento` y volver. Los tres frames de una decisión son UN intento.
5. Tres rechazos consecutivos generan Telegram incluso de día. Se pueden
   mezclar: RFID rechazado → rostro rechazado → RFID rechazado = alerta.
6. Un éxito por cualquiera de los métodos reinicia el contador.
7. Fuera de horario se alerta por intentos aceptados y rechazados:
   lunes–viernes [21:00, 06:00), sábado–domingo [17:00, 09:00).
8. Si ambas reglas coinciden, se envía un solo mensaje con ambos motivos.
9. Desconectar la cámara: RFID debe continuar; la alerta lleva texto sin foto.
10. Para probar tres fallos RFID sin que el rostro válido reinicie el contador,
    usar `--methods rfid` con tres presentaciones de una tarjeta desconocida.

Detener con Ctrl+C. El lector libera únicamente GPIO25 y SPI, no los GPIO
de otros sensores. Sólo debe correr un proceso que use RC522 a la vez.

## Comportamiento y límites

- El contador es global por puerta, no por persona: no se conoce la identidad
  de todos los desconocidos. Cuenta decisiones en el orden de recepción y se
  reinicia por éxito o reinicio del programa. Avisa en los rechazos 3, 6, 9...
- El cooldown de 60 s por método/resultado evita repetir la alerta horaria.
  No suprime la alerta de tres fallos. Es ajustable con `--alert-cooldown`.
- Cámara sin conexión, ausencia de rostro/tarjeta y errores técnicos no cuentan
  como denegación de credenciales. Varias caras/tarjetas no conceden acceso.
- Para rostro se usa una de las tres capturas de la decisión. Para RFID, la
  foto se solicita cuando se procesa la alerta: puede tener un pequeño retraso
  y no prueba que la persona retratada sea quien presentó la tarjeta.
- Los métodos trabajan en hilos independientes. Telegram usa otro hilo y una
  cola limitada (8 alertas); si se llena o falla el envío se informa en consola.
  No existe almacenamiento persistente ni entrega garantizada/reintentos.
- Esta integración autoriza por UID. **Un UID puede copiarse**: el HMAC protege
  la base, no convierte la tarjeta en una credencial resistente a clonación.
  Para una puerta de alta seguridad se necesita autenticación criptográfica de
  tarjetas y un lector compatible. Las fotos no confirman apertura de puerta.

## Si algo falla

| Síntoma | Revisar |
|---|---|
| No existe `/dev/spidev0.0` | Habilitar SPI y reiniciar |
| Permiso denegado en SPI/GPIO | Grupos del usuario; cerrar y abrir sesión |
| RC522 versión `0x00` o `0xFF` | Alimentación, GND, SDA/CE0, SPI, soldaduras |
| No lee tarjeta | Compatibilidad 13,56 MHz, distancia, una sola tarjeta |
| Tarjeta rechazada | Alta, estado del usuario/tarjeta, misma base y `k_rfid` |
| Telegram falla | Token/chat, bot iniciado, Internet y reloj sincronizado |

Fuentes de cableado y biblioteca: [pi-rc522](https://github.com/ondryaso/pi-rc522#connecting),
[documentación Raspberry Pi](https://www.raspberrypi.com/documentation/computers/raspberry-pi.html),
[MFRC522 de NXP](https://www.nxp.com/products/rfid-nfc/nfc-hf/nfc-readers/standard-performance-mifare-and-ntag-frontend:MFRC52202HN1).

Validación sin hardware: `python -m unittest discover -s tests -v`.
Las pruebas simulan lector/cámara/Telegram; completar los pasos 1–10 físicamente
antes de afirmar que está validado en la instalación.
