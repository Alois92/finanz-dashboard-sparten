"""Stammdaten: Sparten und Kategorien."""
import sqlite3
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..db import db_dep
from ..bereiche import Bereich, BereichDep, pruefe_sparte, pruefe_kategorie
from ..schemas import KategorieIn

router = APIRouter(tags=["stammdaten"])


class KategoriePatchIn(BaseModel):
    name: Optional[str] = None
    aktiv: Optional[int] = Field(default=None, ge=0, le=1)
    richtung: Optional[str] = None
    sortierung: Optional[int] = None


@router.get("/sparten")
def list_sparten(con: sqlite3.Connection = Depends(db_dep), bereich: BereichDep = Bereich(1)):
    rows = con.execute(
        "SELECT id, name, kuerzel, typ, geschuetzt, farbe "
        "FROM sparte WHERE aktiv = 1 AND bereich_id = ? ORDER BY sortierung, name", (bereich.id,)
    ).fetchall()
    return [dict(r) for r in rows]


@router.get("/kategorien")
def list_kategorien(sparte_id: int | None = None,
                    nur_aktive: bool = False,
                    con: sqlite3.Connection = Depends(db_dep), bereich: BereichDep = Bereich(1)):
    if sparte_id is not None:
        pruefe_sparte(con, sparte_id, bereich)
    sql = ("SELECT id, sparte_id, parent_id, name, richtung, sortierung, aktiv "
           "FROM kategorie WHERE sparte_id IN (SELECT id FROM sparte WHERE bereich_id = ?)")
    params: list = [bereich.id]
    if nur_aktive:
        sql += " AND aktiv = 1"
    if sparte_id is not None:
        sql += " AND sparte_id = ?"
        params.append(sparte_id)
    sql += " ORDER BY sortierung, name"
    rows = con.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


@router.patch("/kategorien/{kategorie_id}")
def patch_kategorie(kategorie_id: int, body: KategoriePatchIn | dict,
                    con: sqlite3.Connection = Depends(db_dep), bereich: BereichDep = Bereich(1)):
    pruefe_kategorie(con, kategorie_id, bereich)
    daten = body if isinstance(body, dict) else body.model_dump(exclude_unset=True)
    erlaubte = {"name", "aktiv", "richtung", "sortierung"}
    if set(daten) - erlaubte:
        raise HTTPException(422, "Unbekanntes Kategorienfeld")
    if "name" in daten:
        daten["name"] = str(daten["name"]).strip()
        if not daten["name"]:
            raise HTTPException(400, "Name darf nicht leer sein")
    if "aktiv" in daten and daten["aktiv"] not in (0, 1, False, True):
        raise HTTPException(422, "aktiv muss 0 oder 1 sein")
    if "richtung" in daten and daten["richtung"] not in ("einnahme", "ausgabe", "beides"):
        raise HTTPException(422, "ungueltige Richtung")
    if not daten:
        raise HTTPException(400, "Keine Aenderung angegeben")
    felder = ", ".join(f"{name} = ?" for name in daten)
    con.execute(f"UPDATE kategorie SET {felder} WHERE id = ?", (*daten.values(), kategorie_id))
    con.commit()
    return dict(con.execute(
        "SELECT id, sparte_id, parent_id, name, richtung, sortierung, aktiv FROM kategorie WHERE id=?",
        (kategorie_id,),
    ).fetchone())


@router.post("/kategorien", status_code=201)
def create_kategorie(k: KategorieIn, con: sqlite3.Connection = Depends(db_dep), bereich: BereichDep = Bereich(1)):
    pruefe_sparte(con, k.sparte_id, bereich)
    if k.parent_id is not None:
        pruefe_kategorie(con, k.parent_id, bereich)
    cur = con.execute(
        "INSERT INTO kategorie(sparte_id, parent_id, name, richtung) VALUES(?,?,?,?)",
        (k.sparte_id, k.parent_id, k.name.strip(), k.richtung),
    )
    con.commit()
    row = con.execute(
        "SELECT id, sparte_id, parent_id, name, richtung FROM kategorie WHERE id = ?",
        (cur.lastrowid,),
    ).fetchone()
    return dict(row)


@router.get("/bereiche")
def list_bereiche(con: sqlite3.Connection = Depends(db_dep), bereich: BereichDep = Bereich(1)):
    return [dict(row) for row in con.execute(
        "SELECT id, name, kuerzel, typ, aktiv, sortierung FROM bereich WHERE aktiv=1 ORDER BY sortierung, id"
    )]
