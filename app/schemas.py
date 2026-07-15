"""Pydantic-Modelle fuer die API. Betraege durchgaengig in Cent (int)."""
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator

TYPEN = {"einnahme", "ausgabe", "umbuchung"}
RICHTUNGEN = {"einnahme", "ausgabe", "beides"}
ZAHLUNGSARTEN = {"bar", "bank", "karte", "sonstiges"}


class KategorieIn(BaseModel):
    sparte_id: int
    name: str
    richtung: str
    parent_id: Optional[int] = None

    @field_validator("richtung")
    @classmethod
    def _richtung(cls, v: str) -> str:
        if v not in RICHTUNGEN:
            raise ValueError(f"richtung muss eine von {sorted(RICHTUNGEN)} sein")
        return v


class GruppeIn(BaseModel):
    name: str
    beschreibung: Optional[str] = None
    kategorie_ids: List[int] = Field(default_factory=list)


class ZeileIn(BaseModel):
    kategorie_id: int
    betrag_cent: int = Field(ge=0)
    notiz: Optional[str] = None


class BuchungIn(BaseModel):
    sparte_id: int
    datum: str  # ISO 8601 YYYY-MM-DD
    typ: str
    zahlungsart: str = "bank"
    kontakt_id: Optional[int] = None
    person_id: Optional[int] = None
    bankkonto_id: Optional[int] = None
    text: Optional[str] = None
    notiz: Optional[str] = None
    zeilen: List[ZeileIn]

    @field_validator("typ")
    @classmethod
    def _typ(cls, v: str) -> str:
        if v not in TYPEN:
            raise ValueError(f"typ muss eine von {sorted(TYPEN)} sein")
        return v

    @field_validator("zahlungsart")
    @classmethod
    def _zahlungsart(cls, v: str) -> str:
        if v not in ZAHLUNGSARTEN:
            raise ValueError(f"zahlungsart muss eine von {sorted(ZAHLUNGSARTEN)} sein")
        return v

    @field_validator("zeilen")
    @classmethod
    def _zeilen(cls, v: List[ZeileIn]) -> List[ZeileIn]:
        if not v:
            raise ValueError("Eine Buchung braucht mindestens eine Zeile")
        if sum(z.betrag_cent for z in v) <= 0:
            raise ValueError("Der Gesamtbetrag muss groesser als 0 sein")
        return v
