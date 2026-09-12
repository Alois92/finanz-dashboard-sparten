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
import datetime as dt
import json
import sqlite3
import urllib.error
import urllib.request
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from ..auswertung import OLLAMA_MODEL, OLLAMA_URL
from ..db import db_dep
from ..bereiche import Bereich, BereichDep, pruefe_beleg, pruefe_auswertung, pruefe_sparte, pruefe_kategorie
from ..schemas import BETRAG_CENT_MAX, ZAHLUNGSARTEN, ZeileIn
from ..wiederholung import speichere_antwort, wiederhole
from .belege import _aktualisiere_belegstatus
from .buchungen import erstelle_buchung

router = APIRouter(tags=["beleg-auswertung"])

# Kurzes Timeout fuer die reine Erreichbarkeitspruefung - das ist kein
# Ollama-Aufruf mit Bildanalyse, sondern nur ein GET auf /api/tags, das
# die Oberflaeche niemals haengen lassen soll (siehe OLLAMA_TIMEOUT_SEKUNDEN
# in app/auswertung.py fuer den eigentlichen, viel laengeren Timeout).
STATUS_TIMEOUT_SEKUNDEN = 3


class AuswertungStatusIn(BaseModel):
    status: Literal["verworfen", "verbucht"]


class UebernehmenPosition(BaseModel):
    text: str
    betrag_cent: int = Field(gt=0, le=BETRAG_CENT_MAX)
    kategorie_id: int
    typ: Literal["einnahme", "ausgabe"] = "ausgabe"


class UebernehmenIn(BaseModel):
    sparte_id: int
    datum: Optional[str] = None
    bezahlt_von_sparte_id: Optional[int] = None
    zahlungsart: str = "bar"
    positionen: List[UebernehmenPosition]
    client_request_id: Optional[str] = Field(default=None, min_length=1)
    # Kopf-Nachzug: Buchungstext (Vorgabe: erkannter Haendler), damit Suche und
    # Merkregeln die Uebernahme genauso behandeln wie eine Handeingabe.
    text: Optional[str] = None

    @field_validator("zahlungsart")
    @classmethod
    def _zahlungsart(cls, v: str) -> str:
        if v not in ZAHLUNGSARTEN:
            raise ValueError(f"zahlungsart muss eine von {sorted(ZAHLUNGSARTEN)} sein")
        return v

    @field_validator("datum")
    @classmethod
    def _datum(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        try:
            if dt.date.fromisoformat(v).isoformat() != v:
                raise ValueError
        except ValueError:
            raise ValueError("datum muss YYYY-MM-DD entsprechen")
        return v

    @field_validator("positionen")
    @classmethod
    def _positionen(cls, v: List[UebernehmenPosition]) -> List[UebernehmenPosition]:
        if not v:
            raise ValueError("positionen darf nicht leer sein")
        return v


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


@router.post("/beleg-auswertungen/{auswertung_id}/uebernehmen", status_code=201)
def auswertung_uebernehmen(
    auswertung_id: int,
    body: UebernehmenIn,
    con: sqlite3.Connection = Depends(db_dep), bereich: BereichDep = Bereich(1),
):
    """Uebernimmt einen fertigen Auswertungsauftrag als Buchung (P43).

    Erzeugt ueber `erstelle_buchung` (app/routers/buchungen.py) eine Buchung mit
    einer Zeile je Position, verknuepft den Beleg und schliesst den Auftrag als
    'verbucht' ab. Die Wiederholungspruefung (client_request_id) laeuft VOR der
    Statuspruefung, damit ein wiederholter Aufruf auch nach dem Statuswechsel auf
    'verbucht' noch die gleiche Antwort liefert statt faelschlich 409 zu melden.
    """
    pruefe_auswertung(con, auswertung_id, bereich)

    # P43b (Migration 016): eigener Wiederholungs-Topf 'beleg_uebernahme', getrennt von
    # der normalen Buchungserfassung ('buchung') - vorher teilten sich beide Aktionen
    # denselben Topf, siehe SCHULDEN.md.
    antwort = wiederhole(con, 'beleg_uebernahme', body, bereich)
    if antwort is not None:
        return antwort

    pruefe_sparte(con, body.sparte_id, bereich)

    auftrag = con.execute(
        "SELECT id, beleg_id, status, ergebnis_json FROM beleg_auswertung WHERE id = ?",
        (auswertung_id,),
    ).fetchone()
    if auftrag["status"] != "fertig":
        raise HTTPException(409, "Auswertung ist noch nicht fertig oder bereits abgeschlossen")

    for p in body.positionen:
        pruefe_kategorie(con, p.kategorie_id, bereich)
        krow = con.execute(
            "SELECT sparte_id FROM kategorie WHERE id = ? AND aktiv = 1",
            (p.kategorie_id,),
        ).fetchone()
        if not krow:
            raise HTTPException(404, f"Kategorie {p.kategorie_id} nicht gefunden")
        if krow["sparte_id"] != body.sparte_id:
            raise HTTPException(400, "Kategorie gehoert nicht zur gewaehlten Sparte")

    typen = {p.typ for p in body.positionen}
    if len(typen) > 1:
        raise HTTPException(422, "Alle Positionen einer Uebernahme muessen denselben Typ haben")
    typ = next(iter(typen))

    ergebnis = json.loads(auftrag["ergebnis_json"]) if auftrag["ergebnis_json"] else {}
    datum = body.datum
    if datum is None:
        datum = ergebnis.get("datum") or dt.date.today().isoformat()
    text = (body.text or ergebnis.get("haendler") or "").strip() or None

    zeilen = [
        ZeileIn(kategorie_id=p.kategorie_id, betrag_cent=p.betrag_cent, notiz=p.text)
        for p in body.positionen
    ]

    # client_request_id=None: die Wiederholungspruefung fuer diese Aktion ist
    # bereits oben (derselbe 'buchung'-Topf) erledigt - erstelle_buchung soll
    # hier keinen zweiten, unabhaengigen Wiederholungs-Eintrag anlegen.
    def beleg_verknuepfen_und_abschliessen(con_, buchung_id_):
        # Laeuft innerhalb der Transaktion von erstelle_buchung: Buchung, Beleg-Verknuepfung
        # und Statuswechsel werden nur gemeinsam gespeichert (sonst koennte eine Buchung ohne
        # Beleg entstehen und die Auswertung bliebe 'fertig' - zweites Uebernehmen = Doppelbuchung).
        # F3: die Statuspruefung oben (status != 'fertig' -> 409) laeuft ausserhalb
        # jeder Transaktion; parallele Aufrufe koennten sie beide bestehen. Der
        # Status wird deshalb hier atomar reserviert (con_ haelt den
        # BEGIN-IMMEDIATE-Lock von erstelle_buchung) - nur der erste rowcount==1
        # gewinnt, alle anderen bekommen 409 und ihre Buchung wird zurueckgerollt.
        cur = con_.execute(
            "UPDATE beleg_auswertung SET status = 'verbucht', aktualisiert = datetime('now') "
            "WHERE id = ? AND status = 'fertig'",
            (auswertung_id,),
        )
        if cur.rowcount != 1:
            raise HTTPException(409, "Auswertung wurde bereits uebernommen")
        con_.execute(
            "INSERT OR IGNORE INTO buchung_beleg(buchung_id, beleg_id) VALUES(?, ?)",
            (buchung_id_, auftrag["beleg_id"]),
        )
        _aktualisiere_belegstatus(con_, buchung_id_)

    buchung_antwort, buchung_id = erstelle_buchung(
        con, bereich, sparte_id=body.sparte_id, datum=datum, typ=typ,
        zahlungsart=body.zahlungsart, bezahlt_von_sparte_id=body.bezahlt_von_sparte_id,
        positionen=zeilen, client_request_id=None, text=text,
        nach_anlage=beleg_verknuepfen_und_abschliessen,
    )

    ergebnis_antwort = {"buchung_id": buchung_id, "version": buchung_antwort["version"]}
    speichere_antwort(con, 'beleg_uebernahme', body, bereich, ergebnis_antwort)
    # QA4-05: erstelle_buchung() committet seine eigene Transaktion bereits selbst
    # (with con: ... BEGIN IMMEDIATE), der Wiederholungs-Eintrag oben laeuft aber
    # erst danach auf derselben Verbindung und wurde ohne expliziten Commit beim
    # Verbindungsschluss verworfen - ein wiederholter Aufruf mit derselben
    # client_request_id bekam dadurch faelschlich 409 statt der gecachten Antwort.
    con.commit()
    return ergebnis_antwort
