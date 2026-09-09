"""Konten, Bewegungen und Transfers im ausgewählten Bereich."""
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from ..db import db_dep
from ..bereiche import Bereich, BereichDep, pruefe_konto, pruefe_sparte
from ..bewegungen import erzeuge_transfer, storniere_transfer, pruefe_transfer

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
    return [dict(r) for r in con.execute(f'SELECT {FELDER} FROM bankkonto WHERE bereich_id=? ORDER BY sortierung,name,id',(bereich.id,))]


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
def kontostand(konto_id: int, con=Depends(db_dep), bereich: BereichDep = Bereich(1)):
    pruefe_konto(con,konto_id,bereich)
    return {'konto_id':konto_id,'saldo_cent':con.execute('SELECT COALESCE(SUM(betrag_signed_cent),0) FROM bewegung WHERE konto_id=? AND storniert_am IS NULL',(konto_id,)).fetchone()[0]}


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
