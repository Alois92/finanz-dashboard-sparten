import os
import tempfile
import unittest
from pathlib import Path


TEST_DIR = tempfile.TemporaryDirectory(prefix="finanz-regeln-")
os.environ["FINANZ_DB"] = str(Path(TEST_DIR.name) / "regeln-test.db")

from app.db import get_connection, init_db
from app.routers import import_bank
from app.routers.import_bank import (
    UmsatzVerbuchenIn, list_bankumsaetze, verbuche_umsatz,
)


class RegelvorschlagApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()

    def setUp(self):
        con = get_connection()
        try:
            con.execute("DELETE FROM regel")
            con.execute("DELETE FROM buchungszeile")
            con.execute("DELETE FROM buchung")
            con.execute("DELETE FROM bankumsatz")
            con.execute("DELETE FROM import_batch")
            con.execute("DELETE FROM bankkonto")
            con.commit()
            kategorie = con.execute(
                "SELECT k.id, k.sparte_id FROM kategorie k "
                "JOIN sparte s ON s.id = k.sparte_id "
                "WHERE k.aktiv = 1 AND s.aktiv = 1 "
                "AND k.richtung IN ('ausgabe', 'beides') "
                "ORDER BY k.id LIMIT 1"
            ).fetchone()
            if kategorie is None:
                sparte_id = con.execute(
                    "INSERT INTO sparte(name, typ) VALUES('Test', 'privat')"
                ).lastrowid
                kategorie_id = con.execute(
                    "INSERT INTO kategorie(sparte_id, name, richtung) "
                    "VALUES(?, 'Testausgabe', 'ausgabe')", (sparte_id,)
                ).lastrowid
                kategorie = {"id": kategorie_id, "sparte_id": sparte_id}
            self.sparte_id = kategorie["sparte_id"]
            self.kategorie_id = kategorie["id"]
            self.bankkonto_id = con.execute(
                "INSERT INTO bankkonto(name, sparte_id) VALUES(?, ?)",
                ("Testkonto", self.sparte_id),
            ).lastrowid
            con.commit()
        finally:
            con.close()

    def _umsatz(self, gegenpartei, text, betrag_cent=-1250):
        con = get_connection()
        try:
            cur = con.execute(
                "INSERT INTO bankumsatz(bankkonto_id, datum, betrag_cent, text, "
                "gegenpartei, import_hash) VALUES(?, '2026-07-15', ?, ?, ?, ?)",
                (
                    self.bankkonto_id,
                    betrag_cent,
                    text,
                    gegenpartei,
                    f"hash-{gegenpartei}-{text}",
                ),
            )
            con.commit()
            return cur.lastrowid
        finally:
            con.close()

    def test_manuelles_verbuchen_lernt_regel_und_liefert_vollstaendigen_vorschlag(self):
        erster_id = self._umsatz(
            "Bergstrom Energie GmbH 123456789",
            "RECHNUNG 9988776655 JULI",
        )

        con = get_connection()
        self.addCleanup(con.close)
        verbuche_umsatz(
            erster_id,
            UmsatzVerbuchenIn(
                sparte_id=self.sparte_id,
                kategorie_id=self.kategorie_id,
                typ="ausgabe",
            ),
            con,
        )
        regeln = [dict(row) for row in con.execute("SELECT * FROM regel").fetchall()]
        self.assertEqual(len(regeln), 1)
        regel = regeln[0]
        self.assertEqual(regel["bedingung_text"], "bergstrom energie gmbh")
        self.assertEqual(regel["ziel_typ"], "ausgabe")

        zweiter_id = self._umsatz(
            "BERGSTROM   ENERGIE GMBH 987654321",
            "Abschlag August 1122334455",
        )
        offene = list_bankumsaetze(
            bankkonto_id=self.bankkonto_id, status="offen", con=con,
        )

        zweiter = next(row for row in offene if row["id"] == zweiter_id)
        self.assertEqual(
            zweiter["vorschlag"],
            {
                "sparte_id": self.sparte_id,
                "kategorie_id": self.kategorie_id,
                "typ": "ausgabe",
                "regel_id": regel["id"],
                "regel_name": "bergstrom energie gmbh",
            },
        )
    def test_regelverwaltung_und_bulk_uebernahme(self):
        erster_id = self._umsatz("Bergstrom Energie GmbH", "Abschlag Juli")
        con = get_connection()
        self.addCleanup(con.close)
        verbuche_umsatz(
            erster_id,
            UmsatzVerbuchenIn(
                sparte_id=self.sparte_id,
                kategorie_id=self.kategorie_id,
                typ="ausgabe",
            ),
            con,
        )
        zweiter_id = self._umsatz("Bergstrom Energie GmbH", "Abschlag August")

        self.assertTrue(hasattr(import_bank, "list_regeln"))
        self.assertTrue(hasattr(import_bank, "patch_regel"))
        self.assertTrue(hasattr(import_bank, "delete_regel"))
        self.assertTrue(hasattr(import_bank, "uebernehme_vorschlaege"))

        regeln = import_bank.list_regeln(con)
        self.assertEqual(len(regeln), 1)
        regel_id = regeln[0]["id"]
        self.assertEqual(
            set(regeln[0]),
            {
                "id", "name", "aktiv", "prioritaet", "bedingung_text",
                "ziel_sparte_id", "ziel_kategorie_id", "ziel_typ",
            },
        )

        import_bank.patch_regel(
            regel_id, import_bank.RegelPatchIn(aktiv=0), con,
        )
        offene = list_bankumsaetze(
            bankkonto_id=self.bankkonto_id, status="offen", con=con,
        )
        self.assertIsNone(next(u for u in offene if u["id"] == zweiter_id)["vorschlag"])

        import_bank.patch_regel(
            regel_id, import_bank.RegelPatchIn(aktiv=1), con,
        )
        ergebnis = import_bank.uebernehme_vorschlaege(
            import_bank.VorschlaegeUebernehmenIn(
                umsatz_ids=[zweiter_id, 999999],
            ),
            con,
        )
        self.assertEqual(ergebnis, {"verbucht": 1, "uebersprungen": 1})

        import_bank.delete_regel(regel_id, con)
        self.assertEqual(import_bank.list_regeln(con), [])

    def test_studio_bietet_bulk_uebernahme_und_regelverwaltung(self):
        root = Path(__file__).resolve().parents[1]
        html = (root / "static-studio" / "index.html").read_text(encoding="utf-8")
        js = (root / "static-studio" / "app.js").read_text(encoding="utf-8")

        self.assertIn('id="vorschlaege-alle"', html)
        self.assertIn('id="tbl-regeln"', html)
        self.assertIn("/bankumsaetze/vorschlaege-uebernehmen", js)
        self.assertIn('api("/regeln")', js)
        self.assertIn('api("/regeln/"', js)


if __name__ == "__main__":
    unittest.main()
