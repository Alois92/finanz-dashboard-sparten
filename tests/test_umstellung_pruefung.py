"""P62: Prüfskript für die Umstellung. Nur synthetische Wegwerf-Datenbanken.

Die „nachher"-Datenbank entsteht aus derselben Fixture wie in P61, nachgezogen
über `scripts.migrationsprobe.lauf`; die unveränderte Fixture-Datei ist die
„Sicherung vorher". Es werden keine echten Daten und keine Geheimnisse benutzt.
"""
import asyncio
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit

from scripts import migrationsprobe, umstellung_pruefung as pruefung
from tests.test_migrationsprobe import fixture


def sha(pfad: Path) -> str:
    return hashlib.sha256(pfad.read_bytes()).hexdigest()


def asgi_get(app, url, cookie=None):
    """Minimaler ASGI-Aufruf wie in tests/test_bereiche.py (kein httpx im venv)."""
    parts = urlsplit(url)
    headers = [(b"host", b"localhost")]
    if cookie:
        headers.append((b"cookie", cookie.encode()))
    scope = {"type": "http", "asgi": {"version": "3.0", "spec_version": "2.4"},
             "http_version": "1.1", "method": "GET", "scheme": "http",
             "path": parts.path, "raw_path": parts.path.encode(),
             "query_string": parts.query.encode(), "headers": headers,
             "client": ("127.0.0.1", 50000), "server": ("localhost", 80), "root_path": ""}
    messages = []

    async def run():
        gesendet = False
        fertig = asyncio.Event()

        async def receive():
            nonlocal gesendet
            if not gesendet:
                gesendet = True
                return {"type": "http.request", "body": b""}
            await fertig.wait()
            return {"type": "http.disconnect"}

        async def send(message):
            messages.append(message)
            if message["type"] == "http.response.body" and not message.get("more_body"):
                fertig.set()

        await app(scope, receive, send)

    asyncio.run(run())
    status = next(m["status"] for m in messages if m["type"] == "http.response.start")
    inhalt = b"".join(m.get("body", b"") for m in messages if m["type"] == "http.response.body")
    try:
        return status, json.loads(inhalt)
    except (ValueError, UnicodeDecodeError):
        return status, None


class ZahlenvergleichTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="p62-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.vorher = self.root / "sicherung-vorher.db"
        fixture(self.vorher)
        arbeit = self.root / "arbeit"
        migrationsprobe.lauf(self.vorher, arbeit)
        self.nachher = self.root / "stand-nachher.db"
        shutil.copy2(arbeit / "kopie.db", self.nachher)

    def test_gleicher_inhalt_meldet_keine_abweichung(self):
        ergebnis = pruefung.pruefe_zahlenvergleich(self.vorher, self.nachher)
        self.assertTrue(ergebnis["gleich"], ergebnis["abweichungen"])
        self.assertEqual([], ergebnis["abweichungen"])
        self.assertTrue(ergebnis["ok"])
        self.assertEqual(ergebnis["anzahl_vorher"], ergebnis["anzahl_nachher"])

    def test_veraenderte_buchung_nur_nachher_wird_gemeldet(self):
        with closing(sqlite3.connect(self.nachher)) as con:
            zeile = con.execute("""
                SELECT z.id FROM buchungszeile z JOIN buchung b ON b.id=z.buchung_id
                WHERE b.sparte_id=1 AND b.typ='ausgabe' AND substr(b.datum,1,4)='2026'
                ORDER BY z.id LIMIT 1""").fetchone()[0]
            con.execute("UPDATE buchungszeile SET betrag_cent=betrag_cent+500 WHERE id=?", (zeile,))
            con.commit()
        ergebnis = pruefung.pruefe_zahlenvergleich(self.vorher, self.nachher)
        self.assertFalse(ergebnis["gleich"])
        self.assertFalse(ergebnis["ok"])
        self.assertEqual(1, len(ergebnis["abweichungen"]))
        abweichung = ergebnis["abweichungen"][0]
        self.assertEqual(1, abweichung["sparte_id"])
        self.assertEqual(2026, abweichung["jahr"])
        self.assertEqual("ausgaben_cent", abweichung["feld"])
        self.assertEqual(500, abweichung["differenz_cent"])
        text = pruefung.zusammenfassung(None, ergebnis)
        self.assertIn("Sparte 1, Jahr 2026, ausgaben_cent", text)
        self.assertIn("+500 Cent", text)

    def test_pruefung_veraendert_keine_der_beiden_datenbanken(self):
        vorher_hashes = (sha(self.vorher), sha(self.nachher))
        ergebnis = pruefung.pruefe_zahlenvergleich(self.vorher, self.nachher)
        self.assertEqual(vorher_hashes, (sha(self.vorher), sha(self.nachher)))
        self.assertTrue(ergebnis["unveraendert"])
        for datei in ergebnis["dateien"]:
            self.assertTrue(datei["unveraendert"])
            self.assertEqual(datei["sha256_vorher"], datei["sha256_nachher"])

    def test_schreibversuch_auf_der_lesenden_verbindung_scheitert(self):
        with pruefung._lesend(pruefung._pruefe_quelle(self.nachher)) as con:
            with self.assertRaises(sqlite3.OperationalError):
                con.execute("UPDATE buchungszeile SET betrag_cent=0")
        with closing(sqlite3.connect(self.nachher)) as con:
            self.assertNotEqual(0, con.execute(
                "SELECT max(betrag_cent) FROM buchungszeile").fetchone()[0])

    def test_quellen_werden_geprueft(self):
        with self.assertRaises(FileNotFoundError):
            pruefung.pruefe_zahlenvergleich(self.root / "gibtsnicht.db", self.nachher)
        with self.assertRaises(ValueError):
            pruefung.pruefe_zahlenvergleich(self.vorher, self.vorher)
        with patch.dict(os.environ, {"FINANZ_DB": str(self.nachher)}):
            with self.assertRaises(ValueError):
                pruefung.pruefe_zahlenvergleich(self.vorher, self.nachher)
        (self.root / "stand-nachher.db-wal").write_bytes(b"x")
        with self.assertRaises(ValueError):
            pruefung.pruefe_zahlenvergleich(self.vorher, self.nachher)

    def test_nicht_nachgezogene_datenbank_meldet_klaren_fehler(self):
        zweite = self.root / "zweite-alt.db"
        fixture(zweite)
        with self.assertRaises(RuntimeError) as fehler:
            pruefung.pruefe_zahlenvergleich(self.vorher, zweite)
        self.assertIn("v_einnahmen_ausgaben", str(fehler.exception))


class ZusammenfassungTest(unittest.TestCase):
    STATUS_OK = {"url": "https://beispiel.invalid/api/betrieb/status", "erreichbar": True,
                 "http_status": 200, "schema": {"aktuell": 15, "anstehend": []},
                 "sicherung": {"letzte": "2026-09-11", "db_ok": True, "belege_fehlend": 0},
                 "schreibgeschuetzt": False, "probleme": [], "ok": True}
    ZAHLEN_OK = {"gleich": True, "abweichungen": [], "anzahl_vorher": {"buchung": 25},
                 "anzahl_nachher": {"buchung": 25}, "dateien": [], "unveraendert": True, "ok": True}

    def test_positiver_text_nur_wenn_beides_stimmt(self):
        text = pruefung.zusammenfassung(self.STATUS_OK, self.ZAHLEN_OK)
        self.assertTrue(text.startswith("Umstellung ok:"))
        self.assertNotIn("NICHT", text)

    def test_kein_ok_bei_problemen(self):
        zahlen = dict(self.ZAHLEN_OK, gleich=False, ok=False, abweichungen=[
            {"sparte_id": 3, "jahr": 2025, "feld": "einnahmen_cent",
             "alt_cent": 100, "neu_cent": 40, "differenz_cent": -60}])
        text = pruefung.zusammenfassung(self.STATUS_OK, zahlen)
        self.assertFalse(text.startswith("Umstellung ok"))
        self.assertIn("NICHT in Ordnung", text)
        self.assertIn("Sparte 3, Jahr 2025, einnahmen_cent", text)
        self.assertIn("-60 Cent", text)
        self.assertIn("Rückweg", text)

    def test_status_problem_schlaegt_durch(self):
        status = dict(self.STATUS_OK, ok=False, probleme=["Anwendung läuft schreibgeschützt."])
        text = pruefung.zusammenfassung(status, self.ZAHLEN_OK)
        self.assertIn("NICHT in Ordnung", text)
        self.assertIn("schreibgeschützt", text)

    def test_veraenderte_datei_verhindert_ok(self):
        zahlen = dict(self.ZAHLEN_OK, unveraendert=False, ok=False, dateien=[
            {"rolle": "db_nachher", "pfad": "/tmp/x.db", "sha256_vorher": "a",
             "sha256_nachher": "b", "unveraendert": False}])
        text = pruefung.zusammenfassung(self.STATUS_OK, zahlen)
        self.assertIn("NICHT in Ordnung", text)
        self.assertIn("verändert", text)


class StatusTest(unittest.TestCase):
    def test_gueltiger_status_ohne_befund(self):
        def oeffner(url, cookie):
            self.assertTrue(url.endswith(pruefung.STATUS_PFAD))
            self.assertEqual("geheim-testtoken", cookie)
            return 200, {"schema": {"aktuell": 15, "anstehend": []},
                         "sicherung": {"letzte": "2026-09-11", "db_ok": True,
                                       "belege_ok": 3, "belege_fehlend": 0, "zweitziel": "ok"},
                         "schreibgeschuetzt": False}
        ergebnis = pruefung.pruefe_status("https://beispiel.invalid/", "geheim-testtoken", oeffner)
        self.assertTrue(ergebnis["ok"])
        self.assertEqual([], ergebnis["probleme"])

    def test_anstehende_migration_und_fehlende_sicherung(self):
        def oeffner(url, cookie):
            return 200, {"schema": {"aktuell": 14, "anstehend": [[15, "neu"]]},
                         "sicherung": {"letzte": None, "db_ok": False, "belege_fehlend": 2},
                         "schreibgeschuetzt": False}
        ergebnis = pruefung.pruefe_status("https://beispiel.invalid", "token", oeffner)
        self.assertFalse(ergebnis["ok"])
        self.assertEqual(3, len(ergebnis["probleme"]))

    def test_unerreichbar_und_401_sind_kein_ok(self):
        def kaputt(url, cookie):
            raise OSError("Verbindung abgelehnt")
        ergebnis = pruefung.pruefe_status("https://beispiel.invalid", "token", kaputt)
        self.assertFalse(ergebnis["ok"])
        self.assertFalse(ergebnis["erreichbar"])
        ergebnis = pruefung.pruefe_status("https://beispiel.invalid", "", lambda url, cookie: (401, None))
        self.assertFalse(ergebnis["ok"])
        self.assertIn("Anmeldung erforderlich (HTTP 401).", ergebnis["probleme"])
        with self.assertRaises(ValueError):
            pruefung.pruefe_status("beispiel.invalid", "token", lambda url, cookie: (200, {}))

    def test_schreibgeschuetzte_instanz_wird_erkannt(self):
        """Echte Anwendung, echte Anmeldung, Nachzug als fehlgeschlagen markiert."""
        from app import auth, backup, db
        from app.main import app
        with tempfile.TemporaryDirectory(prefix="p62-app-") as temp:
            pfad = Path(temp) / "instanz.db"
            with closing(sqlite3.connect(pfad)) as con:
                con.executescript(db.SCHEMA.read_text(encoding="utf-8"))
                con.commit()
            # Wegwerf-Zugang: zufälliges Passwort, nie angezeigt, nie gespeichert.
            manager = auth.AuthManager(auth.AuthSettings(
                auth.hash_password(secrets.token_urlsafe(24)), secrets.token_bytes(32)))
            token = manager.create_session()

            def oeffner(url, session_cookie):
                return asgi_get(app, urlsplit(url).path,
                                f"{pruefung.COOKIE_NAME}={session_cookie}")

            with patch.object(auth, "AUTH", manager), \
                 patch.dict(os.environ, {"FINANZ_TEST_AUTH_BYPASS": "0"}), \
                 patch.object(db, "DB_PATH", pfad), patch.object(backup, "DB_PATH", pfad), \
                 patch.object(app.state, "schreibgeschuetzt", True), \
                 patch.object(app.state, "migrationsfehler", "Migration 15 fehlgeschlagen"):
                ergebnis = pruefung.pruefe_status("http://localhost", token, oeffner)
        self.assertEqual(200, ergebnis["http_status"])
        self.assertTrue(ergebnis["erreichbar"])
        self.assertTrue(ergebnis["schreibgeschuetzt"])
        self.assertFalse(ergebnis["ok"], "schreibgeschützte Instanz darf nie als ok gelten")
        self.assertIn("Anwendung läuft schreibgeschützt: der Nachzug ist fehlgeschlagen.",
                      ergebnis["probleme"])
        self.assertFalse(pruefung.zusammenfassung(ergebnis, None).startswith("Umstellung ok"))


class FrontendMountTest(unittest.TestCase):
    """P30-Befund 2: vor der Umstellung muss `/` auf `static-neu` zeigen können."""

    def test_root_verzeichnis_haengt_an_finanz_frontend(self):
        from app import main
        self.assertEqual(main.NEU_DIR, main.frontend_verzeichnis("neu"))
        self.assertEqual(main.NEU_DIR, main.frontend_verzeichnis(" NEU "))
        for wert in ("studio", "", "unbekannt", None):
            self.assertEqual(main.STUDIO_DIR, main.frontend_verzeichnis(wert))

    def test_anmeldeseiten_bleiben_unter_root_erreichbar(self):
        from app import main
        pfade = {route.path for route in main.app.routes if hasattr(route, "path")}
        for datei in main.AUTH_SEITEN:
            self.assertIn(f"/{datei}", pfade)
        for datei in main.AUTH_SEITEN:
            self.assertTrue((main.STUDIO_DIR / datei).is_file(), datei)
        namen = {getattr(route, "name", None) for route in main.app.routes}
        self.assertLessEqual({"neu", "studio", "root"}, namen)

    def test_studio_und_neu_bleiben_nebeneinander(self):
        from app.main import app
        with patch.dict(os.environ, {"FINANZ_TEST_AUTH_BYPASS": "1"}):
            for pfad in ("/studio/", "/neu/", "/login.html"):
                with self.subTest(pfad=pfad):
                    self.assertEqual(200, asgi_get(app, pfad)[0])


if __name__ == "__main__":
    unittest.main()
