"""Schnelltext-Erfassung: regelbasierter Parser (kein LLM).

Wandelt einen kurzen Freitext wie ``Metro, Essen, 5,50`` in einen
Buchungsvorschlag um. Es wird NICHTS gespeichert - der Aufrufer prueft den
Vorschlag und speichert anschliessend ueber ``POST /api/buchungen``.
"""
import datetime as dt
import re
import sqlite3
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..db import db_dep
from ..bereiche import Bereich, BereichDep, pruefe_sparte
from ..ki_vorschlag import ist_aktiv, kategorie_vorschlag
from ..regeln import finde_regel, finde_regeln

router = APIRouter(tags=["schnellerfassung"])


class ParseIn(BaseModel):
    text: str


class KiVorschlagIn(BaseModel):
    text: str
    sparte_id: Optional[int] = None
    typ: Optional[Literal["einnahme", "ausgabe", "umbuchung"]] = None
    betrag_cent: Optional[int] = None


# Signalwoerter fuer die Typ-Erkennung (auf Wortebene geprueft).
EINNAHME_WORTE = {
    "einnahme", "einnahmen", "gutschrift", "gutschriften", "miete",
    "mieteinnahme", "mieteinnahmen", "eingang", "erstattung", "lohn", "gehalt",
    "verkauf", "verkauft", "erloes", "erlös", "foerderung", "förderung",
    "praemie", "prämie", "zinsen", "rueckzahlung", "rückzahlung",
}
UMBUCHUNG_WORTE = {
    "umbuchung", "umbuchungen", "transfer", "uebertrag", "übertrag",
    "ueberweisung", "überweisung",
}

# Muster fuer Betraege: erst dt. Tausender-Form (1.234,56), dann einfache Zahl.
_BETRAG_RE = re.compile(r"\d{1,3}(?:\.\d{3})+(?:,\d{1,2})?|\d+(?:[.,]\d{1,2})?")
# Numerisches Datum wie 12.3. oder 12.03.2026 (zweiter Punkt Pflicht -> keine
# Verwechslung mit Betraegen wie 5.50).
_DATUM_RE = re.compile(r"\b(\d{1,2})\.(\d{1,2})\.(\d{2,4})?")
# Wort-Token inkl. deutscher Umlaute.
_WORT_RE = re.compile(r"[0-9a-zäöüß]+", re.IGNORECASE)


def _raw_to_cent(raw: str) -> int:
    """Wandelt einen erkannten Betrags-String in Cent (int) um."""
    if "," in raw:
        # Deutsche Schreibweise: Punkte sind Tausendertrenner, Komma ist Dezimal.
        raw = raw.replace(".", "").replace(",", ".")
        return round(float(raw) * 100)
    if "." in raw:
        ganz, _, dez = raw.partition(".")
        # 1.234 (3 Nachkommastellen) -> Tausendertrenner, sonst Dezimalpunkt.
        if len(dez) == 3 and len(ganz) <= 3:
            return int(ganz + dez) * 100
        return round(float(raw) * 100)
    # Reine Ganzzahl = volle Euro (z. B. "120" -> 120,00 EUR).
    return int(raw) * 100


def _match_name(text_lower: str, tokens: set[str], rows: list[dict]):
    """Bestes Namens-Match aus ``rows`` (Feld ``name``) fuer den Text.

    Volltreffer des ganzen Namens schlaegt Einzelwort-Treffer.
    """
    best = None
    best_score = 0
    for r in rows:
        name = (r["name"] or "").strip().lower()
        if not name:
            continue
        if name in text_lower:
            score = 100 + len(name)
        else:
            name_words = set(_WORT_RE.findall(name))
            gemeinsam = name_words & tokens
            if not gemeinsam:
                continue
            score = 10 * len(gemeinsam) + max(len(w) for w in gemeinsam)
        if score > best_score:
            best_score = score
            best = r
    return best


# Trennzeichen fuer die Sammeltext-Erfassung: Zeilenumbruch, Semikolon, sowie
# Kommas, die NICHT direkt vor einer Ziffer stehen (so bleibt "82,30" als
# Dezimalzahl zusammen, waehrend "Einkaufen, Kino" getrennt wird).
_SEGMENT_RE = re.compile(r"[;\n]|,(?!\d)")


@router.post("/parse")
def parse_text(payload: ParseIn, con: sqlite3.Connection = Depends(db_dep), bereich: BereichDep = Bereich(1)):
    text = (payload.text or "").strip()
    return _parse_einzeltext(text, con, bereich.id)


@router.post("/parse-mehrere")
def parse_mehrere(payload: ParseIn, con: sqlite3.Connection = Depends(db_dep), bereich: BereichDep = Bereich(1)):
    text = (payload.text or "").strip()
    segmente = [s.strip(" ,;") for s in _SEGMENT_RE.split(text)]
    eintraege = [
        _parse_einzeltext(segment, con, bereich.id) for segment in segmente if segment.strip()
    ]
    return {"eintraege": eintraege}


@router.post("/kategorie-vorschlag/ki")
def kategorie_vorschlag_ki(
    payload: KiVorschlagIn, con: sqlite3.Connection = Depends(db_dep), bereich: BereichDep = Bereich(1),
):
    """P70: KI-Kategorievorschlag als Rueckfallebene - wird vom Frontend nur
    gerufen, wenn der normale (regelbasierte) Vorschlagsweg leer blieb. Ruft
    das Modell erst NACH der Bereichs-/Spartenpruefung auf, damit ein
    ungueltiges sparte_id nicht erst einen (langsamen) Ollama-Aufruf ausloest."""
    text = (payload.text or "").strip()
    if len(text) < 3:
        raise HTTPException(422, "Text zu kurz")
    if payload.sparte_id is not None:
        pruefe_sparte(con, payload.sparte_id, bereich)
    if not ist_aktiv():
        return {"vorschlag": None, "grund": "abgeschaltet"}
    vorschlag = kategorie_vorschlag(
        con, text=text, bereich_id=bereich.id, sparte_id=payload.sparte_id,
        typ=payload.typ, betrag_cent=payload.betrag_cent,
    )
    if vorschlag is None:
        return {"vorschlag": None, "grund": "kein_modell"}
    return {"vorschlag": vorschlag, "grund": None}


def _parse_einzeltext(text: str, con: sqlite3.Connection, bereich_id: int) -> dict:
    heute = dt.date.today()

    # Arbeitskopie, aus der erkannte Datums-/Betrags-Teile entfernt werden,
    # damit sie sich nicht gegenseitig stoeren und im Rest-Text nicht auftauchen.
    rest = text

    # ---- Datum ----
    datum = heute.isoformat()
    low = text.lower()
    if re.search(r"\bvorgestern\b", low):
        datum = (heute - dt.timedelta(days=2)).isoformat()
        rest = re.sub(r"(?i)\bvorgestern\b", " ", rest)
    elif re.search(r"\bgestern\b", low):
        datum = (heute - dt.timedelta(days=1)).isoformat()
        rest = re.sub(r"(?i)\bgestern\b", " ", rest)
    elif re.search(r"\bheute\b", low):
        datum = heute.isoformat()
        rest = re.sub(r"(?i)\bheute\b", " ", rest)
    else:
        m = _DATUM_RE.search(text)
        if m:
            tag = int(m.group(1))
            monat = int(m.group(2))
            jahr = m.group(3)
            if jahr:
                jahr = int(jahr)
                if jahr < 100:
                    jahr += 2000
            else:
                jahr = heute.year
            try:
                datum = dt.date(jahr, monat, tag).isoformat()
                rest = rest.replace(m.group(0), " ", 1)
            except ValueError:
                pass  # ungueltiges Datum -> Default (heute) beibehalten

    # ---- Betrag (letzte Zahl im verbleibenden Text) ----
    betrag_cent = 0
    treffer = list(_BETRAG_RE.finditer(rest))
    if treffer:
        m = treffer[-1]
        try:
            betrag_cent = _raw_to_cent(m.group(0))
        except ValueError:
            betrag_cent = 0
        rest = rest[:m.start()] + " " + rest[m.end():]

    # ---- Typ ----
    tokens = {t.lower() for t in _WORT_RE.findall(text)}
    if tokens & UMBUCHUNG_WORTE:
        typ = "umbuchung"
    elif tokens & EINNAHME_WORTE:
        typ = "einnahme"
    else:
        typ = "ausgabe"

    # ---- Sparte / Kategorie per Namensabgleich ----
    text_lower = text.lower()
    sparten = [dict(r) for r in con.execute(
        "SELECT id, name FROM sparte WHERE aktiv = 1 AND bereich_id = ?", (bereich_id,)).fetchall()]
    sparte = _match_name(text_lower, tokens, sparten)
    sparte_id = sparte["id"] if sparte else None
    sparte_name = sparte["name"] if sparte else None

    kategorien = [dict(r) for r in con.execute(
        "SELECT id, name, sparte_id FROM kategorie WHERE aktiv = 1 "
        "AND sparte_id IN (SELECT id FROM sparte WHERE bereich_id = ?)", (bereich_id,)).fetchall()]
    kategorie = None
    if sparte_id is not None:
        kategorie = _match_name(
            text_lower, tokens,
            [k for k in kategorien if k["sparte_id"] == sparte_id])
    if kategorie is None:
        kategorie = _match_name(text_lower, tokens, kategorien)
        # Falls ohne Sparten-Kontext gefunden: Sparte aus der Kategorie ableiten.
        if kategorie is not None and sparte_id is None:
            sparte_id = kategorie["sparte_id"]
            s = next((x for x in sparten if x["id"] == sparte_id), None)
            sparte_name = s["name"] if s else None
    kategorie_id = kategorie["id"] if kategorie else None
    kategorie_name = kategorie["name"] if kategorie else None
    # Herkunft der Kategorie (P70/P40b): "name" (Namensabgleich oben), "regel"
    # (Merkregel unten) oder None (nichts gefunden - Frontend fragt ggf. die KI).
    quelle = "name" if kategorie_id is not None else None
    regel_name = None

    # ---- Kategorie-Treffer-Liste (P40c): bis zu 3, Reihenfolge Namensabgleich
    # -> Merkregeln. kategorie_id/quelle/regel_name (oben/unten) bleiben der
    # ERSTE Treffer, damit bestehende Aufrufer unveraendert funktionieren.
    kategorie_treffer: list[dict] = []
    if kategorie_id is not None:
        kategorie_treffer.append({
            "kategorie_id": kategorie_id, "kategorie_name": kategorie_name,
            "sparte_id": sparte_id, "sparte_name": sparte_name,
            "quelle": "name", "regel_name": None,
        })

    # ---- Merkregeln: greifen als Vorschlag nur, wenn der Namensabgleich
    # keine Kategorie fand (unveraendertes Verhalten der Top-Level-Felder) ----
    if kategorie_id is None:
        regel = finde_regel(con, text, bereich_id=bereich_id, sparte_id=sparte_id)
        if regel and not regel.get("konflikt") and regel["ziel_kategorie_id"]:
            kategorie_id = regel["ziel_kategorie_id"]
            kat_row = next((k for k in kategorien if k["id"] == kategorie_id), None)
            kategorie_name = kat_row["name"] if kat_row else None
            quelle = "regel"
            regel_name = regel["name"]
            if regel["ziel_typ"]:
                typ = regel["ziel_typ"]
            if sparte_id is None:
                regel_sparte_id = regel["ziel_sparte_id"] or regel["kat_sparte_id"]
                if regel_sparte_id:
                    sparte_id = regel_sparte_id
                    s = next((x for x in sparten if x["id"] == sparte_id), None)
                    sparte_name = s["name"] if s else None
            kategorie_treffer.append({
                "kategorie_id": kategorie_id, "kategorie_name": kategorie_name,
                "sparte_id": sparte_id, "sparte_name": sparte_name,
                "quelle": "regel", "regel_name": regel_name,
            })

    # ---- Weitere Regeltreffer fuer die Auswahlliste (max. 3 insgesamt) ----
    # Wird unabhaengig davon geholt, ob der Namensabgleich schon eine
    # Kategorie fand - so kann der Nutzer trotzdem zwischen Herkunftsquellen
    # waehlen (QA2-03/P40-Karte).
    if len(kategorie_treffer) < 3:
        ausgeschlossene_kategorien = {t["kategorie_id"] for t in kategorie_treffer}
        weitere = finde_regeln(
            con, text, bereich_id=bereich_id, sparte_id=sparte_id,
            maximal=3 + len(ausgeschlossene_kategorien),
        )
        for kandidat in weitere:
            if len(kategorie_treffer) >= 3:
                break
            kat_id = kandidat["ziel_kategorie_id"]
            if not kat_id or kat_id in ausgeschlossene_kategorien:
                continue
            kat_row = next((k for k in kategorien if k["id"] == kat_id), None)
            if kat_row is None:
                continue
            s_id = kandidat["ziel_sparte_id"] or kandidat["kat_sparte_id"]
            s_row = next((x for x in sparten if x["id"] == s_id), None) if s_id else None
            kategorie_treffer.append({
                "kategorie_id": kat_id, "kategorie_name": kat_row["name"],
                "sparte_id": s_id, "sparte_name": s_row["name"] if s_row else None,
                "quelle": "regel", "regel_name": kandidat["name"],
            })
            ausgeschlossene_kategorien.add(kat_id)

    # ---- Rest-Text als Beschreibung aufbereiten ----
    beschreibung = re.sub(r"\s+", " ", rest).strip(" ,;.-").strip()
    if not beschreibung:
        beschreibung = text

    return {
        "typ": typ,
        "datum": datum,
        "betrag_cent": betrag_cent,
        "text": beschreibung,
        "sparte_id": sparte_id,
        "sparte_name": sparte_name,
        "kategorie_id": kategorie_id,
        "kategorie_name": kategorie_name,
        "quelle": quelle,
        "regel_name": regel_name,
        "treffer": kategorie_treffer,
    }
