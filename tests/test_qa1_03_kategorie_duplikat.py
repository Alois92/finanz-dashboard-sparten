"""QA1-03/QA1-04: Kategorie-Umbenennen/Anlegen muss Duplikatnamen ablehnen
und leere Namen verstaendlich melden.

QA1-03: Umbenennen (oder Neuanlegen) einer Kategorie auf einen bereits von
einer anderen aktiven Kategorie derselben Sparte (und desselben Parents)
verwendeten Namen wurde bisher klaglos akzeptiert -> zwei nicht
unterscheidbare Kategorien mit gleichem Namen.
QA1-04: leerer Name soll mit einer verstaendlichen Fehlermeldung abgelehnt
werden (Backend gab schon vorher 400, dieser Test haelt es fest).
"""
import test_bereiche as bereiche_tests


class KategorieDuplikatTest(bereiche_tests.BereicheTest):
    def _neue_kategorie(self, name, richtung="ausgabe", sparte_id=None, bereich_id=1):
        status, k = self.request("POST", f"/api/kategorien?bereich_id={bereich_id}", {
            "sparte_id": sparte_id or self.haupt, "name": name, "richtung": richtung,
        })
        self.assertEqual(201, status, k)
        return k

    def test_patch_auf_vorhandenen_namen_liefert_409(self):
        ziel = self._neue_kategorie("Versicherung")
        quelle = self._neue_kategorie("Umbau")
        status, fehler = self.request("PATCH", f"/api/kategorien/{quelle['id']}", {"name": "Versicherung"})
        self.assertEqual(409, status, fehler)
        self.assertIn("Versicherung", fehler["detail"])
        # Name darf sich dadurch nicht geaendert haben.
        unveraendert = self.con.execute("SELECT name FROM kategorie WHERE id=?", (quelle["id"],)).fetchone()
        self.assertEqual("Umbau", unveraendert["name"])

    def test_patch_case_insensitiv_und_getrimmt(self):
        self._neue_kategorie("Versicherung")
        quelle = self._neue_kategorie("Umbau")
        status, fehler = self.request("PATCH", f"/api/kategorien/{quelle['id']}", {"name": "  versicherung  "})
        self.assertEqual(409, status, fehler)

    def test_patch_auf_andere_sparte_erlaubt(self):
        self._neue_kategorie("Versicherung", sparte_id=self.verein, bereich_id=2)
        quelle = self._neue_kategorie("Umbau")
        status, ergebnis = self.request("PATCH", f"/api/kategorien/{quelle['id']}", {"name": "Versicherung"})
        self.assertEqual(200, status, ergebnis)

    def test_patch_auf_stillgelegten_namen_erlaubt(self):
        alt = self._neue_kategorie("Versicherung")
        self.request("PATCH", f"/api/kategorien/{alt['id']}", {"aktiv": 0})
        quelle = self._neue_kategorie("Umbau")
        status, ergebnis = self.request("PATCH", f"/api/kategorien/{quelle['id']}", {"name": "Versicherung"})
        self.assertEqual(200, status, ergebnis)

    def test_patch_leerer_name_liefert_400(self):
        quelle = self._neue_kategorie("Umbau")
        status, fehler = self.request("PATCH", f"/api/kategorien/{quelle['id']}", {"name": "   "})
        self.assertEqual(400, status, fehler)

    def test_post_auf_vorhandenen_namen_liefert_409(self):
        self._neue_kategorie("Versicherung")
        status, fehler = self.request("POST", "/api/kategorien", {
            "sparte_id": self.haupt, "name": "Versicherung", "richtung": "ausgabe",
        })
        self.assertEqual(409, status, fehler)


if __name__ == "__main__":
    import unittest
    unittest.main()
