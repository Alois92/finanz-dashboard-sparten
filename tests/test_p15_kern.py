import os
import sqlite3
import tempfile
import unittest
import uuid
from pathlib import Path


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


if __name__ == "__main__":
    unittest.main()
