"""Sicherheits-Regressionstests fuer den Zugriff auf das Finanzstudio."""
import base64
import hashlib
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
from pathlib import Path

from tests._process_cleanup import cleanup_process_tree


APP_DIR = Path(__file__).resolve().parents[1]
PASSWORT = "Korrektes-Testpasswort-2026!"


def _passwort_hash(passwort: str) -> str:
    salt = b"0123456789abcdef"
    wert = hashlib.scrypt(
        passwort.encode("utf-8"), salt=salt, n=2**14, r=8, p=1, dklen=32
    )

    def b64(data):
        return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")

    return f"scrypt$16384$8$1${b64(salt)}${b64(wert)}"


def _freier_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class _KeineWeiterleitung(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class AuthIntegrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tempdir = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tempdir.cleanup)
        cls.port = _freier_port()
        cls.base_url = f"http://127.0.0.1:{cls.port}"
        env = os.environ.copy()
        env["FINANZ_DB"] = str(Path(cls.tempdir.name) / "test.db")
        env["FINANZ_AUTH_FILE"] = str(Path(cls.tempdir.name) / "auth.json")
        env["FINANZ_AUTH_PASSWORD_HASH"] = _passwort_hash(PASSWORT)
        env["FINANZ_SESSION_SECRET"] = (
            "testsitzungsschluessel-mit-mindestens-32-zeichen"
        )
        cls.server = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "app.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(cls.port),
                "--log-level",
                "warning",
            ],
            cwd=APP_DIR,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        cls.addClassCleanup(cleanup_process_tree, cls.server)
        for _ in range(100):
            if cls.server.poll() is not None:
                stdout, stderr = cls.server.communicate()
                raise RuntimeError(f"Uvicorn beendet.\n{stdout}\n{stderr}")
            try:
                with urllib.request.urlopen(
                    f"{cls.base_url}/api/health", timeout=0.5
                ) as response:
                    if response.status == 200:
                        break
            except (urllib.error.URLError, TimeoutError):
                time.sleep(0.05)
        else:
            raise RuntimeError("Uvicorn war nicht rechtzeitig bereit.")

    def test_api_ist_ohne_anmeldung_gesperrt(self):
        with self.assertRaises(urllib.error.HTTPError) as raised:
            urllib.request.urlopen(f"{self.base_url}/api/sparten", timeout=2)
        self.assertEqual(raised.exception.code, 401)

    def test_browser_wird_auf_vorhandene_loginseite_umgeleitet(self):
        opener = urllib.request.build_opener(_KeineWeiterleitung)
        with self.assertRaises(urllib.error.HTTPError) as raised:
            opener.open(f"{self.base_url}/", timeout=2)
        self.assertEqual(raised.exception.code, 303)
        self.assertEqual(raised.exception.headers["Location"], "/login.html")

        with urllib.request.urlopen(
            f"{self.base_url}/login.html", timeout=2
        ) as response:
            html = response.read().decode("utf-8")
        self.assertIn('id="login-form"', html)
        self.assertIn('autocomplete="current-password"', html)

    def _login(self, passwort=PASSWORT):
        request = urllib.request.Request(
            f"{self.base_url}/api/auth/login",
            data=json.dumps({"password": passwort}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        return urllib.request.urlopen(request, timeout=2)

    def test_login_setzt_sicheres_cookie_und_oeffnet_api(self):
        with self._login() as response:
            self.assertEqual(response.status, 204)
            cookie = response.headers["Set-Cookie"]
        self.assertIn("finanz_session=", cookie)
        self.assertIn("HttpOnly", cookie)
        self.assertIn("Secure", cookie)
        self.assertIn("samesite=strict", cookie.lower())
        self.assertIn("Max-Age=43200", cookie)

        cookie_wert = cookie.split(";", 1)[0]
        request = urllib.request.Request(
            f"{self.base_url}/api/sparten",
            headers={"Cookie": cookie_wert},
        )
        with urllib.request.urlopen(request, timeout=2) as response:
            self.assertEqual(response.status, 200)

    def test_falsches_passwort_wird_abgewiesen(self):
        with self.assertRaises(urllib.error.HTTPError) as raised:
            self._login("falsch")
        self.assertEqual(raised.exception.code, 401)

    def test_unbekannter_host_header_wird_abgewiesen(self):
        request = urllib.request.Request(
            f"{self.base_url}/api/health",
            headers={"Host": "angreifer.example"},
        )
        with self.assertRaises(urllib.error.HTTPError) as raised:
            urllib.request.urlopen(request, timeout=2)
        self.assertEqual(raised.exception.code, 400)

    def test_nicht_freigegebenes_tailscale_geraet_wird_abgewiesen(self):
        request = urllib.request.Request(
            f"{self.base_url}/api/health",
            headers={"X-Forwarded-For": "100.72.201.96"},
        )
        with self.assertRaises(urllib.error.HTTPError) as raised:
            urllib.request.urlopen(request, timeout=2)
        self.assertEqual(raised.exception.code, 403)

    def test_freigegebenes_tailscale_geraet_erreicht_den_login(self):
        request = urllib.request.Request(
            f"{self.base_url}/api/health",
            headers={"X-Forwarded-For": "100.105.4.18"},
        )
        with urllib.request.urlopen(request, timeout=2) as response:
            self.assertEqual(response.status, 200)

    def test_manipuliertes_cookie_wird_abgewiesen(self):
        request = urllib.request.Request(
            f"{self.base_url}/api/sparten",
            headers={"Cookie": "finanz_session=manipuliert"},
        )
        with self.assertRaises(urllib.error.HTTPError) as raised:
            urllib.request.urlopen(request, timeout=2)
        self.assertEqual(raised.exception.code, 401)

    def test_logout_loescht_cookie(self):
        with self._login() as response:
            cookie = response.headers["Set-Cookie"].split(";", 1)[0]
        request = urllib.request.Request(
            f"{self.base_url}/api/auth/logout",
            headers={"Cookie": cookie},
            data=b"",
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=2) as response:
            self.assertEqual(response.status, 204)
            geloescht = response.headers["Set-Cookie"]
        self.assertIn("finanz_session=", geloescht)
        self.assertIn("Max-Age=0", geloescht)

        wiederverwendung = urllib.request.Request(
            f"{self.base_url}/api/sparten",
            headers={"Cookie": cookie},
        )
        with self.assertRaises(urllib.error.HTTPError) as raised:
            urllib.request.urlopen(wiederverwendung, timeout=2)
        self.assertEqual(raised.exception.code, 401)


if __name__ == "__main__":
    unittest.main()
