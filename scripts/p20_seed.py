"""Reproduzierbare 5.000 Buchungen für die P20-Laufzeitmessung.

Aufruf: python scripts/p20_seed.py
Verwendet ausschließlich eine automatisch entfernte TemporaryDirectory-Datenbank.
"""
import json
import pathlib
import sys
import time
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def seed_5000(con):
    if con.execute('SELECT COUNT(*) FROM buchung').fetchone()[0]:
        raise ValueError('Performance-Seed benötigt eine leere Buchungstabelle')
    con.executemany("INSERT INTO sparte(id,name,typ,bereich_id) VALUES(?,?,'privat',?)",
                    [(901, 'P20 A', 1), (902, 'P20 B', 1), (903, 'P20 Verein', 2)])
    con.executemany("INSERT INTO kategorie(id,sparte_id,name,richtung) VALUES(?,?,?,'beides')",
                    [(911, 901, 'Miete'), (912, 902, 'Futtermittel'), (913, 903, 'Verein')])
    bookings, lines = [], []
    for i in range(5000):
        offset = i % 3
        datum = f'{2025 + i % 2}-{1 + (i // 2) % 12:02}-{1 + i % 28:02}'
        bookings.append((10000 + i, 901 + offset, datum, 'einnahme' if i % 4 == 0 else 'ausgabe'))
        lines.append((10000 + i, 911 + offset, 100 + i))
    con.executemany('INSERT INTO buchung(id,sparte_id,datum,typ) VALUES(?,?,?,?)', bookings)
    con.executemany('INSERT INTO buchungszeile(buchung_id,kategorie_id,betrag_cent) VALUES(?,?,?)', lines)
    con.commit()


def main():
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / 'tests'))
    from test_p20_runner import temporaere_rechte
    temporaere_rechte()
    import test_bereiche

    class Benchmark(unittest.TestCase):
        setUp = test_bereiche.BereicheTest.setUp
        request = test_bereiche.BereicheTest.request

    case = Benchmark()
    case.setUp()
    try:
        case.con.execute('DELETE FROM buchung')
        seed_5000(case.con)
        times = []
        for _ in range(6):
            start = time.perf_counter()
            status, data = case.request('GET', '/api/uebersicht?jahr=2026&stichtag=2026-09-08')
            times.append(round((time.perf_counter() - start) * 1000, 3))
            if status != 200 or data['ist']['ausgaben_cent'] <= 0:
                raise AssertionError((status, data))
        result = {'buchungen': case.con.execute('SELECT COUNT(*) FROM buchung').fetchone()[0],
                  'messung': 'ASGI GET einschließlich JSON und Dependencies',
                  'erster_aufruf_ms': times[0], 'weitere_aufrufe_ms': times[1:],
                  'maximum_ms': max(times), 'grenze_ms': 300}
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if max(times) < 300 else 1
    finally:
        case.doCleanups()


if __name__ == '__main__':
    raise SystemExit(main())
