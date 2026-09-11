"""QA4-05: Regressionstest fuer den fehlenden con.commit() nach speichere_antwort()
in auswertung_uebernehmen() (app/routers/beleg_auswertung.py).

Die bestehenden P43/P50b-Tests ueberschreiben db_dep mit EINER geteilten
Verbindung fuer den ganzen Testlauf (siehe tests/test_bereiche.py setUp) - damit
bleiben auch nicht committete Schreibzugriffe innerhalb desselben Tests sichtbar
und der Bug (fehlender Commit vor Verbindungsschluss) faellt dort nicht auf.

Dieser Test verzichtet bewusst auf die dependency_overrides-Ueberschreibung und
laesst db_dep() wie im echten Betrieb pro Request eine eigene, kurzlebige
sqlite3-Verbindung auf dieselbe FINANZ_DB-Datei oeffnen und wieder schliessen
(siehe app/db.py get_connection). So reproduziert er das echte Verhalten: ein
zweiter Aufruf mit derselben client_request_id muss die gecachte Antwort (200)
liefern, nicht faelschlich 409."""
import asyncio
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


class QA405CommitTest(unittest.TestCase):
    def setUp(self):
        self.path = pathlib.Path(tempfile.mktemp(prefix="finanz-qa4-05-", suffix=".db"))
        self.addCleanup(lambda: self.path.unlink(missing_ok=True))
        con = sqlite3.connect(self.path, check_same_thread=False)
        con.row_factory = sqlite3.Row
        con.executescript(db.SCHEMA.read_text(encoding="utf-8"))
        con.executescript(db.SEED.read_text(encoding="utf-8"))
        self.sparte_id = con.execute(
            "SELECT id FROM sparte WHERE typ <> 'verein' ORDER BY id LIMIT 1"
        ).fetchone()[0]
        self.kategorie_id = con.execute(
            "INSERT INTO kategorie(sparte_id,name,richtung) VALUES(?,?,?) RETURNING id",
            (self.sparte_id, "QA4-05-Test", "ausgabe"),
        ).fetchone()[0]
        self.beleg_id = con.execute(
            "INSERT INTO beleg(sparte_id, dateiname, pfad) VALUES(?, ?, ?) RETURNING id",
            (self.sparte_id, "qa4-05.jpg", "nicht-vorhanden.jpg"),
        ).fetchone()[0]
        ergebnis = {"haendler": "QA4-05 Testmarkt", "datum": "2026-08-01",
                    "positionen": [{"text": "Pos", "betrag_cent": 500, "mwst_prozent": 10}],
                    "gesamt_cent": 500}
        self.auftrag_id = con.execute(
            "INSERT INTO beleg_auswertung(beleg_id, status, ergebnis_json) VALUES(?, 'fertig', ?) RETURNING id",
            (self.beleg_id, json.dumps(ergebnis)),
        ).fetchone()[0]
        con.commit()
        con.close()

        # Keine dependency_overrides fuer db_dep: es soll die echte, pro Request
        # neu geoeffnete/geschlossene Verbindung aus app/db.py verwendet werden.
        # db.DB_PATH wird nur einmal beim Modulimport aus FINANZ_DB aufgeloest
        # (app/db.py _resolve_db_path) - fuer diesen Test daher zusaetzlich
        # direkt patchen, ein reines patch.dict(os.environ,...) kaeme zu spaet.
        env = patch.dict(
            os.environ,
            {"FINANZ_DB": str(self.path), "FINANZ_TEST_AUTH_BYPASS": "1", "FINANZ_INSTANZ": "test"},
        )
        env.start()
        self.addCleanup(env.stop)
        pfad_patch = patch.object(db, "DB_PATH", self.path)
        pfad_patch.start()
        self.addCleanup(pfad_patch.stop)
        persistent_patch = patch.object(db, "DB_PERSISTENT", True)
        persistent_patch.start()
        self.addCleanup(persistent_patch.stop)

    def request(self, method, url, body=None):
        parts = urlsplit(url)
        data = json.dumps(body).encode() if body is not None else b""
        headers = [(b"host", b"localhost")]
        if body is not None:
            headers.append((b"content-type", b"application/json"))
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

    def test_wiederholter_aufruf_liefert_gecachte_antwort_statt_409(self):
        payload = {
            "sparte_id": self.sparte_id,
            "positionen": [{"text": "Pos", "betrag_cent": 500, "kategorie_id": self.kategorie_id}],
            "client_request_id": "qa4-05-commit-test-1",
        }
        status1, res1 = self.request(
            "POST", f"/api/beleg-auswertungen/{self.auftrag_id}/uebernehmen", payload
        )
        self.assertEqual(201, status1, res1)

        # Direkte DB-Pruefung mit einer NEUEN Verbindung (wie ein zweiter,
        # unabhaengiger Request) - ohne den Fix stand hier keine Zeile, weil
        # der INSERT nie committet wurde.
        con = sqlite3.connect(self.path)
        con.row_factory = sqlite3.Row
        zeile = con.execute(
            "SELECT 1 FROM request_wiederholung WHERE art='beleg_uebernahme' AND client_request_id=?",
            ("qa4-05-commit-test-1",),
        ).fetchone()
        con.close()
        self.assertIsNotNone(zeile, "request_wiederholung-Eintrag wurde nicht committet (QA4-05)")

        status2, res2 = self.request(
            "POST", f"/api/beleg-auswertungen/{self.auftrag_id}/uebernehmen", payload
        )
        self.assertEqual(200, status2, res2)
        self.assertEqual(res1["buchung_id"], res2["buchung_id"])


if __name__ == "__main__":
    unittest.main()
