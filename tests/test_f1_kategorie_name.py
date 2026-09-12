"""F1: Kategorienamen werden ungefiltert in Hinweistexten gerendert
(rechenbasis.hinweise -> uebersicht.js). Neben dem esc() im Frontend muss
das Backend ein enges Zeichenset erzwingen, damit weder API noch
Excel-Import Namen mit Winkelklammern/Steuerzeichen anlegen koennen.
"""
import test_bereiche as bereiche_tests


class KategorieNameValidierungTest(bereiche_tests.BereicheTest):
    def test_post_mit_xss_payload_liefert_422(self):
        status, fehler = self.request("POST", "/api/kategorien", {
            "sparte_id": self.haupt, "name": '<img src=x onerror=alert(1)>', "richtung": "ausgabe",
        })
        self.assertEqual(422, status, fehler)

    def test_post_mit_zu_langem_namen_liefert_422(self):
        status, fehler = self.request("POST", "/api/kategorien", {
            "sparte_id": self.haupt, "name": "A" * 81, "richtung": "ausgabe",
        })
        self.assertEqual(422, status, fehler)

    def test_post_mit_genau_80_zeichen_wird_akzeptiert(self):
        status, kategorie = self.request("POST", "/api/kategorien", {
            "sparte_id": self.haupt, "name": "A" * 80, "richtung": "ausgabe",
        })
        self.assertEqual(201, status, kategorie)

    def test_patch_mit_xss_payload_liefert_422(self):
        status, angelegt = self.request("POST", "/api/kategorien", {
            "sparte_id": self.haupt, "name": "Normal", "richtung": "ausgabe",
        })
        self.assertEqual(201, status, angelegt)
        status, fehler = self.request(
            "PATCH", f"/api/kategorien/{angelegt['id']}", {"name": '<img src=x onerror=alert(1)>'}
        )
        self.assertEqual(422, status, fehler)
        unveraendert = self.con.execute(
            "SELECT name FROM kategorie WHERE id=?", (angelegt["id"],)
        ).fetchone()
        self.assertEqual("Normal", unveraendert["name"])
