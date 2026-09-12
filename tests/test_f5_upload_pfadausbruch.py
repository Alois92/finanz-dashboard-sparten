"""F5: Pfadausbruch beim Beleg-Upload ueber den Dateinamen (nur Windows
betroffen: lexikalische Pfadnormalisierung laesst '..'-Segmente aus dem
Belegordner ausbrechen). Regressionstest ueber die echte ASGI-Route
(app/routers/belege.py upload_beleg) mit rohem multipart-Body, wie in
test_bereiche.py etabliert.
"""
import pathlib
from unittest.mock import patch

import test_bereiche as bereiche_tests


def _multipart(filename: str, inhalt: bytes = b"foto") -> bytes:
    return (
        b'--P10\r\nContent-Disposition: form-data; name="datei"; filename="'
        + filename.encode("utf-8")
        + b'"\r\nContent-Type: image/png\r\n\r\n'
        + inhalt
        + b"\r\n--P10--\r\n"
    )


class UploadPfadausbruchTest(bereiche_tests.BereicheTest):
    def _upload(self, filename: str, bereich_id: int = 1):
        from app.routers import belege
        with patch.object(belege, "DB_PATH", self.path):
            return self.request(
                "POST", f"/api/belege?bereich_id={bereich_id}",
                raw=_multipart(filename), content_type="multipart/form-data; boundary=P10",
            )

    def test_traversal_dateiname_bricht_nicht_aus_dem_belegordner_aus(self):
        status, data = self._upload("../../../../evil.png")
        self.assertEqual(201, status, data)

        pfad = pathlib.Path(data["pfad"])
        belege_root = (self.path.parent / "belege").resolve()
        # Die Datei muss unterhalb von belege/<sparte> liegen, nicht zwei
        # Ebenen darueber.
        pfad.resolve().relative_to(belege_root)
        self.assertTrue(pfad.is_file())
        # Ausserhalb des Belegordners darf nichts entstanden sein.
        self.assertFalse((self.path.parent.parent / "evil.png").exists())
        self.assertFalse((self.path.parent / "evil.png").exists())

    def test_dateiname_mit_schraegstrich_wird_abgelegt_statt_500(self):
        status, data = self._upload("unter/ordner/bild.png")
        self.assertEqual(201, status, data)
        pfad = pathlib.Path(data["pfad"])
        belege_root = (self.path.parent / "belege").resolve()
        pfad.resolve().relative_to(belege_root)
        self.assertTrue(pfad.is_file())

    def test_sehr_langer_dateiname_wird_gekuerzt_statt_500(self):
        status, data = self._upload("a" * 250 + ".png")
        self.assertEqual(201, status, data)
        pfad = pathlib.Path(data["pfad"])
        self.assertTrue(pfad.is_file())
        self.assertLessEqual(len(pfad.name), 130)  # beleg_id + '_' + <=120 Zeichen
