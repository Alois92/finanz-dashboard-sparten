import os
import asyncio
import json
import pathlib
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from app import auth, backup, db
from app.main import app


def _asgi_request(method, path, json_body=None):
    body = b""
    headers = [(b"host", b"localhost")]
    if json_body is not None:
        body = json.dumps(json_body).encode("utf-8")
        headers.append((b"content-type", b"application/json"))
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("ascii"),
        "query_string": b"",
        "headers": headers,
        "client": ("127.0.0.1", 50000),
        "server": ("localhost", 80),
        "root_path": "",
    }
    messages = []
    sent = False

    async def receive():
        nonlocal sent
        if not sent:
            sent = True
            return {"type": "http.request", "body": body, "more_body": False}
        return {"type": "http.disconnect"}

    async def send(message):
        messages.append(message)

    async def run():
        await app(scope, receive, send)

    asyncio.run(run())
    start = next(m for m in messages if m["type"] == "http.response.start")
    parts = [m.get("body", b"") for m in messages if m["type"] == "http.response.body"]
    content = b"".join(parts)

    class Response:
        status_code = start["status"]

        def json(self):
            return json.loads(content.decode("utf-8"))

    return Response()


class MigrationTest(unittest.TestCase):
    @staticmethod
    def _alte_import_batch_form(con):
        for spalte in ("dateihash", "parser_version", "zeitraum_von", "zeitraum_bis", "anzahl_ungueltig"):
            con.execute(f"ALTER TABLE import_batch DROP COLUMN {spalte}")

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="finanz-migrate-")
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)
        self.db_path = self.root / "test.db"
        self.patches = [
            patch.dict(os.environ, {"FINANZ_DB": str(self.db_path), "FINANZ_TEST_AUTH_BYPASS": "1"}),
            patch.object(db, "DB_PATH", self.db_path),
            patch.object(db, "DB_PERSISTENT", True),
            patch.object(backup, "DB_PATH", self.db_path),
            patch.object(backup, "DB_PERSISTENT", True),
            patch.object(auth, "_test_bypass_enabled", return_value=True),
        ]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)

    def test_neue_datenbank_ist_auf_version_14_ohne_anstehende_migrationen(self):
        from app import migrate

        db.init_db()

        con = db.get_connection()
        try:
            versionen = con.execute(
                "SELECT version, name FROM schema_version ORDER BY version"
            ).fetchall()
            self.assertEqual([(1, "schema_version"), (2, "import_batch_erkennung"), (3, "bereiche"), (4, "konten_bewegungen"), (5, "auslagen_ausgleich"), (6, "saldoanker_kassa"), (7, "kredit"), (8, "regeln_kennzahlen"), (9, "export_profil"), (10, "regeln_bestand_herkunft"), (11, "adhoc_schema"), (12, "migrationsprotokoll"), (13, "kennzahl_eindeutigkeit"), (14, "hinweis_aus")], [tuple(r) for r in versionen])
            self.assertEqual(
                {"aktuell": 14, "anstehend": [], "basis": False},
                migrate.status(con),
            )
        finally:
            con.close()

    def test_alte_datenbank_erhaelt_basis_version_und_einmalige_sicherung(self):
        from app import migrate

        con = sqlite3.connect(self.db_path)
        try:
            con.executescript(db.SCHEMA.read_text(encoding="utf-8"))
            self._alte_import_batch_form(con)
            con.execute("DROP TABLE schema_version")
            con.commit()
        finally:
            con.close()

        db.init_db()

        con = db.get_connection()
        try:
            self.assertEqual(
                [(0, "basis"), (1, "schema_version"), (2, "import_batch_erkennung"), (3, "bereiche"), (4, "konten_bewegungen"), (5, "auslagen_ausgleich"), (6, "saldoanker_kassa"), (7, "kredit"), (8, "regeln_kennzahlen"), (9, "export_profil"), (10, "regeln_bestand_herkunft"), (11, "adhoc_schema"), (12, "migrationsprotokoll"), (13, "kennzahl_eindeutigkeit"), (14, "hinweis_aus")],
                [
                    tuple(r)
                    for r in con.execute(
                        "SELECT version, name FROM schema_version ORDER BY version"
                    )
                ],
            )
            self.assertEqual([], migrate.status(con)["anstehend"])
        finally:
            con.close()
        backup_dir = self.db_path.parent / "backup"
        # Nicht auf eine feste Zielversion pruefen - der Name traegt die jeweils
        # hoechste Migrationsnummer und aendert sich mit jedem neuen Paket.
        sicherungen = list(backup_dir.glob("finanz-????-??-??-????-vor-nachzug-v*.db"))
        self.assertEqual(1, len(sicherungen))
        self.assertEqual([], list(backup_dir.glob("finanz-????-??-??.db")))

        db.init_db()

        self.assertEqual(sicherungen, list(backup_dir.glob("finanz-*-vor-nachzug-*.db")))

    def test_fehlerhafte_migration_rollt_zurueck_und_sperrt_version(self):
        from app import migrate

        migrations = self.root / "migrations"
        migrations.mkdir()
        (migrations / "999_kaputt.sql").write_text("CREATE TABLE bleibt_nicht(id;")
        con = sqlite3.connect(self.db_path)
        try:
            con.execute("CREATE TABLE schema_version(version INTEGER PRIMARY KEY, name TEXT NOT NULL, angewendet_am TEXT NOT NULL DEFAULT (datetime('now')))")
            con.execute("CREATE TABLE marker(wert TEXT NOT NULL)")
            con.execute("INSERT INTO marker(wert) VALUES('ok')")
            con.commit()

            with patch.object(migrate, "MIGRATIONS_DIR", migrations):
                with self.assertRaises(migrate.MigrationsFehler) as raised:
                    migrate.anwenden(con, lambda: self.root / "sicherung.db")

            self.assertEqual(999, raised.exception.version)
            self.assertIsNone(
                con.execute("SELECT 1 FROM schema_version WHERE version = 999").fetchone()
            )
            self.assertEqual("ok", con.execute("SELECT wert FROM marker").fetchone()[0])
        finally:
            con.close()

    def test_schreibschutz_blockiert_post_aber_nicht_get(self):
        db.init_db()
        app.state.schreibgeschuetzt = True
        app.state.migrationsfehler = "kaputt"
        self.addCleanup(setattr, app.state, "schreibgeschuetzt", False)
        self.addCleanup(setattr, app.state, "migrationsfehler", None)

        post = _asgi_request(
            "POST",
            "/api/kategorien",
            {"sparte_id": 1, "name": "Test", "richtung": "ausgabe"},
        )
        get = _asgi_request("GET", "/api/sparten")

        self.assertEqual(503, post.status_code)
        self.assertEqual(
            {"detail": "Datenbank-Nachzug fehlgeschlagen: kaputt"},
            post.json(),
        )
        self.assertEqual(200, get.status_code)

    def test_schreibschutz_blockiert_auth_login_nicht(self):
        db.init_db()
        app.state.schreibgeschuetzt = True
        app.state.migrationsfehler = "kaputt"
        self.addCleanup(setattr, app.state, "schreibgeschuetzt", False)
        self.addCleanup(setattr, app.state, "migrationsfehler", None)

        manager = auth.AuthManager(auth.AuthSettings("ungueltig", b"x" * 32))
        with patch.object(auth, "AUTH", manager):
            response = _asgi_request("POST", "/api/auth/login", {"password": "falsch"})

        self.assertEqual(401, response.status_code)

    def test_fehlgeschlagene_pflichtsicherung_stoppt_nachzug(self):
        from app import migrate

        con = sqlite3.connect(self.db_path)
        try:
            con.executescript(db.SCHEMA.read_text(encoding="utf-8"))
            self._alte_import_batch_form(con)
            con.execute("DROP TABLE schema_version")
            con.commit()
        finally:
            con.close()

        with patch.object(backup, "sichere_datenbank", return_value=None):
            with self.assertRaises(migrate.MigrationsFehler) as raised:
                db.init_db()

        self.assertEqual(1, raised.exception.version)
        self.assertIn("Sicherung vor Nachzug fehlgeschlagen", str(raised.exception))
        con = sqlite3.connect(self.db_path)
        try:
            self.assertIsNone(
                con.execute("SELECT 1 FROM schema_version WHERE version = 1").fetchone()
            )
        finally:
            con.close()

    def test_fehlende_sicherung_ist_bei_wegwerf_datenbank_erlaubt(self):
        con = sqlite3.connect(self.db_path)
        try:
            con.executescript(db.SCHEMA.read_text(encoding="utf-8"))
            self._alte_import_batch_form(con)
            con.execute("DROP TABLE schema_version")
            con.commit()
        finally:
            con.close()

        with (
            patch.object(backup, "DB_PERSISTENT", False),
            patch.object(backup, "sichere_datenbank", return_value=None),
        ):
            db.init_db()

        con = sqlite3.connect(self.db_path)
        try:
            self.assertIsNotNone(
                con.execute("SELECT 1 FROM schema_version WHERE version = 1").fetchone()
            )
        finally:
            con.close()

    def test_migrationsfehler_startet_app_schreibgeschuetzt(self):
        from app import main, migrate

        async def run():
            fehler = migrate.MigrationsFehler(
                1, RuntimeError("Sicherung vor Nachzug fehlgeschlagen")
            )
            with patch.object(main, "init_db", side_effect=fehler):
                async with main.lifespan(app):
                    self.assertTrue(app.state.schreibgeschuetzt)
                    self.assertIn(
                        "Sicherung vor Nachzug fehlgeschlagen",
                        app.state.migrationsfehler,
                    )

        asyncio.run(run())

    def test_schema_endpoint_liefert_erwartete_felder(self):
        db.init_db()
        app.state.schreibgeschuetzt = False
        app.state.migrationsfehler = None

        response = _asgi_request("GET", "/api/schema")

        self.assertEqual(200, response.status_code)
        self.assertEqual(
            {
                "aktuell": 14,
                "anstehend": [],
                "schreibgeschuetzt": False,
                "fehler": None,
            },
            response.json(),
        )

    def test_neue_und_alte_datenbank_haben_gleiche_tabellenliste(self):
        db.init_db()
        neu = db.get_connection()
        try:
            neue_tabellen = [
                r[0]
                for r in neu.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
                )
            ]
        finally:
            neu.close()

        alt_path = self.root / "alt.db"
        with patch.object(db, "DB_PATH", alt_path), patch.object(backup, "DB_PATH", alt_path):
            con = sqlite3.connect(alt_path)
            try:
                con.executescript(db.SCHEMA.read_text(encoding="utf-8"))
                self._alte_import_batch_form(con)
                con.execute("DROP TABLE schema_version")
                con.commit()
            finally:
                con.close()
            db.init_db()
            alt = db.get_connection()
            try:
                alte_tabellen = [
                    r[0]
                    for r in alt.execute(
                        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
                    )
                ]
            finally:
                alt.close()

        self.assertEqual(neue_tabellen, alte_tabellen)


if __name__ == "__main__":
    unittest.main()
