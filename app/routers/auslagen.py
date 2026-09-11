"""Offene Auslagen und nachvollziehbare Teilzahlungen im gewählten Bereich."""
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from ..auslagen import offen_cent, pruefe_ausgleich, pruefe_auslage
from ..bereiche import Bereich, BereichDep, pruefe_kategorie, pruefe_konto, pruefe_sparte
from ..bewegungen import erzeuge_transfer, kassa_fuer_sparte, storniere_transfer
from ..db import db_dep
from ..wiederholung import speichere_antwort, wiederhole

router = APIRouter(tags=['auslagen'])


class AusgleichIn(BaseModel):
    von_sparte_id: int
    nach_sparte_id: int
    auslage_ids: list[int] = Field(min_length=1)
    datum: str
    betrag_cent: int = Field(gt=0, le=10_000_000_000, strict=True)
    zahlungsart: Literal['bar', 'bank']
    von_konto_id: int | None = None
    nach_konto_id: int | None = None
    client_request_id: str | None = Field(default=None, min_length=1)
    notiz: str | None = None

    @field_validator('datum')
    @classmethod
    def iso_datum(cls, value):
        datum = date.fromisoformat(value)
        if datum.isoformat() != value:
            raise ValueError('Datum muss YYYY-MM-DD entsprechen')
        if datum > date.today():
            raise ValueError('Datum darf nicht in der Zukunft liegen')
        return value

    @field_validator('auslage_ids')
    @classmethod
    def eindeutige_auslagen(cls, value):
        if len(set(value)) != len(value):
            raise ValueError('Auslagen dürfen nicht doppelt gewählt werden')
        return value


@router.get('/auslagen')
def list_auslagen(stichtag: date | None = None, sparte_id: int | None = None,
                  zahler_sparte_id: int | None = None,
                  con=Depends(db_dep), bereich: BereichDep = Bereich(1)):
    for sid in (sparte_id, zahler_sparte_id):
        if sid is not None:
            pruefe_sparte(con, sid, bereich)
    bis = (stichtag or date.today()).isoformat()
    sql = (
        'SELECT a.*, b.sparte_id, b.datum, b.text FROM auslage a '
        'JOIN buchung b ON b.id = a.buchung_id JOIN sparte s ON s.id = b.sparte_id '
        'WHERE s.bereich_id = ? AND b.datum <= ?'
    )
    params = [bereich.id, bis]
    for feld, wert in (('b.sparte_id', sparte_id), ('a.zahler_sparte_id', zahler_sparte_id)):
        if wert is not None:
            sql += f' AND {feld} = ?'
            params.append(wert)
    gruppen = {}
    for row in con.execute(sql + ' ORDER BY b.datum, a.id', params).fetchall():
        pruefe_auslage(con, row['id'], bereich)
        offen = offen_cent(con, row, bis)
        if offen <= 0:
            continue
        kategorien = []
        for k in con.execute(
            'SELECT DISTINCT k.id, k.name FROM buchungszeile z '
            'JOIN kategorie k ON k.id = z.kategorie_id WHERE z.buchung_id = ? ORDER BY k.id',
            (row['buchung_id'],),
        ):
            pruefe_kategorie(con, k['id'], bereich)
            kategorien.append(k['name'])
        key = (row['zahler_sparte_id'], row['sparte_id'])
        gruppe = gruppen.setdefault(key, {
            'zahler_sparte_id': key[0], 'sparte_id': key[1],
            'offen_cent': 0, 'anzahl': 0, 'auslagen': [],
        })
        gruppe['offen_cent'] += offen
        gruppe['anzahl'] += 1
        gruppe['auslagen'].append({
            'id': row['id'], 'buchung_id': row['buchung_id'], 'datum': row['datum'],
            'text': row['text'], 'kategorie': ', '.join(kategorien),
            'betrag_cent': row['betrag_cent'], 'offen_cent': offen,
        })
    return list(gruppen.values())


def _konten(con, a, bereich):
    konten = []
    for sid, kid in ((a.von_sparte_id, a.von_konto_id),
                     (a.nach_sparte_id, a.nach_konto_id)):
        if kid is None:
            if a.zahlungsart == 'bank':
                raise HTTPException(422, 'Bankausgleich benötigt von_konto_id und nach_konto_id')
            kid = kassa_fuer_sparte(con, sid, bereich)
        pruefe_konto(con, kid, bereich)
        konto = con.execute('SELECT * FROM bankkonto WHERE id = ?', (kid,)).fetchone()
        if konto['sparte_id'] != sid:
            raise HTTPException(422, 'Konto gehört nicht zur angegebenen Sparte')
        art = 'kassa' if a.zahlungsart == 'bar' else 'bank'
        if konto['art'] != art:
            raise HTTPException(422, f'Zahlungsart benötigt Kontoart {art}')
        konten.append(konto)
    if konten[0]['waehrung'] != konten[1]['waehrung']:
        raise HTTPException(422, 'Transfer benötigt dieselbe Währung')
    return konten


@router.post('/ausgleiche', status_code=201)
def create_ausgleich(a: AusgleichIn, con=Depends(db_dep), bereich: BereichDep = Bereich(1)):
    with con:
        con.execute('BEGIN IMMEDIATE')
        antwort = wiederhole(con, 'ausgleich', a, bereich)
        if antwort is not None:
            return antwort
        for sid in (a.von_sparte_id, a.nach_sparte_id):
            pruefe_sparte(con, sid, bereich)
        for kid in (a.von_konto_id, a.nach_konto_id):
            if kid is not None:
                pruefe_konto(con, kid, bereich)
        auslagen = []
        for aid in a.auslage_ids:
            row = dict(pruefe_auslage(con, aid, bereich))
            b = con.execute('SELECT sparte_id, datum FROM buchung WHERE id = ?',
                            (row['buchung_id'],)).fetchone()
            row.update(sparte_id=b['sparte_id'], datum=b['datum'])
            auslagen.append(row)
        for row in auslagen:
            row['offen_cent'] = offen_cent(con, row)
            if (row['sparte_id'] != a.von_sparte_id
                    or row['zahler_sparte_id'] != a.nach_sparte_id
                    or row['offen_cent'] <= 0):
                raise HTTPException(422, 'Auslage passt nicht zu den Sparten oder ist nicht offen')
        summe = sum(row['offen_cent'] for row in auslagen)
        if a.betrag_cent > summe:
            raise HTTPException(422, f'Betrag übersteigt offene Summe: {summe} Cent')
        if a.datum < min(row['datum'] for row in auslagen):
            raise HTTPException(422, 'Datum liegt vor der ältesten gewählten Auslage')
        von, nach = _konten(con, a, bereich)
        warnungen = []
        if a.zahlungsart == 'bar':
            stand = con.execute(
                'SELECT COALESCE(SUM(betrag_signed_cent), 0) FROM bewegung '
                'WHERE konto_id = ? AND storniert_am IS NULL AND datum <= ?',
                (von['id'], a.datum),
            ).fetchone()[0]
            if stand < a.betrag_cent:
                euro = f'{stand / 100:,.2f}'.translate(str.maketrans({',': '.', '.': ','}))
                warnungen.append(f"{von['name']} hat nur {euro} €, danach negativ")
        tid, _ = erzeuge_transfer(
            con, 'ausgleich', von['id'], nach['id'], a.datum,
            a.betrag_cent, a.notiz, quelle='ausgleich',
        )
        aid = con.execute(
            'INSERT INTO ausgleich(transfer_id, datum, von_sparte_id, nach_sparte_id, '
            'betrag_cent, zahlungsart, client_request_id, notiz) VALUES(?, ?, ?, ?, ?, ?, ?, ?)',
            (tid, a.datum, a.von_sparte_id, a.nach_sparte_id, a.betrag_cent,
             a.zahlungsart, a.client_request_id, a.notiz),
        ).lastrowid
        rest = a.betrag_cent
        zuordnungen = []
        for row in sorted(auslagen, key=lambda r: (r['datum'], r['id'])):
            cent = min(rest, row['offen_cent'])
            if cent == 0:
                break
            con.execute(
                'INSERT INTO ausgleich_zuordnung(ausgleich_id, auslage_id, betrag_cent) '
                'VALUES(?, ?, ?)', (aid, row['id'], cent),
            )
            zuordnungen.append({'auslage_id': row['id'], 'betrag_cent': cent})
            rest -= cent
        antwort = {'id': aid, 'transfer_id': tid, 'zuordnungen': zuordnungen,
                   'warnungen': warnungen}
        speichere_antwort(con, 'ausgleich', a, bereich, antwort)
        return antwort


@router.delete('/ausgleiche/{ausgleich_id}', status_code=204)
def delete_ausgleich(ausgleich_id: int, con=Depends(db_dep), bereich: BereichDep = Bereich(1)):
    with con:
        con.execute('BEGIN IMMEDIATE')
        row = pruefe_ausgleich(con, ausgleich_id, bereich)
        con.execute(
            "UPDATE ausgleich SET aufgehoben_am = COALESCE(aufgehoben_am, datetime('now')) "
            'WHERE id = ?', (ausgleich_id,),
        )
        storniere_transfer(con, row['transfer_id'])


@router.get('/ausgleiche')
def list_ausgleiche(sparte_id: int | None = None, jahr: int | None = None,
                    con=Depends(db_dep), bereich: BereichDep = Bereich(1)):
    if sparte_id is not None:
        pruefe_sparte(con, sparte_id, bereich)
    sql = ('SELECT a.* FROM ausgleich a JOIN sparte s ON s.id = a.von_sparte_id '
           'WHERE s.bereich_id = ?')
    params = [bereich.id]
    if sparte_id is not None:
        sql += ' AND (a.von_sparte_id = ? OR a.nach_sparte_id = ?)'
        params.extend((sparte_id, sparte_id))
    if jahr is not None:
        if not 1 <= jahr <= 9999:
            raise HTTPException(422, 'Ungültiges Jahr')
        sql += ' AND a.datum >= ? AND a.datum <= ?'
        params.extend((f'{jahr:04d}-01-01', f'{jahr:04d}-12-31'))
    result = []
    for row in con.execute(sql + ' ORDER BY a.datum DESC, a.id DESC', params).fetchall():
        pruefe_ausgleich(con, row['id'], bereich)
        item = dict(row)
        item['zuordnungen'] = [dict(z) for z in con.execute(
            'SELECT z.auslage_id, z.betrag_cent FROM ausgleich_zuordnung z '
            'JOIN auslage a ON a.id = z.auslage_id JOIN buchung b ON b.id = a.buchung_id '
            'WHERE z.ausgleich_id = ? ORDER BY b.datum, a.id', (row['id'],),
        )]
        result.append(item)
    return result
