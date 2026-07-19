"""Feature A: Merkregeln ueberall + automatisches Lernen.

Prueft, dass eine erfasste Buchung automatisch eine Regel anlegt/aktualisiert
(app/routers/buchungen.py::_lerne_regel) und dass der Schnelltext-Parser
(app/routers/schnellerfassung.py::_parse_einzeltext) diese Regeln nutzt, wenn
der Namensabgleich selbst keine Kategorie findet - der Namensabgleich hat
aber weiterhin Vorrang. Umbuchungen lernen nicht.
"""
import os
import tempfile
import unittest
from pathlib import Path


TEST_DIR = tempfile.TemporaryDirectory(prefix="finanz-auto-kategorien-")
os.environ["FINANZ_DB"] = str(Path(TEST_DIR.name) / "auto-kategorien-test.db")

from app.db import get_connection, init_db
from app.routers.buchungen import create_buchung
from app.routers.schnellerfassung import ParseIn, parse_text
from app.schemas import BuchungIn, ZeileIn


class AutoKategorienTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()

    def setUp(self):
        con = get_connection()
        try:
            con.execute("DELETE FROM regel")
            con.execute("DELETE FROM buchungszeile")
            con.execute("DELETE FROM buchung")
            con.commit()
            self.sparte_id = con.execute(
                "INSERT INTO sparte(name, typ) VALUES('Testsparte AK', 'privat')"
            ).lastrowid
            self.kategorie_id = con.execute(
                "INSERT INTO kategorie(sparte_id, name, richtung) "
                "VALUES(?, 'Sonstige Ausgaben AK', 'ausgabe')", (self.sparte_id,)
            ).lastrowid
            self.umbuchung_kategorie_id = con.execute(
                "INSERT INTO kategorie(sparte_id, name, richtung) "
                "VALUES(?, 'Umbuchung AK', 'beides')", (self.sparte_id,)
            ).lastrowid
            con.commit()
        finally:
            con.close()

    def _buchung(self, text, kategorie_id=None, typ="ausgabe", betrag_cent=1500):
        return BuchungIn(
            sparte_id=self.sparte_id,
            datum="2026-07-15",
            typ=typ,
            zahlungsart="bank",
            text=text,
            zeilen=[ZeileIn(kategorie_id=kategorie_id or self.kategorie_id,
                            betrag_cent=betrag_cent)],
        )

    def test_buchung_speichern_legt_regel_an(self):
        con = get_connection()
        self.addCleanup(con.close)
        create_buchung(
            self._buchung("Xylophonzz Supermarkt Wocheneinkauf"), con,
        )
        regeln = [dict(r) for r in con.execute("SELECT * FROM regel").fetchall()]
        self.assertEqual(1, len(regeln))
        regel = regeln[0]
        self.assertEqual("xylophonzz supermarkt wocheneinkauf", regel["bedingung_text"])
        self.assertEqual(self.sparte_id, regel["ziel_sparte_id"])
        self.assertEqual(self.kategorie_id, regel["ziel_kategorie_id"])
        self.assertEqual("ausgabe", regel["ziel_typ"])
        self.assertTrue(regel["name"].startswith("Gelernt: "))

    def test_parse_ordnet_per_regel_zu_ohne_kategorienamen(self):
        con = get_connection()
        self.addCleanup(con.close)
        create_buchung(
            self._buchung("Xylophonzz Supermarkt"), con,
        )
        vorschlag = parse_text(
            ParseIn(text="Xylophonzz Supermarkt 12,50"), con,
        )
        self.assertEqual(self.kategorie_id, vorschlag["kategorie_id"])
        self.assertEqual(self.sparte_id, vorschlag["sparte_id"])
        self.assertEqual("ausgabe", vorschlag["typ"])

    def test_namensabgleich_hat_vorrang_vor_regel(self):
        con = get_connection()
        self.addCleanup(con.close)
        create_buchung(
            self._buchung("Baumarkt Einkauf Werkzeug"), con,
        )
        andere_kategorie_id = con.execute(
            "INSERT INTO kategorie(sparte_id, name, richtung) "
            "VALUES(?, 'Baumarkt', 'ausgabe')", (self.sparte_id,)
        ).lastrowid
        con.commit()

        vorschlag = parse_text(
            ParseIn(text="Baumarkt Einkauf Werkzeug 20"), con,
        )
        # Der Namensabgleich findet die neu angelegte Kategorie "Baumarkt"
        # direkt im Text und hat Vorrang vor der zuvor gelernten Regel.
        self.assertEqual(andere_kategorie_id, vorschlag["kategorie_id"])
        self.assertNotEqual(self.kategorie_id, vorschlag["kategorie_id"])

    def test_kurze_eingabe_trifft_lange_gelernte_regel_ueber_wort_tokens(self):
        # Live-Smoke-Test-Befund: "Lagerhaus Rechnung" lernt die Regel
        # bedingung_text="lagerhaus rechnung". Die kurze Folgeeingabe
        # "Lagerhaus 42" enthaelt diese Phrase NICHT als Substring, aber ihr
        # einziges signifikantes Wort ("lagerhaus") ist eine Teilmenge der
        # Regel-Tokens {lagerhaus, rechnung} - die Regel muss trotzdem greifen.
        con = get_connection()
        self.addCleanup(con.close)
        create_buchung(
            self._buchung("Lagerhaus Rechnung"), con,
        )
        regel = con.execute(
            "SELECT bedingung_text FROM regel ORDER BY id DESC LIMIT 1"
        ).fetchone()
        self.assertEqual("lagerhaus rechnung", regel["bedingung_text"])

        vorschlag = parse_text(ParseIn(text="Lagerhaus 42"), con)
        self.assertEqual(self.kategorie_id, vorschlag["kategorie_id"])
        self.assertEqual(self.sparte_id, vorschlag["sparte_id"])

    def test_ein_einzelnes_gemeinsames_wort_reicht_nicht_fuer_einen_treffer(self):
        # Gegenbeispiel aus dem Befund: gelernt wird "Spar Einkauf
        # Lebensmittel" (Tokens {spar, einkauf, lebensmittel}). Die Eingabe
        # "Einkauf Werkzeug" (Tokens {einkauf, werkzeug}) ist KEINE Teilmenge
        # davon (werkzeug fehlt in der Regel) - darf also nicht zuordnen.
        con = get_connection()
        self.addCleanup(con.close)
        create_buchung(
            self._buchung("Spar Einkauf Lebensmittel"), con,
        )
        regel = con.execute(
            "SELECT bedingung_text FROM regel ORDER BY id DESC LIMIT 1"
        ).fetchone()
        self.assertEqual("spar einkauf lebensmittel", regel["bedingung_text"])

        vorschlag = parse_text(ParseIn(text="Einkauf Werkzeug"), con)
        self.assertIsNone(vorschlag["kategorie_id"])

    def test_umbuchung_lernt_nicht(self):
        con = get_connection()
        self.addCleanup(con.close)
        create_buchung(
            self._buchung("Ruecklage Verschieben", kategorie_id=self.umbuchung_kategorie_id,
                          typ="umbuchung"),
            con,
        )
        regeln = con.execute("SELECT * FROM regel").fetchall()
        self.assertEqual(0, len(regeln))


if __name__ == "__main__":
    unittest.main()
