"""Schema-Nachzug auf einer separaten, ruhenden SQLite-Dateikopie prüfen.

python -m scripts.migrationsprobe <kopie.db> [--arbeitsordner <neuer-ordner>]
Keine App-Konfiguration wird geladen. Die Quelle wird nie mit SQLite geöffnet.
Für WAL-Datenbanken zuerst eine konsistente, abgeschlossene Sicherung erstellen.
Exitcodes: 0 Prüfungen bestanden (Hinweise möglich), 1 Abweichung, 2 Lauf fehlgeschlagen.
"""
from __future__ import annotations

import argparse
from contextlib import closing
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import shutil
import sqlite3
import tempfile

from app import migrate

FELDER = ('einnahmen_cent', 'ausgaben_cent')


def _spalten(con, tabelle):
    return {r[1] for r in con.execute(f'PRAGMA table_info({tabelle})')}


def _summen(con, sql):
    ergebnis = {}
    for sid, jahr, einnahmen, ausgaben in con.execute(sql):
        ergebnis.setdefault(sid, {})[int(jahr)] = dict(zip(FELDER, (einnahmen, ausgaben)))
    return ergebnis


def summen_je_sparte_jahr(con) -> dict:
    """Alte Kostenrechnung: Zeilen, keine Zahlungs-/Neutral-/Stornofilter."""
    return _summen(con, """
        SELECT b.sparte_id, substr(b.datum,1,4),
               SUM(CASE WHEN b.typ='einnahme' THEN z.betrag_cent ELSE 0 END),
               SUM(CASE WHEN b.typ='ausgabe' THEN z.betrag_cent ELSE 0 END)
        FROM buchung b JOIN buchungszeile z ON z.buchung_id=b.id
        WHERE b.typ <> 'umbuchung'
        GROUP BY b.sparte_id, substr(b.datum,1,4) ORDER BY 1,2
    """)


def summen_neu(con) -> dict:
    """E/A-View, gegebenenfalls ergänzt um explizite Kostenstorno-Spalten.

    Version 14 kennt Stornos nur an Bewegung/Transfer. Diese betreffen die
    Zahlung, nicht die Kosten, und dürfen hier keine Kosten verschwinden lassen.
    """
    filter_sql = ['v.neutral=0', "v.typ <> 'umbuchung'"]
    for tabelle, alias in (('buchung', 'b'), ('buchungszeile', 'z')):
        if 'storniert_am' in _spalten(con, tabelle):
            filter_sql.append(f'{alias}.storniert_am IS NULL')
    return _summen(con, f"""
        SELECT v.sparte_id, substr(v.datum,1,4),
               SUM(CASE WHEN v.typ='einnahme' THEN v.betrag_cent ELSE 0 END),
               SUM(CASE WHEN v.typ='ausgabe' THEN v.betrag_cent ELSE 0 END)
        FROM v_einnahmen_ausgaben v
        JOIN buchung b ON b.id=v.buchung_id
        JOIN buchungszeile z ON z.id=v.zeile_id
        WHERE {' AND '.join(filter_sql)}
        GROUP BY v.sparte_id, substr(v.datum,1,4) ORDER BY 1,2
    """)


def vergleiche(alt: dict, neu: dict) -> dict:
    """Jede Cent-Abweichung über die Vereinigung beider Schlüsselmengen."""
    abweichungen = []
    for sid in sorted(alt.keys() | neu.keys()):
        a, n = alt.get(sid, {}), neu.get(sid, {})
        for jahr in sorted(a.keys() | n.keys()):
            for feld in FELDER:
                vorher = a.get(jahr, {}).get(feld, 0)
                nachher = n.get(jahr, {}).get(feld, 0)
                if vorher != nachher:
                    abweichungen.append(dict(sparte_id=sid, jahr=jahr, feld=feld,
                                             alt_cent=vorher, neu_cent=nachher,
                                             differenz_cent=nachher-vorher))
    return {'gleich': not abweichungen, 'abweichungen': abweichungen}


def _bereiche(con):
    bereich = 's.bereich_id' if 'bereich_id' in _spalten(con, 'sparte') else 'NULL'
    return {(sid, int(jahr) if jahr is not None else None): (bid, soll)
            for sid, jahr, bid, soll in con.execute(f"""
                SELECT DISTINCT s.id, substr(b.datum,1,4), {bereich},
                    CASE WHEN upper(s.kuerzel)='ZINA' OR upper(s.name)='ZINA' THEN 2 ELSE 1 END
                FROM sparte s LEFT JOIN buchung b ON b.sparte_id=s.id
                ORDER BY s.id, 2
            """)}


def _bereiche_vergleichen(alt, neu):
    zeilen = []
    for sid, jahr in sorted(alt.keys() | neu.keys(), key=lambda k: (k[0], k[1] or 0)):
        vorher, soll_alt = alt.get((sid, jahr), (None, None))
        nachher, soll = neu.get((sid, jahr), (None, soll_alt))
        # Fehlende Bereichsspalte in Version 0 wird erstmals korrekt zugeordnet.
        korrekt = ((sid, jahr) in alt and (sid, jahr) in neu and nachher == soll
                   and (vorher is None or vorher == nachher))
        zeilen.append(dict(sparte_id=sid, jahr=jahr, vorher=vorher, nachher=nachher,
                           erwartet=soll, korrekt=korrekt))
    return {'korrekt': all(z['korrekt'] for z in zeilen), 'je_sparte_jahr': zeilen}


def _anzahl(con):
    return {t: con.execute(f'SELECT count(*) FROM {t}').fetchone()[0]
            for t in ('buchung', 'buchungszeile')}


def _sha256(path):
    with path.open('rb') as datei:
        return hashlib.file_digest(datei, 'sha256').hexdigest()


class _Migrationslog(logging.Handler):
    def __init__(self):
        super().__init__(logging.INFO)
        self.meldungen = []

    def emit(self, record):
        self.meldungen.append(record.getMessage())


def _ungeklaerte_faelle(con, protokoll, meldungen):
    gruppen = {r['objektkennung'] for r in protokoll if r['art']=='umbuchung_ungeklaert'}
    for (notiz,) in con.execute("SELECT notiz FROM transfer WHERE notiz IS NOT NULL"):
        marker = 'Nachzug Umbuchung '
        if notiz.startswith(marker) and notiz.endswith(('; Konten ungeklärt', '; Konten ungeklaert')):
            gruppen.add('umbuchungsgruppe:' + notiz[len(marker):].rsplit('; ',1)[0])
    zahlungen = {f'buchung:{r[0]}' for r in con.execute("""
        SELECT id FROM buchung WHERE zahlungsart IN ('bank','karte')
        AND bankumsatz_id IS NULL AND typ IN ('einnahme','ausgabe')
    """)}
    zahlungen.update(r['objektkennung'] for r in protokoll if r['art']=='zahlung_ungeklaert')
    log_zahlen = {'transfers': None, 'zahlungen': None, 'barbuchungen': None}
    for meldung in meldungen:
        for key, muster in (
            ('transfers', r'ungeklärte Transfers=(\d+)'),
            ('zahlungen', r'Zahlung unbekannt: Anzahl=(\d+)'),
            ('barbuchungen', r'ungeklärte Barbuchungen=(\d+)'),
        ):
            treffer = re.search(muster, meldung)
            if treffer:
                log_zahlen[key] = int(treffer[1])
    return {'transfer_objekte': sorted(gruppen), 'zahlungs_objekte': sorted(zahlungen),
            'log': log_zahlen,
            'transfers': max(len(gruppen), log_zahlen['transfers'] or 0),
            'zahlungen': max(len(zahlungen), log_zahlen['zahlungen'] or 0)}


def lauf(quelle_db: Path, arbeitsordner: Path) -> dict:
    """Prüft eine explizite Offline-Kopie. Keine vorhandenen Artefakte ersetzen."""
    quelle = Path(quelle_db).resolve()
    ordner = Path(arbeitsordner).resolve()
    finanz_db = os.environ.get('FINANZ_DB', '').strip()
    pfade = (quelle, *(ordner / name for name in ('kopie.db', 'sicherung.db', 'bericht.json')))
    if finanz_db and Path(finanz_db).resolve() in pfade:
        raise ValueError('FINANZ_DB darf weder Quelle noch Schreibziel der Migrationsprobe sein')
    if quelle == Path('/var/lib/finanz/finanz.db').resolve() or str(quelle).startswith('\\\\'):
        raise ValueError('Nur eine lokale Offline-Kopie verwenden, keine Betriebsdatenbank')
    if not quelle.is_file():
        raise FileNotFoundError(f'Quelle fehlt oder ist keine Datei: {quelle}')
    if quelle.parent == ordner:
        raise ValueError('Arbeitsordner muss von der Quelle getrennt sein')
    for suffix in ('-wal', '-journal'):
        sidecar = Path(str(quelle) + suffix)
        if sidecar.exists() and sidecar.stat().st_size:
            raise ValueError('Quelle hat WAL/Journal-Daten; abgeschlossene Offline-Sicherung verwenden')
    # Auch leere/defekte Symlinks und SQLite-Sidecars dürfen nicht überschrieben werden.
    for name in ('kopie.db', 'sicherung.db', 'bericht.json',
                 'kopie.db-wal', 'kopie.db-shm', 'kopie.db-journal',
                 'sicherung.db-wal', 'sicherung.db-shm', 'sicherung.db-journal'):
        if os.path.lexists(ordner / name):
            raise FileExistsError(f'Artefakt existiert bereits: {ordner / name}')
    vorher_hash = _sha256(quelle)  # Prüft zugleich die Lesbarkeit.
    ordner.mkdir(parents=True, exist_ok=True)
    kopie = ordner / 'kopie.db'
    # Exklusiv reservieren; copy2 selbst folgt der Vorgabe der Paketkarte.
    with kopie.open('xb'):
        pass
    shutil.copy2(quelle, kopie)
    if _sha256(kopie) != vorher_hash:
        raise RuntimeError('Quelle hat sich während des Kopierens verändert')
    with closing(sqlite3.connect(kopie)) as con:
        con.execute('PRAGMA foreign_keys=ON')
        vorher = summen_je_sparte_jahr(con)
        bereiche_alt, anzahl_alt = _bereiche(con), _anzahl(con)
        status_alt = migrate.status(con)

        def sicherung():
            ziel = ordner / 'sicherung.db'
            with ziel.open('xb'):
                pass
            with closing(sqlite3.connect(ziel)) as dest:
                con.backup(dest)
                if dest.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
                    raise RuntimeError('Integritätsprüfung der Sicherung fehlgeschlagen')
            return ziel

        logger = logging.getLogger('finanz.migrate')
        handler, level = _Migrationslog(), logger.level
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        try:
            angewendet = migrate.anwenden(con, sicherung, sicherung_pflicht=True)
            zweiter_lauf = migrate.anwenden(con, sicherung, sicherung_pflicht=True)
        finally:
            logger.removeHandler(handler)
            logger.setLevel(level)
            handler.close()
        nachher = summen_neu(con)
        cursor = con.execute('SELECT * FROM migrationsprotokoll ORDER BY id')
        protokoll = [dict(zip([c[0] for c in cursor.description], row)) for row in cursor]
        faelle = _ungeklaerte_faelle(con, protokoll, handler.meldungen)
        bericht = dict(
            summen_vorher=vorher, summen_nachher=nachher,
            vergleich=vergleiche(vorher, nachher), migrationslog=handler.meldungen,
            migrationsprotokoll=protokoll, ungeklaerte_transfers=faelle['transfers'],
            zahlung_unbekannt=faelle['zahlungen'], ungeklaerte_faelle=faelle,
            bereiche=_bereiche_vergleichen(bereiche_alt, _bereiche(con)),
            anzahl_vorher=anzahl_alt, anzahl_nachher=_anzahl(con),
            foreign_key_check=[list(r) for r in con.execute('PRAGMA foreign_key_check')],
            integrity_check=[r[0] for r in con.execute('PRAGMA integrity_check')],
            angewendet=angewendet, zweiter_anwenden_lauf=zweiter_lauf,
            status_vorher=status_alt, status_nachher=migrate.status(con),
            kostenstorno_spalten={t: 'storniert_am' in _spalten(con, t)
                                  for t in ('buchung', 'buchungszeile')},
        )
    bericht['quelle_sha256_vorher'] = vorher_hash
    bericht['quelle_sha256_nachher'] = _sha256(quelle)
    bericht['erfolgreich'] = (
        bericht['vergleich']['gleich'] and bericht['bereiche']['korrekt']
        and bericht['anzahl_vorher'] == bericht['anzahl_nachher']
        and not bericht['foreign_key_check'] and bericht['integrity_check'] == ['ok']
        and not zweiter_lauf and not bericht['status_nachher']['anstehend']
        and vorher_hash == bericht['quelle_sha256_nachher']
    )
    # JSON-kompatible Rückgabe: Status-Tupel werden wie im gespeicherten Bericht Listen.
    bericht['status_vorher']['anstehend'] = [list(r) for r in status_alt['anstehend']]
    with (ordner / 'bericht.json').open('x', encoding='utf-8') as datei:
        json.dump(bericht, datei, ensure_ascii=False, indent=2)
        datei.write('\n')
    return bericht


def _zusammenfassung(bericht):
    print('Migrationsprobe:', 'Prüfungen bestanden' if bericht['erfolgreich'] else 'ABWEICHUNGEN')
    alt, neu = bericht['summen_vorher'], bericht['summen_nachher']
    for sid in sorted(alt.keys() | neu.keys()):
        for jahr in sorted(alt.get(sid, {}).keys() | neu.get(sid, {}).keys()):
            a, n = alt.get(sid, {}).get(jahr, {}), neu.get(sid, {}).get(jahr, {})
            print(f'Sparte {sid}, Jahr {jahr}: ' + '; '.join(
                f'{f} alt={a.get(f, 0)} neu={n.get(f, 0)}' for f in FELDER))
    print('Abweichungen:', json.dumps(bericht['vergleich']['abweichungen'], ensure_ascii=False))
    print('Bereiche:', json.dumps(bericht['bereiche'], ensure_ascii=False))
    print('Anzahl vorher/nachher:', bericht['anzahl_vorher'], bericht['anzahl_nachher'])
    print('Transfers ungeklärt:', bericht['ungeklaerte_transfers'],
          '; Zahlung unbekannt:', bericht['zahlung_unbekannt'])
    print('Ungeklärte Fälle (Protokoll/Bestand und Log):', bericht['ungeklaerte_faelle'])
    print('Migrationsprotokoll:', json.dumps(bericht['migrationsprotokoll'], ensure_ascii=False))
    print('Migrationslog:')
    for meldung in bericht['migrationslog']:
        print(' ', meldung)
    print('foreign_key_check:', bericht['foreign_key_check'],
          '; integrity_check:', bericht['integrity_check'])
    print('Angewendet:', bericht['angewendet'], '; zweiter Lauf:', bericht['zweiter_anwenden_lauf'])
    print('Quelle SHA256 vorher/nachher:', bericht['quelle_sha256_vorher'], bericht['quelle_sha256_nachher'])


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('quelle_db', type=Path)
    parser.add_argument('--arbeitsordner', type=Path)
    args = parser.parse_args(argv)
    try:
        if args.arbeitsordner is not None:
            bericht = lauf(args.quelle_db, args.arbeitsordner)
            bericht_pfad = args.arbeitsordner.resolve() / 'bericht.json'
        else:
            with tempfile.TemporaryDirectory(prefix='p61-arbeit-') as temp:
                bericht = lauf(args.quelle_db, Path(temp))
                with tempfile.NamedTemporaryFile(prefix='p61-bericht-', suffix='.json', delete=False) as ziel:
                    bericht_pfad = Path(ziel.name)
                    with (Path(temp) / 'bericht.json').open('rb') as quelle:
                        shutil.copyfileobj(quelle, ziel)
        _zusammenfassung(bericht)
        print('Bericht:', bericht_pfad)
        return 0 if bericht['erfolgreich'] else 1
    except (OSError, ValueError, RuntimeError, sqlite3.Error, migrate.MigrationsFehler) as exc:
        parser.exit(2, f'Migrationsprobe fehlgeschlagen: {exc}\n')


if __name__ == '__main__':
    raise SystemExit(main())
