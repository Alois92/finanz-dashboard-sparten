"""Prüfung nach der Umstellung auf den Neubau (P62) — liest nur, ändert nie.

python -m scripts.umstellung_pruefung --status-url <basis-url>
    --sicherung-vorher <pfad> --db-nachher <pfad>

Der Sitzungs-Cookie für ``GET /api/betrieb/status`` kommt aus der Umgebungs-
variablen ``FINANZ_SESSION_COOKIE``; er steht bewusst nicht auf der Kommando-
zeile, damit er nicht in Shell-Historie oder Prozessliste landet.

Beide Datenbanken werden ausschließlich schreibgeschützt (``mode=ro``) geöffnet
und ihre SHA256-Prüfsumme vor und nach der Prüfung verglichen. Es wird nie eine
laufende Datenbank gelesen: beide Angaben sind abgeschlossene Sicherungskopien
(Quellen mit offenem WAL/Journal werden abgewiesen). Die fachliche Rechnung
stammt unverändert aus ``scripts.migrationsprobe`` (P61).

Exitcodes: 0 alles in Ordnung, 1 Abweichung oder Problem, 2 Lauf fehlgeschlagen.
"""
from __future__ import annotations

import argparse
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import urllib.error
import urllib.request

from scripts import migrationsprobe
from scripts.migrationsprobe import summen_je_sparte_jahr, summen_neu, vergleiche

COOKIE_NAME = '__Host-finanz_session'
STATUS_PFAD = '/api/betrieb/status'
UMGEBUNG_COOKIE = 'FINANZ_SESSION_COOKIE'
ZEITSPERRE = 30


def _sha256(pfad: Path) -> str:
    with pfad.open('rb') as datei:
        return hashlib.file_digest(datei, 'sha256').hexdigest()


def _pruefe_quelle(pfad) -> Path:
    """Nur abgeschlossene, lokale Kopien; niemals die Betriebsdatenbank."""
    quelle = Path(pfad).resolve()
    finanz_db = os.environ.get('FINANZ_DB', '').strip()
    if finanz_db and Path(finanz_db).resolve() == quelle:
        raise ValueError(f'FINANZ_DB darf keine Prüfquelle sein: {quelle}')
    if quelle == Path('/var/lib/finanz/finanz.db').resolve() or str(quelle).startswith('\\\\'):
        raise ValueError('Nur eine lokale Sicherungskopie verwenden, keine Betriebsdatenbank')
    if not quelle.is_file():
        raise FileNotFoundError(f'Quelle fehlt oder ist keine Datei: {quelle}')
    for suffix in ('-wal', '-journal'):
        sidecar = Path(str(quelle) + suffix)
        if sidecar.exists() and sidecar.stat().st_size:
            raise ValueError('Quelle hat WAL/Journal-Daten; abgeschlossene Sicherungskopie verwenden')
    return quelle


def _lesend(quelle: Path):
    """Schreibgeschützte Verbindung; SQLite lehnt jede Änderung selbst ab."""
    return closing(sqlite3.connect(f'{quelle.as_uri()}?mode=ro', uri=True))


def _hole_status(url: str, session_cookie: str):
    anfrage = urllib.request.Request(url, headers={'Accept': 'application/json'})
    if session_cookie:
        anfrage.add_header('Cookie', f'{COOKIE_NAME}={session_cookie}')
    try:
        with urllib.request.urlopen(anfrage, timeout=ZEITSPERRE) as antwort:
            return antwort.status, json.loads(antwort.read().decode('utf-8'))
    except urllib.error.HTTPError as fehler:
        return fehler.code, None


def pruefe_status(basis_url: str, session_cookie: str, oeffner=None) -> dict:
    """Ruft GET /api/betrieb/status angemeldet ab und bewertet ihn.

    ``oeffner`` ist ein Testeinstieg: eine Funktion (url, cookie) -> (status, daten).
    """
    if not basis_url.startswith(('http://', 'https://')):
        raise ValueError(f'Basis-URL muss mit http:// oder https:// beginnen: {basis_url}')
    url = basis_url.rstrip('/') + STATUS_PFAD
    ergebnis = {'url': url, 'erreichbar': False, 'http_status': None, 'schema': None,
                'sicherung': None, 'schreibgeschuetzt': None, 'probleme': [], 'ok': False}
    if not session_cookie:
        ergebnis['probleme'].append(
            f'Kein Sitzungs-Cookie ({UMGEBUNG_COOKIE}); der Status verlangt eine Anmeldung.')
    try:
        http_status, daten = (oeffner or _hole_status)(url, session_cookie)
    except (OSError, ValueError, json.JSONDecodeError) as fehler:
        ergebnis['probleme'].append(f'Status nicht abrufbar: {fehler}')
        return ergebnis
    ergebnis['http_status'] = http_status
    if http_status != 200 or not isinstance(daten, dict):
        ergebnis['probleme'].append(
            'Anmeldung erforderlich (HTTP 401).' if http_status == 401
            else f'Unerwartete Antwort: HTTP {http_status}')
        return ergebnis
    ergebnis['erreichbar'] = True
    schema = daten.get('schema') or {}
    sicherung = daten.get('sicherung') or {}
    ergebnis.update(schema=schema, sicherung=sicherung,
                    schreibgeschuetzt=daten.get('schreibgeschuetzt'))
    if daten.get('schreibgeschuetzt'):
        ergebnis['probleme'].append('Anwendung läuft schreibgeschützt: der Nachzug ist fehlgeschlagen.')
    if schema.get('anstehend'):
        ergebnis['probleme'].append(f'Schema nicht aktuell, anstehend: {schema["anstehend"]}')
    if not schema.get('aktuell'):
        ergebnis['probleme'].append('Schema-Version unbekannt oder 0.')
    if not sicherung.get('letzte'):
        ergebnis['probleme'].append('Keine Sicherung vorhanden.')
    elif not sicherung.get('db_ok'):
        ergebnis['probleme'].append(f'Sicherung {sicherung["letzte"]}: Datenbankkopie nicht in Ordnung.')
    if sicherung.get('belege_fehlend'):
        ergebnis['probleme'].append(f'{sicherung["belege_fehlend"]} Beleg(e) fehlen in der Sicherung.')
    ergebnis['ok'] = not ergebnis['probleme']
    return ergebnis


def pruefe_zahlenvergleich(sicherung_vorher: Path, db_nachher: Path) -> dict:
    """Summen je Sparte und Jahr: alte Rechenweise vorher gegen E/A-View nachher."""
    vorher_pfad = _pruefe_quelle(sicherung_vorher)
    nachher_pfad = _pruefe_quelle(db_nachher)
    if vorher_pfad == nachher_pfad:
        raise ValueError('Sicherung vorher und Stand nachher müssen verschiedene Dateien sein')
    hash_vorher = {pfad: _sha256(pfad) for pfad in (vorher_pfad, nachher_pfad)}
    with _lesend(vorher_pfad) as con:
        alt = summen_je_sparte_jahr(con)
        anzahl_alt = migrationsprobe._anzahl(con)
    with _lesend(nachher_pfad) as con:
        try:
            neu = summen_neu(con)
        except sqlite3.OperationalError as fehler:
            raise RuntimeError(
                f'Stand nachher ist nicht nachgezogen (v_einnahmen_ausgaben fehlt): {fehler}') from fehler
        anzahl_neu = migrationsprobe._anzahl(con)
    dateien = [{'rolle': rolle, 'pfad': str(pfad), 'sha256_vorher': hash_vorher[pfad],
                'sha256_nachher': _sha256(pfad)}
               for rolle, pfad in (('sicherung_vorher', vorher_pfad), ('db_nachher', nachher_pfad))]
    for datei in dateien:
        datei['unveraendert'] = datei['sha256_vorher'] == datei['sha256_nachher']
    ergebnis = vergleiche(alt, neu)
    unveraendert = all(datei['unveraendert'] for datei in dateien)
    return {'gleich': ergebnis['gleich'], 'abweichungen': ergebnis['abweichungen'],
            'summen_vorher': alt, 'summen_nachher': neu,
            'anzahl_vorher': anzahl_alt, 'anzahl_nachher': anzahl_neu,
            'dateien': dateien, 'unveraendert': unveraendert,
            'ok': ergebnis['gleich'] and unveraendert}


def zusammenfassung(status: dict, zahlenvergleich: dict) -> str:
    """Klartext für den Nutzer. Sagt nie „ok", solange ein Problem offen ist."""
    status_ok = bool(status and status.get('ok'))
    zahlen_ok = bool(zahlenvergleich and zahlenvergleich.get('ok'))
    zeilen = ['Umstellung ok: Betriebsstatus und Zahlenvergleich ohne Befund.' if status_ok and zahlen_ok
              else 'Umstellung NICHT in Ordnung — die folgenden Punkte sind offen:']
    if status is None:
        zeilen.append('Betriebsstatus: nicht geprüft (keine --status-url angegeben).')
    elif status_ok:
        zeilen.append(f'Betriebsstatus: Schema {status["schema"].get("aktuell")}, '
                      f'nichts anstehend, nicht schreibgeschützt, '
                      f'letzte Sicherung {status["sicherung"].get("letzte")}.')
    else:
        zeilen.append(f'Betriebsstatus ({status["url"]}):')
        zeilen.extend(f'  - {problem}' for problem in status['probleme'])
    if zahlenvergleich is None:
        zeilen.append('Zahlenvergleich: nicht geprüft.')
    elif zahlen_ok:
        zeilen.append(f'Zahlenvergleich: keine Abweichung je Sparte und Jahr; '
                      f'{zahlenvergleich["anzahl_vorher"]} vorher, '
                      f'{zahlenvergleich["anzahl_nachher"]} nachher; beide Dateien unverändert.')
    else:
        if zahlenvergleich['abweichungen']:
            zeilen.append(f'Zahlenvergleich: {len(zahlenvergleich["abweichungen"])} Abweichung(en):')
            zeilen.extend(
                f'  - Sparte {a["sparte_id"]}, Jahr {a["jahr"]}, {a["feld"]}: '
                f'vorher {a["alt_cent"]} Cent, nachher {a["neu_cent"]} Cent, '
                f'Differenz {a["differenz_cent"]:+d} Cent' for a in zahlenvergleich['abweichungen'])
        else:
            zeilen.append('Zahlenvergleich: keine Abweichung in den Summen.')
        zeilen.extend(f'  - Datei {datei["rolle"]} hat sich während der Prüfung verändert: {datei["pfad"]}'
                      for datei in zahlenvergleich['dateien'] if not datei['unveraendert'])
    if not (status_ok and zahlen_ok):
        zeilen.append('Weiter mit dem Abschnitt „Rückweg" in docs/BETRIEB-UND-ARCHITEKTUR.md.')
    return '\n'.join(zeilen)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--status-url', help=f'Basis-URL der Instanz; Cookie aus {UMGEBUNG_COOKIE}')
    parser.add_argument('--sicherung-vorher', type=Path, required=True)
    parser.add_argument('--db-nachher', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        status = (pruefe_status(args.status_url, os.environ.get(UMGEBUNG_COOKIE, ''))
                  if args.status_url else None)
        zahlen = pruefe_zahlenvergleich(args.sicherung_vorher, args.db_nachher)
    except (OSError, ValueError, RuntimeError, sqlite3.Error) as fehler:
        parser.exit(2, f'Umstellungsprüfung fehlgeschlagen: {fehler}\n')
    print(zusammenfassung(status, zahlen))
    return 0 if status is not None and status['ok'] and zahlen['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
