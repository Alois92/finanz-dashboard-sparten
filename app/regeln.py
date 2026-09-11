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


def aktive_regeln(con: sqlite3.Connection, bereich_id: int):
    """Alle aktiven Regeln, inkl. Sparte der Zielkategorie (kat_sparte_id).

    Sortierung: prioritaet, dann laengster bedingung_text zuerst (spezifischere
    Regeln vor allgemeineren), dann id.
    """
    return con.execute(
        "SELECT r.*, k.sparte_id AS kat_sparte_id FROM regel r "
        "LEFT JOIN kategorie k ON k.id = r.ziel_kategorie_id "
        "WHERE r.aktiv = 1 AND r.bereich_id = ? "
        "AND (r.ziel_sparte_id IS NULL OR r.ziel_sparte_id IN "
        "(SELECT id FROM sparte WHERE bereich_id = ?)) "
        "AND (r.ziel_kategorie_id IS NULL OR (k.aktiv = 1 AND k.sparte_id IN "
        "(SELECT id FROM sparte WHERE bereich_id = ?))) "
        "AND (r.bankkonto_id IS NULL OR r.bankkonto_id IN "
        "(SELECT id FROM bankkonto WHERE bereich_id = ?)) "
        "ORDER BY r.prioritaet, LENGTH(r.bedingung_text) DESC, r.id",
        (bereich_id, bereich_id, bereich_id, bereich_id)
    ).fetchall()


def _regel_kandidaten(
    con_oder_regeln: Union[sqlite3.Connection, list], text: Optional[str], *,
    sparte_id: int | None = None, konto_id: int | None = None,
    bereich_id: int = 1, betrag_cent: int | None = None,
) -> list:
    """Alle aktiven Regeln, die zum ``text`` passen (unsortierte Kandidatenliste).

    Gemeinsame Trefferlogik fuer ``finde_regel`` (ein Treffer) und
    ``finde_regeln`` (Trefferliste, P40c) - NICHT doppelt implementieren.
    Jeder Kandidat ist ein Tupel (regel_row, laenge_bedingung, ausgabe_dict).
    Eine Regel trifft, wenn EINE der beiden Richtungen passt:

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
    """
    if isinstance(con_oder_regeln, sqlite3.Connection):
        regeln = aktive_regeln(con_oder_regeln, bereich_id)
    else:
        regeln = con_oder_regeln
    haystack = normalisiere_regeltext(text)
    if not haystack:
        return []
    eingabe_tokens = _signifikante_tokens(text)
    kandidaten = []
    for r in regeln:
        if r["bereich_id"] != bereich_id:
            continue
        if konto_id is not None and r["bankkonto_id"] is not None and r["bankkonto_id"] != konto_id:
            continue
        # Ohne gewaehlte Sparte darf die Regel die Zuordnung vorschlagen.
        # Eine explizite Eingabesparte bleibt dagegen verbindlich.
        if sparte_id is not None and r["eingabe_sparte_id"] is not None and r["eingabe_sparte_id"] != sparte_id:
            continue
        if sparte_id is not None and r["kat_sparte_id"] != sparte_id:
            continue
        if betrag_cent is not None:
            betrag = abs(betrag_cent)
            if r["bedingung_betrag_von_cent"] is not None and betrag < r["bedingung_betrag_von_cent"]:
                continue
            if r["bedingung_betrag_bis_cent"] is not None and betrag > r["bedingung_betrag_bis_cent"]:
                continue
        bedingung = normalisiere_regeltext(r["bedingung_text"])
        if not bedingung:
            continue
        treffer = bedingung in haystack
        if not treffer and eingabe_tokens:
            bedingung_tokens = _signifikante_tokens(bedingung)
            treffer = bool(bedingung_tokens) and eingabe_tokens <= bedingung_tokens
        if not treffer:
            continue
        kandidaten.append((r, len(bedingung), {
            "regel_id": r["id"],
            "name": r["name"],
            "ziel_sparte_id": r["ziel_sparte_id"],
            "ziel_kategorie_id": r["ziel_kategorie_id"],
            "ziel_typ": r["ziel_typ"],
            "kat_sparte_id": r["kat_sparte_id"],
            "quelle": r["quelle"],
            "auto_verbuchen": r["auto_verbuchen"],
        }))
    return kandidaten


def finde_regel(
    con_oder_regeln: Union[sqlite3.Connection, list], text: Optional[str], *,
    sparte_id: int | None = None, konto_id: int | None = None,
    bereich_id: int = 1, betrag_cent: int | None = None,
) -> Optional[dict]:
    """Erste aktive Regel, die zum ``text`` passt (Reihenfolge wie
    ``aktive_regeln``). Trefferlogik siehe ``_regel_kandidaten``.

    Rueckgabe (oder ``None``, falls nichts passt):
      regel_id, name, ziel_sparte_id, ziel_kategorie_id, ziel_typ, kat_sparte_id
    """
    kandidaten = _regel_kandidaten(
        con_oder_regeln, text, sparte_id=sparte_id, konto_id=konto_id,
        bereich_id=bereich_id, betrag_cent=betrag_cent,
    )
    if not kandidaten:
        return None
    beste_prioritaet = min(item[0]["prioritaet"] for item in kandidaten)
    priorisierte = [item for item in kandidaten if item[0]["prioritaet"] == beste_prioritaet]
    beste_laenge = max(item[1] for item in priorisierte)
    beste = [item for item in priorisierte if item[1] == beste_laenge]
    ziele = {item[2]["ziel_kategorie_id"] for item in beste}
    if len(ziele) > 1:
        result = dict(beste[0][2])
        result["konflikt"] = True
        result["konflikte"] = [item[2] for item in beste]
        return result
    result = dict(beste[0][2])
    result["konflikt"] = False
    result["konflikte"] = []
    return result


def finde_regeln(
    con_oder_regeln: Union[sqlite3.Connection, list], text: Optional[str], *,
    sparte_id: int | None = None, konto_id: int | None = None,
    bereich_id: int = 1, betrag_cent: int | None = None, maximal: int = 3,
) -> list:
    """P40c: bis zu ``maximal`` Regeltreffer statt nur des einen besten.

    Nutzt dieselbe Trefferlogik wie ``finde_regel`` (``_regel_kandidaten``),
    sortiert aber nach Prioritaet (aufsteigend) und Bedingungslaenge
    (absteigend, spezifischere Regeln zuerst) und liefert je Zielkategorie
    hoechstens einen Eintrag (Duplikate durch mehrere passende Regeln auf
    dieselbe Kategorie werden herausgefiltert). Konflikte zwischen
    gleichwertigen Regeln (wie bei ``finde_regel``) tauchen hier einfach als
    mehrere Treffer auf - das ist fuer eine Auswahlliste gewuenscht, anders
    als bei ``finde_regel``, wo ein einzelner Vorschlag entschieden sein muss.
    """
    kandidaten = _regel_kandidaten(
        con_oder_regeln, text, sparte_id=sparte_id, konto_id=konto_id,
        bereich_id=bereich_id, betrag_cent=betrag_cent,
    )
    if not kandidaten:
        return []
    kandidaten_sortiert = sorted(
        kandidaten, key=lambda item: (item[0]["prioritaet"], -item[1], item[0]["id"])
    )
    ergebnis = []
    gesehene_kategorien = set()
    for _r, _laenge, daten in kandidaten_sortiert:
        kategorie_id = daten["ziel_kategorie_id"]
        if kategorie_id is None or kategorie_id in gesehene_kategorien:
            continue
        gesehene_kategorien.add(kategorie_id)
        ergebnis.append(dict(daten))
        if len(ergebnis) >= maximal:
            break
    return ergebnis
