"""Globale Kategoriegruppen: CRUD und Kategorie-Zuordnungen."""
import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from ..db import db_dep
from ..schemas import GruppeIn

router = APIRouter(tags=["gruppen"])


def _gruppe(con: sqlite3.Connection, gruppe_id: int) -> dict:
    row = con.execute(
        "SELECT id, name, beschreibung FROM globale_kategoriegruppe WHERE id = ?",
        (gruppe_id,),
    ).fetchone()
    if not row:
        raise HTTPException(404, "Gruppe nicht gefunden")
    result = dict(row)
    result["kategorie_ids"] = [r["kategorie_id"] for r in con.execute(
        "SELECT kategorie_id FROM kategorie_globalgruppe "
        "WHERE globalgruppe_id = ? ORDER BY kategorie_id", (gruppe_id,)).fetchall()]
    return result


def _werte(gruppe: GruppeIn) -> tuple[str, str | None]:
    name = gruppe.name.strip()
    if not name:
        raise HTTPException(400, "Name darf nicht leer sein")
    beschreibung = gruppe.beschreibung.strip() if gruppe.beschreibung else None
    return name, beschreibung or None


@router.get("/globalgruppen")
def list_globalgruppen(con: sqlite3.Connection = Depends(db_dep)):
    ids = [r["id"] for r in con.execute(
        "SELECT id FROM globale_kategoriegruppe WHERE aktiv = 1 ORDER BY name, id"
    ).fetchall()]
    return [_gruppe(con, gruppe_id) for gruppe_id in ids]


@router.post("/globalgruppen", status_code=201)
def create_globalgruppe(gruppe: GruppeIn, con: sqlite3.Connection = Depends(db_dep)):
    name, beschreibung = _werte(gruppe)
    cur = con.execute(
        "INSERT INTO globale_kategoriegruppe(name, beschreibung) VALUES(?, ?)",
        (name, beschreibung),
    )
    con.commit()
    return _gruppe(con, cur.lastrowid)


@router.put("/globalgruppen/{gruppe_id}")
def update_globalgruppe(gruppe_id: int, gruppe: GruppeIn,
                        con: sqlite3.Connection = Depends(db_dep)):
    _gruppe(con, gruppe_id)
    name, beschreibung = _werte(gruppe)
    kategorie_ids = sorted(set(gruppe.kategorie_ids))
    if kategorie_ids:
        marks = ",".join("?" for _ in kategorie_ids)
        vorhanden = {r["id"] for r in con.execute(
            f"SELECT id FROM kategorie WHERE aktiv = 1 AND id IN ({marks})",
            kategorie_ids,
        ).fetchall()}
        fehlend = [kategorie_id for kategorie_id in kategorie_ids
                   if kategorie_id not in vorhanden]
        if fehlend:
            raise HTTPException(404, f"Kategorie {fehlend[0]} nicht gefunden")
    try:
        con.execute(
            "UPDATE globale_kategoriegruppe SET name = ?, beschreibung = ? WHERE id = ?",
            (name, beschreibung, gruppe_id),
        )
        con.execute("DELETE FROM kategorie_globalgruppe WHERE globalgruppe_id = ?",
                    (gruppe_id,))
        con.executemany(
            "INSERT INTO kategorie_globalgruppe(kategorie_id, globalgruppe_id) VALUES(?, ?)",
            [(kategorie_id, gruppe_id) for kategorie_id in kategorie_ids],
        )
        con.commit()
    except sqlite3.IntegrityError as error:
        con.rollback()
        raise HTTPException(400, f"Datenbankfehler: {error}") from error
    return _gruppe(con, gruppe_id)


@router.delete("/globalgruppen/{gruppe_id}", status_code=204)
def delete_globalgruppe(gruppe_id: int, con: sqlite3.Connection = Depends(db_dep)):
    _gruppe(con, gruppe_id)
    con.execute("DELETE FROM globale_kategoriegruppe WHERE id = ?", (gruppe_id,))
    con.commit()
