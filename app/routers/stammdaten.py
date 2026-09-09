"""Stammdaten: Sparten und Kategorien."""
import sqlite3

from fastapi import APIRouter, Depends

from ..db import db_dep
from ..bereiche import Bereich, BereichDep, pruefe_sparte, pruefe_kategorie
from ..schemas import KategorieIn

router = APIRouter(tags=["stammdaten"])


@router.get("/sparten")
def list_sparten(con: sqlite3.Connection = Depends(db_dep), bereich: BereichDep = Bereich(1)):
    rows = con.execute(
        "SELECT id, name, kuerzel, typ, geschuetzt, farbe "
        "FROM sparte WHERE aktiv = 1 AND bereich_id = ? ORDER BY sortierung, name", (bereich.id,)
    ).fetchall()
    return [dict(r) for r in rows]


@router.get("/kategorien")
def list_kategorien(sparte_id: int | None = None,
                    con: sqlite3.Connection = Depends(db_dep), bereich: BereichDep = Bereich(1)):
    if sparte_id is not None:
        pruefe_sparte(con, sparte_id, bereich)
    sql = ("SELECT id, sparte_id, parent_id, name, richtung, sortierung "
           "FROM kategorie WHERE aktiv = 1 AND sparte_id IN (SELECT id FROM sparte WHERE bereich_id = ?)")
    params: list = [bereich.id]
    if sparte_id is not None:
        sql += " AND sparte_id = ?"
        params.append(sparte_id)
    sql += " ORDER BY sortierung, name"
    rows = con.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


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
        "SELECT id, name, kuerzel, typ FROM bereich WHERE aktiv=1 ORDER BY sortierung, id"
    )]
