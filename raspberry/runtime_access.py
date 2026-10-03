#!/usr/bin/env python3
"""Face OR RC522 access, with shared alerts and independent input workers."""

from datetime import datetime
from pathlib import Path
from queue import Queue, Empty, Full
from threading import Event, Thread
import argparse
import math
import os
import sqlite3
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))

from securegate.access import AccessController, AccessEvent, PresenceGate
from securegate.access_log import AccessLogRepository
from securegate.alerts import DEFAULT_TIMEZONE, TelegramNotifier, load_timezone
from securegate.alerts.commands import (
    build_logs_text,
    extract_message,
    is_authorized,
    parse_command,
    parse_limit,
    should_send_as_document,
)
from securegate.alerts.schedule import is_restricted_time
from securegate.alerts.telegram import TelegramDeliveryError
from securegate.daily_log import DailyLogger
from securegate.door import DoorControlError, create_door
from securegate.rfid.enrollment import RFIDEnrollmentRepository
from securegate.rfid.registry import CardRegistry, DEFAULT_DB, DEFAULT_KEY
from securegate.rfid.reader import RC522Reader
from securegate.runtime_status import RuntimeStatusRepository


class FaceSource:
    def __init__(self, url, timeout):
        import runtime_recognize_espcam as facial
        from securegate.vision.pipeline import NoFaceDetected
        self.facial = facial
        self.no_face_error = NoFaceDetected
        self.url = url
        self.timeout = timeout
        self.recognizer = facial.create_recognizer()
        self.templates = facial.load_active_templates()

    def capture(self):
        return self.facial.capture_frame(self.url, self.timeout)

    def match(self, image):
        embedding = self.facial.extract_embedding_from_image(image, self.recognizer)
        return self.facial.recognize(embedding, self.recognizer, self.templates)

    def decide(self, results):
        user, _matches, _score = self.facial.decide(results)
        return user, self.facial.select_alert_image(results, user)


def report(events, message):
    # Drop diagnostics (never access decisions) if consumer is briefly busy.
    try:
        events.put_nowait(message)
    except Full:
        pass


def emit(events, stop, event):
    while not stop.is_set():
        try:
            events.put(event, timeout=0.2)
            return
        except Full:
            continue


def face_worker(source, events, stop, timezone, interval=0.4, cooldown=3):
    results = []
    gate = PresenceGate()
    last_error = float("-inf")
    try:
        while not stop.is_set():
            try:
                image = source.capture()
                captured_at = datetime.now(timezone)
                user, score = source.match(image)
            except source.no_face_error:
                results.clear()
                was_present = gate.last_identity is not None
                gate.observe(None)
                if was_present and gate.last_identity is None:
                    report(events, "[INFO] Rostro retirado; listo para otro intento.")
            except Exception:
                # Camera/vision faults must never become credential denials.
                results.clear()
                gate.absent_since = None
                if time.monotonic() - last_error >= 10:
                    report(events, "[ERROR] Cámara/visión no disponible o múltiples rostros. No se cuenta un rechazo.")
                    last_error = time.monotonic()
            else:
                gate.absent_since = None
                if gate.last_identity is None:
                    results.append((user, score, image))
                    if len(results) == 3:
                        accepted_user, photo = source.decide(results)
                        gate.observe("face")
                        emit(events, stop, AccessEvent("facial", accepted_user, captured_at, photo))
                        results.clear()
                        stop.wait(cooldown)
            stop.wait(interval)
    except Exception:
        report(events, "[ERROR] El proceso de reconocimiento se detuvo; reiniciar y revisar modelos.")


def rfid_worker(
    reader,
    registry,
    events,
    stop,
    timezone,
    interval=0.1,
    enrollment=None,
):
    gate = PresenceGate(release_seconds=0.8)
    last_error = float("-inf")
    try:
        while not stop.is_set():
            try:
                uid = reader.poll()
                captured_at = datetime.now(timezone)
                if uid is None:
                    gate.observe(None)
                elif gate.observe(uid):
                    request = None
                    if enrollment is not None:
                        try:
                            request = enrollment.pending()
                        except (OSError, ValueError, sqlite3.Error):
                            report(
                                events,
                                "[ERROR] No se pudo consultar la solicitud RFID; "
                                "no se procesa la tarjeta.",
                            )
                            continue
                    if request:
                        try:
                            registry.enroll(request["external_id"], uid)
                            enrollment.complete(request["request_id"])
                        except ValueError:
                            try:
                                enrollment.fail(
                                    request["request_id"], "card_unavailable"
                                )
                            except Exception:
                                pass
                            report(
                                events,
                                "[ERROR] No se pudo asociar la tarjeta. "
                                "La solicitud RFID quedó rechazada.",
                            )
                        except (OSError, sqlite3.Error):
                            report(
                                events,
                                "[ERROR] Falló la base durante el enrolamiento RFID.",
                            )
                        else:
                            report(
                                events,
                                "[RFID] Tarjeta asociada correctamente a "
                                f"{request['external_id']}.",
                            )
                        continue
                    try:
                        user = registry.authorize(uid)
                    except (OSError, ValueError, sqlite3.Error):
                        report(events, "[ERROR] No se pudo consultar la base RFID; no se autoriza ni se cuenta un rechazo.")
                    else:
                        emit(events, stop, AccessEvent("RFID", user, captured_at))
            except Exception:
                gate.absent_since = None
                if time.monotonic() - last_error >= 10:
                    report(events, "[ERROR] Falló el lector RFID. Revisar conexión y cableado; no se cuenta un rechazo.")
                    last_error = time.monotonic()
            stop.wait(interval)
    finally:
        reader.close()


def deliver_alert(notifier, alert, capture=None):
    """RFID events get a fresh photo only when needed. Text survives photo errors."""
    image = alert.event.image
    caption = alert.caption()
    if image is None and capture is not None:
        try:
            image = capture()
            caption += "\nFoto tomada al procesar la alerta RFID."
        except Exception:
            caption += "\nFoto no disponible (cámara sin conexión)."
    if image is None:
        notifier.send_message(caption)
    else:
        try:
            notifier.send_photo(image, caption, captured_at=alert.event.occurred_at)
        except Exception:
            # Do not print exception URLs: Telegram tokens are in those URLs.
            notifier.send_message(caption + "\nNo se pudo enviar la fotografía.")


def notification_worker(notifier, alerts, stop, capture=None, daily_logger=None):
    while not stop.is_set() or not alerts.empty():
        try:
            alert = alerts.get(timeout=0.2)
        except Empty:
            continue
        try:
            deliver_alert(notifier, alert, capture)
            _emit("[ALERTA] Telegram confirmó la recepción.", daily_logger)
        except TelegramDeliveryError as exc:
            _emit(f"[ERROR] Telegram: {exc}", daily_logger)
        except Exception:
            _emit("[ERROR] No se pudo enviar la alerta Telegram.", daily_logger)
        finally:
            alerts.task_done()


def _emit(message, daily_logger=None, moment=None):
    """Muestra por consola y anexa al log diario (sin romper el runtime)."""
    print(message, flush=True)
    if daily_logger is None:
        return
    try:
        if message.startswith("[ACCESO]"):
            level, text = "ACCESO", message[len("[ACCESO]"):].strip()
        elif message.startswith("[ALERTA]"):
            level, text = "ALERTA", message[len("[ALERTA]"):].strip()
        elif message.startswith("[ERROR]"):
            level, text = "ERROR", message[len("[ERROR]"):].strip()
        elif message.startswith("[ADVERTENCIA]"):
            level, text = "ADVERTENCIA", message[len("[ADVERTENCIA]"):].strip()
        else:
            level, text = "INFO", message.replace("[INFO]", "").strip()
        daily_logger.write(level, text, moment=moment)
    except Exception:
        pass


def command_worker(notifier, daily_logger, access_log, stop, poll_interval=5.0,
                   default_limit=50):
    """Polling getUpdates para responder /logs solo al chat autorizado."""
    offset = None
    while not stop.is_set():
        try:
            updates = notifier.get_updates(offset=offset, timeout=0)
        except TelegramDeliveryError:
            stop.wait(poll_interval)
            continue
        except Exception:
            stop.wait(poll_interval)
            continue
        try:
            for update in updates:
                try:
                    update_id = update.get("update_id")
                    if update_id is not None:
                        candidate = int(update_id) + 1
                        offset = candidate if offset is None else max(offset, candidate)
                except (AttributeError, ValueError, TypeError):
                    continue
                if not is_authorized(update, notifier.config.chat_id):
                    continue
                text, _ = extract_message(update)
                command, arg = parse_command(text)
                if command is None:
                    continue
                if command in ("/start", "/help"):
                    notifier.send_message(
                        "secureGate activo. Usa /logs [n] para ver el log de hoy "
                        "(00:00 hasta ahora). Ej: /logs 50"
                    )
                elif command == "/logs":
                    limit = parse_limit(arg) if arg else default_limit
                    try:
                        response = build_logs_text(
                            daily_logger, access_log, limit=limit
                        )
                    except Exception:
                        notifier.send_message("No se pudo leer el log de hoy.")
                        continue
                    if should_send_as_document(response):
                        lines, _ = daily_logger.read_today(limit=limit)
                        full = "\n".join(lines) if lines else "Sin eventos hoy."
                        notifier.send_document(
                            full,
                            f"securegate-{daily_logger.today_label()}.log",
                            caption=response[:1024],
                        )
                    else:
                        notifier.send_message(response)
                else:
                    notifier.send_message("Comando no reconocido. Usa /logs.")
        except TelegramDeliveryError:
            pass
        except Exception:
            pass
        if not updates:
            stop.wait(poll_interval)


def positive_float(value):
    result = float(value)
    if not math.isfinite(result) or result <= 0:
        raise argparse.ArgumentTypeError("Debe ser un número finito mayor que cero.")
    return result


def nonnegative_float(value):
    result = float(value)
    if not math.isfinite(result) or result < 0:
        raise argparse.ArgumentTypeError("Debe ser un número finito no negativo.")
    return result


def main(default_mode="both"):
    parser = argparse.ArgumentParser(description="secureGate: reconocimiento facial O tarjeta RC522.")
    parser.add_argument(
        "url",
        nargs="?",
        default=os.environ.get("SECUREGATE_ESP_CAM_URL"),
        help="URL /capture de ESP-CAM.",
    )
    parser.add_argument(
        "--methods",
        choices=("both", "face", "rfid"),
        default=os.environ.get("SECUREGATE_METHODS", default_mode),
    )
    parser.add_argument("--timeout", type=positive_float, default=5.0)
    parser.add_argument("--interval", type=positive_float, default=0.4)
    parser.add_argument("--cooldown", type=nonnegative_float, default=3.0)
    parser.add_argument("--alert-cooldown", type=nonnegative_float, default=60.0)
    parser.add_argument("--timezone", default=os.environ.get("SECUREGATE_TIMEZONE", DEFAULT_TIMEZONE))
    parser.add_argument("--rfid-database", type=Path, default=DEFAULT_DB)
    parser.add_argument("--rfid-key", type=Path, default=DEFAULT_KEY)
    parser.add_argument(
        "--door-mode",
        choices=("simulate", "gpio"),
        default=os.environ.get("SECUREGATE_DOOR_MODE", "simulate"),
        help="simulate no energiza GPIO; gpio acciona un relé configurado.",
    )
    parser.add_argument(
        "--relay-pin",
        type=int,
        default=os.environ.get("SECUREGATE_RELAY_PIN"),
        help="Número GPIO BCM. Obligatorio únicamente en modo gpio.",
    )
    parser.add_argument(
        "--relay-active",
        choices=("high", "low"),
        default=os.environ.get("SECUREGATE_RELAY_ACTIVE", "high"),
        help="Nivel eléctrico que activa el módulo de relé.",
    )
    parser.add_argument(
        "--door-open-seconds",
        type=positive_float,
        default=os.environ.get("SECUREGATE_DOOR_OPEN_SECONDS", "3"),
    )
    parser.add_argument(
        "--log-dir",
        type=Path,
        default=os.environ.get(
            "SECUREGATE_LOG_DIR",
            str(Path(__file__).resolve().parents[1] / "logs"),
        ),
        help="Carpeta de logs diarios securegate-AAAA-MM-DD.log.",
    )
    parser.add_argument(
        "--logs-limit",
        type=int,
        default=int(os.environ.get("SECUREGATE_LOGS_LIMIT", "50")),
        help="Líneas devueltas por /logs (1-200).",
    )
    parser.add_argument(
        "--telegram-poll",
        type=positive_float,
        default=float(os.environ.get("SECUREGATE_TELEGRAM_POLL", "5")),
        help="Segundos entre consultas getUpdates para /logs.",
    )
    args = parser.parse_args()
    if args.methods != "rfid" and not args.url:
        parser.error("Se requiere URL de cámara para reconocimiento facial.")
    if args.logs_limit < 1 or args.logs_limit > 200:
        parser.error("--logs-limit debe estar entre 1 y 200.")

    reader = None
    door = None
    runtime_status = None
    daily_logger = None
    try:
        timezone = load_timezone(args.timezone)
        daily_logger = DailyLogger(args.log_dir, timezone)
        notifier = TelegramNotifier.from_environment()
        access_log = AccessLogRepository(args.rfid_database)
        runtime_status = RuntimeStatusRepository(args.rfid_database)
        door = create_door(
            args.door_mode,
            pin=args.relay_pin,
            active_high=args.relay_active == "high",
            duration_seconds=args.door_open_seconds,
        )
        face = FaceSource(args.url, args.timeout) if args.methods != "rfid" else None
        registry = None
        enrollment = None
        if args.methods != "face":
            registry = CardRegistry(args.rfid_database, args.rfid_key)
            enrollment = RFIDEnrollmentRepository(args.rfid_database)
            reader = RC522Reader()
    except Exception as exc:
        if reader:
            reader.close()
        if door:
            door.close()
        # Startup has no network Telegram calls; configuration errors contain no token.
        print(f"[ERROR] No se pudo iniciar secureGate: {exc}")
        return 1

    _emit(f"[INFO] Métodos: {args.methods}; zona horaria: {args.timezone}", daily_logger)
    _emit("[INFO] Autorización alternativa: facial O RFID.", daily_logger)
    if args.door_mode == "simulate":
        _emit("[INFO] Puerta en simulación: no se activa ningún GPIO.", daily_logger)
    else:
        _emit(
            f"[INFO] Puerta física: GPIO BCM {args.relay_pin}, "
            f"activo en {args.relay_active.upper()}.",
            daily_logger,
        )
    _emit("[INFO] Retirar rostro/tarjeta entre intentos. Ctrl+C para detener.", daily_logger)
    _emit(
        "[INFO] Telegram habilitado. Usa /logs para ver el log de hoy."
        if notifier
        else "[ADVERTENCIA] Telegram deshabilitado: faltan token y chat.",
        daily_logger,
    )
    _emit(f"[INFO] Log diario: {daily_logger.path_for()}", daily_logger)
    events = Queue(maxsize=32)
    alerts = Queue(maxsize=8)
    stop = Event()
    notification_stop = Event()
    command_stop = Event()
    controller = AccessController(args.alert_cooldown)
    workers = []
    if face:
        workers.append(Thread(target=face_worker, args=(
            face, events, stop, timezone, args.interval, args.cooldown,
        ), name="securegate-face", daemon=True))
    if reader:
        workers.append(Thread(
            target=rfid_worker,
            args=(reader, registry, events, stop, timezone),
            kwargs={"enrollment": enrollment},
            name="securegate-rfid",
            daemon=True,
        ))
    sender = None
    commander = None
    if notifier:
        capture = None
        if args.url:
            # A separate capture avoids sharing the facial recognizer across threads.
            def capture():
                from runtime_recognize_espcam import capture_frame
                return capture_frame(args.url, args.timeout)
        sender = Thread(target=notification_worker, args=(
            notifier, alerts, notification_stop, capture, daily_logger,
        ), name="securegate-telegram", daemon=True)
        sender.start()
        commander = Thread(target=command_worker, args=(
            notifier, daily_logger, access_log, command_stop,
            args.telegram_poll, args.logs_limit,
        ), name="securegate-commands", daemon=True)
        commander.start()
    for worker in workers:
        worker.start()
    try:
        runtime_status.update("running", args.methods, args.door_mode)
    except (OSError, ValueError, sqlite3.Error):
        _emit("[ADVERTENCIA] No se pudo publicar el estado inicial del runtime.", daily_logger)
    last_heartbeat = time.monotonic()
    try:
        while True:
            if time.monotonic() - last_heartbeat >= 5:
                try:
                    runtime_status.update("running", args.methods, args.door_mode)
                except (OSError, ValueError, sqlite3.Error):
                    _emit("[ADVERTENCIA] No se pudo actualizar el heartbeat.", daily_logger)
                last_heartbeat = time.monotonic()
            try:
                event = events.get(timeout=0.5)
            except Empty:
                if not any(worker.is_alive() for worker in workers):
                    _emit("[ERROR] Todos los lectores se detuvieron.", daily_logger)
                    return 1
                continue
            if isinstance(event, str):
                _emit(event, daily_logger)
                continue
            result = f"USUARIO VÁLIDO: {event.user}" if event.granted else "USUARIO NO AUTORIZADO"
            alert = controller.process(event)
            restricted = is_restricted_time(event.occurred_at)
            _emit(
                f"[ACCESO] {event.method}: {result}; rechazos consecutivos={controller.failures}",
                daily_logger,
                moment=event.occurred_at,
            )
            if alert:
                _emit(f"[ALERTA] {'; '.join(alert.reasons)}", daily_logger, moment=event.occurred_at)
                if notifier:
                    try:
                        alerts.put_nowait(alert)
                    except Full:
                        _emit("[ERROR] Cola Telegram llena; alerta no enviada. Revisar conexión.", daily_logger)

            door_status = "not_requested"
            if event.granted:
                try:
                    door_status = door.open().status
                except DoorControlError as exc:
                    door_status = "error"
                    _emit(f"[ERROR] Puerta: {exc}", daily_logger)

            try:
                access_log.record(
                    event,
                    restricted,
                    alert.reasons if alert else (),
                    door_status,
                )
            except (OSError, ValueError, sqlite3.Error) as exc:
                _emit(f"[ERROR] No se pudo guardar el registro de acceso: {exc}", daily_logger)
    except KeyboardInterrupt:
        _emit("\n[INFO] Deteniendo secureGate.", daily_logger)
        return 0
    finally:
        stop.set()
        for worker in workers:
            worker.join(timeout=args.timeout + 2)
        notification_stop.set()
        command_stop.set()
        if sender:
            sender.join(timeout=12)
            if sender.is_alive():
                _emit("[ADVERTENCIA] Hay alertas pendientes que se perderán al salir.", daily_logger)
        if commander:
            commander.join(timeout=12)
        if door:
            try:
                door.close()
            except Exception:
                print("[ADVERTENCIA] No se pudo liberar limpiamente el GPIO del relé.")
        if runtime_status:
            try:
                runtime_status.update("stopped", args.methods, args.door_mode)
            except (OSError, ValueError, sqlite3.Error):
                pass


if __name__ == "__main__":
    sys.exit(main())
