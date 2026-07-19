"""Gemeinsame Merkregel-Logik.

Regeln (Tabelle ``regel``) ordnen wiederkehrenden Texten eine Sparte/Kategorie/
einen Typ zu. Diese Zuordnungen werden an mehreren Stellen gebraucht:
Bankumsatz-Vorschlaege (app/routers/import_bank.py), Schnelltext-Parser
(app/routers/schnellerfassung.py) und die Foto-Auswertung (app/auswertung.py).
Die Logik lebt deshalb hier statt mehrfach implementiert zu sein.
"""
import re
import sqlite3
from typing import Optional, Union


def normalisiere_regeltext(text: Optional[str]) -> str:
    """Stabilen, klein geschriebenen Regeltext ohne lange Nummern liefern."""
    wert = re.sub(r"\d{5,}", " ", (text or "").lower())
    wert = re.sub(r"\s+", " ", wert).strip(" -_,.;:/")
    return wert[:60].strip()


# Signifikante Wort-Tokens: nur Buchstaben (inkl. Umlaute), mind. 3 Zeichen -
# Zahlen/Betraege/Datumsteile werden dadurch automatisch ignoriert.
_SIGNIFIKANTES_WORT_RE = re.compile(r"[a-zäöüß]+", re.IGNORECASE)


def _signifikante_tokens(text: Optional[str]) -> set:
    return {t.lower() for t in _SIGNIFIKANTES_WORT_RE.findall(text or "") if len(t) >= 3}


def aktive_regeln(con: sqlite3.Connection):
    """Alle aktiven Regeln, inkl. Sparte der Zielkategorie (kat_sparte_id).

    Sortierung: prioritaet, dann laengster bedingung_text zuerst (spezifischere
    Regeln vor allgemeineren), dann id.
    """
    return con.execute(
        "SELECT r.*, k.sparte_id AS kat_sparte_id FROM regel r "
        "LEFT JOIN kategorie k ON k.id = r.ziel_kategorie_id "
        "WHERE r.aktiv = 1 "
        "ORDER BY r.prioritaet, LENGTH(r.bedingung_text) DESC, r.id"
    ).fetchall()


def finde_regel(
    con_oder_regeln: Union[sqlite3.Connection, list], text: Optional[str]
) -> Optional[dict]:
    """Erste aktive Regel, die zum ``text`` passt (Reihenfolge wie
    ``aktive_regeln``). Eine Regel trifft, wenn EINE der beiden Richtungen
    passt:

      (a) die normalisierte bedingung_text ist Substring des normalisierten
          Eingabetexts (langer Text, z. B. Bankumsatz-Haystack oder ein
          voll ausgeschriebener Buchungstext, enthaelt die kurze Regel); oder
      (b) NEU: alle signifikanten Wort-Tokens des Eingabetexts (Woerter mit
          >= 3 Buchstaben, Zahlen/Betraege/Datumsteile werden ignoriert) sind
          eine nichtleere Teilmenge der Wort-Tokens der bedingung - so trifft
          z. B. eine kurze Eingabe wie "Lagerhaus 42" auch eine laenger
          gelernte Regel "lagerhaus rechnung". Ein einzelnes zufaellig
          gemeinsames Wort reicht dabei NICHT (die Eingabe muss vollstaendig
          in den Regel-Tokens aufgehen).

    ``con_oder_regeln`` ist entweder eine offene Verbindung (dann werden die
    aktiven Regeln selbst geladen) oder bereits das Ergebnis von
    ``aktive_regeln`` (z. B. um sie ueber mehrere Aufrufe wiederzuverwenden).

    Rueckgabe (oder ``None``, falls nichts passt):
      regel_id, name, ziel_sparte_id, ziel_kategorie_id, ziel_typ, kat_sparte_id
    """
    if isinstance(con_oder_regeln, sqlite3.Connection):
        regeln = aktive_regeln(con_oder_regeln)
    else:
        regeln = con_oder_regeln
    haystack = normalisiere_regeltext(text)
    if not haystack:
        return None
    eingabe_tokens = _signifikante_tokens(text)
    for r in regeln:
        bedingung = normalisiere_regeltext(r["bedingung_text"])
        if not bedingung:
            continue
        treffer = bedingung in haystack
        if not treffer and eingabe_tokens:
            bedingung_tokens = _signifikante_tokens(bedingung)
            treffer = bool(bedingung_tokens) and eingabe_tokens <= bedingung_tokens
        if not treffer:
            continue
        return {
            "regel_id": r["id"],
            "name": r["name"],
            "ziel_sparte_id": r["ziel_sparte_id"],
            "ziel_kategorie_id": r["ziel_kategorie_id"],
            "ziel_typ": r["ziel_typ"],
            "kat_sparte_id": r["kat_sparte_id"],
        }
    return None
