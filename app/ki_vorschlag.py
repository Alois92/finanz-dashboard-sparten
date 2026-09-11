"""P70: KI-Kategorievorschlag als Rueckfallebene (Text, kein Bild).

Findet der bestehende regelbasierte Vorschlagsweg (Namensabgleich in
schnellerfassung._match_name, Merkregeln in regeln.finde_regel) keine
Kategorie, kann die App auf Wunsch das lokale Sprachmodell (Ollama) nach
einer Kategorie aus der Liste der Sparte fragen. Der Vorschlag ist IMMER nur
ein Vorschlag: er wird hier nicht gespeichert, nicht automatisch verbucht und
lebt nur in der HTTP-Antwort - erst ein Klick des Nutzers (Frontend) macht
ihn wirksam.

Wiederverwendet bewusst den bestehenden Ollama-Aufruf aus app.auswertung
(_ollama_aufruf, _denkmodus_abschalten, OLLAMA_URL, OLLAMA_MODEL) statt ihn
zu duplizieren - siehe dort fuer den Foto-Auswertungsweg.

Konfiguration per ENV:
  FINANZ_KI_VORSCHLAG        1/0, Standard 1 (an). 0 schaltet die gesamte
                              Funktion ab, ohne Ollama ueberhaupt zu rufen.
  FINANZ_OLLAMA_TEXT_TIMEOUT Zeitsperre in Sekunden fuer den Textaufruf,
                              Standard 60 (Textantworten sind viel schneller
                              als die Bild-Auswertung mit ihren bis zu 600 s).
"""
import json
import logging
import os
import sqlite3
import urllib.error

from . import auswertung

log = logging.getLogger("finanz.ki_vorschlag")

OLLAMA_TEXT_TIMEOUT_SEKUNDEN = int(os.environ.get("FINANZ_OLLAMA_TEXT_TIMEOUT", "60"))

_SICHERHEITEN = {"hoch", "mittel", "niedrig"}

PROMPT_VORLAGE = (
    "Ordne den folgenden Buchungstext genau EINER der aufgelisteten Kategorien "
    "zu, oder keiner, wenn nichts eindeutig passt.\n"
    "Buchungstext: {text!r}\n"
    "Betrag: {betrag}\n"
    "Richtung: {richtung}\n"
    "Kategorien (id: Sparte / Kategorie):\n{liste}\n"
    "Antworte AUSSCHLIESSLICH mit einem JSON-Objekt in genau diesem Format, "
    "ohne weiteren Text davor oder danach: "
    '{{"kategorie_id": ganze Zahl aus der Liste oder null, '
    '"sicherheit": "hoch" oder "mittel" oder "niedrig", "begruendung": string}}. '
    "Ist keine Kategorie eindeutig passend, liefere kategorie_id null."
)

_RICHTUNG_TEXT = {"einnahme": "Einnahme", "ausgabe": "Ausgabe", "umbuchung": "Umbuchung"}
_RICHTUNG_FILTER = {"einnahme": ("einnahme", "beides"), "ausgabe": ("ausgabe", "beides")}


def ist_aktiv() -> bool:
    """FINANZ_KI_VORSCHLAG=0 schaltet den KI-Weg komplett ab (Standard: an)."""
    return os.environ.get("FINANZ_KI_VORSCHLAG", "1") != "0"


def _kandidaten(con: sqlite3.Connection, bereich_id: int, sparte_id, typ) -> tuple[list, dict]:
    """Aktive Kategorien der Sparte (oder aller aktiven Sparten des Bereichs,
    falls keine Sparte vorgegeben ist), gefiltert nach Richtung. Liefert
    (kategorie_rows, sparte_name_je_id)."""
    if sparte_id is not None:
        sparten = con.execute(
            "SELECT id, name FROM sparte WHERE id = ? AND aktiv = 1 AND bereich_id = ?",
            (sparte_id, bereich_id),
        ).fetchall()
    else:
        sparten = con.execute(
            "SELECT id, name FROM sparte WHERE aktiv = 1 AND bereich_id = ?",
            (bereich_id,),
        ).fetchall()
    sparten_namen = {r["id"]: r["name"] for r in sparten}
    if not sparten_namen:
        return [], {}

    platzhalter = ",".join("?" * len(sparten_namen))
    sql = (
        f"SELECT id, name, sparte_id, richtung FROM kategorie "
        f"WHERE aktiv = 1 AND sparte_id IN ({platzhalter})"
    )
    params: list = list(sparten_namen.keys())
    richtungen = _RICHTUNG_FILTER.get(typ)
    if richtungen:
        sql += " AND richtung IN (?, ?)"
        params += list(richtungen)
    kategorien = con.execute(sql, params).fetchall()
    return kategorien, sparten_namen


def _prompt(text: str, betrag_cent, typ, kategorien, sparten_namen: dict) -> str:
    betrag = f"{abs(betrag_cent) / 100:.2f} EUR".replace(".", ",") if betrag_cent is not None else "unbekannt"
    richtung = _RICHTUNG_TEXT.get(typ, "unbekannt")
    liste = "\n".join(
        f"{k['id']}: {sparten_namen.get(k['sparte_id'], '?')} / {k['name']}" for k in kategorien
    )
    return PROMPT_VORLAGE.format(text=text, betrag=betrag, richtung=richtung, liste=liste)


def kategorie_vorschlag(
    con: sqlite3.Connection, *, text: str, bereich_id: int, sparte_id: int | None = None,
    typ: str | None = None, betrag_cent: int | None = None,
) -> dict | None:
    """Fragt bei Bedarf das lokale Sprachmodell nach einer Kategorie.

    Liefert None statt einer Exception bei jedem Fehler (Ollama nicht
    erreichbar, Zeitsperre, kaputtes JSON, Vorschlag ausserhalb der
    Kandidatenliste) - der Aufrufer (Endpunkt) soll dem Nutzer nur "kein
    Vorschlag" zeigen muessen, nie einen 500er.
    """
    if not ist_aktiv():
        return None
    text = (text or "").strip()
    if len(text) < 3:
        return None

    kategorien, sparten_namen = _kandidaten(con, bereich_id, sparte_id, typ)
    if not kategorien:
        return None

    body = {
        "model": auswertung.OLLAMA_MODEL,
        "stream": False,
        "format": "json",
        "options": {"temperature": 0},
        "messages": [{
            "role": "user",
            "content": _prompt(text, betrag_cent, typ, kategorien, sparten_namen),
        }],
    }
    if auswertung._denkmodus_abschalten(auswertung.OLLAMA_MODEL):
        # Wie bei der Foto-Auswertung: Qwen-3-Modelle liefern ohne "think: false"
        # nur denkende Zwischentexte statt der eigentlichen JSON-Antwort.
        body["think"] = False

    try:
        antwort = auswertung._ollama_aufruf(
            auswertung.OLLAMA_URL + "/api/chat", body, timeout=OLLAMA_TEXT_TIMEOUT_SEKUNDEN,
        )
        rohtext = (antwort.get("message") or {}).get("content")
        if not rohtext:
            raise ValueError("Ollama-Antwort enthält keinen Inhalt")
        daten = json.loads(rohtext)
        if not isinstance(daten, dict):
            raise ValueError("Antwort ist kein JSON-Objekt")
    except (urllib.error.URLError, OSError, ValueError, json.JSONDecodeError) as exc:
        log.warning("KI-Kategorievorschlag fehlgeschlagen: %s", exc)
        return None

    try:
        kategorie_id = int(daten.get("kategorie_id")) if daten.get("kategorie_id") is not None else None
    except (TypeError, ValueError):
        kategorie_id = None

    kat_row = next((k for k in kategorien if k["id"] == kategorie_id), None) if kategorie_id is not None else None
    if kat_row is None:
        return None

    sicherheit = daten.get("sicherheit")
    if sicherheit not in _SICHERHEITEN:
        sicherheit = "niedrig"
    begruendung = str(daten.get("begruendung") or "").strip()

    return {
        "sparte_id": kat_row["sparte_id"],
        "sparte_name": sparten_namen.get(kat_row["sparte_id"]),
        "kategorie_id": kat_row["id"],
        "kategorie_name": kat_row["name"],
        "sicherheit": sicherheit,
        "begruendung": begruendung,
        "quelle": "ki",
        "modell": auswertung.OLLAMA_MODEL,
    }
