"""Integrationstests fuer Auth-Ersteinrichtung und Zugangswiederherstellung."""
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from app.auth import hash_password
from app.auth_store import AuthConfig, AuthConfigStore


APP_DIR = Path(__file__).resolve().parents[1]
START_PASSWORD = "Start!1"
INITIAL_PASSWORD = "Ab3!xy"


def _freier_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@dataclass
class _Antwort:
    status: int
    body: bytes
    headers: object

    def json(self):
        return json.loads(self.body.decode("utf-8"))


class AuthLifecycleIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.auth_path = Path(self.tempdir.name) / "auth.json"
        self.store = AuthConfigStore(self.auth_path)
        config = AuthConfig(
            password_hash=hash_password(START_PASSWORD),
            session_secret="s" * 64,
            recovery_hash=None,
            must_change_password=True,
            version=1,
        )
        self.store.save(config)
        self.port = _freier_port()
        self.base_url = f"http://127.0.0.1:{self.port}"
        env = os.environ.copy()
        env["FINANZ_DB"] = str(Path(self.tempdir.name) / "test.db")
        env["FINANZ_AUTH_FILE"] = str(self.auth_path)
        # Ermoeglicht den fachlich fokussierten RED-Lauf, solange der Store
        # noch nicht durch den Produktcode verdrahtet ist.
        env["FINANZ_AUTH_PASSWORD_HASH"] = config.password_hash
        env["FINANZ_SESSION_SECRET"] = config.session_secret
        self.server = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "app.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(self.port),
                "--log-level",
                "warning",
            ],
            cwd=APP_DIR,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for _ in range(100):
            if self.server.poll() is not None:
                stdout, stderr = self.server.communicate()
                raise RuntimeError(f"Uvicorn beendet.\n{stdout}\n{stderr}")
            try:
                if self.request("/api/health").status == 200:
                    break
            except urllib.error.URLError:
                time.sleep(0.05)
        else:
            raise RuntimeError("Uvicorn war nicht rechtzeitig bereit.")

    def tearDown(self):
        self.server.terminate()
        try:
            self.server.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            self.server.kill()
            self.server.communicate(timeout=5)
        self.tempdir.cleanup()

    def request(self, path, payload=None, cookie=None, method=None):
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=data,
            headers={
                **({"Content-Type": "application/json"} if data else {}),
                **({"Cookie": cookie} if cookie else {}),
            },
            method=method or ("POST" if data is not None else "GET"),
        )
        try:
            with urllib.request.urlopen(request, timeout=2) as response:
                return _Antwort(response.status, response.read(), response.headers)
        except urllib.error.HTTPError as error:
            return _Antwort(error.code, error.read(), error.headers)

    def get(self, path, cookie):
        return self.request(path, cookie=cookie)

    def get_status(self, path, cookie):
        return self.get(path, cookie).status

    def post(self, path, payload, cookie):
        return self.request(path, payload, cookie)

    def post_public(self, path, payload):
        return self.request(path, payload)

    def post_raw(self, path, body, cookie=None):
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=body,
            headers={
                "Content-Type": "application/json",
                **({"Cookie": cookie} if cookie else {}),
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=2) as response:
                return _Antwort(response.status, response.read(), response.headers)
        except urllib.error.HTTPError as error:
            return _Antwort(error.code, b"", error.headers)

    def login(self, password):
        response = self.post_public("/api/auth/login", {"password": password})
        self.assertEqual(response.status, 204)
        return response.headers["Set-Cookie"].split(";", 1)[0]

    def complete_initial_setup(self):
        cookie = self.login(START_PASSWORD)
        response = self.post(
            "/api/auth/initial-password",
            {"new_password": INITIAL_PASSWORD, "repeat_password": INITIAL_PASSWORD},
            cookie,
        )
        self.assertEqual(response.status, 200)
        return response.json()["recovery_code"]

    def test_startpasswort_erlaubt_nur_ersteinrichtung(self):
        cookie = self.login(START_PASSWORD)
        self.assertEqual(
            self.get("/api/auth/state", cookie).json(),
            {"must_change_password": True},
        )
        self.assertEqual(self.get_status("/api/sparten", cookie), 403)

    def test_ersteinrichtung_gibt_code_einmal_aus(self):
        cookie = self.login(START_PASSWORD)
        response = self.post(
            "/api/auth/initial-password",
            {"new_password": INITIAL_PASSWORD, "repeat_password": INITIAL_PASSWORD},
            cookie,
        )
        self.assertEqual(response.status, 200)
        recovery_code = response.json()["recovery_code"]
        self.assertRegex(recovery_code, r"^(?:[A-Z2-9]{4}-){6}[A-Z2-9]{4}$")
        config = self.store.load()
        self.assertFalse(config.must_change_password)
        self.assertNotIn(recovery_code, self.auth_path.read_text(encoding="utf-8"))

    def test_ersteinrichtung_lehnt_ungueltige_eingaben_ab(self):
        cookie = self.login(START_PASSWORD)
        mismatch = self.post(
            "/api/auth/initial-password",
            {"new_password": INITIAL_PASSWORD, "repeat_password": "anders"},
            cookie,
        )
        self.assertEqual(mismatch.status, 422)
        invalid = self.post(
            "/api/auth/initial-password",
            {"new_password": "kurz", "repeat_password": "kurz"},
            cookie,
        )
        self.assertEqual(invalid.status, 422)
        self.assertTrue(self.store.load().must_change_password)

    def test_ersteinrichtung_kann_nicht_wiederholt_werden(self):
        self.complete_initial_setup()
        cookie = self.login(INITIAL_PASSWORD)
        response = self.post(
            "/api/auth/initial-password",
            {"new_password": "Neu#77", "repeat_password": "Neu#77"},
            cookie,
        )
        self.assertEqual(response.status, 409)

    def test_passwortaenderung_widerruft_alte_sitzung(self):
        self.complete_initial_setup()
        cookie = self.login(INITIAL_PASSWORD)
        response = self.post(
            "/api/auth/change-password",
            {
                "current_password": INITIAL_PASSWORD,
                "new_password": "Neu#77",
                "repeat_password": "Neu#77",
            },
            cookie,
        )
        self.assertEqual(response.status, 204)
        self.assertEqual(self.get_status("/api/sparten", cookie), 401)
        self.assertEqual(self.get_status("/api/sparten", self.login("Neu#77")), 200)

    def test_passwortaenderung_lehnt_fehlerhafte_eingaben_ab(self):
        self.complete_initial_setup()
        cookie = self.login(INITIAL_PASSWORD)
        incorrect = self.post(
            "/api/auth/change-password",
            {
                "current_password": "falsch",
                "new_password": "Neu#77",
                "repeat_password": "Neu#77",
            },
            cookie,
        )
        self.assertEqual(incorrect.status, 401)
        mismatch = self.post(
            "/api/auth/change-password",
            {
                "current_password": INITIAL_PASSWORD,
                "new_password": "Neu#77",
                "repeat_password": "anders",
            },
            cookie,
        )
        self.assertEqual(mismatch.status, 422)
        self.assertEqual(self.get_status("/api/sparten", cookie), 200)

    def test_recovery_rotiert_code_und_lehnt_wiederverwendung_ab(self):
        first_code = self.complete_initial_setup()
        response = self.post_public(
            "/api/auth/recover",
            {
                "recovery_code": first_code,
                "new_password": "Reset!8",
                "repeat_password": "Reset!8",
            },
        )
        self.assertEqual(response.status, 200)
        new_code = response.json()["recovery_code"]
        self.assertNotEqual(new_code, first_code)
        reused = self.post_public(
            "/api/auth/recover",
            {
                "recovery_code": first_code,
                "new_password": "NochNeu9!",
                "repeat_password": "NochNeu9!",
            },
        )
        self.assertEqual(reused.status, 401)
        self.assertEqual(self.get_status("/api/sparten", self.login("Reset!8")), 200)

    def test_recovery_lehnt_fehlerhafte_eingaben_ab(self):
        recovery_code = self.complete_initial_setup()
        unknown = self.post_public(
            "/api/auth/recover",
            {
                "recovery_code": "AAAA-BBBB-CCCC-DDDD-EEEE-FFFF-GGGG",
                "new_password": "Reset!8",
                "repeat_password": "Reset!8",
            },
        )
        self.assertEqual(unknown.status, 401)
        mismatch = self.post_public(
            "/api/auth/recover",
            {
                "recovery_code": recovery_code,
                "new_password": "Reset!8",
                "repeat_password": "anders",
            },
        )
        self.assertEqual(mismatch.status, 422)
        invalid = self.post_public(
            "/api/auth/recover",
            {
                "recovery_code": recovery_code,
                "new_password": "kurz",
                "repeat_password": "kurz",
            },
        )
        self.assertEqual(invalid.status, 422)

    def test_recovery_lehnt_malformedes_json_neutral_ab(self):
        response = self.post_raw("/api/auth/recover", b"{")
        self.assertEqual(response.status, 401)

    def test_recovery_lehnt_json_array_neutral_ab(self):
        response = self.post_raw("/api/auth/recover", b"[]")
        self.assertEqual(response.status, 401)

    def test_recovery_lehnt_ungueltiges_utf8_neutral_ab(self):
        response = self.post_raw("/api/auth/recover", b"\xff")
        self.assertEqual(response.status, 401)

    def test_recovery_sperrt_nach_fuenf_ungueltigen_payloads(self):
        for _ in range(5):
            response = self.post_raw("/api/auth/recover", b"{")
            self.assertEqual(response.status, 401)
        blocked = self.post_raw("/api/auth/recover", b"{")
        self.assertEqual(blocked.status, 429)

    def test_ersteinrichtung_lehnt_malformedes_json_ab(self):
        cookie = self.login(START_PASSWORD)
        response = self.post_raw("/api/auth/initial-password", b"{", cookie)
        self.assertEqual(response.status, 422)

    def test_ersteinrichtung_lehnt_json_array_ab(self):
        cookie = self.login(START_PASSWORD)
        response = self.post_raw("/api/auth/initial-password", b"[]", cookie)
        self.assertEqual(response.status, 422)

    def test_ersteinrichtung_lehnt_ungueltiges_utf8_ab(self):
        cookie = self.login(START_PASSWORD)
        response = self.post_raw("/api/auth/initial-password", b"\xff", cookie)
        self.assertEqual(response.status, 422)

    def test_passwortaenderung_lehnt_malformedes_json_ab(self):
        self.complete_initial_setup()
        cookie = self.login(INITIAL_PASSWORD)
        response = self.post_raw("/api/auth/change-password", b"{", cookie)
        self.assertEqual(response.status, 422)

    def test_passwortaenderung_lehnt_json_array_ab(self):
        self.complete_initial_setup()
        cookie = self.login(INITIAL_PASSWORD)
        response = self.post_raw("/api/auth/change-password", b"[]", cookie)
        self.assertEqual(response.status, 422)

    def test_passwortaenderung_lehnt_ungueltiges_utf8_ab(self):
        self.complete_initial_setup()
        cookie = self.login(INITIAL_PASSWORD)
        response = self.post_raw("/api/auth/change-password", b"\xff", cookie)
        self.assertEqual(response.status, 422)


if __name__ == "__main__":
    unittest.main()
