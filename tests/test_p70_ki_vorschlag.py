"""P70: KI-Kategorievorschlag als Rueckfallebene.

Ollama wird NIE echt aufgerufen - app.auswertung._ollama_aufruf wird ueber
patch.object gemockt (gleiches Muster wie tests/test_beleg_auswertung.py).
Deckt die Punkte 1-5 der Auftragskarte ab: Kandidatenliste, Validierung der
Modellantwort, Abschaltbarkeit, Endpunkt, "quelle" in /api/parse.
"""
import json
import os
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

TEST_DIR = None
if not os.environ.get("FINANZ_DB"):
    TEST_DIR = tempfile.TemporaryDirectory(prefix="finanz-ki-vorschlag-")
    os.environ["FINANZ_DB"] = str(Path(TEST_DIR.name) / "ki-vorschlag-test.db")

from app import auswertung, ki_vorschlag
from app.bereiche import Bereich
from app.db import get_connection, init_db
from app.routers.schnellerfassung import KiVorschlagIn, ParseIn, kategorie_vorschlag_ki, parse_text


def _gemockte_antwort(kategorie_id, sicherheit="hoch", begruendung="Testbegruendung"):
    return {
        "message": {
            "content": json.dumps({
                "kategorie_id": kategorie_id,
                "sicherheit": sicherheit,
                "begruendung": begruendung,
            }),
        },
    }


class KiVorschlagTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()

    def setUp(self):
        self.con = get_connection()
        self.addCleanup(self.con.close)
        self.con.execute("DELETE FROM regel WHERE name LIKE 'P70%'")
        self.con.execute("DELETE FROM kategorie WHERE sparte_id IN (SELECT id FROM sparte WHERE name LIKE 'P70%')")
        self.con.execute("DELETE FROM sparte WHERE name LIKE 'P70%'")
        self.con.commit()
        self.sparte_id = self.con.execute(
            "INSERT INTO sparte(name, typ, bereich_id) VALUES('P70 Testsparte', 'privat', 1)"
        ).lastrowid
        self.andere_sparte_id = self.con.execute(
            "INSERT INTO sparte(name, typ, bereich_id) VALUES('P70 Andere Sparte', 'privat', 1)"
        ).lastrowid
        self.kat_essen_id = self.con.execute(
            "INSERT INTO kategorie(sparte_id, name, richtung) VALUES(?, 'P70 Essen', 'ausgabe')",
            (self.sparte_id,),
        ).lastrowid
        self.kat_lohn_id = self.con.execute(
            "INSERT INTO kategorie(sparte_id, name, richtung) VALUES(?, 'P70 Lohn', 'einnahme')",
            (self.sparte_id,),
        ).lastrowid
        self.kat_inaktiv_id = self.con.execute(
            "INSERT INTO kategorie(sparte_id, name, richtung, aktiv) VALUES(?, 'P70 Inaktiv', 'ausgabe', 0)",
            (self.sparte_id,),
        ).lastrowid
        self.kat_andere_sparte_id = self.con.execute(
            "INSERT INTO kategorie(sparte_id, name, richtung) VALUES(?, 'P70 Fremd', 'ausgabe')",
            (self.andere_sparte_id,),
        ).lastrowid
        self.con.commit()

    # ---- 1. Kandidatenliste ----------------------------------------------

    def test_kandidaten_nur_aktive_kategorien_der_sparte(self):
        kategorien, sparten_namen = ki_vorschlag._kandidaten(
            self.con, bereich_id=1, sparte_id=self.sparte_id, typ=None,
        )
        ids = {k["id"] for k in kategorien}
        self.assertIn(self.kat_essen_id, ids)
        self.assertIn(self.kat_lohn_id, ids)
        self.assertNotIn(self.kat_inaktiv_id, ids)  # inaktiv ausgeschlossen
        self.assertNotIn(self.kat_andere_sparte_id, ids)  # fremde Sparte ausgeschlossen
        self.assertEqual({self.sparte_id: 'P70 Testsparte'}, sparten_namen)

    def test_kandidaten_ohne_platzhalterkategorien(self):
        # Abnahme P70: „… (noch zuordnen)“ ist kein Vorschlag, sondern das Fehlen eines Vorschlags.
        platzhalter_id = self.con.execute(
            "INSERT INTO kategorie(sparte_id, name, richtung) VALUES(?, 'P70 Ausgabe (noch zuordnen)', 'ausgabe')",
            (self.sparte_id,),
        ).lastrowid
        self.con.commit()
        kategorien, _ = ki_vorschlag._kandidaten(
            self.con, bereich_id=1, sparte_id=self.sparte_id, typ="ausgabe",
        )
        ids = {k["id"] for k in kategorien}
        self.assertIn(self.kat_essen_id, ids)
        self.assertNotIn(platzhalter_id, ids)

    def test_kandidaten_richtungsfilter_bei_typ(self):
        kategorien, _ = ki_vorschlag._kandidaten(
            self.con, bereich_id=1, sparte_id=self.sparte_id, typ="ausgabe",
        )
        ids = {k["id"] for k in kategorien}
        self.assertIn(self.kat_essen_id, ids)
        self.assertNotIn(self.kat_lohn_id, ids)  # Lohn ist 'einnahme', passt nicht zu 'ausgabe'

    def test_kandidaten_ohne_sparte_alle_aktiven_sparten_des_bereichs(self):
        kategorien, sparten_namen = ki_vorschlag._kandidaten(
            self.con, bereich_id=1, sparte_id=None, typ=None,
        )
        ids = {k["id"] for k in kategorien}
        self.assertIn(self.kat_essen_id, ids)
        self.assertIn(self.kat_andere_sparte_id, ids)  # jetzt auch die andere Sparte dabei
        self.assertIn(self.sparte_id, sparten_namen)
        self.assertIn(self.andere_sparte_id, sparten_namen)

    # ---- 2. Modellantwort validieren --------------------------------------

    def test_gueltige_antwort_liefert_vorschlag_mit_namen(self):
        with patch.object(auswertung, "_ollama_aufruf", return_value=_gemockte_antwort(self.kat_essen_id)) as mock:
            vorschlag = ki_vorschlag.kategorie_vorschlag(
                self.con, text="Merkur Einkauf", bereich_id=1, sparte_id=self.sparte_id,
                typ="ausgabe", betrag_cent=1234,
            )
        mock.assert_called_once()
        self.assertIsNotNone(vorschlag)
        self.assertEqual(self.kat_essen_id, vorschlag["kategorie_id"])
        self.assertEqual("P70 Essen", vorschlag["kategorie_name"])
        self.assertEqual(self.sparte_id, vorschlag["sparte_id"])
        self.assertEqual("P70 Testsparte", vorschlag["sparte_name"])
        self.assertEqual("hoch", vorschlag["sicherheit"])
        self.assertEqual("ki", vorschlag["quelle"])
        self.assertEqual(auswertung.OLLAMA_MODEL, vorschlag["modell"])

    def test_id_ausserhalb_der_kandidatenliste_liefert_none(self):
        fremde_id = self.kat_andere_sparte_id  # gehoert nicht zur angefragten Sparte
        with patch.object(auswertung, "_ollama_aufruf", return_value=_gemockte_antwort(fremde_id)):
            vorschlag = ki_vorschlag.kategorie_vorschlag(
                self.con, text="Irgendwas", bereich_id=1, sparte_id=self.sparte_id,
            )
        self.assertIsNone(vorschlag)

    def test_null_id_liefert_none(self):
        with patch.object(auswertung, "_ollama_aufruf", return_value=_gemockte_antwort(None, sicherheit="niedrig")):
            vorschlag = ki_vorschlag.kategorie_vorschlag(
                self.con, text="Unklarer Text", bereich_id=1, sparte_id=self.sparte_id,
            )
        self.assertIsNone(vorschlag)

    def test_kaputtes_json_liefert_none_ohne_exception(self):
        kaputte_antwort = {"message": {"content": "das ist kein JSON"}}
        with patch.object(auswertung, "_ollama_aufruf", return_value=kaputte_antwort):
            vorschlag = ki_vorschlag.kategorie_vorschlag(
                self.con, text="Merkur Einkauf", bereich_id=1, sparte_id=self.sparte_id,
            )
        self.assertIsNone(vorschlag)

    def test_leere_antwort_ohne_content_liefert_none(self):
        with patch.object(auswertung, "_ollama_aufruf", return_value={"message": {}}):
            vorschlag = ki_vorschlag.kategorie_vorschlag(
                self.con, text="Merkur Einkauf", bereich_id=1, sparte_id=self.sparte_id,
            )
        self.assertIsNone(vorschlag)

    def test_urlerror_liefert_none_ohne_exception(self):
        with patch.object(
            auswertung, "_ollama_aufruf",
            side_effect=urllib.error.URLError("Verbindung abgelehnt"),
        ):
            vorschlag = ki_vorschlag.kategorie_vorschlag(
                self.con, text="Merkur Einkauf", bereich_id=1, sparte_id=self.sparte_id,
            )
        self.assertIsNone(vorschlag)

    def test_zu_kurzer_text_liefert_none_ohne_ollama_aufruf(self):
        with patch.object(auswertung, "_ollama_aufruf") as mock:
            vorschlag = ki_vorschlag.kategorie_vorschlag(
                self.con, text="ab", bereich_id=1, sparte_id=self.sparte_id,
            )
        self.assertIsNone(vorschlag)
        mock.assert_not_called()

    # ---- 3. Abschaltbar über FINANZ_KI_VORSCHLAG=0 ------------------------

    def test_abgeschaltet_liefert_none_ohne_ollama_aufruf(self):
        with patch.dict(os.environ, {"FINANZ_KI_VORSCHLAG": "0"}):
            with patch.object(auswertung, "_ollama_aufruf") as mock:
                vorschlag = ki_vorschlag.kategorie_vorschlag(
                    self.con, text="Merkur Einkauf", bereich_id=1, sparte_id=self.sparte_id,
                )
            mock.assert_not_called()
        self.assertIsNone(vorschlag)

    # ---- 4. Endpunkt -------------------------------------------------------

    def test_endpunkt_200_mit_vorschlag(self):
        with patch.object(auswertung, "_ollama_aufruf", return_value=_gemockte_antwort(self.kat_essen_id)):
            antwort = kategorie_vorschlag_ki(
                KiVorschlagIn(text="Merkur Einkauf", sparte_id=self.sparte_id, typ="ausgabe"),
                self.con, Bereich(1),
            )
        self.assertIsNotNone(antwort["vorschlag"])
        self.assertIsNone(antwort["grund"])
        self.assertEqual(self.kat_essen_id, antwort["vorschlag"]["kategorie_id"])

    def test_endpunkt_200_mit_null_und_grund_kein_modell(self):
        with patch.object(auswertung, "_ollama_aufruf", side_effect=urllib.error.URLError("weg")):
            antwort = kategorie_vorschlag_ki(
                KiVorschlagIn(text="Merkur Einkauf", sparte_id=self.sparte_id),
                self.con, Bereich(1),
            )
        self.assertIsNone(antwort["vorschlag"])
        self.assertEqual("kein_modell", antwort["grund"])

    def test_endpunkt_200_mit_null_und_grund_abgeschaltet(self):
        with patch.dict(os.environ, {"FINANZ_KI_VORSCHLAG": "0"}):
            with patch.object(auswertung, "_ollama_aufruf") as mock:
                antwort = kategorie_vorschlag_ki(
                    KiVorschlagIn(text="Merkur Einkauf", sparte_id=self.sparte_id),
                    self.con, Bereich(1),
                )
            mock.assert_not_called()
        self.assertIsNone(antwort["vorschlag"])
        self.assertEqual("abgeschaltet", antwort["grund"])

    def test_endpunkt_422_bei_leerem_text(self):
        with self.assertRaises(HTTPException) as cm:
            kategorie_vorschlag_ki(KiVorschlagIn(text="ab"), self.con, Bereich(1))
        self.assertEqual(422, cm.exception.status_code)

    def test_endpunkt_404_bei_fremder_sparte(self):
        fremde_sparte_id = self.andere_sparte_id + 10_000  # existiert sicher nicht
        with self.assertRaises(HTTPException) as cm:
            kategorie_vorschlag_ki(
                KiVorschlagIn(text="Merkur Einkauf", sparte_id=fremde_sparte_id),
                self.con, Bereich(1),
            )
        self.assertEqual(404, cm.exception.status_code)

    # ---- 5. /api/parse liefert "quelle" ------------------------------------

    def test_parse_quelle_name_bei_namensabgleich(self):
        vorschlag = parse_text(ParseIn(text="P70 Essen 12,50"), self.con, Bereich(1))
        self.assertEqual(self.kat_essen_id, vorschlag["kategorie_id"])
        self.assertEqual("name", vorschlag["quelle"])
        self.assertIsNone(vorschlag["regel_name"])

    def test_parse_quelle_regel_bei_regeltreffer(self):
        self.con.execute(
            "INSERT INTO regel(name, bedingung_text, ziel_kategorie_id, ziel_sparte_id, "
            "bereich_id, quelle, auto_verbuchen) VALUES('P70 Testregel', 'sonderling xyz', ?, ?, 1, 'manuell', 0)",
            (self.kat_essen_id, self.sparte_id),
        )
        self.con.commit()
        vorschlag = parse_text(ParseIn(text="sonderling xyz 9,90"), self.con, Bereich(1))
        self.assertEqual(self.kat_essen_id, vorschlag["kategorie_id"])
        self.assertEqual("regel", vorschlag["quelle"])
        self.assertEqual("P70 Testregel", vorschlag["regel_name"])

    def test_parse_quelle_none_ohne_treffer(self):
        vorschlag = parse_text(ParseIn(text="voellig unbekannter vorgang 3,20"), self.con, Bereich(1))
        self.assertIsNone(vorschlag["kategorie_id"])
        self.assertIsNone(vorschlag["quelle"])
        self.assertIsNone(vorschlag["regel_name"])

    def test_parse_bestehendes_verhalten_unveraendert(self):
        # Regressionsschutz: bestehende Felder bleiben wie zuvor befuellt.
        vorschlag = parse_text(ParseIn(text="gestern Diesel 82,30 Hof"), self.con, Bereich(1))
        self.assertEqual(8230, vorschlag["betrag_cent"])
        self.assertEqual("ausgabe", vorschlag["typ"])


if __name__ == "__main__":
    unittest.main()
