"""HTTP tests for the booking filters used by chart drill-downs."""
from __future__ import annotations

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
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class DrilldownApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory(prefix="finanz-drilldown-")
        cls.db_path = Path(cls.tmp.name) / "finanz.db"
        con = sqlite3.connect(cls.db_path)
        con.row_factory = sqlite3.Row
        con.executescript((ROOT / "db" / "schema.sql").read_text(encoding="utf-8"))
        con.executescript((ROOT / "db" / "seed.sql").read_text(encoding="utf-8"))
        con.executemany(
            "INSERT INTO sparte(id, name, typ) VALUES(?, ?, 'privat')",
            [(901, "Test A"), (902, "Test B")],
        )
        con.executemany(
            "INSERT INTO kategorie(id, sparte_id, name, richtung) VALUES(?, ?, ?, 'ausgabe')",
            [(911, 901, "Kategorie A"), (912, 902, "Kategorie B")],
        )
        cls.cat1_id, cls.cat2_id = 911, 912
        cls.sparte1_id, cls.sparte2_id = 901, 902

        cur = con.execute("INSERT INTO globale_kategoriegruppe(name) VALUES('Drilldown-Test')")
        cls.gruppe_id = cur.lastrowid
        con.executemany(
            "INSERT INTO kategorie_globalgruppe(kategorie_id, globalgruppe_id) VALUES(?, ?)",
            [(cls.cat1_id, cls.gruppe_id), (cls.cat2_id, cls.gruppe_id)],
        )
        cls.ids = {}
        for key, sparte_id, datum, kategorie_id, betrag in (
            ("juli_cat1", cls.sparte1_id, "2026-07-05", cls.cat1_id, 1100),
            ("juli_cat2", cls.sparte2_id, "2026-07-15", cls.cat2_id, 2200),
            ("juni_cat1", cls.sparte1_id, "2026-06-20", cls.cat1_id, 3300),
        ):
            cur = con.execute(
                "INSERT INTO buchung(sparte_id, datum, typ, text) VALUES(?, ?, 'ausgabe', ?)",
                (sparte_id, datum, key),
            )
            cls.ids[key] = cur.lastrowid
            con.execute(
                "INSERT INTO buchungszeile(buchung_id, kategorie_id, betrag_cent) VALUES(?, ?, ?)",
                (cur.lastrowid, kategorie_id, betrag),
            )
        con.commit()
        con.close()

        cls.port = _free_port()
        env = os.environ.copy()
        env["FINANZ_DB"] = str(cls.db_path)
        cls.server = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1",
             "--port", str(cls.port), "--log-level", "warning"],
            cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            if cls.server.poll() is not None:
                raise RuntimeError("Uvicorn wurde vor dem HTTP-Test beendet")
            try:
                cls._get("/api/health")
                break
            except (OSError, urllib.error.URLError):
                time.sleep(0.2)
        else:
            raise RuntimeError("Uvicorn war nach 45 Sekunden nicht bereit")

    @classmethod
    def tearDownClass(cls) -> None:
        if hasattr(cls, "server"):
            cls.server.terminate()
            try:
                cls.server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                cls.server.kill()
                cls.server.wait(timeout=10)
        if hasattr(cls, "tmp"):
            cls.tmp.cleanup()

    @classmethod
    def _request(cls, path: str, method: str = "GET", body: dict | None = None):
        data = json.dumps(body).encode("utf-8") if body is not None else None
        request = urllib.request.Request(
            f"http://127.0.0.1:{cls.port}{path}", data=data, method=method,
            headers={"Content-Type": "application/json"} if data else {},
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            return json.load(response)

    @classmethod
    def _get(cls, path: str):
        return cls._request(path)

    def test_monat_kategorie_und_sparte_sind_kombinierbar(self) -> None:
        data = self._get(
            f"/api/buchungen?monat=2026-07&kategorie_id={self.cat1_id}"
            f"&sparte_id={self.sparte1_id}"
        )
        self.assertEqual([self.ids["juli_cat1"]], [row["id"] for row in data])

    def test_kategorie_filtert_buchungen_mit_passender_zeile(self) -> None:
        data = self._get(f"/api/buchungen?kategorie_id={self.cat1_id}")
        self.assertEqual(
            {self.ids["juli_cat1"], self.ids["juni_cat1"]},
            {row["id"] for row in data},
        )

    def test_globalgruppe_filtert_ueber_zugeordnete_kategorien(self) -> None:
        data = self._get(f"/api/buchungen?monat=2026-07&globalgruppe_id={self.gruppe_id}")
        self.assertEqual(
            {self.ids["juli_cat1"], self.ids["juli_cat2"]},
            {row["id"] for row in data},
        )

    def test_dashboard_liefert_kategorie_id_fuer_ranking_drilldown(self) -> None:
        data = self._get("/api/dashboard")
        row = next(
            item for item in data["per_kategorie"]
            if item["kategorie"] == "Kategorie A"
        )
        self.assertEqual(self.cat1_id, row["kategorie_id"])

    def test_bestehende_buchung_bleibt_bearbeitbar(self) -> None:
        buchung = self._get(f"/api/buchungen?kategorie_id={self.cat1_id}")[0]
        payload = {
            "sparte_id": buchung["sparte_id"], "datum": buchung["datum"],
            "typ": buchung["typ"], "zahlungsart": buchung["zahlungsart"],
            "text": "Bearbeitung funktioniert",
            "zeilen": [
                {"kategorie_id": zeile["kategorie_id"], "betrag_cent": zeile["betrag_cent"]}
                for zeile in buchung["zeilen"]
            ],
        }
        aktualisiert = self._request(
            f"/api/buchungen/{buchung['id']}", method="PUT", body=payload
        )
        self.assertEqual("Bearbeitung funktioniert", aktualisiert["text"])

    def test_ungueltige_neue_filter_liefern_deutsche_4xx_fehler(self) -> None:
        for query, status, detail in (
            ("monat=2026-13", 400, "Monat"),
            ("kategorie_id=999999", 404, "Kategorie"),
            ("globalgruppe_id=999999", 404, "Gruppe"),
        ):
            with self.subTest(query=query):
                with self.assertRaises(urllib.error.HTTPError) as ctx:
                    self._get("/api/buchungen?" + query)
                self.assertEqual(status, ctx.exception.code)
                body = json.loads(ctx.exception.read().decode("utf-8"))
                self.assertIn(detail, body["detail"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
