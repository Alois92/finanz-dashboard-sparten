"""P14: Kredite, centgenaue Zinsen und neutrale Tilgung."""
import sqlite3
import os
import pathlib
import tempfile
import unittest
from unittest.mock import patch
from fastapi import HTTPException

from app import migrate
from app import auth
from app import db
from app.db import SCHEMA
from app.bereiche import Bereich
from app.routers.kredite import (JahreszinsIn, KreditIn, RateIn, ZuordnenIn,
                                  assign_rates, confirm_year, create_kredit,
                                  create_rate, list_rates)


class KreditLogikTest(unittest.TestCase):
    def test_verteile_zins_erhaelt_jeden_cent(self):
        from app.kredite import verteile_zins

        werte = verteile_zins(1205, 12)
        self.assertEqual(12, len(werte))
        self.assertEqual(1205, sum(werte))
        self.assertLessEqual(max(werte) - min(werte), 1)


class KreditApiTest(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory(
            prefix="finanz-kredit-", dir="C:\\Users\\lblet\\dev"
        )
        self.addCleanup(self.tempdir.cleanup)
        self.path = pathlib.Path(self.tempdir.name) / "test.db"
        self.con = sqlite3.connect(self.path, check_same_thread=False)
        self.con.row_factory = sqlite3.Row
        self.addCleanup(self.con.close)
        self.con.executescript(SCHEMA.read_text(encoding="utf-8"))
        self.con.executescript(db.SEED.read_text(encoding="utf-8"))
        env = patch.dict(os.environ, {"FINANZ_DB": str(self.path), "FINANZ_TEST_AUTH_BYPASS": "1"})
        env.start()
        self.addCleanup(env.stop)
        bypass = patch.object(auth, "_test_bypass_enabled", return_value=True)
        bypass.start()
        self.addCleanup(bypass.stop)
        self.haupt = 1
        self.verein = self.con.execute("SELECT id FROM sparte WHERE typ='verein'").fetchone()[0]
        self.kategorie = self.con.execute(
            "INSERT INTO kategorie(sparte_id,name,richtung) VALUES(1,'Grundkategorie','ausgabe')"
        ).lastrowid
        self.konto_id = self.con.execute(
            "INSERT INTO bankkonto(name,sparte_id,bereich_id) VALUES('Kreditkonto',?,?)",
            (self.haupt, 1),
        ).lastrowid
        self.zins_id = self.con.execute(
            "INSERT INTO kategorie(sparte_id,name,richtung) VALUES(?, 'Zinsen', 'ausgabe')",
            (self.haupt,),
        ).lastrowid
        self.rate_id = self.kategorie
        self.con.commit()

    def kredit(self):
        data = KreditIn(sparte_id=self.haupt, konto_id=self.konto_id,
                        name="Wohnkredit", monatsrate_cent=42000,
                        zinssatz=0.03, beginn="2025-01-01",
                        kategorie_zins_id=self.zins_id,
                        kategorie_rate_id=self.rate_id)
        return create_kredit(data, self.con, Bereich(1))["id"]

    def test_jahreszins_wird_auf_raten_und_auswertung_verteilt(self):
        kredit_id = self.kredit()
        for monat in range(1, 13):
            data = create_rate(kredit_id, RateIn(datum=f"2025-{monat:02d}-15"), self.con, Bereich(1))
            self.assertEqual("geschaetzt", data["status"])
        data = confirm_year(kredit_id, 2025, JahreszinsIn(zins_cent=120000,
                                                           restschuld_cent=5000000),
                            self.con, Bereich(1))
        self.assertEqual({"raten": 12, "verteilt_cent": 120000, "abweichungen": []}, data)
        raten = list_rates(kredit_id, 2025, self.con, Bereich(1))
        self.assertEqual([10000] * 12, [rate["zins_cent"] for rate in raten])
        self.assertEqual([32000] * 12, [rate["tilgung_cent"] for rate in raten])
        self.assertEqual(120000, self.con.execute(
            "SELECT COALESCE(SUM(betrag_cent),0) FROM v_einnahmen_ausgaben "
            "WHERE sparte_id=? AND datum LIKE '2025-%'", (self.haupt,)
        ).fetchone()[0])
        self.assertEqual(-504000, self.con.execute(
            "SELECT saldo_cent FROM (SELECT COALESCE(SUM(betrag_signed_cent),0) saldo_cent "
            "FROM bewegung WHERE konto_id=?)", (self.konto_id,)
        ).fetchone()[0])

    def test_elf_raten_melden_abweichung_und_vorjahreszins_schaetzt(self):
        kredit_id = self.kredit()
        for monat in range(1, 12):
            create_rate(kredit_id, RateIn(datum=f"2025-{monat:02d}-15"), self.con, Bereich(1))
        bestaetigt = confirm_year(kredit_id, 2025, JahreszinsIn(zins_cent=120000),
                                  self.con, Bereich(1))
        self.assertTrue(any("11 Raten" in text for text in bestaetigt["abweichungen"]))
        rate = create_rate(kredit_id, RateIn(datum="2026-01-15"), self.con, Bereich(1))
        self.assertEqual(10909, rate["zins_cent"])
        self.assertEqual("geschaetzt", rate["status"])

    def test_bereich_und_referenzen_werden_geprueft(self):
        with self.assertRaises(HTTPException):
            create_kredit(KreditIn(sparte_id=self.verein, konto_id=self.konto_id,
                                    name="Fremd", monatsrate_cent=42000,
                                    beginn="2025-01-01", kategorie_zins_id=self.zins_id,
                                    kategorie_rate_id=self.rate_id), self.con, Bereich(1))

    def test_zuordnen_lehnt_mehrzeilige_buchung_ohne_datenverlust_ab(self):
        kredit_id = self.kredit()
        sonstige_id = self.con.execute(
            "INSERT INTO kategorie(sparte_id,name,richtung) "
            "VALUES(?, 'Kontofuehrung', 'ausgabe')", (self.haupt,)
        ).lastrowid
        buchung_id = self.con.execute(
            "INSERT INTO buchung(sparte_id,datum,typ,betrag_cent,bankkonto_id,"
            "zahlungsart,buchungsstatus,text) VALUES(?, '2025-01-15', 'ausgabe', "
            "50500, ?, 'bank', 'zugeordnet', 'Kreditrate')",
            (self.haupt, self.konto_id),
        ).lastrowid
        self.con.execute(
            "INSERT INTO buchungszeile(buchung_id,kategorie_id,betrag_cent,notiz) "
            "VALUES(?,?,?,?)", (buchung_id, self.rate_id, 50000, "Rate")
        )
        self.con.execute(
            "INSERT INTO buchungszeile(buchung_id,kategorie_id,betrag_cent,notiz) "
            "VALUES(?,?,?,?)", (buchung_id, sonstige_id, 500, "Gebuehr")
        )
        self.con.commit()
        vorher = [tuple(row) for row in self.con.execute(
            "SELECT id,kategorie_id,betrag_cent,notiz,neutral "
            "FROM buchungszeile WHERE buchung_id=? ORDER BY id", (buchung_id,)
        )]
        summe_vorher = self.con.execute(
            "SELECT SUM(betrag_cent) FROM buchungszeile WHERE buchung_id=?",
            (buchung_id,),
        ).fetchone()[0]

        with self.assertRaisesRegex(HTTPException, "weitere Positionen") as fehler:
            assign_rates(kredit_id, ZuordnenIn(buchung_ids=[buchung_id]),
                         self.con, Bereich(1))

        self.assertEqual(422, fehler.exception.status_code)
        nachher = [tuple(row) for row in self.con.execute(
            "SELECT id,kategorie_id,betrag_cent,notiz,neutral "
            "FROM buchungszeile WHERE buchung_id=? ORDER BY id", (buchung_id,)
        )]
        summe_nachher = self.con.execute(
            "SELECT SUM(betrag_cent) FROM buchungszeile WHERE buchung_id=?",
            (buchung_id,),
        ).fetchone()[0]
        self.assertEqual(vorher, nachher)
        self.assertEqual(summe_vorher, summe_nachher)

    def test_zuordnen_teilt_eine_einzelne_ratenzeile_in_zins_und_tilgung(self):
        kredit_id = self.kredit()
        buchung_id = self.con.execute(
            "INSERT INTO buchung(sparte_id,datum,typ,betrag_cent,bankkonto_id,"
            "zahlungsart,buchungsstatus,text) VALUES(?, '2025-01-15', 'ausgabe', "
            "50000, ?, 'bank', 'zugeordnet', 'Kreditrate')",
            (self.haupt, self.konto_id),
        ).lastrowid
        self.con.execute(
            "INSERT INTO buchungszeile(buchung_id,kategorie_id,betrag_cent) "
            "VALUES(?,?,?)", (buchung_id, self.rate_id, 50000)
        )
        self.con.commit()

        result = assign_rates(kredit_id, ZuordnenIn(buchung_ids=[buchung_id]),
                              self.con, Bereich(1))

        self.assertEqual([buchung_id], result["buchung_ids"])
        zeilen = self.con.execute(
            "SELECT kategorie_id,betrag_cent,neutral FROM buchungszeile "
            "WHERE buchung_id=? ORDER BY neutral", (buchung_id,)
        ).fetchall()
        self.assertEqual([(self.zins_id, 0, 0), (self.rate_id, 50000, 1)],
                         [tuple(row) for row in zeilen])
        self.assertEqual(50000, self.con.execute(
            "SELECT SUM(betrag_cent) FROM buchungszeile WHERE buchung_id=?",
            (buchung_id,),
        ).fetchone()[0])


class KreditMigrationTest(unittest.TestCase):
    def test_migration_007_zweimal_und_view(self):
        with sqlite3.connect(":memory:") as con:
            con.executescript(SCHEMA.read_text(encoding="utf-8"))
            con.execute("DELETE FROM schema_version")
            con.executemany(
                "INSERT INTO schema_version(version,name) VALUES(?,?)",
                [(1, "schema_version"), (2, "import_batch_erkennung"),
                 (3, "bereiche"), (4, "konten_bewegungen")],
            )
            con.commit()
            self.assertEqual([5, 6, 7, 8, 9], migrate.anwenden(con, None))
            snapshot = "\n".join(con.iterdump())
            self.assertEqual([], migrate.anwenden(con, None))
            self.assertEqual(snapshot, "\n".join(con.iterdump()))
            self.assertEqual(1, con.execute(
                "SELECT 1 FROM sqlite_master WHERE type='view' AND name='v_einnahmen_ausgaben'"
            ).fetchone()[0])
