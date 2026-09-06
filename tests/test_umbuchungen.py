"""Tests fuer Umbuchungen zwischen Sparten (POST /api/umbuchungen,
app/routers/buchungen.py::create_umbuchung).

Deckt ab: zwei gekoppelte Buchungen mit gemeinsamer transfer_gruppe_id,
Erfolgsneutralitaet im Dashboard (Umbuchungen tauchen nicht als Einnahme/
Ausgabe auf) und Ablehnung ungueltiger Eingaben (gleiche Sparte, Betrag <= 0).
"""
import os
import tempfile
import unittest
from pathlib import Path

from fastapi import HTTPException
from pydantic import ValidationError


TEST_DIR = tempfile.TemporaryDirectory(prefix="finanz-umbuchungen-")
os.environ["FINANZ_DB"] = str(Path(TEST_DIR.name) / "umbuchungen-test.db")

from app.db import get_connection, init_db
from app.routers.buchungen import UmbuchungIn, create_umbuchung
from app.routers.dashboard import dashboard


class UmbuchungenApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()

    def setUp(self):
        con = get_connection()
        try:
            con.execute("DELETE FROM buchungszeile")
            con.execute("DELETE FROM buchung")
            con.commit()
            self.von_sparte_id = con.execute(
                "INSERT INTO sparte(name, typ) VALUES('Testsparte Von', 'privat')"
            ).lastrowid
            self.nach_sparte_id = con.execute(
                "INSERT INTO sparte(name, typ) VALUES('Testsparte Nach', 'privat')"
            ).lastrowid
            con.commit()
        finally:
            con.close()

    def test_umbuchung_erzeugt_zwei_gekoppelte_buchungen(self):
        con = get_connection()
        self.addCleanup(con.close)

        ergebnis = create_umbuchung(
            UmbuchungIn(
                von_sparte_id=self.von_sparte_id,
                nach_sparte_id=self.nach_sparte_id,
                datum="2026-04-01",
                betrag_cent=5000,
            ),
            con,
        )

        self.assertEqual(len(ergebnis["buchung_ids"]), 2)
        self.assertEqual(ergebnis["betrag_cent"], 5000)

        buchungen = con.execute(
            "SELECT id, sparte_id, typ, transfer_gruppe_id, betrag_cent FROM buchung "
            "WHERE id IN (?, ?)", tuple(ergebnis["buchung_ids"]),
        ).fetchall()
        self.assertEqual(len(buchungen), 2)
        gruppen = {b["transfer_gruppe_id"] for b in buchungen}
        self.assertEqual(gruppen, {ergebnis["transfer_gruppe_id"]})
        sparten = {b["sparte_id"] for b in buchungen}
        self.assertEqual(sparten, {self.von_sparte_id, self.nach_sparte_id})
        for b in buchungen:
            self.assertEqual(b["typ"], "umbuchung")
            self.assertEqual(b["betrag_cent"], 5000)

    def test_umbuchung_ist_erfolgsneutral_im_dashboard(self):
        con = get_connection()
        self.addCleanup(con.close)

        create_umbuchung(
            UmbuchungIn(
                von_sparte_id=self.von_sparte_id,
                nach_sparte_id=self.nach_sparte_id,
                datum="2026-04-02",
                betrag_cent=7500,
            ),
            con,
        )

        ergebnis = dashboard(
            sparte_id=None, globalgruppe_id=None, von=None, bis=None, con=con,
        )
        self.assertEqual(ergebnis["einnahmen_cent"], 0)
        self.assertEqual(ergebnis["ausgaben_cent"], 0)
        self.assertEqual(ergebnis["saldo_cent"], 0)
        self.assertEqual(ergebnis["per_kategorie"], [])
        self.assertEqual(ergebnis["per_sparte"], [])

    def test_gleiche_sparte_wird_abgelehnt(self):
        con = get_connection()
        self.addCleanup(con.close)

        with self.assertRaises(HTTPException) as ctx:
            create_umbuchung(
                UmbuchungIn(
                    von_sparte_id=self.von_sparte_id,
                    nach_sparte_id=self.von_sparte_id,
                    datum="2026-04-03",
                    betrag_cent=1000,
                ),
                con,
            )
        self.assertEqual(400, ctx.exception.status_code)

        anzahl = con.execute("SELECT COUNT(*) AS n FROM buchung").fetchone()["n"]
        self.assertEqual(anzahl, 0)

    def test_betrag_0_oder_negativ_wird_abgelehnt(self):
        # betrag_cent unterliegt Field(gt=0) im Pydantic-Schema: ein Wert <= 0
        # scheitert bereits an der Eingabevalidierung (von FastAPI in einen
        # 422-Fehler uebersetzt) und erreicht den Endpoint-Code gar nicht erst.
        for ungueltiger_betrag in (0, -100):
            with self.assertRaises(ValidationError):
                UmbuchungIn(
                    von_sparte_id=self.von_sparte_id,
                    nach_sparte_id=self.nach_sparte_id,
                    datum="2026-04-04",
                    betrag_cent=ungueltiger_betrag,
                )

        con = get_connection()
        try:
            n = con.execute("SELECT COUNT(*) AS n FROM buchung").fetchone()["n"]
            self.assertEqual(n, 0)
        finally:
            con.close()


if __name__ == "__main__":
    unittest.main()
