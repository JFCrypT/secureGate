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
from securegate.alerts.schedule import is_restricted_time
from securegate.alerts.telegram import TelegramDeliveryError
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


def notification_worker(notifier, alerts, stop, capture=None):
    while not stop.is_set() or not alerts.empty():
        try:
            alert = alerts.get(timeout=0.2)
        except Empty:
            continue
        try:
            deliver_alert(notifier, alert, capture)
            print("[ALERTA] Telegram confirmó la recepción.", flush=True)
        except TelegramDeliveryError as exc:
            print(f"[ERROR] Telegram: {exc}", flush=True)
        except Exception:
            print("[ERROR] No se pudo enviar la alerta Telegram.", flush=True)
        finally:
            alerts.task_done()


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
    args = parser.parse_args()
    if args.methods != "rfid" and not args.url:
        parser.error("Se requiere URL de cámara para reconocimiento facial.")

    reader = None
    door = None
    runtime_status = None
    try:
        timezone = load_timezone(args.timezone)
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

    print(f"[INFO] Métodos: {args.methods}; zona horaria: {args.timezone}")
    print("[INFO] Autorización alternativa: facial O RFID.")
    if args.door_mode == "simulate":
        print("[INFO] Puerta en simulación: no se activa ningún GPIO.")
    else:
        print(
            f"[INFO] Puerta física: GPIO BCM {args.relay_pin}, "
            f"activo en {args.relay_active.upper()}.",
        )
    print("[INFO] Retirar rostro/tarjeta entre intentos. Ctrl+C para detener.")
    print("[INFO] Telegram habilitado." if notifier else "[ADVERTENCIA] Telegram deshabilitado: faltan token y chat.")
    events = Queue(maxsize=32)
    alerts = Queue(maxsize=8)
    stop = Event()
    notification_stop = Event()
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
    if notifier:
        capture = None
        if args.url:
            # A separate capture avoids sharing the facial recognizer across threads.
            def capture():
                from runtime_recognize_espcam import capture_frame
                return capture_frame(args.url, args.timeout)
        sender = Thread(target=notification_worker, args=(
            notifier, alerts, notification_stop, capture,
        ), name="securegate-telegram", daemon=True)
        sender.start()
    for worker in workers:
        worker.start()
    try:
        runtime_status.update("running", args.methods, args.door_mode)
    except (OSError, ValueError, sqlite3.Error):
        print("[ADVERTENCIA] No se pudo publicar el estado inicial del runtime.")
    last_heartbeat = time.monotonic()
    try:
        while True:
            if time.monotonic() - last_heartbeat >= 5:
                try:
                    runtime_status.update("running", args.methods, args.door_mode)
                except (OSError, ValueError, sqlite3.Error):
                    print("[ADVERTENCIA] No se pudo actualizar el heartbeat.", flush=True)
                last_heartbeat = time.monotonic()
            try:
                event = events.get(timeout=0.5)
            except Empty:
                if not any(worker.is_alive() for worker in workers):
                    print("[ERROR] Todos los lectores se detuvieron.")
                    return 1
                continue
            if isinstance(event, str):
                print(event, flush=True)
                continue
            result = f"USUARIO VÁLIDO: {event.user}" if event.granted else "USUARIO NO AUTORIZADO"
            alert = controller.process(event)
            restricted = is_restricted_time(event.occurred_at)
            print(f"[ACCESO] {event.method}: {result}; rechazos consecutivos={controller.failures}", flush=True)
            if alert:
                print(f"[ALERTA] {'; '.join(alert.reasons)}", flush=True)
                if notifier:
                    try:
                        alerts.put_nowait(alert)
                    except Full:
                        print("[ERROR] Cola Telegram llena; alerta no enviada. Revisar conexión.", flush=True)

            door_status = "not_requested"
            if event.granted:
                try:
                    door_status = door.open().status
                except DoorControlError as exc:
                    door_status = "error"
                    print(f"[ERROR] Puerta: {exc}", flush=True)

            try:
                access_log.record(
                    event,
                    restricted,
                    alert.reasons if alert else (),
                    door_status,
                )
            except (OSError, ValueError, sqlite3.Error) as exc:
                print(f"[ERROR] No se pudo guardar el registro de acceso: {exc}", flush=True)
    except KeyboardInterrupt:
        print("\n[INFO] Deteniendo secureGate.")
        return 0
    finally:
        stop.set()
        for worker in workers:
            worker.join(timeout=args.timeout + 2)
        notification_stop.set()
        if sender:
            sender.join(timeout=12)
            if sender.is_alive():
                print("[ADVERTENCIA] Hay alertas pendientes que se perderán al salir.")
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
