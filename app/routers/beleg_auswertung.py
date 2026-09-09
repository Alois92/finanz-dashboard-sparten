"""Endpunkte fuer die lokale Foto-Auswertung (Ollama) von Belegen.

Die eigentliche Auswertung laeuft asynchron im Hintergrund (app/auswertung.py
:: auswertung_schleife). Diese Endpunkte legen nur Auftraege an, listen sie
auf und setzen den Abschlussstatus (verbucht/verworfen).

Endpunkte:
  POST /api/belege/{beleg_id}/auswerten     - Auswertungsauftrag anlegen (dedupliziert)
  GET  /api/beleg-auswertungen              - Auftraege auflisten (neueste zuerst)
  POST /api/beleg-auswertungen/{id}/status  - Status auf verworfen/verbucht setzen
  GET  /api/auswertung/status               - Erreichbarkeit des Ollama-Servers pruefen
"""
import json
import sqlite3
import urllib.error
import urllib.request
from typing import Literal, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..auswertung import OLLAMA_MODEL, OLLAMA_URL
from ..db import db_dep
from ..bereiche import Bereich, BereichDep, pruefe_beleg, pruefe_auswertung

router = APIRouter(tags=["beleg-auswertung"])

# Kurzes Timeout fuer die reine Erreichbarkeitspruefung - das ist kein
# Ollama-Aufruf mit Bildanalyse, sondern nur ein GET auf /api/tags, das
# die Oberflaeche niemals haengen lassen soll (siehe OLLAMA_TIMEOUT_SEKUNDEN
# in app/auswertung.py fuer den eigentlichen, viel laengeren Timeout).
STATUS_TIMEOUT_SEKUNDEN = 3


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
def auswerten_anfordern(beleg_id: int, con: sqlite3.Connection = Depends(db_dep), bereich: BereichDep = Bereich(1)):
    pruefe_beleg(con, beleg_id, bereich)

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
    con: sqlite3.Connection = Depends(db_dep), bereich: BereichDep = Bereich(1),
):
    sql = (
        "SELECT a.id, a.beleg_id, a.status, a.ergebnis_json, a.fehler, "
        "a.versuche, a.erstellt, a.aktualisiert, "
        "b.dateiname, b.sparte_id "
        "FROM beleg_auswertung a JOIN beleg b ON b.id = a.beleg_id WHERE b.bereich_id = ?"
    )
    params: list = [bereich.id]
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
    con: sqlite3.Connection = Depends(db_dep), bereich: BereichDep = Bereich(1),
):
    pruefe_auswertung(con, auswertung_id, bereich)
    con.execute(
        "UPDATE beleg_auswertung SET status = ?, aktualisiert = datetime('now') "
        "WHERE id = ?",
        (body.status, auswertung_id),
    )
    con.commit()
    return {"id": auswertung_id, "status": body.status}


@router.get("/auswertung/status")
def auswertung_status(bereich: BereichDep = Bereich(1)):
    """Erreichbarkeit des konfigurierten Ollama-Servers pruefen.

    Liefert immer einen regulaeren Antwortkoerper - ist der Server nicht
    erreichbar, ist das ein normaler Zustand (keine Exception/kein 500er),
    damit die Oberflaeche das dem Nutzer erklaeren kann statt nur stumm zu
    haengen.
    """
    ergebnis = {
        "erreichbar": False,
        "url": OLLAMA_URL,
        "modell": OLLAMA_MODEL,
        "modell_vorhanden": False,
    }
    try:
        request = urllib.request.Request(OLLAMA_URL + "/api/tags", method="GET")
        with urllib.request.urlopen(request, timeout=STATUS_TIMEOUT_SEKUNDEN) as resp:
            daten = json.loads(resp.read().decode("utf-8"))
        ergebnis["erreichbar"] = True
        modelle = [m.get("name") for m in daten.get("models", []) if isinstance(m, dict)]
        ergebnis["modell_vorhanden"] = OLLAMA_MODEL in modelle
    except (urllib.error.URLError, OSError, ValueError, TimeoutError):
        pass
    return ergebnis
