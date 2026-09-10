"""Regressionen fuer Regelkontext und das Zusammenspiel mit P12-Replays."""
import json
import sqlite3
import unittest

from app import db
from app.regeln import finde_regel
from app.routers.buchungen import create_buchung, delete_buchung
from app.schemas import BuchungIn, ZeileIn


class P15Runde3Test(unittest.TestCase):
    def setUp(self):
        self.con = sqlite3.connect(':memory:')
        self.addCleanup(self.con.close)
        self.con.row_factory = sqlite3.Row
        self.con.executescript(db.SCHEMA.read_text(encoding='utf-8'))
        self.con.executescript(db.SEED.read_text(encoding='utf-8'))
        self.sparten = []
        self.kategorien = []
        for name in ('Erste', 'Zweite'):
            sid = self.con.execute(
                "INSERT INTO sparte(name, typ) VALUES(?, 'privat')", (name,)
            ).lastrowid
            kid = self.con.execute(
                "INSERT INTO kategorie(sparte_id, name, richtung) VALUES(?, ?, 'ausgabe')",
                (sid, name),
            ).lastrowid
            self.sparten.append(sid)
            self.kategorien.append(kid)
        self.con.commit()

    def buchung(self, index=0, **extra):
        return BuchungIn(
            sparte_id=self.sparten[index], datum='2026-09-10', typ='ausgabe',
            zahlungsart='bank', text='Lieferant Rechnung',
            zeilen=[ZeileIn(kategorie_id=self.kategorien[index], betrag_cent=1500)],
            **extra,
        )

    def test_regel_ohne_kontext_und_mit_verbindlicher_sparte(self):
        create_buchung(self.buchung(), self.con)
        ohne = finde_regel(self.con, 'Lieferant 42')
        self.assertIsNotNone(ohne)
        self.assertEqual(self.kategorien[0], ohne['ziel_kategorie_id'])
        self.assertEqual(ohne, finde_regel(
            self.con, 'Lieferant 42', sparte_id=self.sparten[0]))
        self.assertIsNone(finde_regel(
            self.con, 'Lieferant 42', sparte_id=self.sparten[1]))
        self.assertIsNone(finde_regel(self.con, 'Lieferant 42', bereich_id=2))
        self.con.execute(
            "INSERT INTO regel(name, bedingung_text, ziel_sparte_id, ziel_kategorie_id, "
            "eingabe_sparte_id) VALUES('zweite', 'lieferant rechnung', ?, ?, ?)",
            (self.sparten[1], self.kategorien[1], self.sparten[1]),
        )
        self.con.commit()
        self.assertTrue(finde_regel(self.con, 'Lieferant 42')['konflikt'])
        self.assertFalse(finde_regel(
            self.con, 'Lieferant 42', sparte_id=self.sparten[0])['konflikt'])

    def test_replay_erhaelt_antwort_und_lernt_nicht_erneut(self):
        body = self.buchung(client_request_id='p15-runde3-replay')
        antwort = create_buchung(body, self.con)
        regel = dict(self.con.execute('SELECT * FROM regel').fetchone())
        self.assertEqual(antwort['id'], regel['gelernt_aus_buchung_id'])
        self.assertEqual(self.sparten[0], regel['eingabe_sparte_id'])
        self.assertEqual('gelernt', regel['quelle'])
        self.assertEqual(0, regel['auto_verbuchen'])
        self.con.execute('UPDATE regel SET aktiv=0')
        self.con.commit()
        delete_buchung(antwort['id'], self.con)
        self.assertIsNone(self.con.execute(
            'SELECT gelernt_aus_buchung_id FROM regel').fetchone()[0])
        replay = create_buchung(body, self.con)
        self.assertEqual(200, replay.status_code)
        self.assertEqual(antwort, json.loads(replay.body))
        self.assertEqual(0, self.con.execute('SELECT COUNT(*) FROM buchung').fetchone()[0])
        self.assertEqual((1, 0), tuple(self.con.execute(
            'SELECT COUNT(*), MAX(aktiv) FROM regel').fetchone()))

    def test_mehrzeilige_buchung_lernt_keine_regel(self):
        body = self.buchung()
        body.zeilen.append(ZeileIn(kategorie_id=self.kategorien[0], betrag_cent=500))
        antwort = create_buchung(body, self.con)
        self.assertEqual(2, len(antwort['zeilen']))
        self.assertEqual(0, self.con.execute('SELECT COUNT(*) FROM regel').fetchone()[0])
