import os
import io
import sqlite3
import tempfile
import unittest
import uuid
from pathlib import Path

from starlette.datastructures import UploadFile


class P15KernTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="finanz-p15-kern-", ignore_cleanup_errors=True)
        self.tmp._finalizer.detach()
        self.db = Path(tempfile.gettempdir()) / f"p15-{uuid.uuid4().hex}.db"
        os.environ["FINANZ_DB"] = str(self.db)
        import app.db as db
        db.DB_PATH = self.db
        db.DB_PERSISTENT = True
        from app.db import get_connection, init_db
        self.get_connection = get_connection
        init_db()
        self.con = get_connection()
        self.addCleanup(self.con.close)
        self.sparte = self.con.execute(
            "SELECT id FROM sparte WHERE bereich_id=1 ORDER BY id LIMIT 1"
        ).fetchone()[0]
        self.con.execute(
            "INSERT INTO kategorie(sparte_id,name,richtung) VALUES(?,?,?)",
            (self.sparte, "Start P15", "ausgabe"),
        )
        self.con.commit()
        self.kategorie = self.con.execute(
            "SELECT id FROM kategorie WHERE sparte_id=? ORDER BY id LIMIT 1",
            (self.sparte,),
        ).fetchone()[0]

    def test_migration_008_is_idempotent(self):
        from app import migrate
        self.assertEqual([], migrate.status(self.con)["anstehend"])
        self.con.execute("DELETE FROM schema_version WHERE version=8")
        self.con.commit()
        self.assertEqual([8], migrate.anwenden(self.con, None))
        self.assertEqual([], migrate.anwenden(self.con, None))
        self.assertIsNotNone(self.con.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='kennzahl'"
        ).fetchone())
        self.con.execute("DELETE FROM schema_version WHERE version=10")
        self.con.commit()
        self.assertEqual([10], migrate.anwenden(self.con, None))
        self.assertEqual([], migrate.anwenden(self.con, None))

    def test_bestandsregeln_bleiben_vorschlaege_und_csv_import_verbucht_nichts(self):
        from app import migrate
        from app.routers.import_bank import import_csv

        self.con.executemany(
            "INSERT INTO regel(name, bedingung_text, ziel_sparte_id, ziel_kategorie_id, "
            "ziel_typ, bereich_id, quelle, auto_verbuchen) VALUES(?,?,?,?,?,?,?,?)",
            [
                ("alt 1", "altlieferant", self.sparte, self.kategorie, "ausgabe", 1, "gelernt", 1),
                ("alt 2", "zweiterlieferant", self.sparte, self.kategorie, "ausgabe", 1, "gelernt", 1),
            ],
        )
        konto_id = self.con.execute(
            "INSERT INTO bankkonto(name, sparte_id) VALUES(?, ?)",
            ("P15 Bestandskonto", self.sparte),
        ).lastrowid
        self.con.execute("DELETE FROM schema_version WHERE version=8")
        self.con.commit()

        self.assertEqual([8], migrate.anwenden(self.con, None))
        self.assertEqual(
            [0, 0],
            [row[0] for row in self.con.execute(
                "SELECT auto_verbuchen FROM regel WHERE quelle='gelernt' ORDER BY id"
            )],
        )

        import_csv(
            bankkonto_id=konto_id,
            datei=UploadFile(file=io.BytesIO(
                b"Buchungsdatum;Betrag;Verwendungszweck\n"
                b"01.09.2026;-12,34;Altlieferant Rechnung\n"
            ), filename="bestand.csv"),
            con=self.con,
        )
        self.assertEqual(0, self.con.execute("SELECT COUNT(*) FROM buchung").fetchone()[0])
        self.assertEqual(
            1,
            self.con.execute(
                "SELECT COUNT(*) FROM bankumsatz WHERE importstatus='offen'"
            ).fetchone()[0],
        )

    def test_category_list_includes_inactive_and_patch_preserves_id(self):
        from app.routers.stammdaten import list_kategorien, patch_kategorie
        from app.bereiche import Bereich
        self.con.execute("UPDATE kategorie SET aktiv=0 WHERE id=?", (self.kategorie,))
        self.con.commit()
        rows = list_kategorien(sparte_id=self.sparte, nur_aktive=False, con=self.con, bereich=Bereich(1))
        self.assertEqual(1, next(row["id"] for row in rows if row["id"] == self.kategorie))
        updated = patch_kategorie(self.kategorie, {"name": "Umbenannt", "aktiv": 1}, self.con, Bereich(1))
        self.assertEqual(self.kategorie, updated["id"])
        self.assertEqual("Umbenannt", updated["name"])

    def test_rule_resolution_returns_origin_and_conflict(self):
        from app.regeln import finde_regel
        other = self.con.execute(
            "INSERT INTO kategorie(sparte_id,name,richtung) VALUES(?,?,?)",
            (self.sparte, "Andere P15", "ausgabe"),
        ).lastrowid
        self.con.executemany(
            "INSERT INTO regel(name, bedingung_text, ziel_sparte_id, ziel_kategorie_id, ziel_typ, bereich_id, quelle, auto_verbuchen) VALUES(?,?,?,?,?,?,?,?)",
            [
                ("a", "lieferant", self.sparte, self.kategorie, "ausgabe", 1, "stichwort", 0),
                ("b", "lieferant", self.sparte, other, "ausgabe", 1, "manuell", 0),
            ],
        )
        self.con.commit()
        result = finde_regel(self.con, "Lieferant", sparte_id=self.sparte, bereich_id=1)
        self.assertTrue(result["konflikt"])
        self.assertIn("quelle", result)

    def test_metric_value_uses_terms_and_months_with_data(self):
        from app.kennzahlen import wert
        kat_einnahme = self.con.execute(
            "INSERT INTO kategorie(sparte_id,name,richtung) VALUES(?,?,?)",
            (self.sparte, "Einnahme P15", "einnahme"),
        ).lastrowid
        kat_ausgabe = self.con.execute(
            "INSERT INTO kategorie(sparte_id,name,richtung) VALUES(?,?,?)",
            (self.sparte, "Ausgabe P15", "ausgabe"),
        ).lastrowid
        self.con.execute(
            "INSERT INTO kennzahl(sparte_id,name) VALUES(?,?)", (self.sparte, "Netto")
        )
        kid = self.con.execute("SELECT last_insert_rowid()").fetchone()[0]
        self.con.executemany(
            "INSERT INTO kennzahl_term(kennzahl_id,kategorie_id,messgroesse,vorzeichen) VALUES(?,?,?,?)",
            [(kid, kat_einnahme, "einnahmen", 1), (kid, kat_ausgabe, "ausgaben", -1)],
        )
        for datum, typ, kat, betrag in [
            ("2026-01-10", "einnahme", kat_einnahme, 10000),
            ("2026-01-10", "ausgabe", kat_ausgabe, 3000),
        ]:
            bid = self.con.execute(
                "INSERT INTO buchung(sparte_id,datum,typ,zahlungsart) VALUES(?,?,?,?)",
                (self.sparte, datum, typ, "bank"),
            ).lastrowid
            self.con.execute(
                "INSERT INTO buchungszeile(buchung_id,kategorie_id,betrag_cent) VALUES(?,?,?)",
                (bid, kat, betrag),
            )
        self.con.commit()
        self.assertEqual(7000, wert(self.con, kid, 2026, {}))

    def test_metric_value_does_not_multiply_rows_for_duplicate_legacy_terms(self):
        from app.kennzahlen import wert

        self.con.execute("DROP INDEX IF EXISTS idx_kennzahl_term_eindeutig")
        self.con.execute(
            "INSERT INTO kennzahl(sparte_id,name) VALUES(?,?)", (self.sparte, "Alt")
        )
        kid = self.con.execute("SELECT last_insert_rowid()").fetchone()[0]
        self.con.executemany(
            "INSERT INTO kennzahl_term(kennzahl_id,kategorie_id,messgroesse,vorzeichen) VALUES(?,?,?,?)",
            [(kid, self.kategorie, "einnahmen", 1), (kid, self.kategorie, "einnahmen", 1)],
        )
        bid = self.con.execute(
            "INSERT INTO buchung(sparte_id,datum,typ,zahlungsart) VALUES(?,?,?,?)",
            (self.sparte, "2026-01-10", "einnahme", "bank"),
        ).lastrowid
        self.con.execute(
            "INSERT INTO buchungszeile(buchung_id,kategorie_id,betrag_cent) VALUES(?,?,?)",
            (bid, self.kategorie, 10000),
        )
        self.con.commit()

        self.assertEqual(20000, wert(self.con, kid, 2026, {}))

    def test_duplicate_term_is_rejected_with_422_and_other_metric_allows_category(self):
        from app.bereiche import Bereich
        from app.routers.kennzahlen import KennzahlIn, TermIn, create_kennzahl
        from fastapi import HTTPException

        terme = [
            TermIn(kategorie_id=self.kategorie, messgroesse="einnahmen", vorzeichen=1),
            TermIn(kategorie_id=self.kategorie, messgroesse="netto", vorzeichen=1),
        ]
        with self.assertRaises(HTTPException) as raised:
            create_kennzahl(
                KennzahlIn(sparte_id=self.sparte, name="Doppelt", terme=terme),
                self.con,
                Bereich(1),
            )
        self.assertEqual(422, raised.exception.status_code)
        create_kennzahl(
            KennzahlIn(
                sparte_id=self.sparte,
                name="Gegenlaeufig",
                terme=[
                    TermIn(kategorie_id=self.kategorie, messgroesse="einnahmen", vorzeichen=1),
                    TermIn(kategorie_id=self.kategorie, messgroesse="netto", vorzeichen=-1),
                ],
            ),
            self.con,
            Bereich(1),
        )
        create_kennzahl(
            KennzahlIn(sparte_id=self.sparte, name="Kennzahl 1", terme=[terme[0]]),
            self.con,
            Bereich(1),
        )
        create_kennzahl(
            KennzahlIn(sparte_id=self.sparte, name="Kennzahl 2", terme=[terme[0]]),
            self.con,
            Bereich(1),
        )


if __name__ == "__main__":
    unittest.main()
