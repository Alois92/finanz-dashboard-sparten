"""Buchungen: erfassen (Kopf + Zeilen), auflisten, bearbeiten, loeschen.
Dazu Umbuchungen zwischen Sparten (zwei gekoppelte Buchungen)."""
import re
import sqlite3
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..db import db_dep
from ..schemas import BuchungIn

router = APIRouter(tags=["buchungen"])

UMBUCHUNG_KATEGORIE = "Umbuchung"


class UmbuchungIn(BaseModel):
    von_sparte_id: int
    nach_sparte_id: int
    datum: str
    betrag_cent: int = Field(gt=0)
    text: str | None = None


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
                   monat: str | None = None,
                   kategorie_id: int | None = None,
                   globalgruppe_id: int | None = None,
                   con: sqlite3.Connection = Depends(db_dep)):
    if monat is not None and not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", monat):
        raise HTTPException(400, "Monat muss das Format JJJJ-MM haben")
    if kategorie_id is not None and not con.execute(
        "SELECT 1 FROM kategorie WHERE id = ?", (kategorie_id,)
    ).fetchone():
        raise HTTPException(404, "Kategorie nicht gefunden")
    if globalgruppe_id is not None and not con.execute(
        "SELECT 1 FROM globale_kategoriegruppe WHERE id = ?", (globalgruppe_id,)
    ).fetchone():
        raise HTTPException(404, "Gruppe nicht gefunden")
    sql = ("SELECT b.id, b.sparte_id, s.name AS sparte_name, b.datum, b.typ, "
           "b.betrag_cent, b.zahlungsart, b.belegstatus, b.buchungsstatus, "
           "b.text, b.notiz, b.transfer_gruppe_id "
           "FROM buchung b JOIN sparte s ON s.id = b.sparte_id WHERE 1=1")
    params: list = []
    if sparte_id is not None:
        sql += " AND b.sparte_id = ?"; params.append(sparte_id)
    if von:
        sql += " AND b.datum >= ?"; params.append(von)
    if bis:
        sql += " AND b.datum <= ?"; params.append(bis)
    if monat:
        sql += " AND strftime('%Y-%m', b.datum) = ?"; params.append(monat)
    if kategorie_id is not None:
        sql += (" AND EXISTS (SELECT 1 FROM buchungszeile fz "
                "WHERE fz.buchung_id = b.id AND fz.kategorie_id = ?)")
        params.append(kategorie_id)
    if globalgruppe_id is not None:
        sql += (" AND EXISTS (SELECT 1 FROM buchungszeile gz "
                "JOIN kategorie_globalgruppe kg ON kg.kategorie_id = gz.kategorie_id "
                "WHERE gz.buchung_id = b.id AND kg.globalgruppe_id = ?)")
        params.append(globalgruppe_id)
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
        belege = con.execute(
            f"SELECT bb.buchung_id, bl.id, bl.dateiname "
            f"FROM buchung_beleg bb JOIN beleg bl ON bl.id = bb.beleg_id "
            f"WHERE bb.buchung_id IN ({marks}) ORDER BY bl.id",
            ids,
        ).fetchall()
        belege_by: dict[int, list] = {}
        for bl in belege:
            belege_by.setdefault(bl["buchung_id"], []).append(
                {"id": bl["id"], "dateiname": bl["dateiname"]})
        for b in buchungen:
            b["zeilen"] = by_buchung.get(b["id"], [])
            b["belege"] = belege_by.get(b["id"], [])
    return buchungen


@router.post("/umbuchungen", status_code=201)
def create_umbuchung(u: UmbuchungIn, con: sqlite3.Connection = Depends(db_dep)):
    """Geld zwischen zwei Sparten verschieben: zwei gekoppelte Buchungen
    (typ='umbuchung'), verbunden ueber transfer_gruppe_id. Umbuchungen sind
    in allen Einnahmen/Ausgaben-Auswertungen ausgeblendet (v_einnahmen_ausgaben).
    """
    if u.von_sparte_id == u.nach_sparte_id:
        raise HTTPException(400, "Von- und Nach-Sparte muessen verschieden sein")
    for sid in (u.von_sparte_id, u.nach_sparte_id):
        if not con.execute("SELECT 1 FROM sparte WHERE id = ?", (sid,)).fetchone():
            raise HTTPException(404, f"Sparte {sid} nicht gefunden")

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
        con.commit()
    except sqlite3.Error as e:
        con.rollback()
        raise HTTPException(400, f"Datenbankfehler: {e}")
    return {"transfer_gruppe_id": gruppe, "buchung_ids": ids,
            "betrag_cent": u.betrag_cent}


@router.put("/buchungen/{buchung_id}")
def update_buchung(buchung_id: int, b: BuchungIn,
                   con: sqlite3.Connection = Depends(db_dep)):

    """Buchung ueberschreiben: Kopf-Felder aktualisieren, Zeilen ersetzen.

    Verknuepfungen, die nicht im Formular stehen (bankumsatz_id, Belegstatus,
    transfer_gruppe_id), bleiben unveraendert erhalten.
    """
    alt = con.execute("SELECT transfer_gruppe_id FROM buchung WHERE id = ?",
                      (buchung_id,)).fetchone()
    if not alt:
        raise HTTPException(404, "Buchung nicht gefunden")
    if alt["transfer_gruppe_id"]:
        raise HTTPException(400, "Umbuchungen sind gekoppelt - bitte loeschen "
                                 "und neu anlegen statt bearbeiten")
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
    row = con.execute(
        "SELECT bankumsatz_id, transfer_gruppe_id FROM buchung WHERE id = ?",
        (buchung_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Buchung nicht gefunden")
    # Umbuchungen sind gekoppelt: immer beide Seiten der Gruppe entfernen.
    if row["transfer_gruppe_id"]:
        betroffen = con.execute(
            "SELECT id, bankumsatz_id FROM buchung WHERE transfer_gruppe_id = ?",
            (row["transfer_gruppe_id"],)).fetchall()
    else:
        betroffen = [{"id": buchung_id, "bankumsatz_id": row["bankumsatz_id"]}]
    for b in betroffen:
        con.execute("DELETE FROM buchung WHERE id = ?", (b["id"],))  # Zeilen via CASCADE
        # War die Buchung aus einem Bankumsatz uebernommen, wird dieser wieder
        # geoeffnet, damit er nicht unerledigt als "verbucht" haengen bleibt.
        if b["bankumsatz_id"] is not None:
            con.execute("UPDATE bankumsatz SET importstatus = 'offen' WHERE id = ?",
                        (b["bankumsatz_id"],))
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
