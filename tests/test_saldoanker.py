"""P13: Kontostandanker und Kassazählungen."""
import io
import sqlite3
import unittest

from app import migrate
from app.bereiche import Bereich
from app.routers.import_bank import import_csv
import test_bereiche as bereiche_tests


class SaldoankerApiTest(unittest.TestCase):
    setUp = bereiche_tests.BereicheTest.setUp
    request = bereiche_tests.BereicheTest.request
    def konto(self, art="bank", sparte_id=None):
        status, result = self.request("POST", "/api/konten", {
            "name": "P13-Konto", "art": art, "sparte_id": sparte_id,
        })
        self.assertEqual(201, status, result)
        return result["id"]

    def bewegung(self, konto_id, datum, cent):
        self.con.execute(
            "INSERT INTO bewegung(konto_id, datum, betrag_signed_cent, quelle) "
            "VALUES(?,?,?,'manuell')", (konto_id, datum, cent)
        )
        self.con.commit()

    def test_unbekannter_stand_ist_nicht_null(self):
        konto_id = self.konto()
        status, result = self.request("GET", f"/api/konten/{konto_id}/stand")
        self.assertEqual(200, status, result)
        self.assertIsNone(result["stand_cent"])
        self.assertEqual("unbekannt", result["datenstand"])

    def test_anker_und_bewegungen_rechnen(self):
        konto_id = self.konto()
        status, result = self.request("POST", f"/api/konten/{konto_id}/anker", {
            "stichtag": "2026-08-31", "saldo_cent": 100000, "quelle": "auszug",
        })
        self.assertEqual(201, status, result)
        self.bewegung(konto_id, "2026-09-02", 20000)
        self.bewegung(konto_id, "2026-09-05", -5000)
        self.assertEqual(100000, self.request(
            "GET", f"/api/konten/{konto_id}/stand?stichtag=2026-09-01"
        )[1]["stand_cent"])
        self.assertEqual(115000, self.request(
            "GET", f"/api/konten/{konto_id}/stand?stichtag=2026-09-08"
        )[1]["stand_cent"])

        status, result = self.request("POST", f"/api/konten/{konto_id}/anker", {
            "stichtag": "2026-09-07", "saldo_cent": 110000, "quelle": "auszug",
        })
        self.assertEqual(201, status, result)
        self.assertEqual(-5000, result["differenz_cent"])
        self.assertEqual(110000, self.request(
            "GET", f"/api/konten/{konto_id}/stand?stichtag=2026-09-08"
        )[1]["stand_cent"])

    def test_voranker_warnung_und_bereich(self):
        konto_id = self.konto()
        self.request("POST", f"/api/konten/{konto_id}/anker", {
            "stichtag": "2026-08-31", "saldo_cent": 100, "quelle": "manuell",
        })
        self.bewegung(konto_id, "2026-08-15", 20)
        result = self.request("GET", f"/api/konten/{konto_id}/stand")[1]
        self.assertIn("Bewegung vor dem letzten Anker", result["hinweis"])
        fremd = self.con.execute(
            "INSERT INTO bankkonto(name,bereich_id,sparte_id) VALUES('Fremd',2,?)",
            (self.verein,)
        ).lastrowid
        self.con.commit()
        self.assertEqual(404, self.request(
            "POST", f"/api/konten/{fremd}/anker", {
                "stichtag": "2026-08-31", "saldo_cent": 100, "quelle": "manuell",
            }
        )[0])

    def test_importalter_und_csv_importanker(self):
        konto_id = self.konto()
        self.con.execute(
            "INSERT INTO import_batch(bankkonto_id, importiert_am, anzahl_zeilen) "
            "VALUES(?, '2026-07-01 12:00:00', 1)", (konto_id,)
        )
        self.con.commit()
        result = self.request("GET", f"/api/konten/{konto_id}/stand?stichtag=2026-09-09")[1]
        self.assertEqual("veraltet", result["datenstand"])
        csv = io.BytesIO(b"Datum;Betrag;Saldo;Text\n01.09.2026;10,00;110,00;Test\n")
        from fastapi import UploadFile
        import_csv(konto_id, UploadFile(filename="saldo.csv", file=csv), self.con, Bereich(1))
        anker = self.request("GET", f"/api/konten/{konto_id}/anker")[1]
        self.assertEqual(11000, anker[-1]["saldo_cent"])

    def test_kassazaehlung_und_buchen(self):
        sparte_id = self.haupt
        konto_id = self.konto(art="kassa", sparte_id=sparte_id)
        self.request("POST", f"/api/konten/{konto_id}/anker", {
            "stichtag": "2026-09-01", "saldo_cent": 30000, "quelle": "manuell",
        })
        status, result = self.request("POST", f"/api/konten/{konto_id}/zaehlung", {
            "datum": "2026-09-08", "gezaehlt_cent": 28000,
        })
        self.assertEqual(201, status, result)
        self.assertEqual((30000, -2000, "offen"), (
            result["gerechnet_cent"], result["differenz_cent"], result["status"]
        ))
        kid = self.kategorien[sparte_id]
        status, gebucht = self.request(
            "POST", f"/api/konten/{konto_id}/zaehlung/{result['id']}/buchen",
            {"kategorie_id": kid, "text": "Kassadifferenz"},
        )
        self.assertEqual(201, status, gebucht)
        self.assertEqual("geklaert", gebucht["status"])
        self.assertEqual(-2000, self.con.execute(
            "SELECT betrag_signed_cent FROM bewegung WHERE konto_id=? ORDER BY id DESC LIMIT 1",
            (konto_id,)
        ).fetchone()[0])
        self.assertEqual(28000, self.request(
            "GET", f"/api/konten/{konto_id}/stand?stichtag=2026-09-08"
        )[1]["stand_cent"])

    def test_zaehlung_nur_kassa_und_liste(self):
        konto_id = self.konto()
        self.assertEqual(422, self.request(
            "POST", f"/api/konten/{konto_id}/zaehlung",
            {"datum": "2026-09-08", "gezaehlt_cent": 1}
        )[0])
        kassa = self.konto(art="kassa", sparte_id=self.haupt)
        self.request("POST", f"/api/konten/{kassa}/anker", {
            "stichtag": "2026-09-01", "saldo_cent": 10, "quelle": "manuell",
        })
        self.request("POST", f"/api/konten/{kassa}/zaehlung", {
            "datum": "2026-09-01", "gezaehlt_cent": 10,
        })
        self.assertEqual(1, len(self.request("GET", "/api/kassazaehlungen")[1]))


class SaldoankerMigrationTest(unittest.TestCase):
    def test_migration_006_idempotent(self):
        con = sqlite3.connect(":memory:")
        con.executescript(bereiche_tests.db.SCHEMA.read_text(encoding='utf-8'))
        con.execute("DROP TABLE kontostand_anker")
        con.execute("DROP TABLE kassazaehlung")
        con.executemany("INSERT INTO schema_version(version, name) VALUES(?, ?)",
                        [(0, 'basis'), (1, 'schema_version'), (2, 'import_batch_erkennung'),
                         (3, 'bereiche'), (4, 'konten_bewegungen'), (5, 'placeholder')])
        con.commit()
        self.assertEqual([6], migrate.anwenden(con, None))
        snapshot = "\n".join(con.iterdump())
        self.assertEqual([], migrate.anwenden(con, None))
        self.assertEqual(snapshot, "\n".join(con.iterdump()))
        con.close()
