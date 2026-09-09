"""Zentrale Bereichsauflösung und Kennungsprüfungen für alle Datenzugriffe."""
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException, Query

from .db import db_dep


@dataclass(frozen=True)
class Bereich:
    id: int


def bereich_dep(bereich_id: int = Query(1), con=Depends(db_dep)) -> Bereich:
    if not con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='bereich'"
    ).fetchone():
        raise HTTPException(503, "Datenbank-Nachzug erforderlich; Bereichsschema nicht verfügbar")
    if not con.execute(
        "SELECT 1 FROM bereich WHERE id = ? AND aktiv = 1", (bereich_id,)
    ).fetchone():
        raise HTTPException(404, "Bereich nicht gefunden")
    return Bereich(bereich_id)


BereichDep = Annotated[Bereich, Depends(bereich_dep)]


def _pruefe(con, sql, kennung, bereich, name):
    if not con.execute(sql, (kennung, bereich.id)).fetchone():
        raise HTTPException(404, f"{name} nicht gefunden")


def pruefe_sparte(con, sparte_id, bereich) -> None:
    _pruefe(con, "SELECT 1 FROM sparte WHERE id=? AND bereich_id=?", sparte_id, bereich, "Sparte")


def pruefe_konto(con, konto_id, bereich) -> None:
    _pruefe(con, "SELECT 1 FROM bankkonto WHERE id=? AND bereich_id=?", konto_id, bereich, "Bankkonto")


def pruefe_beleg(con, beleg_id, bereich) -> None:
    _pruefe(con, "SELECT 1 FROM beleg WHERE id=? AND bereich_id=?", beleg_id, bereich, "Beleg")


def pruefe_kategorie(con, kategorie_id, bereich) -> None:
    _pruefe(con, "SELECT 1 FROM kategorie k JOIN sparte s ON s.id=k.sparte_id WHERE k.id=? AND s.bereich_id=?", kategorie_id, bereich, "Kategorie")


def pruefe_buchung(con, buchung_id, bereich) -> None:
    _pruefe(con, "SELECT 1 FROM buchung b JOIN sparte s ON s.id=b.sparte_id WHERE b.id=? AND s.bereich_id=?", buchung_id, bereich, "Buchung")


def pruefe_umsatz(con, umsatz_id, bereich) -> None:
    _pruefe(con, "SELECT 1 FROM bankumsatz u JOIN bankkonto k ON k.id=u.bankkonto_id WHERE u.id=? AND k.bereich_id=?", umsatz_id, bereich, "Umsatz")


def pruefe_globalgruppe(con, gruppe_id, bereich) -> None:
    _pruefe(con, "SELECT 1 FROM globale_kategoriegruppe WHERE id=? AND bereich_id=?", gruppe_id, bereich, "Gruppe")


def pruefe_auswertungsgruppe(con, gruppe_id, bereich) -> None:
    _pruefe(con, "SELECT 1 FROM auswertungsgruppe WHERE id=? AND bereich_id=?", gruppe_id, bereich, "Auswertungsgruppe")


def pruefe_regel(con, regel_id, bereich) -> None:
    _pruefe(con, "SELECT 1 FROM regel WHERE id=? AND bereich_id=?", regel_id, bereich, "Regel")


def pruefe_auswertung(con, auswertung_id, bereich) -> None:
    _pruefe(con, "SELECT 1 FROM beleg_auswertung a JOIN beleg b ON b.id=a.beleg_id WHERE a.id=? AND b.bereich_id=?", auswertung_id, bereich, "Auswertungsauftrag")


def sparten_ids(con, bereich) -> list[int]:
    return [row[0] for row in con.execute(
        "SELECT id FROM sparte WHERE bereich_id=? ORDER BY sortierung, id", (bereich.id,)
    )]
