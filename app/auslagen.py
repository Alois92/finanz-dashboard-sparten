"""Auslagen-Prüfungen und Salden, gemeinsam für Buchungen und Ausgleiche."""
from datetime import date

from fastapi import HTTPException
from fastapi.responses import JSONResponse

from .bereiche import pruefe_buchung, pruefe_konto, pruefe_sparte
from .bewegungen import kassa_fuer_sparte, pruefe_transfer


def pruefe_auslage(con, auslage_id, bereich):
    row = con.execute('SELECT * FROM auslage WHERE id = ?', (auslage_id,)).fetchone()
    if row is None:
        raise HTTPException(404, 'Auslage nicht gefunden')
    pruefe_buchung(con, row['buchung_id'], bereich)
    pruefe_sparte(con, row['zahler_sparte_id'], bereich)
    if row['zahler_konto_id'] is not None:
        pruefe_konto(con, row['zahler_konto_id'], bereich)
    return row


def pruefe_ausgleich(con, ausgleich_id, bereich):
    row = con.execute('SELECT * FROM ausgleich WHERE id = ?', (ausgleich_id,)).fetchone()
    if row is None:
        raise HTTPException(404, 'Ausgleich nicht gefunden')
    pruefe_sparte(con, row['von_sparte_id'], bereich)
    pruefe_sparte(con, row['nach_sparte_id'], bereich)
    pruefe_transfer(con, row['transfer_id'], bereich)
    for z in con.execute(
        'SELECT auslage_id FROM ausgleich_zuordnung WHERE ausgleich_id = ?',
        (ausgleich_id,),
    ):
        pruefe_auslage(con, z['auslage_id'], bereich)
    return row


def offen_cent(con, auslage, stichtag=None):
    sql = (
        'SELECT COALESCE(SUM(z.betrag_cent), 0) FROM ausgleich_zuordnung z '
        'JOIN ausgleich a ON a.id = z.ausgleich_id '
        'WHERE z.auslage_id = ? AND a.aufgehoben_am IS NULL'
    )
    params = [auslage['id']]
    if stichtag is not None:
        sql += ' AND a.datum <= ?'
        params.append(stichtag)
    return auslage['betrag_cent'] - con.execute(sql, params).fetchone()[0]


def ergaenze_auslage(con, buchung):
    row = con.execute(
        'SELECT * FROM auslage WHERE buchung_id = ?', (buchung['id'],)
    ).fetchone()
    buchung['bezahlt_von_sparte_id'] = row['zahler_sparte_id'] if row else None
    if row:
        offen = offen_cent(con, row, date.today().isoformat())
        buchung['auslage'] = {
            'zahler_sparte_id': row['zahler_sparte_id'],
            'offen_cent': offen, 'ausgeglichen': offen == 0,
        }


def pruefe_zahler(con, b, bereich):
    if b.bezahlt_von_sparte_id is None:
        return
    pruefe_sparte(con, b.bezahlt_von_sparte_id, bereich)
    typ = con.execute(
        'SELECT typ FROM sparte WHERE id = ?', (b.bezahlt_von_sparte_id,)
    ).fetchone()[0]
    if b.typ != 'ausgabe' or typ != 'privat' or b.bezahlt_von_sparte_id == b.sparte_id:
        raise HTTPException(422, 'Auslage benötigt eine Ausgabe und eine andere private Zahlersparte')
    konto_id = b.bankkonto_id
    if b.bankumsatz_id is not None:
        konto_id = con.execute(
            'SELECT bankkonto_id FROM bankumsatz WHERE id = ?', (b.bankumsatz_id,)
        ).fetchone()[0]
    if konto_id is not None:
        pruefe_konto(con, konto_id, bereich)
        konto = con.execute('SELECT sparte_id FROM bankkonto WHERE id = ?', (konto_id,)).fetchone()
        if konto['sparte_id'] != b.bezahlt_von_sparte_id:
            raise HTTPException(422, 'Zahlungskonto gehört nicht zur Zahlersparte')


def zuordnungskonflikt(con, buchung_id, bereich, b=None):
    alt = con.execute('SELECT * FROM auslage WHERE buchung_id = ?', (buchung_id,)).fetchone()
    if alt is None:
        return None
    pruefe_auslage(con, alt['id'], bereich)
    rows = con.execute(
        'SELECT a.id, a.aufgehoben_am, a.datum, z.betrag_cent '
        'FROM ausgleich_zuordnung z JOIN ausgleich a ON a.id = z.ausgleich_id '
        'WHERE z.auslage_id = ? ORDER BY a.id', (alt['id'],),
    ).fetchall()
    for row in rows:
        pruefe_ausgleich(con, row['id'], bereich)
    aktiv = [r for r in rows if r['aufgehoben_am'] is None]
    kopf = con.execute('SELECT sparte_id, datum FROM buchung WHERE id = ?', (buchung_id,)).fetchone()
    identitaet_geaendert = b is None or (
        b.bezahlt_von_sparte_id != alt['zahler_sparte_id']
        or b.sparte_id != kopf['sparte_id'] or b.typ != 'ausgabe'
    )
    betroffen = rows if identitaet_geaendert else aktiv if (
        sum(z.betrag_cent for z in b.zeilen) < sum(r['betrag_cent'] for r in aktiv)
        or (b.datum != kopf['datum'] and any(b.datum > r['datum'] for r in aktiv))
    ) else []
    if betroffen:
        return JSONResponse({
            'detail': 'Buchung ist durch Ausgleichszuordnungen gebunden',
            'ausgleiche': [r['id'] for r in betroffen],
        }, status_code=409)
    return None


def synchronisiere_auslage(con, buchung_id, b, bereich):
    if b.bezahlt_von_sparte_id is None:
        con.execute('DELETE FROM auslage WHERE buchung_id = ?', (buchung_id,))
        return
    konto_id = b.bankkonto_id
    if b.zahlungsart == 'bar':
        konto_id = kassa_fuer_sparte(con, b.bezahlt_von_sparte_id, bereich)
    elif b.bankumsatz_id is not None:
        konto_id = con.execute(
            'SELECT bankkonto_id FROM bankumsatz WHERE id = ?', (b.bankumsatz_id,)
        ).fetchone()[0]
    con.execute(
        'INSERT INTO auslage(buchung_id, zahler_sparte_id, zahler_konto_id, betrag_cent) '
        'VALUES(?, ?, ?, ?) ON CONFLICT(buchung_id) DO UPDATE SET '
        'zahler_sparte_id = excluded.zahler_sparte_id, '
        'zahler_konto_id = excluded.zahler_konto_id, betrag_cent = excluded.betrag_cent',
        (buchung_id, b.bezahlt_von_sparte_id, konto_id, sum(z.betrag_cent for z in b.zeilen)),
    )
