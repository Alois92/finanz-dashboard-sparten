"""F7: Kein Groessenlimit fuer Uploads/Importe - datei.file.read() ohne
Obergrenze liest die komplette Datei in den Speicher. lies_upload() bricht
jetzt mit 413 ab, sobald das Limit ueberschritten wird. Das Limit wird im
Test klein gesetzt (Monkeypatch), damit kein Multi-MB-Body noetig ist.
"""
from unittest.mock import patch

import test_bereiche as bereiche_tests
from app import uploads


def _multipart_datei(inhalt: bytes, dateiname: str, content_type: str, weitere_felder: dict | None = None) -> bytes:
    teile = []
    for feld, wert in (weitere_felder or {}).items():
        teile.append(
            b'--P10\r\nContent-Disposition: form-data; name="' + feld.encode() + b'"\r\n\r\n'
            + str(wert).encode() + b"\r\n"
        )
    teile.append(
        b'--P10\r\nContent-Disposition: form-data; name="datei"; filename="'
        + dateiname.encode("utf-8") + b'"\r\nContent-Type: ' + content_type.encode() + b"\r\n\r\n"
        + inhalt + b"\r\n"
    )
    teile.append(b"--P10--\r\n")
    return b"".join(teile)


class UploadLimitTest(bereiche_tests.BereicheTest):
    def test_beleg_upload_ueber_dem_limit_liefert_413(self):
        from app.routers import belege
        body = _multipart_datei(b"x" * 20, "gross.png", "image/png")
        with patch.object(belege, "DB_PATH", self.path), patch.object(uploads, "MAX_UPLOAD_BYTES", 10):
            status, data = self.request(
                "POST", "/api/belege?bereich_id=1",
                raw=body, content_type="multipart/form-data; boundary=P10",
            )
        self.assertEqual(413, status, data)

    def test_excel_import_ueber_dem_limit_liefert_413(self):
        body = _multipart_datei(
            b"x" * 20, "kassabuch.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            {"sparte_id": self.haupt, "modus": "pruefen"},
        )
        with patch.object(uploads, "MAX_UPLOAD_BYTES", 10):
            status, data = self.request(
                "POST", "/api/import/excel?bereich_id=1",
                raw=body, content_type="multipart/form-data; boundary=P10",
            )
        self.assertEqual(413, status, data)

    def test_csv_import_ueber_dem_limit_liefert_413(self):
        konto_id = self.con.execute(
            "SELECT id FROM bankkonto WHERE sparte_id = ? AND art <> 'kassa' LIMIT 1", (self.haupt,)
        ).fetchone()
        if konto_id is None:
            konto_id = self.con.execute(
                "INSERT INTO bankkonto(sparte_id, name, art) VALUES(?, 'F7-Test', 'bank')", (self.haupt,)
            )
            self.con.commit()
            konto_id = self.con.execute("SELECT last_insert_rowid()").fetchone()
        konto_id = konto_id[0]
        body = _multipart_datei(
            b"x" * 20, "umsaetze.csv", "text/csv", {"bankkonto_id": konto_id},
        )
        with patch.object(uploads, "MAX_UPLOAD_BYTES", 10):
            status, data = self.request(
                "POST", "/api/import/csv?bereich_id=1",
                raw=body, content_type="multipart/form-data; boundary=P10",
            )
        self.assertEqual(413, status, data)
