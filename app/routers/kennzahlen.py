"""CRUD und Auswertung eigener Kennzahlen."""
import sqlite3
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..bereiche import Bereich, BereichDep, pruefe_kategorie, pruefe_sparte, pruefe_kennzahl
from ..db import db_dep
from ..kennzahlen import monate_mit_daten, wert

router = APIRouter(tags=["kennzahlen"])


class TermIn(BaseModel):
    kategorie_id: int
    messgroesse: Literal["einnahmen", "ausgaben", "netto"]
    vorzeichen: Literal[1, -1]


class KennzahlIn(BaseModel):
    sparte_id: int
    name: str
    terme: list[TermIn] = Field(default_factory=list)


class KennzahlUpdateIn(BaseModel):
    name: Optional[str] = None
    terme: Optional[list[TermIn]] = None


def _pruefe_terme(con, sparte_id, terme, bereich):
    pruefe_sparte(con, sparte_id, bereich)
    gesehen = set()
    for term in terme:
        schluessel = (term.kategorie_id, term.vorzeichen)
        if schluessel in gesehen:
            raise HTTPException(422, "Eine Kategorie darf je Vorzeichen nur einmal in einer Kennzahl vorkommen")
        gesehen.add(schluessel)
        pruefe_kategorie(con, term.kategorie_id, bereich)
        row = con.execute("SELECT sparte_id FROM kategorie WHERE id=?", (term.kategorie_id,)).fetchone()
        if row["sparte_id"] != sparte_id:
            raise HTTPException(400, "Jede Kennzahlkategorie muss zur Sparte gehoeren")


def _detail(con, row, jahr=None, bereich_id=1):
    result = dict(row)
    result["terme"] = [dict(r) for r in con.execute(
        "SELECT id, kategorie_id, messgroesse, vorzeichen FROM kennzahl_term WHERE kennzahl_id=? ORDER BY id",
        (row["id"],),
    ).fetchall()]
    if jahr is not None:
        filter_ = {"sparte_id": row["sparte_id"], "bereich_id": bereich_id}
        result["wert_cent"] = wert(con, row["id"], jahr, filter_)
        monate = monate_mit_daten(con, row["id"], jahr, filter_)
        result["monatsdurchschnitt_cent"] = result["wert_cent"] // monate if monate else 0
    return result


@router.get("/kennzahlen")
def list_kennzahlen(sparte_id: int | None = None, jahr: int | None = None,
                    con: sqlite3.Connection = Depends(db_dep), bereich: BereichDep = Bereich(1)):
    if sparte_id is not None:
        pruefe_sparte(con, sparte_id, bereich)
    if jahr is None:
        raise HTTPException(400, "jahr ist erforderlich")
    rows = con.execute(
        "SELECT k.id, k.sparte_id, k.name, k.sortierung, k.aktiv FROM kennzahl k "
        "JOIN sparte s ON s.id=k.sparte_id WHERE k.aktiv=1 AND s.bereich_id=? "
        "AND (? IS NULL OR k.sparte_id=?) ORDER BY k.sortierung, k.id",
        (bereich.id, sparte_id, sparte_id),
    ).fetchall()
    return [_detail(con, row, jahr, bereich.id) for row in rows]


@router.post("/kennzahlen", status_code=201)
def create_kennzahl(body: KennzahlIn, con: sqlite3.Connection = Depends(db_dep), bereich: BereichDep = Bereich(1)):
    _pruefe_terme(con, body.sparte_id, body.terme, bereich)
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "Name darf nicht leer sein")
    cur = con.execute("INSERT INTO kennzahl(sparte_id,name) VALUES(?,?)", (body.sparte_id, name))
    for term in body.terme:
        con.execute("INSERT INTO kennzahl_term(kennzahl_id,kategorie_id,messgroesse,vorzeichen) VALUES(?,?,?,?)",
                    (cur.lastrowid, term.kategorie_id, term.messgroesse, term.vorzeichen))
    con.commit()
    return _detail(con, con.execute("SELECT * FROM kennzahl WHERE id=?", (cur.lastrowid,)).fetchone(), bereich_id=bereich.id)


@router.put("/kennzahlen/{kennzahl_id}")
def update_kennzahl(kennzahl_id: int, body: KennzahlUpdateIn,
                    con: sqlite3.Connection = Depends(db_dep), bereich: BereichDep = Bereich(1)):
    pruefe_kennzahl(con, kennzahl_id, bereich)
    row = con.execute("SELECT * FROM kennzahl WHERE id=?", (kennzahl_id,)).fetchone()
    if body.terme is not None:
        _pruefe_terme(con, row["sparte_id"], body.terme, bereich)
    if body.name is not None and not body.name.strip():
        raise HTTPException(400, "Name darf nicht leer sein")
    if body.name is not None:
        con.execute("UPDATE kennzahl SET name=? WHERE id=?", (body.name.strip(), kennzahl_id))
    if body.terme is not None:
        con.execute("DELETE FROM kennzahl_term WHERE kennzahl_id=?", (kennzahl_id,))
        con.executemany("INSERT INTO kennzahl_term(kennzahl_id,kategorie_id,messgroesse,vorzeichen) VALUES(?,?,?,?)",
                        [(kennzahl_id, t.kategorie_id, t.messgroesse, t.vorzeichen) for t in body.terme])
    con.commit()
    return _detail(con, con.execute("SELECT * FROM kennzahl WHERE id=?", (kennzahl_id,)).fetchone(), bereich_id=bereich.id)


@router.delete("/kennzahlen/{kennzahl_id}", status_code=204)
def delete_kennzahl(kennzahl_id: int, con: sqlite3.Connection = Depends(db_dep), bereich: BereichDep = Bereich(1)):
    pruefe_kennzahl(con, kennzahl_id, bereich)
    con.execute("DELETE FROM kennzahl WHERE id=?", (kennzahl_id,))
    con.commit()
