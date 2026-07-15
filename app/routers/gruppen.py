"""Globale Kategoriegruppen: CRUD und Kategorie-Zuordnungen."""
import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from ..db import db_dep
from ..schemas import AuswertungsgruppeIn, GruppeIn

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


def _auswertungsgruppe(con: sqlite3.Connection, gruppe_id: int) -> dict:
    row = con.execute(
        "SELECT id, name, beschreibung FROM auswertungsgruppe WHERE id = ?",
        (gruppe_id,),
    ).fetchone()
    if not row:
        raise HTTPException(404, "Auswertungsgruppe nicht gefunden")
    result = dict(row)
    result["sparte_ids"] = [r["sparte_id"] for r in con.execute(
        "SELECT sparte_id FROM auswertungsgruppe_sparte "
        "WHERE auswertungsgruppe_id = ? ORDER BY sparte_id", (gruppe_id,)).fetchall()]
    return result


def _auswertungswerte(
    gruppe: AuswertungsgruppeIn, con: sqlite3.Connection,
) -> tuple[str, str | None, list[int]]:
    name = gruppe.name.strip()
    if not name:
        raise HTTPException(400, "Name darf nicht leer sein")
    beschreibung = gruppe.beschreibung.strip() if gruppe.beschreibung else None
    sparte_ids = sorted(set(gruppe.sparte_ids))
    if sparte_ids:
        marks = ",".join("?" for _ in sparte_ids)
        vorhanden = {r["id"] for r in con.execute(
            f"SELECT id FROM sparte WHERE aktiv = 1 AND id IN ({marks})",
            sparte_ids,
        ).fetchall()}
        fehlend = [sparte_id for sparte_id in sparte_ids if sparte_id not in vorhanden]
        if fehlend:
            raise HTTPException(404, f"Sparte {fehlend[0]} nicht gefunden")
    return name, beschreibung or None, sparte_ids


def _speichere_auswertungssparten(
    con: sqlite3.Connection, gruppe_id: int, sparte_ids: list[int],
) -> None:
    con.execute(
        "DELETE FROM auswertungsgruppe_sparte WHERE auswertungsgruppe_id = ?",
        (gruppe_id,),
    )
    con.executemany(
        "INSERT INTO auswertungsgruppe_sparte(auswertungsgruppe_id, sparte_id) "
        "VALUES(?, ?)",
        [(gruppe_id, sparte_id) for sparte_id in sparte_ids],
    )


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


@router.get("/auswertungsgruppen")
def list_auswertungsgruppen(con: sqlite3.Connection = Depends(db_dep)):
    ids = [r["id"] for r in con.execute(
        "SELECT id FROM auswertungsgruppe WHERE aktiv = 1 ORDER BY name, id"
    ).fetchall()]
    return [_auswertungsgruppe(con, gruppe_id) for gruppe_id in ids]


@router.post("/auswertungsgruppen", status_code=201)
def create_auswertungsgruppe(
    gruppe: AuswertungsgruppeIn, con: sqlite3.Connection = Depends(db_dep),
):
    name, beschreibung, sparte_ids = _auswertungswerte(gruppe, con)
    try:
        cur = con.execute(
            "INSERT INTO auswertungsgruppe(name, beschreibung) VALUES(?, ?)",
            (name, beschreibung),
        )
        _speichere_auswertungssparten(con, cur.lastrowid, sparte_ids)
        con.commit()
    except sqlite3.IntegrityError as error:
        con.rollback()
        raise HTTPException(400, f"Datenbankfehler: {error}") from error
    return _auswertungsgruppe(con, cur.lastrowid)


@router.put("/auswertungsgruppen/{gruppe_id}")
def update_auswertungsgruppe(
    gruppe_id: int, gruppe: AuswertungsgruppeIn,
    con: sqlite3.Connection = Depends(db_dep),
):
    _auswertungsgruppe(con, gruppe_id)
    name, beschreibung, sparte_ids = _auswertungswerte(gruppe, con)
    try:
        con.execute(
            "UPDATE auswertungsgruppe SET name = ?, beschreibung = ? WHERE id = ?",
            (name, beschreibung, gruppe_id),
        )
        _speichere_auswertungssparten(con, gruppe_id, sparte_ids)
        con.commit()
    except sqlite3.IntegrityError as error:
        con.rollback()
        raise HTTPException(400, f"Datenbankfehler: {error}") from error
    return _auswertungsgruppe(con, gruppe_id)


@router.delete("/auswertungsgruppen/{gruppe_id}", status_code=204)
def delete_auswertungsgruppe(
    gruppe_id: int, con: sqlite3.Connection = Depends(db_dep),
):
    _auswertungsgruppe(con, gruppe_id)
    con.execute("DELETE FROM auswertungsgruppe WHERE id = ?", (gruppe_id,))
    con.commit()
