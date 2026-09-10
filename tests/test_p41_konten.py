"""P41: Konten-/Ausgleichsseite (Frontend-Anbindung und Auslieferung)."""
import pathlib
import subprocess
import sys
import unittest

import test_bereiche as bereiche_tests

ROOT = pathlib.Path(__file__).resolve().parents[1]
STATIC = ROOT / "static-neu" / "pages"


class P41KontenTest(unittest.TestCase):
    setUp = bereiche_tests.BereicheTest.setUp
    request = bereiche_tests.BereicheTest.request

    def konto(self, art="bank", sparte_id=None, name="P41-Konto"):
        status, res = self.request("POST", "/api/konten", {
            "name": name, "art": art, "sparte_id": sparte_id,
        })
        self.assertEqual(201, status, res)
        return res

    def kategorie(self, sparte_id, name, richtung="beides"):
        kid = self.con.execute(
            "INSERT INTO kategorie(sparte_id, name, richtung) VALUES(?, ?, ?)",
            (sparte_id, name, richtung),
        ).lastrowid
        self.con.commit()
        return kid

    # ---- Auslieferung ----

    def test_seite_und_stylesheet_werden_ausgeliefert(self):
        status, body = self.request("GET", "/neu/pages/konten.js")
        self.assertEqual(200, status)
        self.assertIn(b"export function render", body)
        status, body = self.request("GET", "/neu/pages/konten.css")
        self.assertEqual(200, status)
        self.assertIn(b".kto-row", body)

    def test_konten_js_hat_gueltige_syntax(self):
        for datei in sorted(STATIC.glob("konten*.js")):
            result = subprocess.run(["node", "--check", str(datei)], capture_output=True, text=True)
            self.assertEqual(0, result.returncode, f"{datei}: {result.stderr}")

    # ---- Konten: Liste, Anlegen, Anker, Zaehlung ----

    def test_kontenliste_liefert_die_vom_modul_gelesenen_felder(self):
        self.konto(art="bank", sparte_id=self.haupt, name="P41-Feldertest")
        status, konten = self.request("GET", "/api/konten")
        self.assertEqual(200, status, konten)
        row = next(k for k in konten if k["name"] == "P41-Feldertest")
        for feld in ("id", "name", "art", "waehrung", "sparte_id", "stand_cent", "datenstand", "hinweis"):
            self.assertIn(feld, row)
        self.assertIsNone(row["stand_cent"])
        self.assertEqual("unbekannt", row["datenstand"])

    def test_kassa_ohne_sparte_liefert_422_feldfehler(self):
        status, res = self.request("POST", "/api/konten", {"name": "P41-Kassa-ohne-Sparte", "art": "kassa"})
        self.assertEqual(422, status)
        self.assertIn("detail", res)

    def test_anker_setzen_liefert_differenz_bei_zweitem_anker(self):
        konto = self.konto(art="kassa", sparte_id=self.haupt)
        status, erster = self.request("POST", f"/api/konten/{konto['id']}/anker", {
            "stichtag": "2026-08-01", "saldo_cent": 10000, "quelle": "manuell",
        })
        self.assertEqual(201, status, erster)
        self.assertNotIn("differenz_cent", erster)
        self.con.execute(
            "INSERT INTO bewegung(konto_id, datum, betrag_signed_cent, quelle) VALUES(?,?,?,'manuell')",
            (konto["id"], "2026-08-10", 500),
        )
        self.con.commit()
        status, zweiter = self.request("POST", f"/api/konten/{konto['id']}/anker", {
            "stichtag": "2026-08-15", "saldo_cent": 20000, "quelle": "manuell",
        })
        self.assertEqual(201, status, zweiter)
        self.assertIn("differenz_cent", zweiter)
        self.assertIn("gerechnet_cent", zweiter)
        self.assertEqual(20000 - 10500, zweiter["differenz_cent"])

    def test_kassazaehlung_und_differenz_buchen(self):
        konto = self.konto(art="kassa", sparte_id=self.haupt)
        self.request("POST", f"/api/konten/{konto['id']}/anker", {
            "stichtag": "2026-08-01", "saldo_cent": 10000, "quelle": "manuell",
        })
        status, zaehlung = self.request("POST", f"/api/konten/{konto['id']}/zaehlung", {
            "datum": "2026-08-05", "gezaehlt_cent": 9000,
        })
        self.assertEqual(201, status, zaehlung)
        self.assertEqual(-1000, zaehlung["differenz_cent"])
        kat = self.kategorie(self.haupt, "Kassadifferenz", "beides")
        status, gebucht = self.request(
            "POST", f"/api/konten/{konto['id']}/zaehlung/{zaehlung['id']}/buchen",
            {"kategorie_id": kat},
        )
        self.assertEqual(201, status, gebucht)
        self.assertEqual("geklaert", gebucht["status"])

    def test_bewegungen_liefern_cursor_zum_nachladen(self):
        konto = self.konto(art="bank", sparte_id=self.haupt)
        self.con.executemany(
            "INSERT INTO bewegung(konto_id, datum, betrag_signed_cent, quelle) VALUES(?,?,?,'manuell')",
            [(konto["id"], f"2026-08-0{n}", 100 * n) for n in range(1, 4)],
        )
        self.con.commit()
        status, seite1 = self.request("GET", f"/api/konten/{konto['id']}/bewegungen?limit=1")
        self.assertEqual(200, status, seite1)
        self.assertEqual(1, len(seite1["bewegungen"]))
        self.assertIsNotNone(seite1["naechster_cursor"])
        status, seite2 = self.request(
            "GET", f"/api/konten/{konto['id']}/bewegungen?limit=1&cursor={seite1['naechster_cursor']}"
        )
        self.assertEqual(200, status, seite2)
        self.assertNotEqual(seite1["bewegungen"][0]["id"], seite2["bewegungen"][0]["id"])

    def test_offene_abgleiche_liefert_die_vom_modul_gelesenen_felder(self):
        konto = self.konto(art="bank", sparte_id=self.haupt)
        status, res = self.request("GET", f"/api/konten/{konto['id']}/offene-abgleiche")
        self.assertEqual(200, status, res)
        for feld in ("konto_id", "manuelle_anzahl", "umsaetze_anzahl"):
            self.assertIn(feld, res)

    # ---- Auslagen und Ausgleich ----

    def test_auslagen_ausgleich_und_ruecknahme(self):
        zahler = self.con.execute(
            "SELECT id FROM sparte WHERE typ = 'privat' AND bereich_id = 1 ORDER BY id"
        ).fetchone()[0]
        hof = self.con.execute("INSERT INTO sparte(name, typ) VALUES('P41-Testhof', 'hof')").lastrowid
        self.con.commit()
        kat = self.kategorie(hof, "P41-Testkosten", "beides")
        status, buchung = self.request("POST", "/api/buchungen", {
            "sparte_id": hof, "datum": "2026-08-05", "typ": "ausgabe", "zahlungsart": "bar",
            "bezahlt_von_sparte_id": zahler,
            "zeilen": [{"kategorie_id": kat, "betrag_cent": 5000}],
        })
        self.assertEqual(201, status, buchung)

        status, auslagen = self.request("GET", "/api/auslagen")
        self.assertEqual(200, status, auslagen)
        gruppe = next(g for g in auslagen if g["sparte_id"] == hof and g["zahler_sparte_id"] == zahler)
        for feld in ("zahler_sparte_id", "sparte_id", "offen_cent", "anzahl", "auslagen"):
            self.assertIn(feld, gruppe)
        for feld in ("id", "buchung_id", "datum", "text", "kategorie", "betrag_cent", "offen_cent"):
            self.assertIn(feld, gruppe["auslagen"][0])
        auslage_id = gruppe["auslagen"][0]["id"]

        status, ausgleich = self.request("POST", "/api/ausgleiche", {
            "von_sparte_id": hof, "nach_sparte_id": zahler, "auslage_ids": [auslage_id],
            "datum": "2026-08-06", "betrag_cent": 2000, "zahlungsart": "bar",
            "client_request_id": "p41-test-1",
        })
        self.assertEqual(201, status, ausgleich)
        self.assertIn("warnungen", ausgleich)
        self.assertIn("zuordnungen", ausgleich)

        status, historie = self.request("GET", "/api/ausgleiche")
        self.assertEqual(200, status, historie)
        eintrag = next(a for a in historie if a["id"] == ausgleich["id"])
        for feld in ("id", "datum", "von_sparte_id", "nach_sparte_id", "betrag_cent", "zahlungsart", "aufgehoben_am"):
            self.assertIn(feld, eintrag)

        status, _ = self.request("DELETE", f"/api/ausgleiche/{ausgleich['id']}")
        self.assertEqual(204, status)
        status, danach = self.request("GET", "/api/auslagen")
        gruppe_danach = next(g for g in danach if g["sparte_id"] == hof and g["zahler_sparte_id"] == zahler)
        self.assertEqual(5000, gruppe_danach["offen_cent"])


if __name__ == "__main__":
    unittest.main()
