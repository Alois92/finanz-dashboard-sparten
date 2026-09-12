"""F2: Wettlauf bei Rueckerstattungen - parallele Aufrufe erstatten beliebig
ueber den Originalbetrag hinaus. Regressionstest gegen eine echte
Server-Instanz (eigener Prozess, echte Anmeldung, echte Nebenlaeufigkeit
ueber ThreadPoolExecutor), damit die Rennbedingung tatsaechlich auftritt -
ein einzelner in-process Testclient mit geteilter Verbindung wuerde sie
nicht zeigen.
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


class ErstattungRaceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tempdir = tempfile.TemporaryDirectory(prefix="finanz-f2-race-")
        cls.addClassCleanup(cls.tempdir.cleanup)
        cls.db_path = Path(cls.tempdir.name) / "test.db"

        # Schema/Seed vorab einspielen und eine Ausgabe mit einer
        # 'beides'-Kategorie anlegen, damit sie direkt erstattbar ist.
        con = sqlite3.connect(cls.db_path)
        con.executescript(db.SCHEMA.read_text(encoding="utf-8"))
        con.executescript(db.SEED.read_text(encoding="utf-8"))
        sparte_id = con.execute(
            "SELECT id FROM sparte WHERE typ <> 'verein' ORDER BY id LIMIT 1"
        ).fetchone()[0]
        kat_id = con.execute(
            "INSERT INTO kategorie(sparte_id, name, richtung) VALUES(?, 'F2-Race', 'beides')",
            (sparte_id,),
        ).lastrowid
        buchung_id = con.execute(
            "INSERT INTO buchung(sparte_id, datum, typ, zahlungsart, text) "
            "VALUES(?, '2026-01-13', 'ausgabe', 'bar', 'F2 Race Original')",
            (sparte_id,),
        ).lastrowid
        con.execute(
            "INSERT INTO buchungszeile(buchung_id, kategorie_id, betrag_cent) VALUES(?, ?, 10000)",
            (buchung_id, kat_id),
        )
        con.commit()
        con.close()
        cls.buchung_id = buchung_id

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

    def _erstatten(self):
        body = json.dumps({
            "datum": "2026-01-13",
            "zeilen": [{"original_zeile_id": self._zeile_id(), "betrag_cent": 10000}],
        }).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}/api/buchungen/{self.buchung_id}/erstatten?bereich_id=1",
            data=body,
            headers={"Content-Type": "application/json", "Cookie": self.cookie},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return response.status
        except urllib.error.HTTPError as exc:
            return exc.code

    def _zeile_id(self):
        if not hasattr(self, "_zeile_id_cache"):
            request = urllib.request.Request(
                f"{self.base_url}/api/buchungen/{self.buchung_id}?bereich_id=1",
                headers={"Cookie": self.cookie},
            )
            with urllib.request.urlopen(request, timeout=5) as response:
                daten = json.loads(response.read())
            self._zeile_id_cache = daten["zeilen"][0]["id"]
        return self._zeile_id_cache

    def test_acht_parallele_erstattungen_lassen_nur_eine_zu(self):
        with ThreadPoolExecutor(max_workers=8) as pool:
            ergebnisse = list(pool.map(lambda _: self._erstatten(), range(8)))

        self.assertEqual(1, ergebnisse.count(201), ergebnisse)
        self.assertEqual(7, ergebnisse.count(422), ergebnisse)

        request = urllib.request.Request(
            f"{self.base_url}/api/buchungen/{self.buchung_id}?bereich_id=1",
            headers={"Cookie": self.cookie},
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            daten = json.loads(response.read())
        self.assertEqual(0, daten["netto_cent"])
        self.assertEqual(1, len(daten["erstattungen"]))


if __name__ == "__main__":
    unittest.main()
