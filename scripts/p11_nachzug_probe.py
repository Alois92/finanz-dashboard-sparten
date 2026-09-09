"""Reproduzierbare P11-Bestandsprobe ausschließlich mit synthetischen Daten.

Aufruf aus dem Worktree: python -m scripts.p11_nachzug_probe
Die Ausgangsstruktur ist die unveränderte P10-Kopie von db/schema.sql.
"""
import hashlib
import logging
import os
from pathlib import Path
import sqlite3

from app import migrate


def main():
    path = Path(os.environ['LOCALAPPDATA']) / 'Temp' / 'p11-bestand.db'
    if path.exists():
        raise RuntimeError(f'Probe überschreibt keine vorhandene Datenbank: {path}')
    root = Path(__file__).resolve().parents[1]
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    try:
        con.executescript((root/'tests/fixtures/schema_p10.sql').read_text(encoding='utf-8'))
        con.executescript((root/'db/seed.sql').read_text(encoding='utf-8'))
        con.executemany('INSERT INTO schema_version(version,name) VALUES(?,?)',[(1,'schema_version'),(2,'import_batch_erkennung'),(3,'bereiche')])
        sids = [con.execute("INSERT INTO sparte(name,typ) VALUES(?,'privat')",(f'P11 Test {n}',)).lastrowid for n in (1,2)]
        kids = [con.execute("INSERT INTO bankkonto(name,sparte_id) VALUES(?,?)",(f'P11 Testbank {n}',sid)).lastrowid for n,sid in enumerate(sids,1)]
        cats = [con.execute("INSERT INTO kategorie(sparte_id,name,richtung) VALUES(?,'P11 Test','beides')",(sid,)).lastrowid for sid in sids]
        uids = [con.execute("INSERT INTO bankumsatz(bankkonto_id,datum,betrag_cent,import_hash) VALUES(?,'2026-01-02',?,?)",(kids[0],cent,f'p11-{n}')).lastrowid for n,cent in enumerate((-100,200,300))]
        rows = [(0,'ausgabe','bank',uids[0],None,100,kids[0]),(0,'einnahme','bank',uids[1],None,200,kids[0]),
                (0,'ausgabe','bar',None,None,50,None),(1,'einnahme','bar',None,None,80,None),
                (0,'umbuchung','bank',None,'p11-bekannt',70,kids[0]),(1,'umbuchung','bank',None,'p11-bekannt',70,kids[1]),
                (0,'umbuchung','bank',None,'p11-offen',90,None),(1,'umbuchung','bank',None,'p11-offen',90,None),
                (0,'ausgabe','karte',None,None,40,None)]
        for ix,typ,art,uid,gruppe,cent,kid in rows:
            bid = con.execute("INSERT INTO buchung(sparte_id,datum,typ,zahlungsart,bankumsatz_id,transfer_gruppe_id,bankkonto_id) VALUES(?,'2026-01-02',?,?,?,?,?)",(sids[ix],typ,art,uid,gruppe,kid)).lastrowid
            con.execute('INSERT INTO buchungszeile(buchung_id,kategorie_id,betrag_cent) VALUES(?,?,?)',(bid,cats[ix],cent))
        con.execute("UPDATE bankumsatz SET importstatus='verbucht' WHERE id IN (?,?)",uids[:2])
        con.commit()
        tables = ('buchung','buchungszeile','bankumsatz','bankkonto','sparte','kategorie')
        columns = {t:','.join(r[1] for r in con.execute(f'PRAGMA table_info({t})')) for t in tables}
        before = {t:[tuple(r) for r in con.execute(f'SELECT {columns[t]} FROM {t} ORDER BY id')] for t in tables}
        sums_sql = "SELECT sparte_id,substr(datum,1,4),typ,sum(betrag_cent) FROM buchung GROUP BY sparte_id,substr(datum,1,4),typ ORDER BY 1,2,3"
        sums = [tuple(r) for r in con.execute(sums_sql)]
        def backup():
            target = path.with_name('p11-bestand-vorher.db')
            with sqlite3.connect(target) as dest:
                con.backup(dest)
            return target
        print('Ausgangsdatenbank: aktuelles P10-schema.sql (Fixture) + db/seed.sql, synthetische Ergänzungen',flush=True)
        print('Datenbank:',path,flush=True)
        print('Vorher:',{t:len(rows) for t,rows in before.items()},flush=True)
        first = migrate.anwenden(con,backup,sicherung_pflicht=True)
        print('Erster Runner-Lauf:',first,flush=True)
        assert first == [4]
        for t,rows in before.items():
            after = [tuple(r) for r in con.execute(f'SELECT {columns[t]} FROM {t} ORDER BY id')]
            assert after[:len(rows)] == rows, t
        assert sums == [tuple(r) for r in con.execute(sums_sql)]
        assert con.execute('SELECT count(*) FROM bewegung WHERE bankumsatz_id IS NOT NULL').fetchone()[0]==3
        assert con.execute('SELECT count(*) FROM buchung_bewegung').fetchone()[0]==6
        assert con.execute('SELECT count(*) FROM transfer').fetchone()[0]==2
        assert not con.execute('PRAGMA foreign_key_check').fetchall()
        dump = '\n'.join(con.iterdump())
        second = migrate.anwenden(con,backup,sicherung_pflicht=True)
        assert second == [] and dump == '\n'.join(con.iterdump())
        print('Zweiter Runner-Lauf:',second,flush=True)
        print('Vollständiger SQL-Dump nach Lauf 1 und 2 identisch; SHA256:',hashlib.sha256(dump.encode()).hexdigest(),flush=True)
        print('Alle ursprünglichen Zeilen und Spalten unverändert; Summen je Sparte/Jahr/Typ:',sums,flush=True)
        print('Nachzug:',{t:con.execute(f'SELECT count(*) FROM {t}').fetchone()[0] for t in ('bewegung','transfer','buchung_bewegung')},flush=True)
        print('Kontosummen:',[tuple(r) for r in con.execute('SELECT konto_id,sum(betrag_signed_cent) FROM bewegung GROUP BY konto_id ORDER BY konto_id')],flush=True)
        print('Fremdschlüsselprüfung: fehlerfrei; Status:',migrate.status(con),flush=True)
    finally:
        con.close()


if __name__ == '__main__':
    main()
