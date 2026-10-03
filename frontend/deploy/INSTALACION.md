# Instalación del front en la Raspberry Pi

Esta guía es **sólo documentación**: el front no instala ni cambia nada por su cuenta.
No se toca nginx, ufw, la IP de la Pi, ni el servicio o la configuración de la API.
El front es un proceso más, que escucha en el puerto **8080** y le habla a la API
por `http://127.0.0.1:8000`.

Marcadores: `USUARIO_RPI` (usuario de la Pi) e `IP_PI` (IP de la Pi en la red del lab;
nunca `192.168.1.95`, que es la ESP-CAM).

> `dev/mock_api.py` es sólo para desarrollo. **No se corre en la Pi.**

## 1. Requisitos

- La API de secureGate funcionando en la Pi (`curl http://127.0.0.1:8000/health` responde `ok`).
- Python 3.11 o superior (`python3 --version`).
- El repo en `/home/USUARIO_RPI/secureGate`.

## 2. Entorno virtual propio

Separado del venv del backend:

```bash
cd /home/USUARIO_RPI/secureGate/frontend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

`requirements-dev.txt` (pytest, respx) sólo hace falta para correr los tests.

## 3. Configuración (fuera de Git)

```bash
sudo mkdir -p /etc/securegate
sudo install -o USUARIO_RPI -g USUARIO_RPI -m 600 .env.example /etc/securegate/frontend.env
nano /etc/securegate/frontend.env
```

Valores a completar:

| Variable | Valor en la Pi |
|---|---|
| `SECUREGATE_API_URL` | `http://127.0.0.1:8000` |
| `SECUREGATE_API_TOKEN` | el **mismo** token que usa la API (está en su archivo de entorno; se copia, no se modifica) |
| `FRONT_SESSION_SECRET` | uno nuevo: `python3 -c "import secrets; print(secrets.token_urlsafe(32))"` |
| `FRONT_OPERATORS_FILE` | `/etc/securegate/frontend-operators.json` |
| `FRONT_TIMEZONE` | la misma zona que `SECUREGATE_TIMEZONE` del runtime |

Si falta el token o el secreto, o tienen menos de 32 caracteres, el front **no arranca**
y dice qué variable está mal (sin mostrar el valor).

## 4. Operadores

El archivo de operadores se crea vacío, a nombre del usuario del servicio y con permisos `600`:

```bash
sudo install -o USUARIO_RPI -g USUARIO_RPI -m 600 /dev/null /etc/securegate/frontend-operators.json
cd /home/USUARIO_RPI/secureGate/frontend
.venv/bin/python cli.py --file /etc/securegate/frontend-operators.json add-user admin --role admin
.venv/bin/python cli.py --file /etc/securegate/frontend-operators.json add-user guardia --role viewer
```

Otros comandos: `set-password USUARIO`, `disable-user USUARIO`, `enable-user USUARIO`, `list`.
Los cambios se aplican sin reiniciar el front. Deshabilitar un operador le corta la sesión.

- `admin`: hace todo.
- `viewer`: ve dashboard, historial, alertas y reportes (incluido el CSV); no crea, edita, revoca ni enrola.

## 5. Probar a mano

```bash
cd /home/USUARIO_RPI/secureGate/frontend
set -a; . /etc/securegate/frontend.env; set +a
.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8080
```

Desde otro equipo de la red: `http://IP_PI:8080/dashboard/` tiene que mostrar el login.
`http://IP_PI:8080/` redirige a `/dashboard/`.

## 6. Servicio systemd (opcional)

```bash
sudo cp deploy/securegate-frontend.service.example /etc/systemd/system/securegate-frontend.service
sudo sed -i 's/USUARIO_RPI/el_usuario_real/g' /etc/systemd/system/securegate-frontend.service
sudo systemctl daemon-reload
sudo systemctl enable --now securegate-frontend
systemctl status securegate-frontend
journalctl -u securegate-frontend -f
```

**Un solo worker.** El servicio arranca uvicorn sin `--workers` y así tiene que quedar:
el rate limit de login (5 intentos fallidos por IP cada 5 minutos) y las cachés del front
viven en la memoria del proceso. Con varios workers el límite se multiplicaría por la
cantidad de procesos y cada uno tendría su propia caché.

Tampoco lleva `--proxy-headers`: no hay proxy delante, y la IP del rate limit es la del socket.

## 7. Verificación

Desde una PC o un celular de la red del lab:

- [ ] `http://IP_PI:8080/dashboard/` muestra el login; sin login, cualquier ruta redirige al login.
- [ ] Con el runtime corriendo se ve **ONLINE**; al detenerlo pasa a **OFFLINE** en unos 20 s.
- [ ] En modo `simulate` aparece el banner ámbar y los accesos dicen "Simulada — sin apertura física".
- [ ] Un acceso real aparece en "Último acceso" en menos de 3 s.
- [ ] Con la API detenida el front muestra "API no disponible" y se recupera solo al levantarla.
- [ ] Un `viewer` recibe 403 si entra por URL a `/dashboard/usuarios/nuevo`.

El checklist completo está en `contrato.md` §11.

## 8. Problemas frecuentes

| Síntoma | Causa probable |
|---|---|
| El servicio no arranca y el log dice "Configuración inválida del front" | Falta o está mal una variable de `/etc/securegate/frontend.env` |
| "Error de configuración del servidor" en pantalla | `SECUREGATE_API_TOKEN` no coincide con el de la API |
| "API no disponible" | La API no está corriendo o `SECUREGATE_API_URL` apunta a otro lado |
| "Base de datos no disponible" | La API respondió 500/503 (SQLite inaccesible) |
| Nadie puede entrar | El archivo de operadores no existe, está vacío o el servicio no lo puede leer (dueño y permisos `600`) |
| "Demasiados intentos fallidos" | 5 fallos desde esa IP: esperar 5 minutos (o reiniciar el front) |
| Las horas se ven corridas | `FRONT_TIMEZONE` distinta de la del runtime, o la Pi sin NTP |
| No carga desde el celular | El celular no está en la red del lab, o hay un firewall bloqueando el 8080 |

## 9. Actualizar y desinstalar

```bash
# Actualizar
cd /home/USUARIO_RPI/secureGate && git pull
frontend/.venv/bin/pip install -r frontend/requirements.txt
sudo systemctl restart securegate-frontend

# Desinstalar (no afecta a la API ni al runtime)
sudo systemctl disable --now securegate-frontend
sudo rm /etc/systemd/system/securegate-frontend.service /etc/securegate/frontend.env /etc/securegate/frontend-operators.json
```

## 10. Seguridad

- El token de la API vive sólo en `/etc/securegate/frontend.env`; nunca llega al navegador.
- HTTP plano y cookie sin `Secure`: aceptable sólo en la red controlada del lab.
- Recomendaciones opcionales para quien integre (nginx, IP fija, no exponer el 8000):
  `frontend/PEDIDOS_BACKEND.md`, sección "Recomendaciones para integración".
