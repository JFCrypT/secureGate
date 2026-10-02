from contextlib import closing
from datetime import datetime
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "raspberry"))

from init_db import SCHEMA
from securegate.access import AccessEvent
from securegate.access_log import AccessLogRepository
from securegate.alerts.schedule import load_timezone
from securegate.api import create_app
from securegate.rfid.registry import CardRegistry


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.database = Path(self.temp.name) / "securegate.db"
        with closing(sqlite3.connect(self.database)) as connection:
            connection.executescript(SCHEMA)
        self.token = "test-token-" + "x" * 32
        self.client = TestClient(
            create_app(
                self.database,
                self.token,
                cors_origins=["http://localhost:3000"],
            )
        )
        self.auth = {"Authorization": f"Bearer {self.token}"}

    def test_health_is_public_but_data_requires_bearer_token(self):
        self.assertEqual(self.client.get("/health").status_code, 200)
        unauthorized = self.client.get("/api/v1/users")
        self.assertEqual(unauthorized.status_code, 401)
        self.assertEqual(unauthorized.headers["www-authenticate"], "Bearer")
        self.assertEqual(
            self.client.get(
                "/api/v1/users",
                headers={"Authorization": "Bearer wrong"},
            ).status_code,
            401,
        )

    def test_create_list_get_and_disable_user(self):
        response = self.client.post(
            "/api/v1/users",
            headers=self.auth,
            json={
                "external_id": "user_005",
                "first_name": "Ana",
                "last_name": "Pérez",
                "role": "docente",
            },
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["external_id"], "user_005")
        self.assertEqual(response.json()["first_name"], "Ana")
        self.assertEqual(
            self.client.post(
                "/api/v1/users",
                headers=self.auth,
                json={"external_id": "user_005"},
            ).status_code,
            409,
        )
        users = self.client.get("/api/v1/users", headers=self.auth).json()
        self.assertEqual(len(users), 1)
        updated = self.client.patch(
            "/api/v1/users/user_005",
            headers=self.auth,
            json={"active": False},
        )
        self.assertEqual(updated.status_code, 200)
        self.assertFalse(updated.json()["active"])
        status_response = self.client.get("/api/v1/status", headers=self.auth)
        self.assertEqual(status_response.status_code, 200)
        self.assertEqual(status_response.json()["users"]["total"], 1)
        self.assertEqual(status_response.json()["users"]["active"], 0)

    def test_rfid_enrollment_request_and_cancel(self):
        self.client.post(
            "/api/v1/users",
            headers=self.auth,
            json={"external_id": "user_008"},
        )
        created = self.client.post(
            "/api/v1/users/user_008/rfid-enrollments",
            headers=self.auth,
            json={"timeout_seconds": 60},
        )
        self.assertEqual(created.status_code, 201)
        request_id = created.json()["request_id"]
        self.assertEqual(created.json()["status"], "pending")
        fetched = self.client.get(
            f"/api/v1/rfid-enrollments/{request_id}", headers=self.auth
        )
        self.assertEqual(fetched.status_code, 200)
        cancelled = self.client.delete(
            f"/api/v1/rfid-enrollments/{request_id}", headers=self.auth
        )
        self.assertEqual(cancelled.json()["status"], "cancelled")

    def test_validation_rejects_bad_or_extra_fields(self):
        for payload in (
            {"external_id": "persona-1"},
            {"external_id": "user_001", "admin": True},
        ):
            with self.subTest(payload=payload):
                response = self.client.post(
                    "/api/v1/users", headers=self.auth, json=payload
                )
                self.assertEqual(response.status_code, 422)

    def test_access_events_filters_and_summary(self):
        log = AccessLogRepository(self.database)
        zone = load_timezone()
        log.record(
            AccessEvent("RFID", "user_001", datetime(2026, 10, 2, 22, tzinfo=zone)),
            True,
            ("Intento de ingreso fuera de horario",),
            "simulated",
        )
        log.record(
            AccessEvent("facial", None, datetime(2026, 10, 2, 12, tzinfo=zone)),
            False,
        )
        response = self.client.get(
            "/api/v1/access-events?day=2026-10-02&granted=true",
            headers=self.auth,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 1)
        self.assertEqual(response.json()[0]["method"], "RFID")
        summary = self.client.get(
            "/api/v1/access-events/summary?day=2026-10-02",
            headers=self.auth,
        ).json()
        self.assertEqual(summary["total"], 2)
        self.assertEqual(summary["granted"], 1)
        self.assertEqual(summary["denied"], 1)
        self.assertEqual(summary["restricted"], 1)

    def test_revoke_credentials_without_exposing_them(self):
        self.client.post(
            "/api/v1/users",
            headers=self.auth,
            json={"external_id": "user_006"},
        )
        key = Path(self.temp.name) / "k_rfid"
        key.write_bytes(b"r" * 32)
        CardRegistry(self.database, key).enroll("user_006", "01020304")
        with sqlite3.connect(self.database) as connection:
            connection.execute(
                """INSERT INTO biometric_templates
                   (user_id, ciphertext, nonce, model_version, algorithm_version)
                   VALUES (1, X'1234', X'5678', 'model', 'algorithm')"""
            )
        response = self.client.delete(
            "/api/v1/users/user_006/rfid", headers=self.auth
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["has_rfid"])
        response = self.client.delete(
            "/api/v1/users/user_006/face", headers=self.auth
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["has_face"])
        self.assertEqual(
            self.client.delete(
                "/api/v1/users/user_006/face", headers=self.auth
            ).status_code,
            404,
        )

    def test_cors_allows_only_configured_frontend(self):
        allowed = self.client.options(
            "/api/v1/users",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )
        self.assertEqual(allowed.status_code, 200)
        self.assertEqual(
            allowed.headers["access-control-allow-origin"],
            "http://localhost:3000",
        )


if __name__ == "__main__":
    unittest.main()
