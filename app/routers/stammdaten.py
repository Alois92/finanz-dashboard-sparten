"""Stammdaten: Sparten und Kategorien."""
import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from ..db import db_dep
from ..schemas import KategorieIn

router = APIRouter(tags=["stammdaten"])


@router.get("/sparten")
def list_sparten(con: sqlite3.Connection = Depends(db_dep)):
    rows = con.execute(
        "SELECT id, name, kuerzel, typ, geschuetzt, farbe "
        "FROM sparte WHERE aktiv = 1 ORDER BY sortierung, name"
    ).fetchall()
    return [dict(r) for r in rows]


@router.get("/kategorien")
def list_kategorien(sparte_id: int | None = None,
                    con: sqlite3.Connection = Depends(db_dep)):
    sql = ("SELECT id, sparte_id, parent_id, name, richtung, sortierung "
           "FROM kategorie WHERE aktiv = 1")
    params: list = []
    if sparte_id is not None:
        sql += " AND sparte_id = ?"
        params.append(sparte_id)
    sql += " ORDER BY sortierung, name"
    rows = con.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


@router.post("/kategorien", status_code=201)
def create_kategorie(k: KategorieIn, con: sqlite3.Connection = Depends(db_dep)):
    if not con.execute("SELECT 1 FROM sparte WHERE id = ?", (k.sparte_id,)).fetchone():
        raise HTTPException(404, "Sparte nicht gefunden")
    if k.parent_id is not None and not con.execute(
            "SELECT 1 FROM kategorie WHERE id = ?", (k.parent_id,)).fetchone():
        raise HTTPException(404, "Ueberkategorie (parent) nicht gefunden")
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
