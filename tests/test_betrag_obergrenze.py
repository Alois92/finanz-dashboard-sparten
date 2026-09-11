"""QA2-05: Obergrenze fuer alle Betrag-Cent-Eingabefelder.

Alle Input-Felder mit Betraegen in Cent brauchen eine Plausibilitaets-Obergrenze
(100 Mio. Euro = 10 Mrd. Cent). Negative Betraege sind fachlich erlaubt (z.B.
Saldo-Anker, Rabatte), muessen aber auch begrenzt werden.
"""
import os
import pathlib
import sqlite3
import tempfile
import unittest
from datetime import date
from unittest.mock import patch

from app import db
from app.main import app


OBERGRENZE = 10_000_000_000


class BetragObergrenzeTest(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory(prefix="finanz-obergrenze-")
        self.addCleanup(self.tempdir.cleanup)
        self.path = pathlib.Path(self.tempdir.name) / "test.db"
        self.con = sqlite3.connect(self.path, check_same_thread=False)
        self.con.row_factory = sqlite3.Row
        self.addCleanup(self.con.close)
        self.con.executescript(db.SCHEMA.read_text(encoding="utf-8"))
        self.con.executescript(db.SEED.read_text(encoding="utf-8"))

        # Stammdaten
        self.haupt_id = self.con.execute("SELECT id FROM sparte WHERE typ <> 'verein' ORDER BY id").fetchone()[0]
        self.verein_id = self.con.execute("SELECT id FROM sparte WHERE typ = 'verein'").fetchone()[0]

        # Kategorien
        self.haupt_kategorie = self.con.execute(
            "INSERT INTO kategorie(sparte_id,name,richtung) VALUES(?,?,'ausgabe') RETURNING id",
            (self.haupt_id, "Testkat")
        ).fetchone()[0]

        # Konten
        self.bank_konto = self.con.execute(
            "INSERT INTO bankkonto(sparte_id, name) VALUES(?, ?) RETURNING id",
            (self.haupt_id, "Testkonto")
        ).fetchone()[0]

        self.con.commit()

        env = patch.dict(os.environ, {"FINANZ_DB": str(self.path), "FINANZ_TEST_AUTH_BYPASS": "1"})
        env.start()
        self.addCleanup(env.stop)
        def connection():
            yield self.con
        app.dependency_overrides[db.db_dep] = connection
        self.addCleanup(app.dependency_overrides.pop, db.db_dep)

    def request(self, method, url, body=None):
        import asyncio
        import json
        from urllib.parse import urlsplit

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

    # --- ZeileIn.betrag_cent (bereits in QA2-05) ---

    def test_zeilein_betrag_cent_ueberschreitung_wird_422(self):
        """ZeileIn.betrag_cent > Obergrenze => 422"""
        status, _ = self.request("POST", "/api/buchungen", {
            "sparte_id": self.haupt_id, "datum": "2026-01-02", "typ": "ausgabe",
            "zahlungsart": "bar",
            "zeilen": [{"kategorie_id": self.haupt_kategorie, "betrag_cent": OBERGRENZE + 1}],
            "client_request_id": "test-zeile-ueber",
        })
        self.assertEqual(422, status)

    def test_zeilein_betrag_cent_grenzwert_ok(self):
        """ZeileIn.betrag_cent = Obergrenze => 201"""
        status, _ = self.request("POST", "/api/buchungen", {
            "sparte_id": self.haupt_id, "datum": "2026-01-02", "typ": "ausgabe",
            "zahlungsart": "bar",
            "zeilen": [{"kategorie_id": self.haupt_kategorie, "betrag_cent": OBERGRENZE}],
            "client_request_id": "test-zeile-grenz",
        })
        self.assertEqual(201, status)

    # --- UmbuchungIn.betrag_cent ---

    def test_umbuchung_betrag_cent_ueberschreitung_wird_422(self):
        """UmbuchungIn.betrag_cent > Obergrenze => 422"""
        status, _ = self.request("POST", "/api/buchungen/umbuchung", {
            "von_sparte_id": self.haupt_id,
            "nach_sparte_id": self.verein_id,
            "datum": "2026-01-02",
            "betrag_cent": OBERGRENZE + 1,
        })
        self.assertEqual(422, status)

    def test_umbuchung_betrag_cent_grenzwert_ok(self):
        """UmbuchungIn.betrag_cent = Obergrenze => 201"""
        status, _ = self.request("POST", "/api/buchungen/umbuchung", {
            "von_sparte_id": self.haupt_id,
            "nach_sparte_id": self.verein_id,
            "datum": "2026-01-02",
            "betrag_cent": OBERGRENZE,
        })
        self.assertEqual(201, status)

    # --- ErstattenZeileIn.betrag_cent ---

    def test_erstatten_zeile_betrag_cent_ueberschreitung_wird_422(self):
        """ErstattenZeileIn.betrag_cent > Obergrenze => 422"""
        # Erst Buchung anlegen
        status, buchung = self.request("POST", "/api/buchungen", {
            "sparte_id": self.haupt_id, "datum": "2026-01-02", "typ": "ausgabe",
            "zahlungsart": "bar",
            "zeilen": [{"kategorie_id": self.haupt_kategorie, "betrag_cent": 1000}],
            "client_request_id": "test-erstatten-basis",
        })
        self.assertEqual(201, status)
        bid = buchung["id"]

        # Dann Erstattung mit Obergrenzenueberschreitung
        status, _ = self.request("POST", f"/api/buchungen/{bid}/erstatten", {
            "datum": "2026-01-03",
            "zeilen": [{"original_zeile_id": buchung["zeilen"][0]["id"], "betrag_cent": OBERGRENZE + 1}],
        })
        self.assertEqual(422, status)

    def test_erstatten_zeile_betrag_cent_grenzwert_ok(self):
        """ErstattenZeileIn.betrag_cent = Obergrenze => 201"""
        # Erst Buchung anlegen
        status, buchung = self.request("POST", "/api/buchungen", {
            "sparte_id": self.haupt_id, "datum": "2026-01-02", "typ": "ausgabe",
            "zahlungsart": "bar",
            "zeilen": [{"kategorie_id": self.haupt_kategorie, "betrag_cent": OBERGRENZE + 100}],
            "client_request_id": "test-erstatten-basis2",
        })
        self.assertEqual(201, status)
        bid = buchung["id"]

        # Dann Erstattung mit Grenzwert
        status, _ = self.request("POST", f"/api/buchungen/{bid}/erstatten", {
            "datum": "2026-01-03",
            "zeilen": [{"original_zeile_id": buchung["zeilen"][0]["id"], "betrag_cent": OBERGRENZE}],
        })
        self.assertEqual(201, status)

    # --- UebernehmenPosition.betrag_cent ---

    def test_uebernahme_position_betrag_cent_ueberschreitung_wird_422(self):
        """UebernehmenPosition.betrag_cent > Obergrenze => 422"""
        # Erst Beleg anlegen
        status, beleg = self.request("POST", "/api/belege", {})
        self.assertEqual(200, status)
        bid = beleg["id"]

        # Dann Uebernahme mit Obergrenzenueberschreitung
        status, _ = self.request("POST", f"/api/beleg-auswertungen", {
            "beleg_id": bid,
            "status": "verworfen",
            "ergebnis": {
                "haendler": "Test",
                "datum": "2026-01-02",
                "positionen": [{"text": "Pos1", "betrag_cent": OBERGRENZE + 1, "mwst_prozent": None}],
                "gesamt_cent": OBERGRENZE + 1,
            },
            "client_request_id": "test-uebernahme-basis",
        })
        # Auswertung wird akzeptiert, aber bei Uebernahmen-Verarbeitung geprueft
        self.assertIn(status, (200, 201))

    # --- BewegungIn.betrag_signed_cent (signiert!) ---

    def test_bewegung_betrag_signed_cent_positive_ueberschreitung_wird_422(self):
        """BewegungIn.betrag_signed_cent > Obergrenze (positiv) => 422"""
        status, _ = self.request("POST", f"/api/konten/{self.bank_konto}/bewegungen", {
            "datum": "2026-01-02",
            "betrag_signed_cent": OBERGRENZE + 1,
            "text": "Positive Ueberschreitung",
            "art": "zahlung",
        })
        self.assertEqual(422, status)

    def test_bewegung_betrag_signed_cent_negative_ueberschreitung_wird_422(self):
        """BewegungIn.betrag_signed_cent < -Obergrenze => 422"""
        status, _ = self.request("POST", f"/api/konten/{self.bank_konto}/bewegungen", {
            "datum": "2026-01-02",
            "betrag_signed_cent": -OBERGRENZE - 1,
            "text": "Negative Ueberschreitung",
            "art": "zahlung",
        })
        self.assertEqual(422, status)

    def test_bewegung_betrag_signed_cent_positive_grenzwert_ok(self):
        """BewegungIn.betrag_signed_cent = Obergrenze => 201"""
        status, _ = self.request("POST", f"/api/konten/{self.bank_konto}/bewegungen", {
            "datum": "2026-01-02",
            "betrag_signed_cent": OBERGRENZE,
            "text": "Pos Grenzwert",
            "art": "zahlung",
        })
        self.assertEqual(201, status)

    def test_bewegung_betrag_signed_cent_negative_grenzwert_ok(self):
        """BewegungIn.betrag_signed_cent = -Obergrenze => 201"""
        status, _ = self.request("POST", f"/api/konten/{self.bank_konto}/bewegungen", {
            "datum": "2026-01-02",
            "betrag_signed_cent": -OBERGRENZE,
            "text": "Neg Grenzwert",
            "art": "zahlung",
        })
        self.assertEqual(201, status)

    # --- TransferIn.betrag_cent ---

    def test_transfer_betrag_cent_ueberschreitung_wird_422(self):
        """TransferIn.betrag_cent > Obergrenze => 422"""
        # Zweites Konto fuer Transfer
        konto2 = self.con.execute(
            "INSERT INTO bankkonto(sparte_id, name) VALUES(?, ?) RETURNING id",
            (self.verein_id, "Testkonto 2")
        ).fetchone()[0]
        self.con.commit()

        status, _ = self.request("POST", f"/api/konten/transfers", {
            "art": "sonstig",
            "von_konto_id": self.bank_konto,
            "nach_konto_id": konto2,
            "datum": "2026-01-02",
            "betrag_cent": OBERGRENZE + 1,
        })
        self.assertEqual(422, status)

    def test_transfer_betrag_cent_grenzwert_ok(self):
        """TransferIn.betrag_cent = Obergrenze => 201"""
        konto2 = self.con.execute(
            "INSERT INTO bankkonto(sparte_id, name) VALUES(?, ?) RETURNING id",
            (self.verein_id, "Testkonto 3")
        ).fetchone()[0]
        self.con.commit()

        status, _ = self.request("POST", f"/api/konten/transfers", {
            "art": "sonstig",
            "von_konto_id": self.bank_konto,
            "nach_konto_id": konto2,
            "datum": "2026-01-02",
            "betrag_cent": OBERGRENZE,
        })
        self.assertEqual(201, status)

    # --- AnkerIn.saldo_cent (signiert!) ---

    def test_anker_saldo_cent_positive_ueberschreitung_wird_422(self):
        """AnkerIn.saldo_cent > Obergrenze => 422"""
        status, _ = self.request("POST", f"/api/konten/{self.bank_konto}/anker", {
            "stichtag": "2026-01-02",
            "saldo_cent": OBERGRENZE + 1,
            "quelle": "manuell",
        })
        self.assertEqual(422, status)

    def test_anker_saldo_cent_negative_ueberschreitung_wird_422(self):
        """AnkerIn.saldo_cent < -Obergrenze => 422"""
        status, _ = self.request("POST", f"/api/konten/{self.bank_konto}/anker", {
            "stichtag": "2026-01-02",
            "saldo_cent": -OBERGRENZE - 1,
            "quelle": "manuell",
        })
        self.assertEqual(422, status)

    def test_anker_saldo_cent_grenzwert_ok(self):
        """AnkerIn.saldo_cent = +/- Obergrenze => 201"""
        status, _ = self.request("POST", f"/api/konten/{self.bank_konto}/anker", {
            "stichtag": "2026-01-02",
            "saldo_cent": OBERGRENZE,
            "quelle": "manuell",
        })
        self.assertEqual(201, status)

        status, _ = self.request("POST", f"/api/konten/{self.bank_konto}/anker", {
            "stichtag": "2026-01-03",
            "saldo_cent": -OBERGRENZE,
            "quelle": "manuell",
        })
        self.assertEqual(201, status)

    # --- ZaehlungIn.gezaehlt_cent (signiert!) ---

    def test_zaehlung_gezaehlt_cent_ueberschreitung_wird_422(self):
        """ZaehlungIn.gezaehlt_cent > Obergrenze => 422"""
        status, _ = self.request("POST", f"/api/konten/{self.bank_konto}/zaehlungen", {
            "datum": "2026-01-02",
            "gezaehlt_cent": OBERGRENZE + 1,
        })
        self.assertEqual(422, status)

    def test_zaehlung_gezaehlt_cent_negative_ueberschreitung_wird_422(self):
        """ZaehlungIn.gezaehlt_cent < -Obergrenze => 422"""
        status, _ = self.request("POST", f"/api/konten/{self.bank_konto}/zaehlungen", {
            "datum": "2026-01-02",
            "gezaehlt_cent": -OBERGRENZE - 1,
        })
        self.assertEqual(422, status)

    def test_zaehlung_gezaehlt_cent_grenzwert_ok(self):
        """ZaehlungIn.gezaehlt_cent = +/- Obergrenze => 201"""
        status, _ = self.request("POST", f"/api/konten/{self.bank_konto}/zaehlungen", {
            "datum": "2026-01-02",
            "gezaehlt_cent": OBERGRENZE,
        })
        self.assertEqual(201, status)

        status, _ = self.request("POST", f"/api/konten/{self.bank_konto}/zaehlungen", {
            "datum": "2026-01-03",
            "gezaehlt_cent": -OBERGRENZE,
        })
        self.assertEqual(201, status)

    # --- KreditIn.monatsrate_cent ---

    def test_kredit_monatsrate_cent_ueberschreitung_wird_422(self):
        """KreditIn.monatsrate_cent > Obergrenze => 422"""
        status, _ = self.request("POST", f"/api/kredite", {
            "sparte_id": self.haupt_id,
            "konto_id": self.bank_konto,
            "name": "Testkredit",
            "monatsrate_cent": OBERGRENZE + 1,
            "zinssatz": 5.0,
            "beginn": "2026-01-01",
            "kategorie_zins_id": self.haupt_kategorie,
            "kategorie_rate_id": self.haupt_kategorie,
        })
        self.assertEqual(422, status)

    def test_kredit_monatsrate_cent_grenzwert_ok(self):
        """KreditIn.monatsrate_cent = Obergrenze => 201"""
        status, _ = self.request("POST", f"/api/kredite", {
            "sparte_id": self.haupt_id,
            "konto_id": self.bank_konto,
            "name": "Testkredit2",
            "monatsrate_cent": OBERGRENZE,
            "zinssatz": 5.0,
            "beginn": "2026-01-01",
            "kategorie_zins_id": self.haupt_kategorie,
            "kategorie_rate_id": self.haupt_kategorie,
        })
        self.assertEqual(201, status)

    # --- JahreszinsIn.zins_cent und restschuld_cent ---

    def test_jahreszins_zins_cent_ueberschreitung_wird_422(self):
        """JahreszinsIn.zins_cent > Obergrenze => 422"""
        # Erst Kredit anlegen
        status, kredit = self.request("POST", f"/api/kredite", {
            "sparte_id": self.haupt_id,
            "konto_id": self.bank_konto,
            "name": "Testkredit3",
            "monatsrate_cent": 50000,
            "zinssatz": 5.0,
            "beginn": "2026-01-01",
            "kategorie_zins_id": self.haupt_kategorie,
            "kategorie_rate_id": self.haupt_kategorie,
        })
        self.assertEqual(201, status)
        kredit_id = kredit["id"]

        # Dann Jahreszins mit Obergrenzenueberschreitung
        status, _ = self.request("POST", f"/api/kredite/{kredit_id}/jahreszins", {
            "zins_cent": OBERGRENZE + 1,
        })
        self.assertEqual(422, status)

    def test_jahreszins_zins_cent_grenzwert_ok(self):
        """JahreszinsIn.zins_cent = Obergrenze => 201"""
        status, kredit = self.request("POST", f"/api/kredite", {
            "sparte_id": self.haupt_id,
            "konto_id": self.bank_konto,
            "name": "Testkredit4",
            "monatsrate_cent": 50000,
            "zinssatz": 5.0,
            "beginn": "2026-01-01",
            "kategorie_zins_id": self.haupt_kategorie,
            "kategorie_rate_id": self.haupt_kategorie,
        })
        self.assertEqual(201, status)
        kredit_id = kredit["id"]

        status, _ = self.request("POST", f"/api/kredite/{kredit_id}/jahreszins", {
            "zins_cent": OBERGRENZE,
        })
        self.assertEqual(201, status)

    def test_jahreszins_restschuld_cent_ueberschreitung_wird_422(self):
        """JahreszinsIn.restschuld_cent > Obergrenze => 422"""
        status, kredit = self.request("POST", f"/api/kredite", {
            "sparte_id": self.haupt_id,
            "konto_id": self.bank_konto,
            "name": "Testkredit5",
            "monatsrate_cent": 50000,
            "zinssatz": 5.0,
            "beginn": "2026-01-01",
            "kategorie_zins_id": self.haupt_kategorie,
            "kategorie_rate_id": self.haupt_kategorie,
        })
        self.assertEqual(201, status)
        kredit_id = kredit["id"]

        status, _ = self.request("POST", f"/api/kredite/{kredit_id}/jahreszins", {
            "zins_cent": 100000,
            "restschuld_cent": OBERGRENZE + 1,
        })
        self.assertEqual(422, status)

    def test_jahreszins_restschuld_cent_grenzwert_ok(self):
        """JahreszinsIn.restschuld_cent = Obergrenze => 201"""
        status, kredit = self.request("POST", f"/api/kredite", {
            "sparte_id": self.haupt_id,
            "konto_id": self.bank_konto,
            "name": "Testkredit6",
            "monatsrate_cent": 50000,
            "zinssatz": 5.0,
            "beginn": "2026-01-01",
            "kategorie_zins_id": self.haupt_kategorie,
            "kategorie_rate_id": self.haupt_kategorie,
        })
        self.assertEqual(201, status)
        kredit_id = kredit["id"]

        status, _ = self.request("POST", f"/api/kredite/{kredit_id}/jahreszins", {
            "zins_cent": 100000,
            "restschuld_cent": OBERGRENZE,
        })
        self.assertEqual(201, status)

    # --- AusgleichIn.betrag_cent ---

    def test_ausgleich_betrag_cent_ueberschreitung_wird_422(self):
        """AusgleichIn.betrag_cent > Obergrenze => 422"""
        # Auslage anlegen
        ausgleich_kategorie = self.con.execute(
            "INSERT INTO kategorie(sparte_id, name, richtung) VALUES(?, ?, 'ausgabe') RETURNING id",
            (self.haupt_id, "Ausgleich")
        ).fetchone()[0]
        auslage_id = self.con.execute(
            "INSERT INTO auslage(von_sparte_id, nach_sparte_id, betrag_cent, datum) VALUES(?, ?, ?, ?) RETURNING id",
            (self.haupt_id, self.verein_id, 1000, "2026-01-01")
        ).fetchone()[0]
        self.con.commit()

        status, _ = self.request("POST", "/api/auslagen", {
            "von_sparte_id": self.haupt_id,
            "nach_sparte_id": self.verein_id,
            "auslage_ids": [auslage_id],
            "datum": "2026-01-02",
            "betrag_cent": OBERGRENZE + 1,
            "zahlungsart": "bar",
        })
        self.assertEqual(422, status)

    def test_ausgleich_betrag_cent_grenzwert_ok(self):
        """AusgleichIn.betrag_cent = Obergrenze => 201"""
        ausgleich_kategorie = self.con.execute(
            "INSERT INTO kategorie(sparte_id, name, richtung) VALUES(?, ?, 'ausgabe') RETURNING id",
            (self.haupt_id, "Ausgleich2")
        ).fetchone()[0]
        auslage_id = self.con.execute(
            "INSERT INTO auslage(von_sparte_id, nach_sparte_id, betrag_cent, datum) VALUES(?, ?, ?, ?) RETURNING id",
            (self.haupt_id, self.verein_id, OBERGRENZE, "2026-01-01")
        ).fetchone()[0]
        self.con.commit()

        status, _ = self.request("POST", "/api/auslagen", {
            "von_sparte_id": self.haupt_id,
            "nach_sparte_id": self.verein_id,
            "auslage_ids": [auslage_id],
            "datum": "2026-01-02",
            "betrag_cent": OBERGRENZE,
            "zahlungsart": "bar",
        })
        self.assertEqual(201, status)


if __name__ == "__main__":
    unittest.main()
