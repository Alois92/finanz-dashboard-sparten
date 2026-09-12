"""F3: Wettlauf bei 'Beleg-Auswertung uebernehmen' - ein Beleg wird mehrfach
verbucht, weil die Statuspruefung (status == 'fertig') ausserhalb jeder
Transaktion laeuft. Regressionstest gegen eine echte Server-Instanz (eigener
Prozess, echte Anmeldung, echte Nebenlaeufigkeit ueber ThreadPoolExecutor) -
ein einzelner in-process Testclient mit geteilter Verbindung wuerde die
Rennbedingung nicht zeigen.
"""
import base64
import hashlib
import json
import os
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from app import db

from tests._process_cleanup import cleanup_process_tree

APP_DIR = Path(__file__).resolve().parents[1]
PASSWORT = "Korrektes-Testpasswort-2026!"


def _passwort_hash(passwort: str) -> str:
    salt = b"0123456789abcdef"
    wert = hashlib.scrypt(passwort.encode("utf-8"), salt=salt, n=2**14, r=8, p=1, dklen=32)

    def b64(data):
        return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")

    return f"scrypt$16384$8$1${b64(salt)}${b64(wert)}"


def _freier_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class UebernahmeRaceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tempdir = tempfile.TemporaryDirectory(prefix="finanz-f3-race-")
        cls.addClassCleanup(cls.tempdir.cleanup)
        cls.db_path = Path(cls.tempdir.name) / "test.db"

        con = sqlite3.connect(cls.db_path)
        con.executescript(db.SCHEMA.read_text(encoding="utf-8"))
        con.executescript(db.SEED.read_text(encoding="utf-8"))
        cls.sparte_id = con.execute(
            "SELECT id FROM sparte WHERE typ <> 'verein' ORDER BY id LIMIT 1"
        ).fetchone()[0]
        cls.kat_id = con.execute(
            "INSERT INTO kategorie(sparte_id, name, richtung) VALUES(?, 'F3-Race', 'ausgabe')",
            (cls.sparte_id,),
        ).lastrowid
        beleg_id = con.execute(
            "INSERT INTO beleg(sparte_id, dateiname, pfad, bereich_id) "
            "VALUES(?, 'f3-race.pdf', 'f3-race.pdf', 1)",
            (cls.sparte_id,),
        ).lastrowid
        cls.auswertung_id = con.execute(
            "INSERT INTO beleg_auswertung(beleg_id, status, ergebnis_json) "
            "VALUES(?, 'fertig', '{}')",
            (beleg_id,),
        ).lastrowid
        con.commit()
        con.close()

        cls.port = _freier_port()
        cls.base_url = f"http://127.0.0.1:{cls.port}"
        env = os.environ.copy()
        env["FINANZ_DB"] = str(cls.db_path)
        env["FINANZ_AUTH_FILE"] = str(Path(cls.tempdir.name) / "auth.json")
        env["FINANZ_AUTH_PASSWORD_HASH"] = _passwort_hash(PASSWORT)
        env["FINANZ_SESSION_SECRET"] = "testsitzungsschluessel-mit-mindestens-32-zeichen"
        env["FINANZ_INSTANZ"] = "test"
        env["FINANZ_KI_VORSCHLAG"] = "0"
        cls.server = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1",
             "--port", str(cls.port), "--log-level", "warning"],
            cwd=APP_DIR, env=env,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        cls.addClassCleanup(cleanup_process_tree, cls.server)
        for _ in range(100):
            if cls.server.poll() is not None:
                stdout, stderr = cls.server.communicate()
                raise RuntimeError(f"Uvicorn beendet.\n{stdout}\n{stderr}")
            try:
                with urllib.request.urlopen(f"{cls.base_url}/api/health", timeout=0.5) as response:
                    if response.status == 200:
                        break
            except (urllib.error.URLError, TimeoutError):
                time.sleep(0.05)
        else:
            raise RuntimeError("Uvicorn war nicht rechtzeitig bereit.")

        login = urllib.request.Request(
            f"{cls.base_url}/api/auth/login",
            data=json.dumps({"password": PASSWORT}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(login, timeout=5) as response:
            cls.cookie = response.headers["Set-Cookie"].split(";", 1)[0]

    def _uebernehmen(self, _):
        body = json.dumps({
            "sparte_id": self.sparte_id,
            "datum": "2026-09-01",
            "zahlungsart": "bar",
            "text": "F3 Race",
            "positionen": [{"kategorie_id": self.kat_id, "betrag_cent": 5000,
                             "typ": "ausgabe", "text": "F3 Race"}],
            "client_request_id": uuid.uuid4().hex,
        }).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}/api/beleg-auswertungen/{self.auswertung_id}/uebernehmen?bereich_id=1",
            data=body,
            headers={"Content-Type": "application/json", "Cookie": self.cookie},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return response.status
        except urllib.error.HTTPError as exc:
            return exc.code

    def test_acht_parallele_uebernahmen_erzeugen_nur_eine_buchung(self):
        with ThreadPoolExecutor(max_workers=8) as pool:
            ergebnisse = list(pool.map(self._uebernehmen, range(8)))

        self.assertEqual(1, ergebnisse.count(201), ergebnisse)
        self.assertEqual(7, ergebnisse.count(409), ergebnisse)

        con = sqlite3.connect(self.db_path)
        try:
            anzahl_buchungen = con.execute(
                "SELECT COUNT(*) FROM buchung WHERE sparte_id = ? AND text = 'F3 Race'",
                (self.sparte_id,),
            ).fetchone()[0]
            status = con.execute(
                "SELECT status FROM beleg_auswertung WHERE id = ?", (self.auswertung_id,)
            ).fetchone()[0]
        finally:
            con.close()
        self.assertEqual(1, anzahl_buchungen)
        self.assertEqual("verbucht", status)


if __name__ == "__main__":
    unittest.main()
