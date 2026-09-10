"""Vor dem P20-Umbau aufgezeichnete Antworten der echten ASGI-Routen."""
import json
import pathlib
import unittest

import test_bereiche


class P20Snapshots(unittest.TestCase):
    setUp = test_bereiche.BereicheTest.setUp
    request = test_bereiche.BereicheTest.request

    def responses(self):
        self.con.execute("INSERT INTO buchung(sparte_id,datum,typ,text) VALUES(?,'2025-11-15','einnahme','Altmarker')", (self.haupt,))
        bid = self.con.execute('SELECT max(id) FROM buchung').fetchone()[0]
        self.con.execute('INSERT INTO buchungszeile(buchung_id,kategorie_id,betrag_cent) VALUES(?,?,12345)', (bid, self.kategorien[self.haupt]))
        self.con.commit()
        return {url: self.request('GET', url)[1] for url in (
            '/api/dashboard', '/api/jahresvergleich', '/api/verlauf',
            '/api/buchungen/suche?q=marker', '/api/dashboard?bereich_id=2',
            '/api/dashboard?von=2026-01-01&bis=2026-12-31')}

    def test_antworten_vor_umbau(self):
        expected = json.loads((pathlib.Path(__file__).parent / 'snapshots/p20_alt.json').read_text(encoding='utf-8'))
        self.assertEqual(expected, self.responses())
