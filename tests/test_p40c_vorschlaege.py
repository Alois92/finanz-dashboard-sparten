"""P40c: Vorschlagsliste in der Schnellerfassung (QA2-03/P40b) und
Buchungs-Herkunft im Bankimport (P42b).

Teil 1 prueft die neue Treffer-Liste in POST /api/parse (app/routers/
schnellerfassung.py, ``_parse_einzeltext``) sowie die neue Hilfsfunktion
``finde_regeln`` in app/regeln.py direkt. Teil 2 prueft das neue Feld
``buchung`` in GET /api/bankumsaetze (app/routers/import_bank.py).

Nutzt dieselbe echte ASGI-Testinfrastruktur wie tests/test_bereiche.py.
"""
import pathlib
import subprocess
import unittest

import test_bereiche as bereiche_tests

from app.regeln import finde_regeln

ROOT = pathlib.Path(__file__).resolve().parents[1]


class TrefferListeTest(unittest.TestCase):
    """POST /api/parse liefert bis zu drei Kategorietreffer mit Herkunft."""

    request = bereiche_tests.BereicheTest.request
    setUp = bereiche_tests.BereicheTest.setUp

    def kategorie(self, name, sparte_id=None, richtung="ausgabe"):
        status, result = self.request("POST", "/api/kategorien", {
            "sparte_id": sparte_id or self.haupt, "name": name, "richtung": richtung,
        })
        self.assertEqual(201, status, result)
        return result["id"]

    def regel(self, name, bedingung_text, ziel_kategorie_id, prioritaet=100):
        status, result = self.request("POST", "/api/regeln", {
            "name": name, "bedingung_text": bedingung_text,
            "ziel_kategorie_id": ziel_kategorie_id, "quelle": "stichwort",
            "prioritaet": prioritaet,
        })
        self.assertEqual(201, status, result)
        return result["id"]

    def test_bis_zu_drei_treffer_name_dann_regel(self):
        """Namenstreffer zuerst, danach bis zu zwei weitere Regeltreffer."""
        kat_a = self.kategorie("Metrolebensmittel")
        kat_b = self.kategorie("Regelzielbeta")
        kat_c = self.kategorie("Regelzielgamma")
        self.regel("R-Beta", "regelwortbeta", kat_b)
        self.regel("R-Gamma", "regelwortgamma", kat_c)

        status, vorschlag = self.request(
            "POST", "/api/parse",
            {"text": "Metrolebensmittel regelwortbeta regelwortgamma 12,50"})
        self.assertEqual(200, status, vorschlag)

        treffer = vorschlag["treffer"]
        self.assertEqual(3, len(treffer))

        # Reihenfolge: Namensabgleich zuerst.
        self.assertEqual(kat_a, treffer[0]["kategorie_id"])
        self.assertEqual("name", treffer[0]["quelle"])
        self.assertIsNone(treffer[0]["regel_name"])

        # Danach beide Merkregel-Treffer (Reihenfolge zwischen ihnen nicht
        # vorgeschrieben, da gleiche Prioritaet).
        weitere = {t["kategorie_id"]: t for t in treffer[1:]}
        self.assertEqual({kat_b, kat_c}, set(weitere))
        for kat_id, regel_name in ((kat_b, "R-Beta"), (kat_c, "R-Gamma")):
            self.assertEqual("regel", weitere[kat_id]["quelle"])
            self.assertEqual(regel_name, weitere[kat_id]["regel_name"])
            self.assertEqual(self.haupt, weitere[kat_id]["sparte_id"])

    def test_treffer_liste_bei_reinem_regelweg(self):
        """Findet der Namensabgleich nichts, ist der erste Treffer eine Regel."""
        kat_x = self.kategorie("Zielkategoriex")
        kat_y = self.kategorie("Zielkategoriey")
        self.regel("R-X", "supermarktkette", kat_x, prioritaet=10)
        self.regel("R-Y", "einkaufsstaette", kat_y, prioritaet=50)

        status, vorschlag = self.request(
            "POST", "/api/parse",
            {"text": "supermarktkette einkaufsstaette 8,40"})
        self.assertEqual(200, status, vorschlag)
        treffer = vorschlag["treffer"]
        self.assertGreaterEqual(len(treffer), 1)
        # Bessere (niedrigere) Prioritaet zuerst.
        self.assertEqual(kat_x, treffer[0]["kategorie_id"])
        self.assertEqual("regel", treffer[0]["quelle"])
        self.assertEqual("R-X", treffer[0]["regel_name"])

    def test_maximal_drei_treffer(self):
        """Vier moegliche Regeltreffer werden auf drei gekappt."""
        kategorien = [self.kategorie(f"Kappungskategorie{i}") for i in range(4)]
        for i, kat in enumerate(kategorien):
            self.regel(f"R{i}", f"kappungswortnr{i}", kat, prioritaet=10 + i)
        text = "kappungswortnr0 kappungswortnr1 kappungswortnr2 kappungswortnr3 9,90"
        status, vorschlag = self.request("POST", "/api/parse", {"text": text})
        self.assertEqual(200, status, vorschlag)
        self.assertEqual(3, len(vorschlag["treffer"]))

    def test_abwaertskompatibilitaet_top_level_felder(self):
        """kategorie_id/quelle/regel_name bleiben = erster Treffer (Bestandstests)."""
        kat_a = self.kategorie("Kompatlebensmittel")
        status, vorschlag = self.request(
            "POST", "/api/parse", {"text": "Kompatlebensmittel 4,20"})
        self.assertEqual(200, status, vorschlag)
        treffer = vorschlag["treffer"]
        self.assertEqual(1, len(treffer))
        self.assertEqual(vorschlag["kategorie_id"], treffer[0]["kategorie_id"])
        self.assertEqual(vorschlag["quelle"], treffer[0]["quelle"])
        self.assertEqual(vorschlag["regel_name"], treffer[0]["regel_name"])
        self.assertEqual(kat_a, vorschlag["kategorie_id"])

    def test_ohne_treffer_leere_liste(self):
        status, vorschlag = self.request(
            "POST", "/api/parse", {"text": "voelligunbekannterzzztext 3,00"})
        self.assertEqual(200, status, vorschlag)
        self.assertEqual([], vorschlag["treffer"])
        self.assertIsNone(vorschlag["kategorie_id"])


class FindeRegelnTest(unittest.TestCase):
    """Direkter Test der neuen Hilfsfunktion app.regeln.finde_regeln."""

    setUp = bereiche_tests.BereicheTest.setUp

    def _regel_anlegen(self, name, bedingung_text, ziel_kategorie_id, prioritaet=100):
        self.con.execute(
            "INSERT INTO regel(name, bedingung_text, ziel_kategorie_id, bereich_id, "
            "quelle, prioritaet) VALUES(?,?,?,?, 'stichwort', ?)",
            (name, bedingung_text, ziel_kategorie_id, 1, prioritaet),
        )
        self.con.commit()

    def test_liefert_bis_zu_maximal_kandidaten_je_kategorie_einmal(self):
        kat_a = self.con.execute(
            "INSERT INTO kategorie(sparte_id,name,richtung) VALUES(?,?,'ausgabe')",
            (self.haupt, "FindeRegelnA"),
        ).lastrowid
        kat_b = self.con.execute(
            "INSERT INTO kategorie(sparte_id,name,richtung) VALUES(?,?,'ausgabe')",
            (self.haupt, "FindeRegelnB"),
        ).lastrowid
        self.con.commit()
        self._regel_anlegen("RA1", "findewortalpha", kat_a, prioritaet=10)
        # Zweite Regel auf dieselbe Kategorie - darf in finde_regeln nicht
        # doppelt auftauchen (je Kategorie hoechstens ein Eintrag).
        self._regel_anlegen("RA2", "findewortalpha zusatz", kat_a, prioritaet=20)
        self._regel_anlegen("RB1", "findewortbeta", kat_b, prioritaet=15)

        ergebnis = finde_regeln(
            self.con, "findewortalpha findewortbeta", bereich_id=1, maximal=3)
        kategorien = [r["ziel_kategorie_id"] for r in ergebnis]
        self.assertEqual(sorted({kat_a, kat_b}), sorted(kategorien))
        self.assertEqual(len(set(kategorien)), len(kategorien))

    def test_ohne_treffer_leere_liste(self):
        self.assertEqual([], finde_regeln(self.con, "nichts passt hier", bereich_id=1))

    def test_maximal_begrenzt_ergebnis(self):
        katze = []
        for i in range(4):
            kid = self.con.execute(
                "INSERT INTO kategorie(sparte_id,name,richtung) VALUES(?,?,'ausgabe')",
                (self.haupt, f"MaxKategorie{i}"),
            ).lastrowid
            katze.append(kid)
        self.con.commit()
        for i, kid in enumerate(katze):
            self._regel_anlegen(f"M{i}", f"maxwortnr{i}", kid, prioritaet=10 + i)
        text = "maxwortnr0 maxwortnr1 maxwortnr2 maxwortnr3"
        ergebnis = finde_regeln(self.con, text, bereich_id=1, maximal=2)
        self.assertEqual(2, len(ergebnis))


class BankumsatzBuchungFeldTest(unittest.TestCase):
    """GET /api/bankumsaetze liefert je Umsatz ``buchung`` (P42b)."""

    request = bereiche_tests.BereicheTest.request
    setUp = bereiche_tests.BereicheTest.setUp

    def konto(self, **extra):
        status, result = self.request("POST", "/api/konten", {
            "name": "P40c-Testbank", "art": "bank", "sparte_id": self.haupt, **extra,
        })
        self.assertEqual(201, status, result)
        return result["id"]

    def kategorie(self, name="P40c-Kategorie"):
        status, result = self.request("POST", "/api/kategorien", {
            "sparte_id": self.haupt, "name": name, "richtung": "ausgabe",
        })
        self.assertEqual(201, status, result)
        return result["id"]

    def test_buchung_null_fuer_offene_und_gefuellt_fuer_verbuchte(self):
        kid = self.konto()
        katid = self.kategorie("P40c-Ausgabenkategorie")
        csv_inhalt = (
            "Datum;Betrag;Text\n"
            "03.01.2026;-12,50;Erster Umsatz\n"
            "04.01.2026;-7,00;Zweiter Umsatz\n"
        ).encode("utf-8-sig")
        boundary = "p40ctest"
        kopf = (
            f'--{boundary}\r\nContent-Disposition: form-data; name="bankkonto_id"\r\n\r\n{kid}\r\n'
            f'--{boundary}\r\nContent-Disposition: form-data; name="datei"; filename="umsaetze.csv"\r\n'
            "Content-Type: text/csv\r\n\r\n"
        ).encode() + csv_inhalt + f"\r\n--{boundary}--\r\n".encode()
        status, ergebnis = self.request(
            "POST", "/api/import/csv", raw=kopf,
            content_type=f"multipart/form-data; boundary={boundary}")
        self.assertEqual(200, status, ergebnis)

        status, umsaetze = self.request("GET", f"/api/bankumsaetze?bankkonto_id={kid}")
        self.assertEqual(200, status, umsaetze)
        self.assertEqual(2, len(umsaetze))
        for u in umsaetze:
            self.assertIn("buchung", u)
            self.assertIsNone(u["buchung"])

        erster = next(u for u in umsaetze if "Erster" in (u["text"] or ""))
        status, verbucht = self.request(
            "POST", f"/api/bankumsaetze/{erster['id']}/verbuchen",
            {"sparte_id": self.haupt, "kategorie_id": katid, "text": "Ueberschriebener Text"})
        self.assertEqual(201, status, verbucht)

        status, umsaetze = self.request("GET", f"/api/bankumsaetze?bankkonto_id={kid}")
        self.assertEqual(200, status, umsaetze)
        verbuchter = next(u for u in umsaetze if u["id"] == erster["id"])
        offener = next(u for u in umsaetze if u["id"] != erster["id"])

        self.assertIsNone(offener["buchung"])

        self.assertIsNotNone(verbuchter["buchung"])
        for feld in ("id", "typ", "text", "kategorie_name"):
            self.assertIn(feld, verbuchter["buchung"])
        self.assertEqual("ausgabe", verbuchter["buchung"]["typ"])
        self.assertEqual("Ueberschriebener Text", verbuchter["buchung"]["text"])
        self.assertEqual("P40c-Ausgabenkategorie", verbuchter["buchung"]["kategorie_name"])
        # Bestehendes Feld (P42) bleibt unveraendert: kein "vorschlag" mehr fuer
        # verbuchte Umsaetze.
        self.assertNotIn("vorschlag", verbuchter)


class P40cJsSyntaxTest(unittest.TestCase):
    """node --check fuer die geaenderten JS-Dateien des Pakets."""

    def _node_check(self, relativer_pfad):
        pfad = ROOT / relativer_pfad
        ergebnis = subprocess.run(["node", "--check", str(pfad)], capture_output=True, text=True)
        self.assertEqual(0, ergebnis.returncode, ergebnis.stderr)

    def test_node_check_erfassen_js(self):
        self._node_check("static-neu/pages/erfassen.js")

    def test_node_check_bankimport_js(self):
        self._node_check("static-neu/pages/bankimport.js")


if __name__ == "__main__":
    unittest.main()
