"""Buchungen: erfassen (Kopf + Zeilen), auflisten, bearbeiten, loeschen.
Dazu Umbuchungen zwischen Sparten (zwei gekoppelte Buchungen)."""
import logging
import sqlite3
import uuid
from typing import Literal
from dataclasses import replace

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from .. import rechenbasis as rb
from ..db import db_dep
from ..bereiche import (Bereich, BereichDep, pruefe_sparte, pruefe_kategorie,
                        pruefe_konto, pruefe_buchung, pruefe_beleg, pruefe_umsatz)
from ..regeln import normalisiere_regeltext
from ..schemas import BuchungIn
from ..auslagen import (ergaenze_auslage, pruefe_zahler, synchronisiere_auslage,
                       zuordnungskonflikt)
from ..wiederholung import wiederhole, speichere_antwort
from ..bewegungen import (synchronisiere_buchung, storniere_buchungsbewegungen, kassa_fuer_sparte,
                          erzeuge_transfer, pruefe_bewegungsreferenzen, storniere_transfer, pruefe_transfer)

router = APIRouter(tags=["buchungen"])

log = logging.getLogger("finanz.buchungen")

UMBUCHUNG_KATEGORIE = "Umbuchung"


class UmbuchungIn(BaseModel):
    von_sparte_id: int
    nach_sparte_id: int
    datum: str
    betrag_cent: int = Field(gt=0)
    text: str | None = None
    zahlungsart: Literal['bank', 'bar'] = 'bank'
    von_konto_id: int | None = None
    nach_konto_id: int | None = None


def _pruefe_sparte_und_zeilen(con: sqlite3.Connection, b: BuchungIn, bereich: Bereich) -> None:
    pruefe_sparte(con, b.sparte_id, bereich)
    if b.bankumsatz_id is not None:
        pruefe_umsatz(con, b.bankumsatz_id, bereich)
        konto = con.execute('SELECT bankkonto_id FROM bankumsatz WHERE id=?', (b.bankumsatz_id,)).fetchone()[0]
        if b.bankkonto_id is not None and konto != b.bankkonto_id:
            raise HTTPException(422, 'Bankumsatz gehört nicht zum Konto')
        if b.zahlungsart == 'bar':
            raise HTTPException(422, 'Barbuchung darf keinen Bankumsatz referenzieren')
    if b.bankkonto_id is not None:
        pruefe_konto(con, b.bankkonto_id, bereich)
    pruefe_zahler(con, b, bereich)
    for z in b.zeilen:
        pruefe_kategorie(con, z.kategorie_id, bereich)
        krow = con.execute(
            "SELECT sparte_id FROM kategorie WHERE id = ? AND aktiv = 1",
            (z.kategorie_id,),
        ).fetchone()
        if not krow:
            raise HTTPException(404, f"Kategorie {z.kategorie_id} nicht gefunden")
        if krow["sparte_id"] != b.sparte_id:
            raise HTTPException(400, "Kategorie gehoert nicht zur gewaehlten Sparte")


@router.post("/buchungen", status_code=201)
def create_buchung(b: BuchungIn, con: sqlite3.Connection = Depends(db_dep),
                   bereich: BereichDep = Bereich(1)):
    try:
        with con:
            con.execute('BEGIN IMMEDIATE')
            antwort = wiederhole(con, 'buchung', b, bereich)
            if antwort is not None:
                return antwort
            _pruefe_sparte_und_zeilen(con, b, bereich)
            if any(z.id is not None for z in b.zeilen):
                raise HTTPException(422, 'Neue Buchungen dürfen keine bestehenden Zeilen referenzieren')
            cur = con.execute(
                "INSERT INTO buchung(sparte_id, datum, typ, zahlungsart, kontakt_id, "
                "person_id, bankkonto_id, text, notiz, bankumsatz_id, client_request_id) "
                "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (b.sparte_id, b.datum, b.typ, b.zahlungsart, b.kontakt_id,
                 b.person_id, b.bankkonto_id, b.text, b.notiz, b.bankumsatz_id,
                 b.client_request_id),
            )
            buchung_id = cur.lastrowid
            for z in b.zeilen:
                con.execute(
                    "INSERT INTO buchungszeile(buchung_id, kategorie_id, betrag_cent, notiz) "
                    "VALUES(?, ?, ?, ?)",
                    (buchung_id, z.kategorie_id, z.betrag_cent, z.notiz),
                )
            synchronisiere_auslage(con, buchung_id, b, bereich)
            synchronisiere_buchung(con, buchung_id, bereich)
            antwort = _buchung_detail(con, buchung_id)
            speichere_antwort(con, 'buchung', b, bereich, antwort)
    except sqlite3.IntegrityError as exc:
        raise HTTPException(400, f"Datenbankfehler: {exc}") from exc

    if b.typ != "umbuchung" and b.text and len(b.zeilen) == 1:
        _lerne_regel(con, b.text, b.sparte_id, b.zeilen[0].kategorie_id, b.typ, bereich.id, buchung_id)
    return antwort


def _lerne_regel(con: sqlite3.Connection, text: str, sparte_id: int,
                 kategorie_id: int, typ: str, bereich_id: int,
                 gelernt_aus_buchung_id: int | None = None) -> None:
    """Legt/aktualisiert automatisch eine Merkregel aus einer erfassten Buchung.

    Faellt wie das manuelle Lernen beim Bankumsatz-Verbuchen (import_bank.py)
    auf ein Upsert ueber LOWER(bedingung_text) zurueck. Fehler duerfen das
    Speichern der Buchung NIE ruecknehmen - daher komplett try/except mit Log,
    ohne eigenen Commit-/Rollback-Einfluss auf die bereits gespeicherte Buchung.
    """
    try:
        bedingung = normalisiere_regeltext(text)
        if len(bedingung) < 3:
            return
        name = "Gelernt: " + text[:60]
        vorhanden = con.execute(
            "SELECT id FROM regel WHERE LOWER(bedingung_text) = ? AND bereich_id = ? ORDER BY id LIMIT 1",
            (bedingung, bereich_id),
        ).fetchone()
        if vorhanden:
            con.execute(
                "UPDATE regel SET name = ?, ziel_sparte_id = ?, ziel_kategorie_id = ?, "
                "ziel_typ = ?, quelle = 'gelernt', auto_verbuchen = 0, "
                "eingabe_sparte_id = ?, gelernt_aus_buchung_id = ? WHERE id = ?",
                (name, sparte_id, kategorie_id, typ, sparte_id,
                 gelernt_aus_buchung_id, vorhanden["id"]),
            )
        else:
            con.execute(
                "INSERT INTO regel(name, bedingung_text, ziel_sparte_id, "
                "ziel_kategorie_id, ziel_typ, bereich_id, quelle, auto_verbuchen, "
                "eingabe_sparte_id, gelernt_aus_buchung_id) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (name, bedingung, sparte_id, kategorie_id, typ, bereich_id,
                 "gelernt", 0, sparte_id, gelernt_aus_buchung_id),
            )
        con.commit()
    except Exception:
        con.rollback()
        log.exception("Automatisches Lernen der Regel fehlgeschlagen (Buchung bleibt gespeichert)")


def _lade_buchungen(con, ids, bereich):
    if not ids:
        return []
    marks = ','.join('?' for _ in ids)
    buchungen = [dict(r) for r in con.execute(
        "SELECT b.id,b.sparte_id,s.name AS sparte_name,b.datum,b.typ,b.version,"
        "b.betrag_cent,b.zahlungsart,b.belegstatus,b.buchungsstatus,b.text,b.notiz,b.kredit_id,"
        "b.transfer_gruppe_id,b.kontakt_id,k.name AS kontakt_name "
        "FROM buchung b JOIN sparte s ON s.id=b.sparte_id "
        "LEFT JOIN kontakt k ON k.id=b.kontakt_id "
        f"WHERE b.id IN ({marks}) AND s.bereich_id=? ORDER BY b.datum DESC,b.id DESC",
        [*ids, bereich.id])]
    ids = [b["id"] for b in buchungen]
    marks = ",".join("?" * len(ids))
    zeilen = con.execute(
        f"SELECT z.buchung_id, z.id, z.kategorie_id, k.name AS kategorie_name, "
            f"z.betrag_cent, z.notiz, z.neutral "
        f"FROM buchungszeile z JOIN kategorie k ON k.id = z.kategorie_id "
        f"WHERE z.buchung_id IN ({marks}) ORDER BY z.id",
        ids,
    ).fetchall()
    by_buchung: dict[int, list] = {}
    for zeile in zeilen:
        by_buchung.setdefault(zeile["buchung_id"], []).append(dict(zeile))
    belege = con.execute(
        f"SELECT bb.buchung_id, bl.id, bl.dateiname "
        f"FROM buchung_beleg bb JOIN beleg bl ON bl.id = bb.beleg_id "
        f"WHERE bb.buchung_id IN ({marks}) AND bl.bereich_id = ? ORDER BY bl.id",
        [*ids, bereich.id],
    ).fetchall()
    belege_by: dict[int, list] = {}
    for beleg in belege:
        belege_by.setdefault(beleg["buchung_id"], []).append(
            {"id": beleg["id"], "dateiname": beleg["dateiname"]}
        )
    for buchung in buchungen:
        buchung["zeilen"] = by_buchung.get(buchung["id"], [])
        buchung["neutral_cent"] = sum(z["betrag_cent"] for z in buchung["zeilen"] if z.get("neutral", 0))
        buchung["belege"] = belege_by.get(buchung["id"], [])
        buchung['zahlungsstatus'] = _zahlungsstatus(con, buchung['id'])
        ergaenze_auslage(con, buchung)
    return buchungen


def _buchungsseite(con, f, q='', limit=100, cursor=None, typ=None):
    rb.pruefe_filter(con, f)
    where, params = rb.where_zeilen(con, f)
    # Treffer enthalten auch Umbuchungen und neutrale Zeilen; finanzielle
    # Summen werden ausschließlich aus der gefilterten Einnahmen/Ausgaben-View gebildet.
    selection = ' WHERE b.id IN (SELECT v.buchung_id FROM v_zeile v' + where + ')'
    if typ:
        selection += ' AND b.typ=?'; params.append(typ)
    if q:
        con.create_function('casefold', 1, lambda value: str(value or '').casefold(), deterministic=True)
        escaped = q.strip().casefold().replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
        pattern = '%' + escaped + '%'
        selection += (" AND (casefold(b.text) LIKE ? ESCAPE '\\' OR casefold(b.notiz) LIKE ? ESCAPE '\\' "
                      "OR casefold(k.name) LIKE ? ESCAPE '\\')")
        params.extend((pattern, pattern, pattern))
    source = ' FROM buchung b LEFT JOIN kontakt k ON k.id=b.kontakt_id'
    count = con.execute('SELECT COUNT(*)' + source + selection, params).fetchone()[0]
    w, p = rb.where_zeilen(con, f)
    totals = dict(con.execute('SELECT ' + rb.SUMMEN_SQL + ' FROM v_einnahmen_ausgaben v' + w +
                             ' AND v.buchung_id IN (SELECT b.id' + source + selection + ')', [*p, *params]).fetchone())
    totals['anzahl'] = count
    page_where, page_params = selection, list(params)
    if cursor:
        datum, bid = rb.cursor_decode(cursor)
        page_where += ' AND (b.datum<? OR (b.datum=? AND b.id<?))'
        page_params.extend((datum, datum, bid))
    page = con.execute('SELECT b.id,b.datum' + source + page_where +
                       ' ORDER BY b.datum DESC,b.id DESC LIMIT ?', [*page_params, limit + 1]).fetchall()
    more = len(page) > limit
    page = page[:limit]
    rows = _lade_buchungen(con, [r['id'] for r in page], Bereich(f.bereich_id))
    if f.kategorie_id is not None or f.globalgruppe_id is not None:
        amounts = {r['buchung_id']: r['cent'] for r in con.execute(
            'SELECT v.buchung_id,SUM(v.betrag_cent) AS cent FROM v_einnahmen_ausgaben v' + w +
            ' GROUP BY v.buchung_id', p)}
        for row in rows:
            row['filter_betrag_cent'] = amounts.get(row['id'], 0)
    return {'buchungen': rows, 'summen': totals,
            'naechster_cursor': rb.cursor_encode(page[-1]['datum'], page[-1]['id']) if more else None}


@router.get('/buchungen')
def list_buchungen(f: rb.Filter = Depends(rb.filter_dep), q: str = '',
                    limit: int = Query(100, ge=1, le=1000), cursor: str | None = None,
                    typ: Literal['einnahme', 'ausgabe', 'umbuchung'] | None = None,
                    con: sqlite3.Connection = Depends(db_dep)):
    return _buchungsseite(con, rb.auswertungsfilter(f), q, limit, cursor, typ)


@router.get('/buchungen/suche')
def suche_buchungen(q: str, con: sqlite3.Connection = Depends(db_dep),
                    bereich: BereichDep = Bereich(1), f: rb.Filter = Depends(rb.filter_dep),
                    stichtag: str | None = None):
    """Kompatible Listenform (maximal 200), berechnet über dieselbe Buchungsliste."""
    if not isinstance(f, rb.Filter):
        f = rb.Filter(bereich_id=bereich.id)
    f = replace(f, stichtag=stichtag)
    return _buchungsseite(con, f, q=q, limit=200)['buchungen']


@router.post("/umbuchungen", status_code=201)
def create_umbuchung(u: UmbuchungIn, con: sqlite3.Connection = Depends(db_dep), bereich: BereichDep = Bereich(1)):
    """Geld zwischen zwei Sparten verschieben: zwei gekoppelte Buchungen
    (typ='umbuchung'), verbunden ueber transfer_gruppe_id. Umbuchungen sind
    in allen Einnahmen/Ausgaben-Auswertungen ausgeblendet (v_einnahmen_ausgaben).
    """
    pruefe_sparte(con, u.von_sparte_id, bereich)
    pruefe_sparte(con, u.nach_sparte_id, bereich)
    if u.von_sparte_id == u.nach_sparte_id:
        raise HTTPException(400, "Von- und Nach-Sparte muessen verschieden sein")
    konten = []
    for sid, kid in ((u.von_sparte_id,u.von_konto_id),(u.nach_sparte_id,u.nach_konto_id)):
        if kid is not None:
            pruefe_konto(con,kid,bereich)
            konto = con.execute('SELECT sparte_id,art FROM bankkonto WHERE id=?',(kid,)).fetchone()
            if konto[0] != sid:
                raise HTTPException(422,'Konto gehört nicht zur Sparte')
            if u.zahlungsart == 'bar' and konto[1] != 'kassa':
                raise HTTPException(422,'Barumbuchung benötigt Kassenkonten')
        elif u.zahlungsart == 'bar':
            kandidaten = con.execute("SELECT id FROM bankkonto WHERE sparte_id=? AND art='kassa'",(sid,)).fetchall()
            if len(kandidaten)>1:
                raise HTTPException(409,'Kassa nicht eindeutig')
            kid = kandidaten[0][0] if kandidaten else None
        else:
            kandidaten = con.execute("SELECT id FROM bankkonto WHERE sparte_id=? AND art='bank' AND aktiv=1",(sid,)).fetchall()
            kid = kandidaten[0][0] if len(kandidaten)==1 else None
        if kid is not None:
            pruefe_konto(con,kid,bereich)
        konten.append(kid)
    if all(k is not None for k in konten):
        if len({r[0] for r in con.execute('SELECT waehrung FROM bankkonto WHERE id IN (?,?)',konten)}) != 1:
            raise HTTPException(422,'Transfer benötigt dieselbe Währung')
    else:
        konten = [None,None]
    def umbuchung_kategorie(sparte_id: int) -> int:
        row = con.execute(
            "SELECT id FROM kategorie WHERE sparte_id = ? AND lower(name) = ? "
            "AND aktiv = 1", (sparte_id, UMBUCHUNG_KATEGORIE.lower())).fetchone()
        if row:
            return row["id"]
        return con.execute(
            "INSERT INTO kategorie(sparte_id, name, richtung) VALUES(?,?, 'beides')",
            (sparte_id, UMBUCHUNG_KATEGORIE)).lastrowid

    gruppe = uuid.uuid4().hex
    try:
        if u.zahlungsart == 'bar':
            konten = [kassa_fuer_sparte(con,sid,bereich) for sid in (u.von_sparte_id,u.nach_sparte_id)]
            if len({r[0] for r in con.execute('SELECT waehrung FROM bankkonto WHERE id IN (?,?)',konten)}) != 1:
                raise HTTPException(422,'Transfer benötigt dieselbe Währung')
        ids = []
        for sparte_id, richtung_text in ((u.von_sparte_id, "an"), (u.nach_sparte_id, "von")):
            andere = u.nach_sparte_id if sparte_id == u.von_sparte_id else u.von_sparte_id
            name_andere = con.execute("SELECT name FROM sparte WHERE id = ?",
                                      (andere,)).fetchone()["name"]
            text = u.text or f"Umbuchung {richtung_text} {name_andere}"
            cur = con.execute(
                "INSERT INTO buchung(sparte_id, datum, typ, zahlungsart, "
                "transfer_gruppe_id, buchungsstatus, text) "
                "VALUES(?,?, 'umbuchung', 'bank', ?, 'zugeordnet', ?)",
                (sparte_id, u.datum, gruppe, text))
            con.execute(
                "INSERT INTO buchungszeile(buchung_id, kategorie_id, betrag_cent) "
                "VALUES(?,?,?)",
                (cur.lastrowid, umbuchung_kategorie(sparte_id), u.betrag_cent))
            ids.append(cur.lastrowid)
        tid, mids = erzeuge_transfer(con,'umbuchung',*konten,u.datum,u.betrag_cent,
                                    u.text if all(k is not None for k in konten) else 'Nachzug Umbuchung '+gruppe+'; Konten ungeklärt')
        for bid, kid in zip(ids,konten):
            con.execute('UPDATE buchung SET bankkonto_id=?,zahlungsart=? WHERE id=?',(kid,u.zahlungsart,bid))
        for bid, mid, sign in zip(ids,mids,(-1,1)):
            con.execute('INSERT INTO buchung_bewegung VALUES(?,?,?)',(bid,mid,sign*u.betrag_cent))
        con.commit()
    except sqlite3.Error as e:
        con.rollback()
        raise HTTPException(400, f"Datenbankfehler: {e}")
    except HTTPException:
        con.rollback()
        raise
    return {"transfer_gruppe_id": gruppe, "buchung_ids": ids,
            "betrag_cent": u.betrag_cent, "transfer_id": tid}


@router.put("/buchungen/{buchung_id}")
def update_buchung(buchung_id: int, b: BuchungIn,
                   con: sqlite3.Connection = Depends(db_dep), bereich: BereichDep = Bereich(1)):
    with con:
        con.execute('BEGIN IMMEDIATE')
        return _update_buchung(buchung_id, b, con, bereich)


def _update_buchung(buchung_id: int, b: BuchungIn, con: sqlite3.Connection, bereich: Bereich):

    """Buchung ueberschreiben: Kopf-Felder aktualisieren, Zeilen ersetzen.

    Verknuepfungen, die nicht im Formular stehen (bankumsatz_id, Belegstatus,
    transfer_gruppe_id), bleiben unveraendert erhalten.
    """
    pruefe_buchung(con, buchung_id, bereich)
    _pruefe_buchungsreferenzen(con, buchung_id, bereich)
    if b.version is None:
        raise HTTPException(422, 'PUT benötigt version')
    version = con.execute('SELECT version FROM buchung WHERE id = ?', (buchung_id,)).fetchone()[0]
    if b.version != version:
        raise HTTPException(409, 'Buchung wurde zwischenzeitlich geändert')
    alt = con.execute("SELECT transfer_gruppe_id, bankkonto_id, bankumsatz_id FROM buchung WHERE id = ?",
                      (buchung_id,)).fetchone()
    if not alt:
        raise HTTPException(404, "Buchung nicht gefunden")
    if alt["transfer_gruppe_id"]:
        raise HTTPException(400, "Umbuchungen sind gekoppelt - bitte loeschen "
                                 "und neu anlegen statt bearbeiten")
    b = b.model_copy(update={
        feld: alt[feld] for feld in ('bankkonto_id', 'bankumsatz_id')
        if feld not in b.model_fields_set
    })
    _pruefe_sparte_und_zeilen(con, b, bereich)
    konflikt = zuordnungskonflikt(con, buchung_id, bereich, b)
    if konflikt is not None:
        return konflikt
    zeilen_ids = [z.id for z in b.zeilen if z.id is not None]
    if len(zeilen_ids) != len(set(zeilen_ids)):
        raise HTTPException(422, 'Zeilen dürfen nicht doppelt referenziert werden')
    for zid in zeilen_ids:
        row = con.execute('SELECT buchung_id FROM buchungszeile WHERE id = ?', (zid,)).fetchone()
        if row is None:
            raise HTTPException(404, 'Buchungszeile nicht gefunden')
        pruefe_buchung(con, row['buchung_id'], bereich)
        if row['buchung_id'] != buchung_id:
            raise HTTPException(422, 'Zeile gehört nicht zu dieser Buchung')
    try:
        con.execute(
            "UPDATE buchung SET sparte_id = ?, datum = ?, typ = ?, zahlungsart = ?, "
            "kontakt_id = ?, person_id = ?, text = ?, notiz = ? WHERE id = ?",
            (b.sparte_id, b.datum, b.typ, b.zahlungsart, b.kontakt_id,
             b.person_id, b.text, b.notiz, buchung_id),
        )
        erhalten = []
        for z in b.zeilen:
            if z.id is not None:
                con.execute(
                    'UPDATE buchungszeile SET kategorie_id = ?, betrag_cent = ?, notiz = ? '
                    'WHERE id = ?', (z.kategorie_id, z.betrag_cent, z.notiz, z.id),
                )
                erhalten.append(z.id)
            else:
                zid = con.execute(
                    'INSERT INTO buchungszeile(buchung_id, kategorie_id, betrag_cent, notiz) '
                    'VALUES(?, ?, ?, ?)',
                    (buchung_id, z.kategorie_id, z.betrag_cent, z.notiz),
                ).lastrowid
                erhalten.append(zid)
        marks = ', '.join('?' for _ in erhalten)
        con.execute(
            f'DELETE FROM buchungszeile WHERE buchung_id = ? AND id NOT IN ({marks})',
            (buchung_id, *erhalten),
        )
        for feld in ('bankkonto_id', 'bankumsatz_id'):
            if feld in b.model_fields_set:
                con.execute(f'UPDATE buchung SET {feld}=? WHERE id=?', (getattr(b, feld), buchung_id))
        synchronisiere_auslage(con, buchung_id, b, bereich)
        synchronisiere_buchung(con, buchung_id, bereich)
        con.execute('UPDATE buchung SET version = version + 1 WHERE id = ?', (buchung_id,))
        if alt['bankumsatz_id'] is not None and alt['bankumsatz_id'] != b.bankumsatz_id:
            con.execute("UPDATE bankumsatz SET importstatus='offen' WHERE id=? AND NOT EXISTS (SELECT 1 FROM buchung WHERE bankumsatz_id=?)",(alt['bankumsatz_id'],alt['bankumsatz_id']))
    except sqlite3.IntegrityError as e:
        con.rollback()
        raise HTTPException(400, f"Datenbankfehler: {e}")
    except HTTPException:
        con.rollback()
        raise
    return _buchung_detail(con, buchung_id)


@router.delete("/buchungen/{buchung_id}", status_code=204)
def delete_buchung(buchung_id: int, con: sqlite3.Connection = Depends(db_dep), bereich: BereichDep = Bereich(1)):
    with con:
        con.execute('BEGIN IMMEDIATE')
        return _delete_buchung(buchung_id, con, bereich)


def _delete_buchung(buchung_id: int, con: sqlite3.Connection, bereich: Bereich):
    pruefe_buchung(con, buchung_id, bereich)
    row = con.execute(
        "SELECT bankumsatz_id, transfer_gruppe_id FROM buchung WHERE id = ?",
        (buchung_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Buchung nicht gefunden")
    konflikt = zuordnungskonflikt(con, buchung_id, bereich)
    if konflikt is not None:
        return konflikt
    # Umbuchungen sind gekoppelt: immer beide Seiten der Gruppe entfernen.
    if row["transfer_gruppe_id"]:
        betroffen = con.execute(
            "SELECT id, bankumsatz_id FROM buchung WHERE transfer_gruppe_id = ?",
            (row["transfer_gruppe_id"],)).fetchall()
    else:
        betroffen = [{"id": buchung_id, "bankumsatz_id": row["bankumsatz_id"]}]
    for b in betroffen:
        pruefe_buchung(con, b["id"], bereich)
        _pruefe_buchungsreferenzen(con, b["id"], bereich)
    if row['transfer_gruppe_id']:
        marker = 'Nachzug Umbuchung '+row['transfer_gruppe_id']
        for t in con.execute('SELECT id FROM transfer WHERE von_konto_id IS NULL AND nach_konto_id IS NULL AND notiz IN (?,?)',(marker,marker+'; Konten ungeklärt')).fetchall():
            pruefe_transfer(con,t[0],bereich)
            storniere_transfer(con,t[0])
    for b in betroffen:
        storniere_buchungsbewegungen(con, b['id'])
        con.execute("DELETE FROM buchung WHERE id = ?", (b["id"],))  # Zeilen via CASCADE
        # War die Buchung aus einem Bankumsatz uebernommen, wird dieser wieder
        # geoeffnet, damit er nicht unerledigt als "verbucht" haengen bleibt.
        if b["bankumsatz_id"] is not None:
            con.execute("UPDATE bankumsatz SET importstatus = 'offen' WHERE id = ? AND NOT EXISTS (SELECT 1 FROM buchung WHERE bankumsatz_id=?)",
                        (b["bankumsatz_id"],b["bankumsatz_id"]))


def _buchung_detail(con: sqlite3.Connection, buchung_id: int) -> dict:
    row = con.execute(
        "SELECT b.id, b.sparte_id, s.name AS sparte_name, b.datum, b.typ, "
        "b.version, b.betrag_cent, b.zahlungsart, b.belegstatus, b.buchungsstatus, b.text, b.notiz, b.kredit_id "
        "FROM buchung b JOIN sparte s ON s.id = b.sparte_id WHERE b.id = ?",
        (buchung_id,),
    ).fetchone()
    result = dict(row)
    result['zahlungsstatus'] = _zahlungsstatus(con, buchung_id)
    ergaenze_auslage(con, result)
    result["zeilen"] = [
        dict(z) for z in con.execute(
            "SELECT z.id, z.kategorie_id, k.name AS kategorie_name, z.betrag_cent, z.notiz, z.neutral "
            "FROM buchungszeile z JOIN kategorie k ON k.id = z.kategorie_id "
            "WHERE z.buchung_id = ? ORDER BY z.id",
            (buchung_id,),
        ).fetchall()
    ]
    result["neutral_cent"] = sum(z["betrag_cent"] for z in result["zeilen"] if z.get("neutral", 0))
    return result


def _zahlungsstatus(con, buchung_id):
    row = con.execute("""SELECT b.zahlungsart, EXISTS (
        SELECT 1 FROM buchung_bewegung x JOIN bewegung m ON m.id=x.bewegung_id
        WHERE x.buchung_id=b.id AND m.storniert_am IS NULL)
        FROM buchung b WHERE b.id=?""",(buchung_id,)).fetchone()
    return 'verknuepft' if row[1] else 'Zahlung unbekannt' if row[0] in ('bank','karte') else None


def _pruefe_buchungsreferenzen(con, buchung_id, bereich):
    """Auch erhaltene Verweise und gekoppelte Loeschfolgen bleiben im Bereich."""
    pruefe_bewegungsreferenzen(con,buchung_id,bereich)
    row = con.execute("SELECT bankkonto_id, bankumsatz_id FROM buchung WHERE id=?", (buchung_id,)).fetchone()
    if row["bankkonto_id"] is not None:
        pruefe_konto(con, row["bankkonto_id"], bereich)
    if row["bankumsatz_id"] is not None:
        pruefe_umsatz(con, row["bankumsatz_id"], bereich)
    for beleg in con.execute("SELECT beleg_id FROM buchung_beleg WHERE buchung_id=?", (buchung_id,)):
        pruefe_beleg(con, beleg[0], bereich)
