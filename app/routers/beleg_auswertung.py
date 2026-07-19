"""Endpunkte fuer die lokale Foto-Auswertung (Ollama) von Belegen.

Die eigentliche Auswertung laeuft asynchron im Hintergrund (app/auswertung.py
:: auswertung_schleife). Diese Endpunkte legen nur Auftraege an, listen sie
auf und setzen den Abschlussstatus (verbucht/verworfen).

Endpunkte:
  POST /api/belege/{beleg_id}/auswerten     - Auswertungsauftrag anlegen (dedupliziert)
  GET  /api/beleg-auswertungen              - Auftraege auflisten (neueste zuerst)
  POST /api/beleg-auswertungen/{id}/status  - Status auf verworfen/verbucht setzen
"""
import json
import sqlite3
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..db import db_dep

router = APIRouter(tags=["beleg-auswertung"])


class AuswertungStatusIn(BaseModel):
    status: Literal["verworfen", "verbucht"]


def _auftrag_dict(row) -> dict:
    d = dict(row)
    ergebnis_json = d.pop("ergebnis_json", None)
    try:
        d["ergebnis"] = json.loads(ergebnis_json) if ergebnis_json else None
    except (TypeError, ValueError):
        d["ergebnis"] = None
    return d


@router.post("/belege/{beleg_id}/auswerten", status_code=201)
def auswerten_anfordern(beleg_id: int, con: sqlite3.Connection = Depends(db_dep)):
    if not con.execute("SELECT 1 FROM beleg WHERE id = ?", (beleg_id,)).fetchone():
        raise HTTPException(404, "Beleg nicht gefunden")

    # Dedupe: laeuft/wartet bereits ein Auftrag oder ist er schon fertig,
    # diesen zurueckgeben statt einen zweiten anzulegen.
    vorhanden = con.execute(
        "SELECT id, status FROM beleg_auswertung WHERE beleg_id = ? "
        "AND status IN ('offen','laeuft','fertig') "
        "ORDER BY id DESC LIMIT 1",
        (beleg_id,),
    ).fetchone()
    if vorhanden:
        return {"id": vorhanden["id"], "status": vorhanden["status"]}

    cur = con.execute(
        "INSERT INTO beleg_auswertung(beleg_id, status) VALUES(?, 'offen')",
        (beleg_id,),
    )
    con.commit()
    return {"id": cur.lastrowid, "status": "offen"}


@router.get("/beleg-auswertungen")
def liste_auswertungen(
    status: Optional[str] = None,
    con: sqlite3.Connection = Depends(db_dep),
):
    sql = (
        "SELECT a.id, a.beleg_id, a.status, a.ergebnis_json, a.fehler, "
        "a.versuche, a.erstellt, a.aktualisiert, "
        "b.dateiname, b.sparte_id "
        "FROM beleg_auswertung a JOIN beleg b ON b.id = a.beleg_id WHERE 1=1"
    )
    params: list = []
    if status:
        sql += " AND a.status = ?"
        params.append(status)
    sql += " ORDER BY a.id DESC LIMIT 100"
    rows = con.execute(sql, params).fetchall()
    return [_auftrag_dict(r) for r in rows]


@router.post("/beleg-auswertungen/{auswertung_id}/status")
def setze_auswertungsstatus(
    auswertung_id: int,
    body: AuswertungStatusIn,
    con: sqlite3.Connection = Depends(db_dep),
):
    if not con.execute(
        "SELECT 1 FROM beleg_auswertung WHERE id = ?", (auswertung_id,)
    ).fetchone():
        raise HTTPException(404, "Auswertungsauftrag nicht gefunden")
    con.execute(
        "UPDATE beleg_auswertung SET status = ?, aktualisiert = datetime('now') "
        "WHERE id = ?",
        (body.status, auswertung_id),
    )
    con.commit()
    return {"id": auswertung_id, "status": body.status}
