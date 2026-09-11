"""Betriebliche, lesende Informationen fuer angemeldete Nutzer.

P72: ergaenzt die reine Migrationsprotokoll-Liste um eine gebuendelte
Betriebsuebersicht (Schema, Sicherung, Ollama-Erreichbarkeit, KI-Vorschlag,
Frontend/Instanz, Auswertungswarteschlange) fuer die neue Betriebsseite sowie
einen Endpunkt, um eine Sicherung manuell anzustossen.
"""
import asyncio
import os
import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Request

from .. import backup
from ..bereiche import Bereich, BereichDep
from ..db import db_dep
from ..ki_vorschlag import ist_aktiv as ki_vorschlag_aktiv
from ..migrate import status as migrationsstatus
from .beleg_auswertung import auswertung_status

router = APIRouter(prefix="/betrieb", tags=["betrieb"])


@router.get("/migrationsprotokoll")
def migrationsprotokoll(con: sqlite3.Connection = Depends(db_dep), bereich: BereichDep = Bereich(1)):
    return [dict(row) for row in con.execute(
        "SELECT id, version, zeitpunkt, art, objektkennung, hinweis "
        "FROM migrationsprotokoll ORDER BY zeitpunkt, id"
    )]


def baue_sicherung_und_schema_status(schema: dict, schreibgeschuetzt: bool) -> dict:
    """Baut den Schema-/Sicherungsteil des Betriebsstatus.

    Ausgelagert aus app/main.py::betrieb_status() (P72), damit dieselbe Logik
    auch in GET /api/betrieb/uebersicht verwendet werden kann, ohne sie ein
    zweites Mal zu schreiben. Arbeitet ausschliesslich ueber das gemeinsame
    ``backup``-Modul (dessen Patches in Tests modulweit wirken, egal von wo
    aus sie aufgerufen werden); die eigentliche DB-Verbindung und der
    Migrationsstatus werden vom jeweiligen Aufrufer beschafft, damit
    main.py::betrieb_status() fuer bestehende Tests, die main.get_connection/
    main.migrationsstatus patchen, unveraendert bleibt (siehe
    tests/test_backup.py::test_betriebsstatus_enthaelt_nur_oeffentliche_sicherungsfelder).
    """
    ordner = backup.DB_PATH.parent / "backup"
    sicherungen = sorted(ordner.glob("finanz-????-??-??.db"))
    letzte = sicherungen[-1].stem.removeprefix("finanz-") if sicherungen else None
    pruefung = backup.pruefe_sicherung(letzte) if letzte else {
        "db_ok": False,
        "belege_ok": 0,
        "belege_fehlend": 0,
        "manifest_ok": False,
    }
    letztes_ergebnis = backup._letztes_ergebnis
    if letztes_ergebnis is not None:
        zweitziel = letztes_ergebnis["zweitziel"]
    elif backup.BACKUP_ZIEL2 is None:
        zweitziel = "nicht konfiguriert"
    elif letzte and backup._vollstaendiger_satz(backup.BACKUP_ZIEL2, letzte):
        zweitziel = "ok"
    else:
        zweitziel = "fehlt"
    return {
        "schema": {"aktuell": schema["aktuell"], "anstehend": schema["anstehend"]},
        "sicherung": {
            "letzte": letzte,
            "db_ok": pruefung["db_ok"],
            "belege_ok": pruefung["belege_ok"],
            "belege_fehlend": pruefung["belege_fehlend"],
            "zweitziel": zweitziel,
            "ergebnis": letztes_ergebnis,
        },
        "schreibgeschuetzt": schreibgeschuetzt,
    }


def _frontend_wert() -> str:
    """Normalisierter FINANZ_FRONTEND-Wert (siehe app/main.py::frontend_verzeichnis)."""
    return "neu" if (os.environ.get("FINANZ_FRONTEND") or "").strip().lower() == "neu" else "studio"


def _auswertungswarteschlange(con: sqlite3.Connection, bereich: Bereich) -> dict:
    zaehler = {"offen": 0, "laeuft": 0, "fehler": 0}
    rows = con.execute(
        "SELECT a.status, COUNT(*) AS n FROM beleg_auswertung a "
        "JOIN beleg b ON b.id = a.beleg_id "
        "WHERE b.bereich_id = ? AND a.status IN ('offen','laeuft','fehler') "
        "GROUP BY a.status",
        (bereich.id,),
    ).fetchall()
    for row in rows:
        zaehler[row["status"]] = row["n"]
    return zaehler


@router.get("/uebersicht")
def uebersicht(request: Request, con: sqlite3.Connection = Depends(db_dep), bereich: BereichDep = Bereich(1)):
    """Buendelt die fuer die Betriebsseite noetigen Informationen in einem Aufruf.

    Enthaelt nie Pfade der Auth-Datei, Cookies oder sonstige Geheimnisse - nur
    betriebliche Kennzahlen (siehe P72-Auftrag).
    """
    schema = migrationsstatus(con)
    schreibgeschuetzt = getattr(request.app.state, "schreibgeschuetzt", False)
    status = baue_sicherung_und_schema_status(schema, schreibgeschuetzt)
    ollama = auswertung_status(bereich)
    return {
        **status,
        "ollama": {
            "modell": ollama["modell"],
            "url": ollama["url"],
            "erreichbar": ollama["erreichbar"],
        },
        "ki_vorschlag_aktiv": ki_vorschlag_aktiv(),
        "frontend": _frontend_wert(),
        "instanz": os.environ.get("FINANZ_INSTANZ", "prod"),
        "auswertungswarteschlange": _auswertungswarteschlange(con, bereich),
    }


@router.post("/sicherung")
async def sicherung_starten():
    """Stoesst dieselbe Sicherung an, die auch im Lifespan periodisch laeuft (A6).

    409, falls backup.sicherungs_lock bereits gehalten wird (eine Sicherung
    laeuft schon) - ein bewusst einfacher, nicht race-freier Check-then-act
    (siehe P72-Bericht, Restrisiko): eine manuell ausgeloeste Admin-Aktion,
    kein hochfrequentierter Pfad. Schreibgeschuetzt (503) faengt bereits die
    allgemeine schreibschutz_middleware in app/main.py ab, bevor diese Route
    ueberhaupt erreicht wird - hier ist dafuer keine eigene Pruefung noetig.
    """
    if backup.sicherungs_lock.locked():
        raise HTTPException(409, "Es laeuft bereits eine Sicherung")
    return await asyncio.to_thread(backup.sichere_datenbank)
