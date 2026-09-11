"""P72: Betriebsseite (Backend).

Ollama wird NICHT echt aufgerufen - urllib.request.urlopen wird in
app.routers.beleg_auswertung gemockt (dort liegt die Erreichbarkeitspruefung,
die betrieb.uebersicht() wiederverwendet). Kein FINANZ_TEST_AUTH_BYPASS in
dieser Suite: die meisten Tests rufen die Router-Funktionen direkt auf (wie
tests/test_beleg_auswertung.py), der 503-Test prueft die Middleware ueber die
echte ASGI-App, laeuft aber unauthentifiziert durch - die schreibschutz_
middleware in app/main.py greift vor der Auth-Pruefung (siehe Kommentar dort
bzw. Registrierungsreihenfolge in app/main.py)."""
import asyncio
import json
import os
import subprocess
import tempfile
import unittest
import urllib.error
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import urlsplit

TEST_DIR = tempfile.TemporaryDirectory(prefix="finanz-p72-betrieb-")
os.environ["FINANZ_DB"] = str(Path(TEST_DIR.name) / "p72-betrieb-test.db")

from app import backup
from app.bereiche import Bereich
from app.db import get_connection, init_db
from app.routers import beleg_auswertung, betrieb

REPO_ROOT = Path(__file__).resolve().parent.parent


def _dummy_request(schreibgeschuetzt=False):
    """Minimaler Ersatz fuer fastapi.Request: uebersicht() liest nur app.state."""
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(schreibgeschuetzt=schreibgeschuetzt)))


def _urlopen_erreichbar(*_a, **_kw):
    class _Antwort:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return json.dumps({"models": [{"name": beleg_auswertung.OLLAMA_MODEL}]}).encode("utf-8")

    return _Antwort()


def _urlopen_nicht_erreichbar(*_a, **_kw):
    raise urllib.error.URLError("kein Ollama erreichbar (Test)")


class BetriebUebersichtTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()

    def setUp(self):
        con = get_connection()
        try:
            con.execute("DELETE FROM beleg_auswertung")
            con.execute("DELETE FROM beleg")
            con.commit()
            self.sparte_id = con.execute(
                "INSERT INTO sparte(name, typ) VALUES('Testsparte P72', 'privat')"
            ).lastrowid
            con.commit()
            self.beleg_ids = []
            for _ in range(3):
                cur = con.execute(
                    "INSERT INTO beleg(sparte_id, dateiname, pfad) VALUES(?, 'x.jpg', '/tmp/x.jpg')",
                    (self.sparte_id,),
                )
                self.beleg_ids.append(cur.lastrowid)
            con.commit()
            for beleg_id, status in zip(self.beleg_ids, ("offen", "laeuft", "fehler")):
                con.execute(
                    "INSERT INTO beleg_auswertung(beleg_id, status) VALUES(?, ?)",
                    (beleg_id, status),
                )
            con.commit()
        finally:
            con.close()

    def _uebersicht(self, schreibgeschuetzt=False):
        con = get_connection()
        try:
            return betrieb.uebersicht(_dummy_request(schreibgeschuetzt), con, Bereich(1))
        finally:
            con.close()

    def test_uebersicht_enthaelt_alle_felder_ohne_geheimnisse(self):
        with patch("app.routers.beleg_auswertung.urllib.request.urlopen", _urlopen_erreichbar):
            daten = self._uebersicht()

        for feld in ("schema", "sicherung", "schreibgeschuetzt", "ollama",
                     "ki_vorschlag_aktiv", "frontend", "instanz", "auswertungswarteschlange"):
            self.assertIn(feld, daten)
        self.assertEqual({"modell", "url", "erreichbar"}, set(daten["ollama"]))
        self.assertTrue(daten["ollama"]["erreichbar"])
        self.assertEqual({"offen": 1, "laeuft": 1, "fehler": 1}, daten["auswertungswarteschlange"])

        # Keine Auth-/Session-/Pfad-Geheimnisse in der Antwort - die komplette
        # Serialisierung (kleingeschrieben) nach verbotenen Bruchstuecken durchsuchen,
        # statt nur einzelne Felder stichprobenartig zu pruefen.
        serialisiert = json.dumps(daten, ensure_ascii=False).lower()
        for verboten in ("auth.json", "finanz_session", "session_secret", "passwort_hash", "cookie"):
            self.assertNotIn(verboten, serialisiert)

    def test_ollama_nicht_erreichbar_wird_gemeldet(self):
        with patch("app.routers.beleg_auswertung.urllib.request.urlopen", _urlopen_nicht_erreichbar):
            daten = self._uebersicht()
        self.assertFalse(daten["ollama"]["erreichbar"])

    def test_schreibgeschuetzt_wird_durchgereicht(self):
        with patch("app.routers.beleg_auswertung.urllib.request.urlopen", _urlopen_nicht_erreichbar):
            daten = self._uebersicht(schreibgeschuetzt=True)
        self.assertTrue(daten["schreibgeschuetzt"])


class BetriebSicherungTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="finanz-p72-sicherung-"))
        self.addCleanup(lambda: __import__("shutil").rmtree(self.root, ignore_errors=True))
        self.source = self.root / "quelle.db"
        import sqlite3
        con = sqlite3.connect(self.source)
        con.execute("CREATE TABLE marker(wert TEXT NOT NULL)")
        con.execute("CREATE TABLE beleg(id INTEGER PRIMARY KEY, dateiname TEXT NOT NULL, pfad TEXT NOT NULL, sparte_id INTEGER)")
        con.execute("INSERT INTO marker(wert) VALUES('p72')")
        con.commit()
        con.close()

    def _source_connection(self):
        import sqlite3
        return sqlite3.connect(self.source)

    def test_sicherung_liefert_ergebnis(self):
        with (
            patch.object(backup, "DB_PATH", self.source),
            patch.object(backup, "DB_PERSISTENT", True),
            patch.object(backup, "get_connection", self._source_connection),
        ):
            ergebnis = asyncio.run(betrieb.sicherung_starten())
        self.assertEqual("ok", ergebnis["datenbank"])
        self.assertEqual("ok", ergebnis["belege"])

    def test_409_bei_laufender_sicherung(self):
        # Sperre haelt bereits jemand anderes - der Endpunkt darf keine zweite starten.
        backup.sicherungs_lock.acquire()
        try:
            from fastapi import HTTPException
            with self.assertRaises(HTTPException) as cm:
                asyncio.run(betrieb.sicherung_starten())
            self.assertEqual(409, cm.exception.status_code)
        finally:
            backup.sicherungs_lock.release()


def _asgi_request(app, method, path, schreibgeschuetzt=True):
    """Minimaler ASGI-Aufruf (Muster tests/test_bereiche.py::request), hier nur fuer
    den Nachweis, dass die schreibschutz_middleware POST /api/betrieb/sicherung schon
    vor der Route mit 503 abweist - ganz ohne Login/Session noetig, weil diese
    Middleware (Registrierungsreihenfolge in app/main.py) vor der Auth-Pruefung laeuft."""
    parts = urlsplit(path)
    scope = {
        "type": "http", "asgi": {"version": "3.0", "spec_version": "2.4"},
        "http_version": "1.1", "method": method, "scheme": "http",
        "path": parts.path, "raw_path": parts.path.encode(), "query_string": parts.query.encode(),
        "headers": [(b"host", b"localhost")], "client": ("127.0.0.1", 50000),
        "server": ("localhost", 80), "root_path": "",
    }
    messages = []

    async def run():
        sent = False
        complete = asyncio.Event()

        async def receive():
            nonlocal sent
            if not sent:
                sent = True
                return {"type": "http.request", "body": b""}
            await complete.wait()
            return {"type": "http.disconnect"}

        async def send(message):
            messages.append(message)
            if message["type"] == "http.response.body" and not message.get("more_body"):
                complete.set()

        await app(scope, receive, send)

    asyncio.run(run())
    status = next(m["status"] for m in messages if m["type"] == "http.response.start")
    content = b"".join(m.get("body", b"") for m in messages if m["type"] == "http.response.body")
    try:
        return status, json.loads(content)
    except (ValueError, UnicodeDecodeError):
        return status, content


class BetriebSicherungSchreibschutzTest(unittest.TestCase):
    """503, wenn app.state.schreibgeschuetzt gesetzt ist - ueber die echte Middleware,
    nicht ueber einen eigenen Pruefpfad im Router (Auftrag P72: keine zweite
    Implementierung neben der bereits vorhandenen schreibschutz_middleware)."""

    def test_503_bei_schreibgeschuetzter_datenbank(self):
        from app.main import app
        with (
            patch.object(app.state, "schreibgeschuetzt", True),
            patch.object(app.state, "migrationsfehler", "Test-Nachzugsfehler"),
        ):
            status, body = _asgi_request(app, "POST", "/api/betrieb/sicherung")
        self.assertEqual(503, status)
        self.assertIn("Nachzug", body["detail"])


class BetriebJsSyntaxTest(unittest.TestCase):
    def test_node_check_betrieb_js(self):
        self._node_check(REPO_ROOT / "static-neu" / "pages" / "betrieb.js")

    def test_node_check_app_js(self):
        self._node_check(REPO_ROOT / "static-neu" / "app.js")

    def _node_check(self, pfad):
        try:
            ergebnis = subprocess.run(
                ["node", "--check", str(pfad)], capture_output=True, text=True, timeout=30,
            )
        except FileNotFoundError:
            self.skipTest("node ist auf diesem System nicht installiert")
        self.assertEqual(0, ergebnis.returncode, ergebnis.stderr)


if __name__ == "__main__":
    unittest.main()
