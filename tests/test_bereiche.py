"""P10: Bereichsgrenzen über die echte ASGI-Anwendung und das echte Schema."""
import asyncio
import io
import json
import os
import pathlib
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit

from app import db
from app.main import app


class BereicheTest(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory(prefix="finanz-bereiche-")
        self.addCleanup(self.tempdir.cleanup)
        self.path = pathlib.Path(self.tempdir.name) / "test.db"
        self.con = sqlite3.connect(self.path, check_same_thread=False)
        self.con.row_factory = sqlite3.Row
        self.addCleanup(self.con.close)
        self.con.executescript(db.SCHEMA.read_text(encoding="utf-8"))
        self.con.executescript(db.SEED.read_text(encoding="utf-8"))
        self.haupt = self.con.execute("SELECT id FROM sparte WHERE typ <> 'verein' ORDER BY id").fetchone()[0]
        self.verein = self.con.execute("SELECT id FROM sparte WHERE typ = 'verein'").fetchone()[0]
        self.kategorien = {}
        self.buchungen = {}
        for sid, name, cent in ((self.haupt, "Hauptmarker", 100), (self.verein, "Vereinsmarker", 900)):
            kid = self.con.execute("INSERT INTO kategorie(sparte_id,name,richtung) VALUES(?,?,'ausgabe')", (sid, name)).lastrowid
            bid = self.con.execute("INSERT INTO buchung(sparte_id,datum,typ,text) VALUES(?,'2026-01-01','ausgabe',?)", (sid, name)).lastrowid
            self.con.execute("INSERT INTO buchungszeile(buchung_id,kategorie_id,betrag_cent) VALUES(?,?,?)", (bid, kid, cent))
            self.kategorien[sid], self.buchungen[sid] = kid, bid
        self.con.commit()
        env = patch.dict(os.environ, {"FINANZ_DB": str(self.path), "FINANZ_TEST_AUTH_BYPASS": "1"})
        env.start()
        self.addCleanup(env.stop)
        def connection():
            yield self.con
        app.dependency_overrides[db.db_dep] = connection
        self.addCleanup(app.dependency_overrides.pop, db.db_dep)

    def request(self, method, url, body=None, raw=None, content_type=None):
        parts = urlsplit(url)
        data = raw if raw is not None else json.dumps(body).encode() if body is not None else b""
        headers = [(b"host", b"localhost")]
        if body is not None or content_type:
            headers.append((b"content-type", (content_type or "application/json").encode()))
        scope = {"type": "http", "asgi": {"version": "3.0", "spec_version": "2.4"},
                 "http_version": "1.1", "method": method, "scheme": "http",
                 "path": parts.path, "raw_path": parts.path.encode(), "query_string": parts.query.encode(),
                 "headers": headers, "client": ("127.0.0.1", 50000), "server": ("localhost", 80), "root_path": ""}
        messages = []
        async def run():
            sent = False
            complete = asyncio.Event()
            async def receive():
                nonlocal sent
                if not sent:
                    sent = True
                    return {"type": "http.request", "body": data}
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

    def test_stammdaten_und_bereichsaufloesung(self):
        status, rows = self.request("GET", "/api/bereiche")
        self.assertEqual(200, status)
        self.assertEqual([1, 2], [r["id"] for r in rows])
        self.assertEqual({"id", "name", "kuerzel", "typ", "aktiv", "sortierung"}, set(rows[0]))
        self.assertEqual([self.verein], [r["id"] for r in self.request("GET", "/api/sparten?bereich_id=2")[1]])
        self.assertNotIn(self.verein, [r["id"] for r in self.request("GET", "/api/sparten")[1]])
        self.assertEqual(404, self.request("GET", "/api/sparten?bereich_id=999")[0])
        self.con.execute("UPDATE bereich SET aktiv=0 WHERE id=2")
        self.con.commit()
        self.assertEqual(404, self.request("GET", "/api/sparten?bereich_id=2")[0])

    def test_kategorien_grenzen(self):
        self.assertEqual([self.kategorien[self.haupt]], [r["id"] for r in self.request("GET", "/api/kategorien")[1]])
        self.assertEqual(404, self.request("GET", f"/api/kategorien?sparte_id={self.verein}")[0])
        for sid, parent in ((self.verein, None), (self.haupt, self.kategorien[self.verein])):
            self.assertEqual(404, self.request("POST", "/api/kategorien", {"sparte_id": sid, "parent_id": parent, "name": "Test", "richtung": "ausgabe"})[0])

    def payload(self, sid=None, kid=None):
        return {"sparte_id": sid or self.haupt, "datum": "2026-01-02", "typ": "ausgabe",
                "text": "Lernmarker", "zeilen": [{"kategorie_id": kid or self.kategorien[self.haupt], "betrag_cent": 150}]}

    def test_buchungen_suche_und_schreiben(self):
        self.assertEqual([self.buchungen[self.haupt]], [r["id"] for r in self.request("GET", "/api/buchungen")[1]['buchungen']])
        self.assertEqual([], self.request("GET", "/api/buchungen/suche?q=Vereinsmarker")[1])
        self.assertEqual([self.buchungen[self.verein]], [r["id"] for r in self.request("GET", "/api/buchungen/suche?q=Vereinsmarker&bereich_id=2")[1]])
        self.assertEqual(404, self.request("POST", "/api/buchungen", self.payload(kid=self.kategorien[self.verein]))[0])
        for method in ("PUT", "DELETE"):
            self.assertEqual(404, self.request(method, f"/api/buchungen/{self.buchungen[self.verein]}", self.payload() if method == "PUT" else None)[0])
        self.assertEqual(404, self.request("POST", "/api/umbuchungen", {"von_sparte_id": self.haupt, "nach_sparte_id": self.verein, "datum": "2026-01-02", "betrag_cent": 100})[0])
        for query in (f"sparte_id={self.verein}", f"kategorie_id={self.kategorien[self.verein]}"):
            self.assertEqual(404, self.request("GET", "/api/buchungen?" + query)[0])
        status, result = self.request("POST", "/api/buchungen?bereich_id=2", self.payload(self.verein, self.kategorien[self.verein]))
        self.assertEqual(201, status)
        self.assertEqual(self.verein, result["sparte_id"])
        self.assertEqual(2, self.con.execute("SELECT bereich_id FROM regel WHERE bedingung_text='lernmarker'").fetchone()[0])

    def test_gruppen_sind_bereichsgebunden(self):
        for route, feld, kennung in (("auswertungsgruppen", "sparte_ids", self.verein), ("globalgruppen", "kategorie_ids", self.kategorien[self.verein])):
            with self.subTest(route=route):
                payload = {"name": "Vereinsgruppe", feld: [kennung]}
                self.assertEqual(404, self.request("POST", "/api/" + route, payload)[0])
                status, gruppe = self.request("POST", "/api/" + route + "?bereich_id=2", payload)
                self.assertEqual(201, status)
                gid = gruppe["id"]
                self.assertNotIn(gid, [r["id"] for r in self.request("GET", "/api/" + route)[1]])
                self.assertIn(gid, [r["id"] for r in self.request("GET", "/api/" + route + "?bereich_id=2")[1]])
                self.assertEqual(404, self.request("PUT", f"/api/{route}/{gid}", payload)[0])
                self.assertEqual(404, self.request("DELETE", f"/api/{route}/{gid}")[0])
                self.assertEqual(200, self.request("PUT", f"/api/{route}/{gid}?bereich_id=2", payload)[0])
                self.assertEqual(204, self.request("DELETE", f"/api/{route}/{gid}?bereich_id=2")[0])

    def test_dashboard_jahre_und_verlauf(self):
        for bid, cent in ((1, 100), (2, 900)):
            for route in ("dashboard", "jahresvergleich", "verlauf"):
                with self.subTest(bereich=bid, route=route):
                    status, data = self.request("GET", f"/api/{route}?bereich_id={bid}")
                    self.assertEqual(200, status)
                    row = data if route == "dashboard" else data["gesamt" if route == "jahresvergleich" else "monate"][0]
                    self.assertEqual(cent, row["ausgaben_cent"])
        for route in ("dashboard", "jahresvergleich", "verlauf"):
            self.assertEqual(404, self.request("GET", f"/api/{route}?sparte_id={self.verein}")[0])

    def test_export_xlsx_und_bericht(self):
        from openpyxl import load_workbook
        for bid, marker, fremd in ((1, "Hauptmarker", "Vereinsmarker"), (2, "Vereinsmarker", "Hauptmarker")):
            status, content = self.request("GET", f"/api/export/xlsx?bereich_id={bid}")
            self.assertEqual(200, status)
            wb = load_workbook(io.BytesIO(content))
            try:
                values = str([list(ws.values) for ws in wb.worksheets])
                self.assertIn(marker, values)
                self.assertNotIn(fremd, values)
            finally:
                wb.close()
            status, content = self.request("GET", f"/export/bericht?jahr=2026&bereich_id={bid}")
            self.assertEqual(200, status)
            self.assertIn(marker.encode(), content)
            self.assertNotIn(fremd.encode(), content)
        self.assertEqual(404, self.request("GET", f"/api/export/xlsx?sparte_id={self.verein}")[0])

    def beleg(self, bereich_id):
        sid = self.haupt if bereich_id == 1 else self.verein
        pfad = pathlib.Path(self.tempdir.name) / f"beleg-{bereich_id}.png"
        pfad.write_bytes(b"testfoto")
        bid = self.con.execute("INSERT INTO beleg(sparte_id,dateiname,pfad,bereich_id) VALUES(?,'test.png',?,?)", (sid, str(pfad), bereich_id)).lastrowid
        self.con.commit()
        return bid

    def test_belege_und_verknuepfungen(self):
        own, foreign = self.beleg(1), self.beleg(2)
        self.assertEqual([own], [r["id"] for r in self.request("GET", "/api/belege")[1]])
        self.assertEqual([foreign], [r["id"] for r in self.request("GET", "/api/belege?bereich_id=2")[1]])
        self.assertEqual(404, self.request("GET", f"/api/belege?sparte_id={self.verein}")[0])
        self.assertEqual(404, self.request("GET", f"/api/belege/{foreign}/datei")[0])
        self.assertEqual(200, self.request("GET", f"/api/belege/{foreign}/datei?bereich_id=2")[0])
        self.assertEqual(404, self.request("DELETE", f"/api/belege/{foreign}")[0])
        bid = self.buchungen[self.haupt]
        self.assertEqual(404, self.request("POST", f"/api/buchungen/{bid}/belege", {"beleg_id": foreign})[0])
        self.assertEqual(201, self.request("POST", f"/api/buchungen/{bid}/belege", {"beleg_id": own})[0])
        self.assertEqual(404, self.request("DELETE", f"/api/buchungen/{bid}/belege/{foreign}")[0])
        self.assertEqual(404, self.request("GET", f"/api/buchungen/{self.buchungen[self.verein]}/belege")[0])
        self.assertEqual([own], [r["id"] for r in self.request("GET", f"/api/buchungen/{bid}/belege")[1]])
        self.assertEqual(204, self.request("DELETE", f"/api/buchungen/{bid}/belege/{own}")[0])

    def test_fotoauftraege_grenzen(self):
        own, foreign = self.beleg(1), self.beleg(2)
        self.assertEqual(404, self.request("POST", f"/api/belege/{foreign}/auswerten")[0])
        self.assertEqual(201, self.request("POST", f"/api/belege/{own}/auswerten")[0])
        status, auftrag = self.request("POST", f"/api/belege/{foreign}/auswerten?bereich_id=2")
        self.assertEqual(201, status)
        self.assertEqual([own], [r["beleg_id"] for r in self.request("GET", "/api/beleg-auswertungen")[1]])
        self.assertEqual([foreign], [r["beleg_id"] for r in self.request("GET", "/api/beleg-auswertungen?bereich_id=2")[1]])
        url = f"/api/beleg-auswertungen/{auftrag['id']}/status"
        self.assertEqual(404, self.request("POST", url, {"status": "verbucht"})[0])
        self.assertEqual(200, self.request("POST", url + "?bereich_id=2", {"status": "verworfen"})[0])

    def test_upload_dubletten_nur_im_bereich(self):
        from app.routers import belege
        body = b'--P10\r\nContent-Disposition: form-data; name="datei"; filename="test.png"\r\nContent-Type: image/png\r\n\r\nfoto\r\n--P10--\r\n'
        with patch.object(belege, "DB_PATH", self.path):
            ids = []
            for bid in (1, 2):
                status, data = self.request("POST", f"/api/belege?bereich_id={bid}", raw=body, content_type="multipart/form-data; boundary=P10")
                self.assertEqual(201, status)
                self.assertFalse(data["dublette"])
                ids.append(data["id"])
                self.assertEqual(bid, self.con.execute("SELECT bereich_id FROM beleg WHERE id=?", (data["id"],)).fetchone()[0])
            self.assertNotEqual(*ids)
            self.assertTrue(self.request("POST", "/api/belege?bereich_id=2", raw=body, content_type="multipart/form-data; boundary=P10")[1]["dublette"])

    def test_regeln_und_namensabgleich_der_schnellerfassung(self):
        self.con.execute("INSERT INTO regel(name,bedingung_text,ziel_sparte_id,ziel_kategorie_id,bereich_id) VALUES('Test','xylophonprobe',?,?,2)", (self.verein, self.kategorien[self.verein]))
        self.con.commit()
        for route, text in (("parse", "xylophonprobe 42"), ("parse", "Vereinsmarker 42"), ("parse-mehrere", "xylophonprobe 42; Vereinsmarker 42")):
            for bid in (1, 2):
                status, result = self.request("POST", f"/api/{route}?bereich_id={bid}", {"text": text})
                self.assertEqual(200, status)
                rows = result["eintraege"] if route == "parse-mehrere" else [result]
                for row in rows:
                    self.assertEqual(self.kategorien[self.verein] if bid == 2 else None, row["kategorie_id"])

    def test_fotoverarbeitung_uebergibt_belegbereich(self):
        from app import auswertung
        bid = self.beleg(2)
        # Die fremde Regel steht zuerst; der Resolver muss innerhalb des Belegbereichs suchen.
        for area, sid in ((1, self.haupt), (2, self.verein)):
            self.con.execute("INSERT INTO regel(name,bedingung_text,ziel_sparte_id,ziel_kategorie_id,bereich_id) VALUES('Test','fotomarker',?,?,?)", (sid, self.kategorien[sid], area))
        self.con.commit()
        answer = {"message": {"content": json.dumps({"positionen": [{"text": "fotomarker", "betrag_cent": 42}], "gesamt_cent": 42})}}
        with patch.object(auswertung, "_ollama_aufruf", return_value=answer), patch.object(auswertung, "_lade_bild_base64", return_value="Zm90bw=="):
            result = auswertung._auswerten(self.con, bid)
        self.assertEqual(self.kategorien[self.verein], result["positionen"][0]["kategorie_id"])
        self.assertEqual(2, self.con.execute("SELECT bereich_id FROM beleg WHERE id=?", (bid,)).fetchone()[0])

    def test_fachliche_endpoints_haben_zentrale_dependency(self):
        from fastapi.routing import APIRoute
        from app.bereiche import bereich_dep
        def has_dependency(dependant):
            return dependant.call is bereich_dep or any(has_dependency(d) for d in dependant.dependencies)
        # Auth, Health und Betriebsdiagnose gelten anwendungsweit und muessen
        # auch nach fehlgeschlagenem Nachzug ohne Bereichstabelle erreichbar sein (P00).
        # /api/betrieb/sicherung (P72) reiht sich hier ein: die Sicherung ist keine
        # bereichsgebundene fachliche Aktion, sondern eine Betriebsdiagnose/-aktion
        # wie /api/betrieb/status.
        ausnahmen = {
            "/api/auth/login", "/api/auth/logout", "/api/auth/state",
            "/api/auth/initial-password", "/api/auth/change-password", "/api/auth/recover",
            "/api/health", "/api/schema", "/api/betrieb/status", "/api/betrieb/sicherung",
        }
        for route in app.routes:
            if isinstance(route, APIRoute) and (route.path.startswith("/api/") or route.path == "/export/bericht"):
                with self.subTest(route=route.path, methods=route.methods):
                    self.assertEqual(route.path not in ausnahmen, has_dependency(route.dependant))

    def test_fehlendes_bereichsschema_bleibt_kontrolliert_gesperrt(self):
        from app import main, migrate
        # Vollständige echte Struktur vor P10, wie nach Rollback der Migration 003.
        self.con.execute("PRAGMA foreign_keys=OFF")
        for table in ("sparte", "bankkonto", "beleg", "regel", "globale_kategoriegruppe", "auswertungsgruppe"):
            self.con.execute(f"DROP INDEX IF EXISTS idx_{table}_bereich")
            self.con.execute(f"ALTER TABLE {table} DROP COLUMN bereich_id")
        self.con.execute("DROP TABLE bereich")
        self.con.commit()
        self.con.execute("PRAGMA foreign_keys=ON")
        migrations = pathlib.Path(self.tempdir.name) / "migrations"
        migrations.mkdir()
        sql = (db.BASE / "db/migrations/003_bereiche.sql").read_text(encoding="utf-8")
        (migrations / "003_bereiche.sql").write_text(
            sql + "\nINSERT INTO absichtlich_fehlende_tabelle VALUES(1);", encoding="utf-8",
        )
        def failed_init():
            migrate.anwenden(self.con, None)
        async def start():
            with patch.object(migrate, "MIGRATIONS_DIR", migrations), patch.object(main, "init_db", failed_init):
                async with main.lifespan(app):
                    self.assertTrue(app.state.schreibgeschuetzt)
                    self.assertIn("Migration 3", app.state.migrationsfehler)
        with patch.object(app.state, "schreibgeschuetzt", True), patch.object(app.state, "migrationsfehler", "Migration 3 fehlgeschlagen"):
            asyncio.run(start())
            self.assertIsNone(self.con.execute("SELECT 1 FROM sqlite_master WHERE name='bereich'").fetchone())
            # GET /api/sparten: 503 kommt von BereichDep selbst (fehlendes
            # Bereichsschema), nicht von der schreibschutz_middleware (die nur
            # POST/PUT/PATCH/DELETE abfaengt) - Text bleibt unveraendert.
            status, result = self.request("GET", "/api/sparten")
            self.assertEqual(503, status)
            self.assertIn("Nachzug", result["detail"])
            # POST /api/buchungen: 503 kommt von der schreibschutz_middleware.
            # F6: der Text ist generisch - Details gibt es nur ueber den
            # angemeldeten /api/schema-Endpunkt.
            status, result = self.request("POST", "/api/buchungen", self.payload())
            self.assertEqual(503, status)
            self.assertEqual("Datenbank derzeit schreibgeschuetzt", result["detail"])
            schema_status, schema = self.request("GET", "/api/schema")
            self.assertEqual(200, schema_status)
            self.assertIn("Migration 3", schema["fehler"])

            from app import auth
            manager = auth.AuthManager(auth.AuthSettings(auth.hash_password("P10-Testpasswort-2026"), b"x" * 32))
            with patch.object(auth, "AUTH", manager), patch.dict(os.environ, {"FINANZ_TEST_AUTH_BYPASS": "0"}):
                self.assertEqual((401, {"detail": "Passwort ist nicht korrekt."}),
                                 self.request("POST", "/api/auth/login", {"password": "falsch"}))
                self.assertEqual(204, self.request("POST", "/api/auth/login", {"password": "P10-Testpasswort-2026"})[0])
                self.assertEqual((200, {"status": "ok"}), self.request("GET", "/api/health"))
            with patch.object(db, "DB_PATH", self.path):
                status, result = self.request("GET", "/api/schema")
                self.assertEqual(200, status)
                self.assertTrue(result["schreibgeschuetzt"])
                self.assertIn("Migration 3", result["fehler"])
                self.assertEqual(200, self.request("GET", "/api/betrieb/status")[0])

    def test_login_ignoriert_unbekannten_bereich_fachlicher_endpoint_nicht(self):
        from app import auth
        manager = auth.AuthManager(auth.AuthSettings(auth.hash_password("P10-Testpasswort-2026"), b"x" * 32))
        with patch.object(auth, "AUTH", manager), patch.dict(os.environ, {"FINANZ_TEST_AUTH_BYPASS": "0"}):
            self.assertEqual((401, {"detail": "Passwort ist nicht korrekt."}),
                             self.request("POST", "/api/auth/login?bereich_id=99", {"password": "falsch"}))
            self.assertEqual(204, self.request("POST", "/api/auth/login?bereich_id=99", {"password": "P10-Testpasswort-2026"})[0])
        self.assertEqual((404, {"detail": "Bereich nicht gefunden"}),
                         self.request("GET", "/api/buchungen?bereich_id=99"))
