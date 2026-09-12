"""Pydantic-Modelle fuer die API. Betraege durchgaengig in Cent (int)."""
import re
from datetime import date
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator

TYPEN = {"einnahme", "ausgabe", "umbuchung"}
RICHTUNGEN = {"einnahme", "ausgabe", "beides"}
ZAHLUNGSARTEN = {"bar", "bank", "karte", "sonstiges"}

# QA2-05: Plausibilitaets-Obergrenze fuer Buchungsbetraege (100 Mio. Euro in Cent).
# Ohne Obergrenze wurden absurde Tippfehler-Betraege (z.B. 10 Mrd. Euro) anstandslos
# gespeichert und verzerrten sofort alle Summen in Uebersicht/Buchungsliste.
BETRAG_CENT_MAX = 10_000_000_000

# F1: Kategorienamen kommen aus API-Aufrufen und aus Excel-Spaltenkoepfen und
# landen ungefiltert in Hinweistexten (rechenbasis.hinweise). Enges Zeichenset
# als serverseitige zweite Bremse neben dem esc() im Frontend.
KATEGORIE_NAME_MAX = 80
_KATEGORIE_NAME_VERBOTEN = re.compile(r"[<>\x00-\x1f\x7f]")


def kategorie_name_gueltig(name: str) -> bool:
    """Max. Laenge, keine Winkelklammern, keine Steuerzeichen."""
    return bool(name) and len(name) <= KATEGORIE_NAME_MAX and not _KATEGORIE_NAME_VERBOTEN.search(name)


class KategorieIn(BaseModel):
    sparte_id: int
    name: str
    richtung: str
    parent_id: Optional[int] = None

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        v = v.strip()
        if not kategorie_name_gueltig(v):
            raise ValueError(
                f"Name ungueltig (max. {KATEGORIE_NAME_MAX} Zeichen, keine Steuerzeichen oder <>)"
            )
        return v

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


class AuswertungsgruppeIn(BaseModel):
    name: str
    beschreibung: Optional[str] = None
    sparte_ids: List[int] = Field(default_factory=list)


class ZeileIn(BaseModel):
    id: Optional[int] = None
    kategorie_id: int
    betrag_cent: int = Field(ge=0, le=BETRAG_CENT_MAX)
    notiz: Optional[str] = None


class BuchungIn(BaseModel):
    sparte_id: int
    datum: str  # ISO 8601 YYYY-MM-DD
    typ: str
    zahlungsart: str = "bank"
    kontakt_id: Optional[int] = None
    person_id: Optional[int] = None
    bankkonto_id: Optional[int] = None
    bankumsatz_id: Optional[int] = None
    text: Optional[str] = None
    notiz: Optional[str] = None
    zeilen: List[ZeileIn]
    bezahlt_von_sparte_id: Optional[int] = None
    client_request_id: Optional[str] = Field(default=None, min_length=1)
    version: Optional[int] = Field(default=None, ge=1, strict=True)
    grund: Optional[str] = None  # P50b: Grund der Aenderung, nur bei PUT ausgewertet

    @field_validator('datum')
    @classmethod
    def _datum(cls, value: str) -> str:
        if date.fromisoformat(value).isoformat() != value:
            raise ValueError('Datum muss YYYY-MM-DD entsprechen')
        return value

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
