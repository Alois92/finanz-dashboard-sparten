"""Konten, Bewegungen und Transfers im ausgewählten Bereich."""
from datetime import date
import sqlite3
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from ..db import db_dep
from ..bereiche import Bereich, BereichDep, pruefe_konto, pruefe_sparte
from ..bewegungen import erzeuge_transfer, storniere_transfer, pruefe_transfer
from ..konten import kontostand as berechne_kontostand
from ..bereiche import pruefe_beleg, pruefe_buchung, pruefe_kategorie

router = APIRouter(tags=['konten'])
KontoArt = Literal['bank','karte','kassa','depot','wallet']
TransferArt = Literal['bankomat','umbuchung','ausgleich','kartenabrechnung','sonstig']
FELDER = 'id,name,art,waehrung,sparte_id,iban,bank,kartenendnummer,aktiv,sortierung'


class KontoIn(BaseModel):
    name: str = Field(min_length=1)
    art: KontoArt = 'bank'
    waehrung: str = Field(default='EUR', pattern=r'^[A-Z]{3}$')
    sparte_id: int | None = None
    iban: str | None = None
    bank: str | None = None
    kartenendnummer: str | None = None

    @field_validator('name')
    @classmethod
    def name_nicht_leer(cls, value):
        if not value.strip():
            raise ValueError('Name darf nicht leer sein')
        return value.strip()


class KontoPatch(BaseModel):
    name: str | None = None
    art: KontoArt | None = None
    waehrung: str | None = None
    sparte_id: int | None = None
    iban: str | None = None
    bank: str | None = None
    kartenendnummer: str | None = None
    aktiv: Literal[0,1] | None = None
    sortierung: int | None = None


class BewegungIn(BaseModel):
    konto_id: int
    datum: date
    betrag_signed_cent: int = Field(strict=True)
    text: str | None = None
    gegenpartei: str | None = None
    art: Literal['zahlung','transfer','gebuehr','zins','trade'] = 'zahlung'


class TransferIn(BaseModel):
    art: TransferArt
    von_konto_id: int
    nach_konto_id: int
    datum: date
    betrag_cent: int = Field(gt=0, strict=True)
    notiz: str | None = None


class AnkerIn(BaseModel):
    stichtag: date
    saldo_cent: int = Field(strict=True)
    quelle: Literal['auszug', 'manuell', 'import']
    beleg_id: int | None = None
    notiz: str | None = None


class ZaehlungIn(BaseModel):
    datum: date
    gezaehlt_cent: int = Field(strict=True)
    notiz: str | None = None


class ZaehlungBuchenIn(BaseModel):
    kategorie_id: int
    text: str | None = None


def _pruefe_kassa(con, daten, bereich, kid=None):
    if daten['sparte_id'] is not None:
        pruefe_sparte(con,daten['sparte_id'],bereich)
    if daten['art']=='kassa':
        if daten['sparte_id'] is None:
            raise HTTPException(422,'Kassa benötigt sparte_id')
        if con.execute("SELECT 1 FROM bankkonto WHERE art='kassa' AND sparte_id=? AND id<>?",(daten['sparte_id'],kid or -1)).fetchone():
            raise HTTPException(409,'Je Sparte ist nur eine Kassa erlaubt')


@router.get('/konten')
@router.get('/bankkonten')
def list_konten(con=Depends(db_dep), bereich: BereichDep = Bereich(1)):
    rows = [dict(r) for r in con.execute(f'SELECT {FELDER} FROM bankkonto WHERE bereich_id=? ORDER BY sortierung,name,id',(bereich.id,))]
    for row in rows:
        stand = berechne_kontostand(con, row['id'], date.today().isoformat())
        row.update({feld: stand[feld] for feld in ('stand_cent', 'datenstand', 'letzter_import')})
    return rows


@router.post('/konten',status_code=201)
@router.post('/bankkonten',status_code=201)
def create_konto(k: KontoIn, con=Depends(db_dep), bereich: BereichDep = Bereich(1)):
    daten = k.model_dump()
    _pruefe_kassa(con,daten,bereich)
    with con:
        kid = con.execute(f"INSERT INTO bankkonto({','.join(daten)},bereich_id) VALUES({','.join('?' for _ in daten)},?)",(*daten.values(),bereich.id)).lastrowid
    return dict(con.execute(f'SELECT {FELDER} FROM bankkonto WHERE id=?',(kid,)).fetchone())


@router.patch('/konten/{konto_id}')
def patch_konto(konto_id: int, k: KontoPatch, con=Depends(db_dep), bereich: BereichDep = Bereich(1)):
    pruefe_konto(con,konto_id,bereich)
    alt = dict(con.execute('SELECT * FROM bankkonto WHERE id=?',(konto_id,)).fetchone())
    daten = k.model_dump(exclude_unset=True)
    neu = {**alt,**daten}
    if any(neu[f] is None for f in ('name','art','waehrung','aktiv','sortierung')):
        raise HTTPException(422,'Pflichtfeld darf nicht null sein')
    try:
        validiert = KontoIn.model_validate(neu)
    except ValueError:
        raise HTTPException(422,'Ungültige Kontodaten') from None
    if 'name' in daten:
        daten['name'] = validiert.name
    _pruefe_kassa(con,neu,bereich,konto_id)
    if any(neu[f]!=alt[f] for f in ('art','waehrung','sparte_id')) and con.execute('SELECT 1 FROM bewegung WHERE konto_id=?',(konto_id,)).fetchone():
        raise HTTPException(409,'Konto mit Bewegungen darf Art, Währung und Sparte nicht wechseln')
    if daten:
        with con:
            con.execute(f"UPDATE bankkonto SET {','.join(f'{f}=?' for f in daten)} WHERE id=?",(*daten.values(),konto_id))
    return dict(con.execute(f'SELECT {FELDER} FROM bankkonto WHERE id=?',(konto_id,)).fetchone())


@router.get('/konten/{konto_id}/bewegungen')
def list_bewegungen(konto_id: int, von: date | None = None, bis: date | None = None,
                    limit: int = Query(100,ge=1,le=1000), cursor: str | None = None,
                    con=Depends(db_dep), bereich: BereichDep = Bereich(1)):
    pruefe_konto(con,konto_id,bereich)
    sql, params = 'SELECT * FROM bewegung WHERE konto_id=?', [konto_id]
    for wert, op in ((von,'>='),(bis,'<=')):
        if wert:
            sql += f' AND datum {op} ?'
            params.append(wert.isoformat())
    if cursor:
        try:
            datum, kennung = cursor.split('_')
            datum = date.fromisoformat(datum).isoformat()
            kennung = int(kennung)
        except ValueError:
            raise HTTPException(422,'Ungültiger Cursor') from None
        sql += ' AND (datum<? OR (datum=? AND id<?))'
        params.extend((datum,datum,kennung))
    rows = [dict(r) for r in con.execute(sql+' ORDER BY datum DESC,id DESC LIMIT ?',(*params,limit+1))]
    mehr = len(rows)>limit
    rows = rows[:limit]
    return {'bewegungen':rows,'naechster_cursor':f"{rows[-1]['datum']}_{rows[-1]['id']}" if mehr else None}


@router.get('/konten/{konto_id}/stand')
def stand_konto(konto_id: int, stichtag: date | None = None,
                con=Depends(db_dep), bereich: BereichDep = Bereich(1)):
    pruefe_konto(con,konto_id,bereich)
    return berechne_kontostand(con, konto_id, (stichtag or date.today()).isoformat())


@router.post('/konten/{konto_id}/anker', status_code=201)
def create_anker(konto_id: int, a: AnkerIn, con=Depends(db_dep), bereich: BereichDep = Bereich(1)):
    pruefe_konto(con, konto_id, bereich)
    if a.beleg_id is not None:
        pruefe_beleg(con, a.beleg_id, bereich)
    vorher = con.execute(
        "SELECT stichtag, saldo_cent FROM kontostand_anker WHERE konto_id=? "
        "AND stichtag<? ORDER BY stichtag DESC, id DESC LIMIT 1",
        (konto_id, a.stichtag.isoformat()),
    ).fetchone()
    antwort = {"stichtag": a.stichtag.isoformat(), "saldo_cent": a.saldo_cent,
               "quelle": a.quelle}
    if vorher:
        gerechnet = vorher['saldo_cent'] + con.execute(
            "SELECT COALESCE(SUM(betrag_signed_cent),0) FROM bewegung "
            "WHERE konto_id=? AND datum>? AND datum<=? AND storniert_am IS NULL",
            (konto_id, vorher['stichtag'], a.stichtag.isoformat()),
        ).fetchone()[0]
        antwort.update({"gerechnet_cent": gerechnet,
                        "differenz_cent": a.saldo_cent - gerechnet})
    try:
        cur = con.execute(
            "INSERT INTO kontostand_anker(konto_id,stichtag,saldo_cent,quelle,beleg_id,notiz) "
            "VALUES(?,?,?,?,?,?)",
            (konto_id, a.stichtag.isoformat(), a.saldo_cent, a.quelle, a.beleg_id, a.notiz),
        )
        con.commit()
    except sqlite3.IntegrityError as exc:
        con.rollback()
        raise HTTPException(409, 'Anker für diesen Stichtag existiert bereits') from exc
    return {"id": cur.lastrowid, "konto_id": konto_id, **antwort,
            "beleg_id": a.beleg_id, "notiz": a.notiz}


@router.get('/konten/{konto_id}/anker')
def list_anker(konto_id: int, con=Depends(db_dep), bereich: BereichDep = Bereich(1)):
    pruefe_konto(con, konto_id, bereich)
    return [dict(row) for row in con.execute(
        'SELECT * FROM kontostand_anker WHERE konto_id=? ORDER BY stichtag, id', (konto_id,)
    )]


@router.delete('/konten/{konto_id}/anker/{anker_id}', status_code=204)
def delete_anker(konto_id: int, anker_id: int, con=Depends(db_dep), bereich: BereichDep = Bereich(1)):
    pruefe_konto(con, konto_id, bereich)
    cur = con.execute('DELETE FROM kontostand_anker WHERE id=? AND konto_id=?', (anker_id, konto_id))
    if cur.rowcount == 0:
        raise HTTPException(404, 'Anker nicht gefunden')
    con.commit()


@router.post('/konten/{konto_id}/zaehlung', status_code=201)
def create_zaehlung(konto_id: int, z: ZaehlungIn, con=Depends(db_dep), bereich: BereichDep = Bereich(1)):
    pruefe_konto(con, konto_id, bereich)
    konto = con.execute('SELECT art FROM bankkonto WHERE id=?', (konto_id,)).fetchone()
    if konto['art'] != 'kassa':
        raise HTTPException(422, 'Kassazählungen sind nur für Kassenkonten zulässig')
    gerechnet = berechne_kontostand(con, konto_id, z.datum.isoformat())['stand_cent']
    if gerechnet is None:
        raise HTTPException(422, 'Kassenstand ist ohne Anker unbekannt')
    differenz = z.gezaehlt_cent - gerechnet
    cur = con.execute(
        "INSERT INTO kassazaehlung(konto_id,datum,gerechnet_cent,gezaehlt_cent,differenz_cent,notiz) "
        "VALUES(?,?,?,?,?,?)",
        (konto_id, z.datum.isoformat(), gerechnet, z.gezaehlt_cent, differenz, z.notiz),
    )
    con.commit()
    return {"id": cur.lastrowid, "konto_id": konto_id, "datum": z.datum.isoformat(),
            "gerechnet_cent": gerechnet, "gezaehlt_cent": z.gezaehlt_cent,
            "differenz_cent": differenz, "status": "offen", "notiz": z.notiz}


@router.post('/konten/{konto_id}/zaehlung/{zaehlung_id}/buchen', status_code=201)
def buchen_zaehlung(konto_id: int, zaehlung_id: int, body: ZaehlungBuchenIn,
                    con=Depends(db_dep), bereich: BereichDep = Bereich(1)):
    pruefe_konto(con, konto_id, bereich)
    zaehlung = con.execute(
        'SELECT * FROM kassazaehlung WHERE id=? AND konto_id=?', (zaehlung_id, konto_id)
    ).fetchone()
    if not zaehlung:
        raise HTTPException(404, 'Kassazählung nicht gefunden')
    if zaehlung['status'] != 'offen':
        raise HTTPException(409, 'Kassazählung ist bereits geklärt')
    if zaehlung['differenz_cent'] == 0:
        raise HTTPException(422, 'Kassazählung hat keine Differenz')
    kassa = con.execute('SELECT sparte_id FROM bankkonto WHERE id=?', (konto_id,)).fetchone()
    pruefe_kategorie(con, body.kategorie_id, bereich)
    kategorie = con.execute(
        'SELECT sparte_id, richtung FROM kategorie WHERE id=? AND aktiv=1', (body.kategorie_id,)
    ).fetchone()
    if not kategorie or kategorie['sparte_id'] != kassa['sparte_id'] or kategorie['richtung'] not in ('beides', 'ausgabe' if zaehlung['differenz_cent'] < 0 else 'einnahme'):
        raise HTTPException(422, 'Kategorie passt nicht zur Kassadifferenz')
    con.execute(
        "INSERT INTO kategorie(sparte_id,name,richtung) "
        "SELECT ?, 'Kassadifferenz', 'beides' WHERE NOT EXISTS "
        "(SELECT 1 FROM kategorie WHERE sparte_id=? AND lower(name)='kassadifferenz')",
        (kassa['sparte_id'], kassa['sparte_id']),
    )
    typ = 'einnahme' if zaehlung['differenz_cent'] > 0 else 'ausgabe'
    betrag = abs(zaehlung['differenz_cent'])
    cur = con.execute(
        "INSERT INTO buchung(sparte_id,datum,typ,betrag_cent,zahlungsart,bankkonto_id,"
        "buchungsstatus,text) VALUES(?,?,?,?,'bar',?,'zugeordnet',?)",
        (kassa['sparte_id'], zaehlung['datum'], typ, betrag, konto_id,
         body.text or 'Kassadifferenz'),
    )
    buchung_id = cur.lastrowid
    con.execute('INSERT INTO buchungszeile(buchung_id,kategorie_id,betrag_cent) VALUES(?,?,?)',
                (buchung_id, body.kategorie_id, betrag))
    con.execute(
        "INSERT INTO bewegung(konto_id,datum,betrag_signed_cent,waehrung,text,quelle) "
        "SELECT id,?,?,waehrung,?,'manuell' FROM bankkonto WHERE id=?",
        (zaehlung['datum'], zaehlung['differenz_cent'], body.text or 'Kassadifferenz', konto_id),
    )
    bewegung_id = con.execute('SELECT last_insert_rowid()').fetchone()[0]
    con.execute('INSERT INTO buchung_bewegung VALUES(?,?,?)',
                (buchung_id, bewegung_id, zaehlung['differenz_cent']))
    con.execute("UPDATE kassazaehlung SET status='geklaert', buchung_id=? WHERE id=?",
                (buchung_id, zaehlung_id))
    con.commit()
    return {"id": zaehlung_id, "buchung_id": buchung_id,
            "gerechnet_cent": zaehlung['gerechnet_cent'],
            "gezaehlt_cent": zaehlung['gezaehlt_cent'],
            "differenz_cent": zaehlung['differenz_cent'], "status": "geklaert"}


@router.get('/kassazaehlungen')
def list_zaehlungen(status: str | None = None, con=Depends(db_dep), bereich: BereichDep = Bereich(1)):
    if status not in (None, 'offen', 'geklaert'):
        raise HTTPException(422, 'Ungültiger Zählstatus')
    sql = "SELECT z.* FROM kassazaehlung z JOIN bankkonto k ON k.id=z.konto_id WHERE k.bereich_id=?"
    params = [bereich.id]
    if status:
        sql += ' AND z.status=?'
        params.append(status)
    sql += ' ORDER BY z.datum DESC, z.id DESC'
    return [dict(row) for row in con.execute(sql, params)]


@router.post('/bewegungen',status_code=201)
def create_bewegung(b: BewegungIn, con=Depends(db_dep), bereich: BereichDep = Bereich(1)):
    pruefe_konto(con,b.konto_id,bereich)
    if b.art=='transfer':
        raise HTTPException(422,'Transfers über /api/transfers anlegen')
    with con:
        mid = con.execute("INSERT INTO bewegung(konto_id,datum,betrag_signed_cent,text,gegenpartei,art,quelle,waehrung) SELECT id,?,?,?,?,?,'manuell',waehrung FROM bankkonto WHERE id=?",(b.datum.isoformat(),b.betrag_signed_cent,b.text,b.gegenpartei,b.art,b.konto_id)).lastrowid
    return dict(con.execute('SELECT * FROM bewegung WHERE id=?',(mid,)).fetchone())


@router.post('/transfers',status_code=201)
def create_transfer(t: TransferIn, con=Depends(db_dep), bereich: BereichDep = Bereich(1)):
    for kid in (t.von_konto_id,t.nach_konto_id):
        pruefe_konto(con,kid,bereich)
    if t.von_konto_id==t.nach_konto_id:
        raise HTTPException(422,'Transfer benötigt zwei verschiedene Konten')
    if len({r[0] for r in con.execute('SELECT waehrung FROM bankkonto WHERE id IN (?,?)',(t.von_konto_id,t.nach_konto_id))})!=1:
        raise HTTPException(422,'Transfer benötigt dieselbe Währung')
    with con:
        tid, _ = erzeuge_transfer(con,t.art,t.von_konto_id,t.nach_konto_id,t.datum.isoformat(),t.betrag_cent,t.notiz)
    return dict(con.execute('SELECT * FROM transfer WHERE id=?',(tid,)).fetchone())


@router.delete('/transfers/{transfer_id}',status_code=204)
def delete_transfer(transfer_id: int, con=Depends(db_dep), bereich: BereichDep = Bereich(1)):
    pruefe_transfer(con,transfer_id,bereich)
    with con:
        storniere_transfer(con,transfer_id)
