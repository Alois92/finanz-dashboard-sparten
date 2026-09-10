"""Abgleich bestehender Bankbuchungen ohne zusätzliche Geldbewegung."""
from datetime import date, timedelta

from fastapi import HTTPException

from .bereiche import pruefe_buchung, pruefe_konto, pruefe_umsatz
from .bewegungen import pruefe_bewegungsreferenzen


def _umsatz(con, umsatz_id, bereich):
    pruefe_umsatz(con, umsatz_id, bereich)
    return con.execute('SELECT * FROM bankumsatz WHERE id=?', (umsatz_id,)).fetchone()


def kandidaten(con, umsatz_id, bereich):
    u = _umsatz(con, umsatz_id, bereich)
    if u['importstatus'] != 'offen':
        return []
    tag = date.fromisoformat(u['datum'])
    rows = con.execute("""SELECT b.id AS buchung_id,b.datum,
        CASE b.typ WHEN 'ausgabe' THEN -b.betrag_cent ELSE b.betrag_cent END AS betrag_cent,b.text
        FROM buchung b JOIN sparte s ON s.id=b.sparte_id
        WHERE s.bereich_id=? AND b.bankkonto_id=? AND b.bankumsatz_id IS NULL
        AND b.typ IN ('einnahme','ausgabe') AND b.zahlungsart IN ('bank','karte')
        AND b.transfer_gruppe_id IS NULL AND b.datum BETWEEN ? AND ?
        AND CASE b.typ WHEN 'ausgabe' THEN -b.betrag_cent ELSE b.betrag_cent END=?
        AND EXISTS (SELECT 1 FROM buchung_bewegung x JOIN bewegung m ON m.id=x.bewegung_id
            WHERE x.buchung_id=b.id AND m.quelle='manuell' AND m.storniert_am IS NULL
            AND m.bankumsatz_id IS NULL AND m.transfer_id IS NULL
            AND m.konto_id=b.bankkonto_id AND m.betrag_signed_cent=?)""",
        (bereich.id, u['bankkonto_id'], (tag-timedelta(days=5)).isoformat(),
         (tag+timedelta(days=5)).isoformat(), u['betrag_cent'], u['betrag_cent']))
    result = [{**dict(r), 'abstand_tage': abs((date.fromisoformat(r['datum'])-tag).days)} for r in rows]
    return sorted(result, key=lambda r: (r['abstand_tage'], r['datum'], r['buchung_id']))


def _bewegungen(con, b, u, bereich, *, ruecknahme=False):
    pruefe_bewegungsreferenzen(con, b['id'], bereich)
    if b['bankkonto_id'] != u['bankkonto_id']:
        raise HTTPException(409, 'Buchung und Umsatz gehören nicht zum selben Konto')
    if b['typ'] not in ('einnahme', 'ausgabe') or b['zahlungsart'] not in ('bank', 'karte') or b['transfer_gruppe_id']:
        raise HTTPException(409, 'Nur manuelle Bank- oder Kartenbuchungen können abgeglichen werden')
    cent = -b['betrag_cent'] if b['typ'] == 'ausgabe' else b['betrag_cent']
    if not ruecknahme and cent != u['betrag_cent']:
        raise HTTPException(409, 'Betrag der Buchung stimmt nicht mit dem Umsatz überein')
    rows = con.execute("""SELECT m.* FROM bewegung m JOIN buchung_bewegung x ON x.bewegung_id=m.id
        WHERE x.buchung_id=?""", (b['id'],)).fetchall()
    manuell = [m for m in rows if m['quelle'] == 'manuell' and m['bankumsatz_id'] is None
               and m['transfer_id'] is None and m['konto_id'] == u['bankkonto_id']]
    if len(manuell) != 1:
        raise HTTPException(409, 'Keine eindeutige manuelle Bewegung für den Abgleich vorhanden')
    m = manuell[0]
    if m['betrag_signed_cent'] != u['betrag_cent'] or any(r['id'] != m['id'] and r['storniert_am'] is None
                                            and r['bankumsatz_id'] != u['id'] for r in rows):
        raise HTTPException(409, 'Bewegungen der Buchung passen nicht zum Abgleich')
    imp = con.execute('SELECT * FROM bewegung WHERE bankumsatz_id=?', (u['id'],)).fetchone()
    if (imp is None or imp['quelle'] != 'import' or imp['storniert_am'] is not None
            or imp['transfer_id'] is not None or imp['konto_id'] != u['bankkonto_id']
            or imp['betrag_signed_cent'] != u['betrag_cent']):
        raise HTTPException(409, 'Keine passende aktive Importbewegung vorhanden')
    for mid in (m['id'], imp['id']):
        if con.execute('SELECT 1 FROM buchung_bewegung WHERE bewegung_id=? AND buchung_id<>?',
                       (mid, b['id'])).fetchone():
            raise HTTPException(409, 'Bewegung ist bereits einer anderen Buchung zugeordnet')
    return m, imp


def zuordnen(con, umsatz_id, buchung_id, bereich):
    with con:
        con.execute('BEGIN IMMEDIATE')
        u = _umsatz(con, umsatz_id, bereich)
        pruefe_buchung(con, buchung_id, bereich)
        b = con.execute('SELECT * FROM buchung WHERE id=?', (buchung_id,)).fetchone()
        if b['bankumsatz_id'] not in (None, umsatz_id):
            raise HTTPException(409, 'Buchung ist bereits einem anderen Umsatz zugeordnet')
        if con.execute('SELECT 1 FROM buchung WHERE bankumsatz_id=? AND id<>?', (umsatz_id, buchung_id)).fetchone():
            raise HTTPException(409, 'Umsatz ist bereits einer anderen Buchung zugeordnet')
        m, imp = _bewegungen(con, b, u, bereich)
        if b['bankumsatz_id'] == umsatz_id:
            if u['importstatus'] != 'verbucht' or m['storniert_am'] is None:
                raise HTTPException(409, 'Bestehende Zuordnung ist inkonsistent')
        else:
            if u['importstatus'] != 'offen' or m['storniert_am'] is not None:
                raise HTTPException(409, 'Umsatz oder manuelle Bewegung ist nicht offen')
            con.execute('UPDATE buchung SET bankumsatz_id=?,version=version+1 WHERE id=?', (umsatz_id, buchung_id))
            con.execute("UPDATE bankumsatz SET importstatus='verbucht' WHERE id=?", (umsatz_id,))
            con.execute("UPDATE bewegung SET storniert_am=datetime('now') WHERE id=?", (m['id'],))
            con.execute('INSERT INTO buchung_bewegung VALUES(?,?,?)', (buchung_id, imp['id'], u['betrag_cent']))
        return {'bankumsatz_id': umsatz_id, 'buchung_id': buchung_id, 'importstatus': 'verbucht'}


def loesen(con, umsatz_id, bereich):
    with con:
        con.execute('BEGIN IMMEDIATE')
        u = _umsatz(con, umsatz_id, bereich)
        rows = con.execute('SELECT * FROM buchung WHERE bankumsatz_id=?', (umsatz_id,)).fetchall()
        for b in rows:
            pruefe_buchung(con, b['id'], bereich)
        if not rows and u['importstatus'] == 'offen':
            return {'bankumsatz_id': umsatz_id, 'buchung_id': None, 'importstatus': 'offen'}
        if len(rows) != 1 or u['importstatus'] != 'verbucht':
            raise HTTPException(409, 'Keine eindeutige Abgleich-Zuordnung vorhanden')
        b = rows[0]
        m, imp = _bewegungen(con, b, u, bereich, ruecknahme=True)
        if m['storniert_am'] is None:
            raise HTTPException(409, 'Manuelle Bewegung ist nicht durch einen Abgleich storniert')
        con.execute('DELETE FROM buchung_bewegung WHERE buchung_id=? AND bewegung_id=?', (b['id'], imp['id']))
        cent = -b['betrag_cent'] if b['typ'] == 'ausgabe' else b['betrag_cent']
        con.execute('UPDATE bewegung SET storniert_am=NULL,datum=?,text=?,betrag_signed_cent=? WHERE id=?',
                    (b['datum'], b['text'], cent, m['id']))
        con.execute('UPDATE buchung_bewegung SET anteil_signed_cent=? WHERE buchung_id=? AND bewegung_id=?',
                    (cent, b['id'], m['id']))
        con.execute('UPDATE buchung SET bankumsatz_id=NULL,version=version+1 WHERE id=?', (b['id'],))
        con.execute("UPDATE bankumsatz SET importstatus='offen' WHERE id=?", (umsatz_id,))
        return {'bankumsatz_id': umsatz_id, 'buchung_id': None, 'importstatus': 'offen'}


def offene_abgleiche(con, konto_id, bereich):
    pruefe_konto(con, konto_id, bereich)
    manuell = [dict(r) for r in con.execute("""SELECT m.id AS bewegung_id,m.datum,
        m.betrag_signed_cent AS betrag_cent,m.text FROM bewegung m
        WHERE m.konto_id=? AND m.quelle='manuell' AND m.bankumsatz_id IS NULL
        AND m.storniert_am IS NULL AND m.transfer_id IS NULL
        AND NOT EXISTS (SELECT 1 FROM buchung_bewegung x JOIN buchung b ON b.id=x.buchung_id
            JOIN sparte s ON s.id=b.sparte_id WHERE x.bewegung_id=m.id
            AND (b.bankumsatz_id IS NOT NULL OR s.bereich_id<>?))
        ORDER BY m.datum,m.id""", (konto_id, bereich.id))]
    umsaetze = []
    for r in con.execute("""SELECT id AS bankumsatz_id,datum,betrag_cent,text FROM bankumsatz
        WHERE bankkonto_id=? AND importstatus='offen' ORDER BY datum,id""", (konto_id,)).fetchall():
        treffer = kandidaten(con, r['bankumsatz_id'], bereich)
        if treffer:
            umsaetze.append({**dict(r), 'kandidaten_anzahl': len(treffer)})
    return {'konto_id': konto_id, 'manuelle_anzahl': len(manuell), 'manuelle_bewegungen': manuell,
            'umsaetze_anzahl': len(umsaetze), 'offene_umsaetze': umsaetze}
