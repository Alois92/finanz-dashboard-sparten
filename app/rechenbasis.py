"""Gemeinsamer Filtervertrag für Kostenbuchungen und ihre Auswertungen."""
import base64
import binascii
import re
from dataclasses import asdict, dataclass, field, replace
from datetime import date, datetime
from statistics import median
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import Depends, HTTPException

from .bereiche import (Bereich, BereichDep, pruefe_sparte, pruefe_kategorie,
                       pruefe_globalgruppe, pruefe_auswertungsgruppe)
from .db import db_dep


def stichtag_heute() -> str:
    try:
        return datetime.now(ZoneInfo('Europe/Vienna')).date().isoformat()
    except ZoneInfoNotFoundError:
        return date.today().isoformat()


@dataclass
class Filter:
    bereich_id: int = 1
    sparte_id: int | None = None
    auswertungsgruppe_id: int | None = None
    globalgruppe_id: int | None = None
    jahr: int | None = None
    von: str | None = None
    bis: str | None = None
    kategorie_id: int | None = None
    richtung: str | None = None
    zahlungsart: str | None = None
    stichtag: str | None = field(default_factory=stichtag_heute)
    monat: str | None = None


def auswertungsfilter(f):
    """Ohne Zeitraum gilt das Stichtagsjahr, freie Datumsintervalle bleiben frei."""
    stichtag = f.stichtag or stichtag_heute()
    jahr = f.jahr
    if jahr is None and not f.von and not f.bis:
        jahr = int((f.monat or stichtag)[:4])
    return replace(f, jahr=jahr, stichtag=stichtag)


def pruefe_filter(con, f):
    bereich = Bereich(f.bereich_id)
    for value, check in ((f.sparte_id, pruefe_sparte),
                         (f.kategorie_id, pruefe_kategorie),
                         (f.globalgruppe_id, pruefe_globalgruppe),
                         (f.auswertungsgruppe_id, pruefe_auswertungsgruppe)):
        if value is not None:
            check(con, value, bereich)
    for value, table in ((f.globalgruppe_id, 'globale_kategoriegruppe'),
                         (f.auswertungsgruppe_id, 'auswertungsgruppe')):
        if value is not None and not con.execute(
                f'SELECT 1 FROM {table} WHERE id=? AND aktiv=1', (value,)).fetchone():
            raise HTTPException(404, 'Gruppe nicht gefunden')
    if f.jahr is not None and not 2 <= f.jahr <= 9999:
        raise HTTPException(422, 'Jahr muss zwischen 2 und 9999 liegen')
    for value in (f.von, f.bis, f.stichtag):
        if value:
            try:
                if date.fromisoformat(value).isoformat() != value:
                    raise ValueError
            except ValueError:
                raise HTTPException(422, 'Datum muss YYYY-MM-DD entsprechen') from None
    if f.von and f.bis and f.von > f.bis:
        raise HTTPException(422, 'von darf nicht nach bis liegen')
    if f.monat and not re.fullmatch(r'\d{4}-(0[1-9]|1[0-2])', f.monat):
        raise HTTPException(400, 'Monat muss das Format JJJJ-MM haben')


def filter_dep(sparte_id: int | None = None, auswertungsgruppe_id: int | None = None,
               globalgruppe_id: int | None = None, jahr: int | None = None,
               von: str | None = None, bis: str | None = None,
               kategorie_id: int | None = None,
               richtung: Literal['einnahme', 'ausgabe'] | None = None,
               zahlungsart: Literal['bar', 'bank', 'karte'] | None = None,
               stichtag: str | None = None, monat: str | None = None,
               con=Depends(db_dep), bereich: BereichDep = Bereich(1)) -> Filter:
    f = Filter(bereich.id, sparte_id, auswertungsgruppe_id, globalgruppe_id,
               jahr, von, bis, kategorie_id, richtung, zahlungsart,
               stichtag or stichtag_heute(), monat)
    pruefe_filter(con, f)
    return f


def _sparten_sql(f):
    sql = 'SELECT s.id FROM sparte s WHERE s.bereich_id=?'
    params = [f.bereich_id]
    if f.sparte_id is not None:
        sql += ' AND s.id=?'; params.append(f.sparte_id)
    if f.auswertungsgruppe_id is not None:
        sql += (' AND EXISTS (SELECT 1 FROM auswertungsgruppe_sparte g '
                'WHERE g.sparte_id=s.id AND g.auswertungsgruppe_id=?)')
        params.append(f.auswertungsgruppe_id)
    return sql, params


def sparten_ids(con, f: Filter) -> list[int]:
    sql, params = _sparten_sql(f)
    return [r[0] for r in con.execute(sql + ' ORDER BY s.sortierung,s.id', params)]


def where_zeilen(con, f):
    sparten_sql, params = _sparten_sql(f)
    sql = ' WHERE v.sparte_id IN (' + sparten_sql + ')'
    for field, value in (('kategorie_id', f.kategorie_id), ('typ', f.richtung)):
        if value is not None:
            sql += f' AND v.{field}=?'; params.append(value)
    if f.globalgruppe_id is not None:
        sql += (' AND v.kategorie_id IN (SELECT kategorie_id FROM '
                'kategorie_globalgruppe WHERE globalgruppe_id=?)')
        params.append(f.globalgruppe_id)
    if f.zahlungsart:
        sql += ' AND v.buchung_id IN (SELECT id FROM buchung WHERE zahlungsart=?)'
        params.append(f.zahlungsart)
    if f.jahr:
        sql += ' AND v.datum>=? AND v.datum<=?'
        params.extend((f'{f.jahr:04}-01-01', f'{f.jahr:04}-12-31'))
    for op, value in (('>=', f.von), ('<=', f.bis)):
        if value:
            sql += f' AND v.datum{op}?'; params.append(value)
    if f.monat:
        sql += " AND substr(v.datum,1,7)=?"; params.append(f.monat)
    # Alt-Routen ohne Jahr bleiben ungekappt. Expliziter Stichtag begrenzt
    # dagegen auch freie Zeiträume des neuen Filtervertrags.
    if f.stichtag:
        sql += ' AND v.datum<=?'; params.append(f.stichtag)
    return sql, params


SUMMEN_SQL = ("COALESCE(SUM(CASE WHEN v.typ='einnahme' THEN v.betrag_cent END),0) AS einnahmen_cent, "
              "COALESCE(SUM(CASE WHEN v.typ='ausgabe' THEN v.betrag_cent END),0) AS ausgaben_cent")


def summen(con, f):
    where, params = where_zeilen(con, f)
    row = dict(con.execute('SELECT ' + SUMMEN_SQL + ' FROM v_einnahmen_ausgaben v' + where, params).fetchone())
    row['saldo_cent'] = row['einnahmen_cent'] - row['ausgaben_cent']
    return row


def monatsreihe(con, f):
    where, params = where_zeilen(con, f)
    result = {'einnahmen': [0] * 12, 'ausgaben': [0] * 12}
    for row in con.execute("SELECT CAST(substr(v.datum,6,2) AS INTEGER) AS monat, " + SUMMEN_SQL +
                           ' FROM v_einnahmen_ausgaben v' + where + ' GROUP BY monat', params):
        for key in result:
            result[key][row['monat'] - 1] = row[key + '_cent']
    return result


def je_kategorie(con, f):
    where, params = where_zeilen(con, f)
    return [dict(r) for r in con.execute(
        'SELECT k.id AS kategorie_id,k.name,v.sparte_id,k.aktiv,k.richtung,' + SUMMEN_SQL +
        ' FROM v_einnahmen_ausgaben v JOIN kategorie k ON k.id=v.kategorie_id' + where +
        ' GROUP BY k.id,v.sparte_id ORDER BY v.sparte_id,k.sortierung,k.name,k.id', params)]


def vorjahresdatum(value):
    d = date.fromisoformat(value)
    try:
        return d.replace(year=d.year - 1).isoformat()
    except ValueError:
        return d.replace(year=d.year - 1, day=28).isoformat()


def vorjahresfilter(f):
    return replace(f, jahr=(f.jahr - 1) if f.jahr else None,
                   von=vorjahresdatum(f.von) if f.von else None,
                   bis=vorjahresdatum(f.bis) if f.bis else None,
                   stichtag=None,
                   monat=f'{int(f.monat[:4])-1:04}{f.monat[4:]}' if f.monat else None)


def vorjahresrest(con, f, stichtag):
    previous = vorjahresfilter(f)
    where, params = where_zeilen(con, previous)
    row = dict(con.execute('SELECT ' + SUMMEN_SQL + ' FROM v_einnahmen_ausgaben v' +
                           where + ' AND v.datum>?', [*params, vorjahresdatum(stichtag)]).fetchone())
    row['saldo_cent'] = row['einnahmen_cent'] - row['ausgaben_cent']
    return row


def erwartung(con, f, stichtag):
    if f.jahr != int(stichtag[:4]):
        return None
    ist = summen(con, replace(f, stichtag=stichtag))
    rest = vorjahresrest(con, f, stichtag)
    return {key: ist[key] + rest[key] for key in ist}


def cursor_encode(datum, kennung):
    return base64.b64encode(f'{datum}|{kennung}'.encode('ascii')).decode('ascii')


def cursor_decode(cursor):
    try:
        datum, kennung = base64.b64decode(cursor, validate=True).decode('ascii').split('|')
        if date.fromisoformat(datum).isoformat() != datum or not kennung.isdecimal() or int(kennung) < 1:
            raise ValueError
        return datum, int(kennung)
    except (ValueError, UnicodeError, binascii.Error):
        raise HTTPException(422, 'Ungültiger Cursor') from None


def _euro_text(cent):
    """Euro-Text wie format.js (fmtEur) ihn im Frontend zeigt, z. B. '50,99 €'."""
    value = f"{abs(cent) / 100:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return ('-' if cent < 0 else '') + value + ' €'


def hinweise(con, f, stichtag):
    result = []
    drill = {k: v for k, v in asdict(f).items() if v is not None}

    def add(art, wert, text, extra=None, ident='', wert_cent=None):
        wert = str(wert)
        result.append({'schluessel': f'{art}:{ident}:{wert}', 'art': art,
                       'wert': wert, 'wert_cent': wert_cent, 'text': text,
                       'drill': {**drill, **(extra or {})}})

    ist = summen(con, f)
    prognose = erwartung(con, f, stichtag)
    previous = vorjahresfilter(f)
    alt = summen(con, previous)
    if prognose and alt['ausgaben_cent'] and prognose['ausgaben_cent'] > alt['ausgaben_cent']:
        prozent = round((prognose['ausgaben_cent'] / alt['ausgaben_cent'] - 1) * 20) * 5
        add('kostenanstieg', prozent, f'Ausgaben hochgerechnet {prozent}% über dem Vorjahr.')
    where, params = where_zeilen(con, f)
    biggest = con.execute('SELECT v.buchung_id,v.kategorie_id,SUM(v.betrag_cent) AS cent '
                          'FROM v_einnahmen_ausgaben v' + where +
                          ' GROUP BY v.buchung_id ORDER BY cent DESC,v.buchung_id DESC LIMIT 1', params).fetchone()
    if biggest:
        add('groesste_buchung', biggest['cent'], f"Größte Buchung: {_euro_text(biggest['cent'])}.",
            {'kategorie_id': biggest['kategorie_id']}, wert_cent=biggest['cent'])
    categories = je_kategorie(con, f)
    if ist['ausgaben_cent']:
        top = max(categories, key=lambda c: c['ausgaben_cent'])
        share = round(top['ausgaben_cent'] / ist['ausgaben_cent'] * 100)
        add('kategorie_anteil', share, f"{top['name']}: {share}% der Ausgaben.",
            {'kategorie_id': top['kategorie_id'], 'richtung': 'ausgabe'}, str(top['kategorie_id']))
    if f.jahr == int(stichtag[:4]) and f.richtung != 'ausgabe':
        history = replace(previous, von=None, bis=None, monat=None, richtung='einnahme')
        w, p = where_zeilen(con, history)
        rows = con.execute('SELECT DISTINCT v.buchung_id,v.kategorie_id,v.datum FROM v_einnahmen_ausgaben v' + w, p)
        per = {}
        for row in rows:
            per.setdefault(row['kategorie_id'], []).append(row['datum'])
        current = replace(f, von=None, bis=None, monat=stichtag[:7], richtung='einnahme')
        present = {r['kategorie_id'] for r in je_kategorie(con, current)}
        for kid, dates in per.items():
            if len({d[5:7] for d in dates}) >= 11 and kid not in present and int(stichtag[8:]) >= median(int(d[8:]) for d in dates) + 5:
                name = con.execute('SELECT name FROM kategorie WHERE id=?', (kid,)).fetchone()[0]
                add('einnahme_fehlt', stichtag[:7], f'{name}: regelmäßige Einnahme fehlt.',
                    {'kategorie_id': kid, 'monat': stichtag[:7], 'richtung': 'einnahme'}, str(kid))
    # Offene Auslagen werden nach der Kostensparte und denselben Buchungen gefiltert.
    open_row = con.execute(
        'SELECT COALESCE(SUM(a.betrag_cent - COALESCE((SELECT SUM(z.betrag_cent) '
        'FROM ausgleich_zuordnung z JOIN ausgleich g ON g.id=z.ausgleich_id '
        'WHERE z.auslage_id=a.id AND g.aufgehoben_am IS NULL AND g.datum<=?),0)),0) '
        'FROM auslage a WHERE a.buchung_id IN (SELECT v.buchung_id FROM v_einnahmen_ausgaben v' + where + ')',
        [stichtag, *params]).fetchone()[0]
    if open_row > 0:
        add('auslagen_offen', open_row, f'Offene Auslagen: {_euro_text(open_row)}.', wert_cent=open_row)
    ids = sparten_ids(con, f)
    sql = ('SELECT COUNT(*) FROM bankumsatz u JOIN bankkonto k ON k.id=u.bankkonto_id '
           "WHERE k.bereich_id=? AND u.datum<=? AND u.importstatus='offen' AND NOT EXISTS "
           '(SELECT 1 FROM buchung b WHERE b.bankumsatz_id=u.id)')
    p = [f.bereich_id, stichtag]
    if f.sparte_id is not None or f.auswertungsgruppe_id is not None:
        sql += ' AND k.sparte_id IN (' + ','.join('?' for _ in ids) + ')'; p.extend(ids)
    count = con.execute(sql, p).fetchone()[0]
    if count:
        add('bankumsaetze_offen', count, f'{count} offene Bankumsätze.')
    hidden = {r['schluessel']: r['bis_wert'] for r in con.execute(
        'SELECT schluessel,bis_wert FROM hinweis_aus WHERE bereich_id=?', (f.bereich_id,))}
    return [h for h in result if h['schluessel'] not in hidden or hidden[h['schluessel']] != h['wert']]
