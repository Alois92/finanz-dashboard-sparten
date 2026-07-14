"""Buchungen: erfassen (Kopf + Zeilen), auflisten, bearbeiten, loeschen."""
import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from ..db import db_dep
from ..schemas import BuchungIn

router = APIRouter(tags=["buchungen"])


def _pruefe_sparte_und_zeilen(con: sqlite3.Connection, b: BuchungIn) -> None:
    if not con.execute("SELECT 1 FROM sparte WHERE id = ?", (b.sparte_id,)).fetchone():
        raise HTTPException(404, "Sparte nicht gefunden")
    for z in b.zeilen:
        krow = con.execute(
            "SELECT sparte_id FROM kategorie WHERE id = ? AND aktiv = 1",
            (z.kategorie_id,),
        ).fetchone()
        if not krow:
            raise HTTPException(404, f"Kategorie {z.kategorie_id} nicht gefunden")
        if krow["sparte_id"] != b.sparte_id:
            raise HTTPException(400, "Kategorie gehoert nicht zur gewaehlten Sparte")


@router.post("/buchungen", status_code=201)
def create_buchung(b: BuchungIn, con: sqlite3.Connection = Depends(db_dep)):
    _pruefe_sparte_und_zeilen(con, b)

    try:
        cur = con.execute(
            "INSERT INTO buchung(sparte_id, datum, typ, zahlungsart, kontakt_id, "
            "person_id, bankkonto_id, text, notiz) VALUES(?,?,?,?,?,?,?,?,?)",
            (b.sparte_id, b.datum, b.typ, b.zahlungsart, b.kontakt_id,
             b.person_id, b.bankkonto_id, b.text, b.notiz),
        )
        buchung_id = cur.lastrowid
        for z in b.zeilen:
            con.execute(
                "INSERT INTO buchungszeile(buchung_id, kategorie_id, betrag_cent, notiz) "
                "VALUES(?,?,?,?)",
                (buchung_id, z.kategorie_id, z.betrag_cent, z.notiz),
            )
        con.commit()
    except sqlite3.IntegrityError as e:
        con.rollback()
        raise HTTPException(400, f"Datenbankfehler: {e}")

    return _buchung_detail(con, buchung_id)


@router.get("/buchungen")
def list_buchungen(sparte_id: int | None = None,
                   von: str | None = None,
                   bis: str | None = None,
                   typ: str | None = None,
                   con: sqlite3.Connection = Depends(db_dep)):
    sql = ("SELECT b.id, b.sparte_id, s.name AS sparte_name, b.datum, b.typ, "
           "b.betrag_cent, b.zahlungsart, b.belegstatus, b.buchungsstatus, "
           "b.text, b.notiz "
           "FROM buchung b JOIN sparte s ON s.id = b.sparte_id WHERE 1=1")
    params: list = []
    if sparte_id is not None:
        sql += " AND b.sparte_id = ?"; params.append(sparte_id)
    if von:
        sql += " AND b.datum >= ?"; params.append(von)
    if bis:
        sql += " AND b.datum <= ?"; params.append(bis)
    if typ:
        sql += " AND b.typ = ?"; params.append(typ)
    sql += " ORDER BY b.datum DESC, b.id DESC"
    buchungen = [dict(r) for r in con.execute(sql, params).fetchall()]

    if buchungen:
        ids = [b["id"] for b in buchungen]
        marks = ",".join("?" * len(ids))
        zeilen = con.execute(
            f"SELECT z.buchung_id, z.id, z.kategorie_id, k.name AS kategorie_name, "
            f"z.betrag_cent, z.notiz "
            f"FROM buchungszeile z JOIN kategorie k ON k.id = z.kategorie_id "
            f"WHERE z.buchung_id IN ({marks}) ORDER BY z.id",
            ids,
        ).fetchall()
        by_buchung: dict[int, list] = {}
        for z in zeilen:
            by_buchung.setdefault(z["buchung_id"], []).append(dict(z))
        for b in buchungen:
            b["zeilen"] = by_buchung.get(b["id"], [])
    return buchungen


@router.put("/buchungen/{buchung_id}")
def update_buchung(buchung_id: int, b: BuchungIn,
                   con: sqlite3.Connection = Depends(db_dep)):
    """Buchung ueberschreiben: Kopf-Felder aktualisieren, Zeilen ersetzen.

    Verknuepfungen, die nicht im Formular stehen (bankumsatz_id, Belegstatus,
    transfer_gruppe_id), bleiben unveraendert erhalten.
    """
    if not con.execute("SELECT 1 FROM buchung WHERE id = ?", (buchung_id,)).fetchone():
        raise HTTPException(404, "Buchung nicht gefunden")
    _pruefe_sparte_und_zeilen(con, b)
    try:
        con.execute(
            "UPDATE buchung SET sparte_id = ?, datum = ?, typ = ?, zahlungsart = ?, "
            "kontakt_id = ?, person_id = ?, text = ?, notiz = ? WHERE id = ?",
            (b.sparte_id, b.datum, b.typ, b.zahlungsart, b.kontakt_id,
             b.person_id, b.text, b.notiz, buchung_id),
        )
        con.execute("DELETE FROM buchungszeile WHERE buchung_id = ?", (buchung_id,))
        for z in b.zeilen:
            con.execute(
                "INSERT INTO buchungszeile(buchung_id, kategorie_id, betrag_cent, notiz) "
                "VALUES(?,?,?,?)",
                (buchung_id, z.kategorie_id, z.betrag_cent, z.notiz),
            )
        con.commit()
    except sqlite3.IntegrityError as e:
        con.rollback()
        raise HTTPException(400, f"Datenbankfehler: {e}")
    return _buchung_detail(con, buchung_id)


@router.delete("/buchungen/{buchung_id}", status_code=204)
def delete_buchung(buchung_id: int, con: sqlite3.Connection = Depends(db_dep)):
    row = con.execute("SELECT bankumsatz_id FROM buchung WHERE id = ?",
                      (buchung_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Buchung nicht gefunden")
    con.execute("DELETE FROM buchung WHERE id = ?", (buchung_id,))  # Zeilen via ON DELETE CASCADE
    # War die Buchung aus einem Bankumsatz uebernommen, wird dieser wieder
    # geoeffnet, damit er nicht unerledigt als "verbucht" haengen bleibt.
    if row["bankumsatz_id"] is not None:
        con.execute("UPDATE bankumsatz SET importstatus = 'offen' WHERE id = ?",
                    (row["bankumsatz_id"],))
    con.commit()


def _buchung_detail(con: sqlite3.Connection, buchung_id: int) -> dict:
    row = con.execute(
        "SELECT b.id, b.sparte_id, s.name AS sparte_name, b.datum, b.typ, "
        "b.betrag_cent, b.zahlungsart, b.belegstatus, b.buchungsstatus, b.text, b.notiz "
        "FROM buchung b JOIN sparte s ON s.id = b.sparte_id WHERE b.id = ?",
        (buchung_id,),
    ).fetchone()
    result = dict(row)
    result["zeilen"] = [
        dict(z) for z in con.execute(
            "SELECT z.id, z.kategorie_id, k.name AS kategorie_name, z.betrag_cent, z.notiz "
            "FROM buchungszeile z JOIN kategorie k ON k.id = z.kategorie_id "
            "WHERE z.buchung_id = ? ORDER BY z.id",
            (buchung_id,),
        ).fetchall()
    ]
    return result
