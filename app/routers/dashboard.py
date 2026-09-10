"""Dashboard: Kennzahlen auf Basis von v_einnahmen_ausgaben (Umbuchungen ausgeblendet)."""
import sqlite3
from dataclasses import replace
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .. import rechenbasis as rb
from ..db import db_dep
from ..bereiche import Bereich, BereichDep
from ..konten import kontostand
from .auslagen import list_auslagen

router = APIRouter(tags=["dashboard"])


@router.get('/jahre')
def jahre(con: sqlite3.Connection = Depends(db_dep), bereich: BereichDep = Bereich(1)):
    """Jahre mit Buchungen im Bereich plus das laufende Wiener Jahr."""
    rows = con.execute(
        "SELECT DISTINCT CAST(strftime('%Y', v.datum) AS INTEGER) AS jahr "
        "FROM v_einnahmen_ausgaben v JOIN sparte s ON s.id=v.sparte_id "
        "WHERE s.bereich_id=? AND v.datum IS NOT NULL", (bereich.id,)
    ).fetchall()
    years = {int(row['jahr']) for row in rows if row['jahr'] is not None}
    years.add(int(rb.stichtag_heute()[:4]))
    return {'jahre': sorted(years, reverse=True)}


def _where(con, sparte_id, globalgruppe_id, von, bis, bereich):
    f = rb.Filter(bereich_id=bereich.id, sparte_id=sparte_id,
                  globalgruppe_id=globalgruppe_id, von=von, bis=bis, stichtag=None)
    rb.pruefe_filter(con, f)
    return rb.where_zeilen(con, f)


@router.get("/dashboard")
def dashboard(sparte_id: int | None = None,
              globalgruppe_id: int | None = None,
              von: str | None = None,
              bis: str | None = None,
              con: sqlite3.Connection = Depends(db_dep), bereich: BereichDep = Bereich(1)):
    where, params = _where(con, sparte_id, globalgruppe_id, von, bis, bereich)

    summe = rb.summen(con, rb.Filter(bereich_id=bereich.id, sparte_id=sparte_id,
                                     globalgruppe_id=globalgruppe_id, von=von, bis=bis, stichtag=None))
    einnahmen = summe['einnahmen_cent']
    ausgaben = summe['ausgaben_cent']

    # sparte je Kategorie mitliefern (Studio nutzt sie fuer Farbe/Zuordnung;
    # gleichnamige Kategorien in verschiedenen Sparten bleiben unterscheidbar).
    per_kategorie = [dict(r) for r in con.execute(
        "SELECT k.id AS kategorie_id, k.name AS kategorie, s.name AS sparte, "
        "v.typ, SUM(v.betrag_cent) AS betrag_cent "
        "FROM v_einnahmen_ausgaben v JOIN kategorie k ON k.id = v.kategorie_id "
        "JOIN sparte s ON s.id = v.sparte_id" + where +
        " GROUP BY k.id, v.typ ORDER BY betrag_cent DESC",
        params,
    ).fetchall()]

    per_sparte = [dict(r) for r in con.execute(
        "SELECT s.name AS sparte, "
        "COALESCE(SUM(CASE WHEN v.typ='einnahme' THEN v.betrag_cent END),0) AS einnahmen_cent, "
        "COALESCE(SUM(CASE WHEN v.typ='ausgabe'  THEN v.betrag_cent END),0) AS ausgaben_cent "
        "FROM v_einnahmen_ausgaben v JOIN sparte s ON s.id = v.sparte_id" + where +
        " GROUP BY s.id ORDER BY s.sortierung",
        params,
    ).fetchall()]

    return {
        "einnahmen_cent": einnahmen,
        "ausgaben_cent": ausgaben,
        "saldo_cent": einnahmen - ausgaben,
        "per_kategorie": per_kategorie,
        "per_sparte": per_sparte,
    }


@router.get("/jahresvergleich")
def jahresvergleich(sparte_id: int | None = None,
                    globalgruppe_id: int | None = None,
                    von: str | None = None,
                    bis: str | None = None,
                    con: sqlite3.Connection = Depends(db_dep), bereich: BereichDep = Bereich(1)):
    """Kennzahlen je Kalenderjahr (Basis: v_einnahmen_ausgaben, Umbuchungen raus).

    Liefert eine Gesamtzeile je Jahr und zusaetzlich eine Saldo-Matrix
    Sparte x Jahr fuer den Jahresvergleich untereinander.
    """
    where, params = _where(con, sparte_id, globalgruppe_id, von, bis, bereich)

    gesamt = [dict(r) for r in con.execute(
        "SELECT strftime('%Y', v.datum) AS jahr, "
        "COALESCE(SUM(CASE WHEN v.typ='einnahme' THEN v.betrag_cent END),0) AS einnahmen_cent, "
        "COALESCE(SUM(CASE WHEN v.typ='ausgabe'  THEN v.betrag_cent END),0) AS ausgaben_cent "
        "FROM v_einnahmen_ausgaben v" + where +
        " GROUP BY jahr ORDER BY jahr",
        params,
    ).fetchall()]
    for g in gesamt:
        g["saldo_cent"] = g["einnahmen_cent"] - g["ausgaben_cent"]
    jahre = [g["jahr"] for g in gesamt]

    rows = con.execute(
        "SELECT s.name AS sparte, strftime('%Y', v.datum) AS jahr, "
        "COALESCE(SUM(CASE WHEN v.typ='einnahme' THEN v.betrag_cent END),0) - "
        "COALESCE(SUM(CASE WHEN v.typ='ausgabe'  THEN v.betrag_cent END),0) AS saldo_cent "
        "FROM v_einnahmen_ausgaben v JOIN sparte s ON s.id = v.sparte_id" + where +
        " GROUP BY s.id, jahr ORDER BY s.sortierung, jahr",
        params,
    ).fetchall()
    per_sparte: dict[str, dict] = {}
    for r in rows:
        per_sparte.setdefault(r["sparte"], {})[r["jahr"]] = r["saldo_cent"]
    per_sparte_list = [{"sparte": name, "werte": werte}
                       for name, werte in per_sparte.items()]

    # Matrix Kategorie x Jahr (Saldo je Kategorie), inkl. Sparte fuer Farbe/Kontext.
    rows_k = con.execute(
        "SELECT s.name AS sparte, k.id AS kategorie_id, k.name AS kategorie, "
        "strftime('%Y', v.datum) AS jahr, "
        "COALESCE(SUM(CASE WHEN v.typ='einnahme' THEN v.betrag_cent END),0) - "
        "COALESCE(SUM(CASE WHEN v.typ='ausgabe'  THEN v.betrag_cent END),0) AS saldo_cent "
        "FROM v_einnahmen_ausgaben v "
        "JOIN kategorie k ON k.id = v.kategorie_id "
        "JOIN sparte s ON s.id = v.sparte_id" + where +
        " GROUP BY k.id, jahr ORDER BY s.sortierung, k.sortierung, k.name, jahr",
        params,
    ).fetchall()
    per_kategorie: dict = {}
    for r in rows_k:
        key = r["kategorie_id"]
        eintrag = per_kategorie.setdefault(
            key, {"sparte": r["sparte"], "kategorie": r["kategorie"], "werte": {}})
        eintrag["werte"][r["jahr"]] = r["saldo_cent"]
    per_kategorie_list = list(per_kategorie.values())

    return {"jahre": jahre, "gesamt": gesamt,
            "per_sparte": per_sparte_list, "per_kategorie": per_kategorie_list}


@router.get("/verlauf")
def verlauf(sparte_id: int | None = None,
            globalgruppe_id: int | None = None,
            von: str | None = None,
            bis: str | None = None,
            con: sqlite3.Connection = Depends(db_dep), bereich: BereichDep = Bereich(1)):
    """Monatsreihe fuer den zeitlichen Verlauf (Basis: v_einnahmen_ausgaben).

    Liefert je Kalendermonat Einnahmen/Ausgaben/Saldo. Versorgt das
    Verlauf-Diagramm und die KPI-Sparklines im Cockpit-Frontend.
    """
    where, params = _where(con, sparte_id, globalgruppe_id, von, bis, bereich)

    rows = [dict(r) for r in con.execute(
        "SELECT strftime('%Y-%m', v.datum) AS monat, "
        "COALESCE(SUM(CASE WHEN v.typ='einnahme' THEN v.betrag_cent END),0) AS einnahmen_cent, "
        "COALESCE(SUM(CASE WHEN v.typ='ausgabe'  THEN v.betrag_cent END),0) AS ausgaben_cent "
        "FROM v_einnahmen_ausgaben v" + where +
        " GROUP BY monat ORDER BY monat",
        params,
    ).fetchall()]
    for r in rows:
        r["saldo_cent"] = r["einnahmen_cent"] - r["ausgaben_cent"]

    return {"monate": rows}


@router.get('/uebersicht')
def uebersicht(f: rb.Filter = Depends(rb.filter_dep), con=Depends(db_dep)):
    stichtag = f.stichtag or rb.stichtag_heute()
    f = rb.auswertungsfilter(f)
    previous = rb.vorjahresfilter(f)
    ist = rb.summen(con, f)
    monate = rb.monatsreihe(con, f)
    alt_monate = rb.monatsreihe(con, previous)
    monate.update(vorjahr_einnahmen=alt_monate['einnahmen'], vorjahr_ausgaben=alt_monate['ausgaben'])
    sparten = []
    ids = rb.sparten_ids(con, f)
    for sid in ids:
        s = dict(con.execute('SELECT id AS sparte_id,name,kuerzel,farbe FROM sparte WHERE id=?', (sid,)).fetchone())
        s.update(rb.summen(con, replace(f, sparte_id=sid)))
        sparten.append(s)
    categories = rb.je_kategorie(con, f)
    top = {}
    for key in ('ausgaben', 'einnahmen'):
        total = ist[key + '_cent']
        top[key] = [{'kategorie_id': c['kategorie_id'], 'name': c['name'],
                     'sparte_id': c['sparte_id'], 'betrag_cent': c[key + '_cent'],
                     'anteil': c[key + '_cent'] / total if total else 0}
                    for c in sorted(categories, key=lambda c: (-c[key + '_cent'], c['kategorie_id']))[:5]
                    if c[key + '_cent']]
    konten = []
    waehrungen = {}
    for konto in con.execute('SELECT id,name,sparte_id,waehrung FROM bankkonto WHERE bereich_id=? ORDER BY sortierung,id', (f.bereich_id,)):
        if (f.sparte_id is not None or f.auswertungsgruppe_id is not None) and konto['sparte_id'] not in ids:
            continue
        stand = {**dict(konto), **kontostand(con, konto['id'], stichtag)}
        konten.append(stand)
        gruppe = waehrungen.setdefault(konto['waehrung'], {'stand_cent': 0, 'unbekannte_konten': 0})
        if stand['stand_cent'] is None:
            gruppe['unbekannte_konten'] += 1
        else:
            gruppe['stand_cent'] += stand['stand_cent']
    for gruppe in waehrungen.values():
        if gruppe['unbekannte_konten']:
            gruppe['stand_cent'] = None
    where, params = rb.where_zeilen(con, f)
    matched = {r[0] for r in con.execute('SELECT DISTINCT v.buchung_id FROM v_einnahmen_ausgaben v' + where, params)}
    auslagen = []
    for gruppe in list_auslagen(stichtag=date.fromisoformat(stichtag), con=con, bereich=Bereich(f.bereich_id)):
        rows = [a for a in gruppe['auslagen'] if a['buchung_id'] in matched]
        if rows:
            auslagen.append({**gruppe, 'auslagen': rows, 'anzahl': len(rows), 'offen_cent': sum(a['offen_cent'] for a in rows)})
    letzte = con.execute('SELECT MAX(v.datum) FROM v_einnahmen_ausgaben v' + where, params).fetchone()[0]
    import_sql = ('SELECT MAX(i.importiert_am) FROM import_batch i JOIN bankkonto k ON k.id=i.bankkonto_id '
                  'WHERE k.bereich_id=?')
    import_params = [f.bereich_id]
    if f.sparte_id is not None or f.auswertungsgruppe_id is not None:
        import_sql += ' AND k.sparte_id IN (' + ','.join('?' for _ in ids) + ')'
        import_params.extend(ids)
    letzter_import = con.execute(import_sql, import_params).fetchone()[0]
    return {'stichtag': stichtag, 'jahr': f.jahr, 'ist': ist,
            'vorjahr_gleicher_zeitraum': rb.summen(con, replace(previous, stichtag=rb.vorjahresdatum(stichtag))),
            'vorjahr_gesamt': rb.summen(con, previous), 'erwartung': rb.erwartung(con, f, stichtag),
            'monate': monate, 'sparten': sparten, 'top': top,
            'hinweise': rb.hinweise(con, f, stichtag), 'auslagen_offen': auslagen,
            'konten': konten, 'konten_je_waehrung': waehrungen,
            'datenstand': {'letzte_buchung': letzte, 'letzter_import': letzter_import}}


@router.get('/jahresmatrix')
def jahresmatrix(jahre: str | None = None, f: rb.Filter = Depends(rb.filter_dep), con=Depends(db_dep)):
    stichtag = f.stichtag or rb.stichtag_heute()
    try:
        years = sorted(set(int(y) for y in jahre.split(','))) if jahre else [f.jahr or int(stichtag[:4])]
        if not years or len(years) > 100 or any(not 2 <= y <= 9999 for y in years):
            raise ValueError
    except ValueError:
        raise HTTPException(422, 'jahre muss eine kommaseparierte Liste gültiger Jahre sein') from None
    rows, totals = {}, {}
    for year in years:
        yf = replace(f, jahr=year)
        totals[str(year)] = rb.summen(con, yf)
        for c in rb.je_kategorie(con, yf):
            key = c['kategorie_id']
            row = rows.setdefault(key, {k: c[k] for k in ('kategorie_id', 'name', 'sparte_id', 'aktiv', 'richtung')})
            row.setdefault('werte', {})[str(year)] = {k: c[k] for k in ('einnahmen_cent', 'ausgaben_cent')}
    current = int(stichtag[:4])
    if current in years:
        for c in rb.je_kategorie(con, rb.vorjahresfilter(replace(f, jahr=current))):
            if c['kategorie_id'] not in rows:
                rows[c['kategorie_id']] = {k: c[k] for k in ('kategorie_id', 'name', 'sparte_id', 'aktiv', 'richtung')}
                rows[c['kategorie_id']]['werte'] = {}
    for row in rows.values():
        for year in years:
            row['werte'].setdefault(str(year), {'einnahmen_cent': 0, 'ausgaben_cent': 0})
        cf = replace(f, jahr=current, kategorie_id=row['kategorie_id'])
        expect = rb.erwartung(con, cf, stichtag) if current in years else None
        row['erwartung_cent'] = {'einnahmen': expect['einnahmen_cent'], 'ausgaben': expect['ausgaben_cent']} if expect else None
        row['ohne_vorjahr'] = not bool(rb.je_kategorie(con, rb.vorjahresfilter(cf))) if current in years else False
        row['monatsdurchschnitt_cent'] = {
            str(year): {key: value // (int(stichtag[5:7]) if year == current else 12)
                        for key, value in row['werte'][str(year)].items()} for year in years}
    return {'jahre': years, 'stichtag': stichtag, 'zeilen': list(rows.values()), 'summen': totals}


class HinweisAusIn(BaseModel):
    schluessel: str = Field(min_length=1, max_length=500)
    bis_wert: str | None = Field(default=None, max_length=500)


@router.get('/hinweise/aus')
def list_hinweise_aus(con=Depends(db_dep), bereich: BereichDep = Bereich(1)):
    return [dict(r) for r in con.execute('SELECT * FROM hinweis_aus WHERE bereich_id=? ORDER BY id', (bereich.id,))]


@router.post('/hinweise/aus')
def hide_hinweis(body: HinweisAusIn, con=Depends(db_dep), bereich: BereichDep = Bereich(1)):
    with con:
        con.execute('INSERT INTO hinweis_aus(bereich_id,schluessel,bis_wert) VALUES(?,?,?) '
                    'ON CONFLICT(bereich_id,schluessel) DO UPDATE SET bis_wert=excluded.bis_wert',
                    (bereich.id, body.schluessel, body.bis_wert if body.bis_wert is not None else body.schluessel.rsplit(':', 1)[-1]))
    return dict(con.execute('SELECT * FROM hinweis_aus WHERE bereich_id=? AND schluessel=?',
                            (bereich.id, body.schluessel)).fetchone())
