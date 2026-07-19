"""Lokale Foto-Auswertung von Kassenbons/Rechnungen via Ollama (Vision-Modell).

Laeuft komplett lokal, ohne neue pip-Abhaengigkeit: der HTTP-Aufruf gegen die
Ollama-Chat-API nutzt urllib.request aus der Standardbibliothek. In der
asynchronen Hintergrundschleife wird er ueber asyncio.to_thread ausgelagert,
damit ein (bis zu zehnminuetiger) Ollama-Aufruf den Event-Loop nicht blockiert.

Ablauf: Foto hochladen (POST /api/belege) -> Auftrag anlegen
(POST /api/belege/{id}/auswerten, status='offen') -> auswertung_schleife()
holt den aeltesten offenen Auftrag, ruft Ollama auf und speichert das Ergebnis
(status='fertig'/'fehler'). Ist Ollama gerade nicht erreichbar, bleibt der
Auftrag 'offen' und wird beim naechsten Schleifendurchlauf erneut versucht
(bis MAX_VERSUCHE erreicht ist).

Konfiguration per ENV:
  FINANZ_OLLAMA_URL   Basis-URL des Ollama-Servers (Default http://127.0.0.1:11434)
  FINANZ_OLLAMA_MODEL Vision-Modell (Default qwen2.5vl:7b)
"""
import asyncio
import base64
import json
import logging
import os
import pathlib
import sqlite3
import urllib.error
import urllib.request

from .db import get_connection
from .regeln import finde_regel
from .routers.schnellerfassung import _match_name, _WORT_RE

log = logging.getLogger("finanz.auswertung")

OLLAMA_URL = os.environ.get("FINANZ_OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
OLLAMA_MODEL = os.environ.get("FINANZ_OLLAMA_MODEL", "qwen2.5vl:7b")

# Nur Bildformate koennen dem Vision-Modell als Base64 mitgegeben werden.
ERLAUBTE_ENDUNGEN = {"jpg", "jpeg", "png", "webp"}
MAX_VERSUCHE = 5
MAX_POSITIONEN = 50
PRUEF_INTERVALL_SEKUNDEN = 15
# Auf langsamer CPU (Token-Generierung teils <1 Token/s) braucht ein Bon mit
# vielen Positionen laenger als 10 min - Timeout deshalb per ENV anpassbar.
OLLAMA_TIMEOUT_SEKUNDEN = int(os.environ.get("FINANZ_OLLAMA_TIMEOUT", "600"))

PROMPT = (
    "Analysiere den abgebildeten Kassenbon oder die Rechnung. "
    "Antworte AUSSCHLIESSLICH mit einem JSON-Objekt in genau diesem Format, "
    "ohne weiteren Text davor oder danach: "
    '{"haendler": string oder null, "datum": "JJJJ-MM-TT" oder null, '
    '"positionen": [{"text": string, "betrag_cent": integer}], '
    '"gesamt_cent": integer oder null}. '
    "Betraege sind ganze Zahlen in Cent (z. B. 5,50 EUR -> 550). "
    "Rabatte und Abzuege werden als negative Betraege angegeben. "
    "Ist der Beleg unleserlich oder kein Kassenbon/keine Rechnung, liefere "
    "eine leere Positionsliste (\"positionen\": [])."
)


# ---------------------------------------------------------------------------
# Ollama-Aufruf (eigene Funktion, damit Tests sie monkeypatchen koennen)
# ---------------------------------------------------------------------------

def _ollama_aufruf(url: str, body: dict) -> dict:
    """POST gegen die Ollama-API, synchron (im Async-Kontext ueber
    asyncio.to_thread aufrufen). Wirft urllib.error.URLError/OSError bei
    Verbindungsproblemen oder Timeout - das ist fuer den Aufrufer der Signal,
    den Auftrag wieder auf 'offen' zu setzen statt endgueltig fehlzuschlagen.
    """
    daten = json.dumps(body).encode("utf-8")
    request = urllib.request.Request(
        url, data=daten, method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=OLLAMA_TIMEOUT_SEKUNDEN) as resp:
        return json.loads(resp.read().decode("utf-8"))


# Laengste Bildkante fuer den Ollama-Aufruf. Der Vision-Encoder skaliert mit
# der Pixelzahl: ein 12-MP-Handyfoto braucht auf 2 CPU-Kernen >10 min, auf
# ~1280 px verkleinert nur einen Bruchteil davon - fuer Kassenbons reicht das.
BILD_MAX_PX = int(os.environ.get("FINANZ_BILD_MAX_PX", "1280"))


def _lade_bild_base64(pfad: pathlib.Path) -> str:
    """Bild laden und fuer die Vision-Analyse verkleinern.

    Verkleinert wird nur die Kopie fuer den Ollama-Aufruf - der Original-Beleg
    auf der Platte bleibt unangetastet. Faellt die Verkleinerung aus (Pillow
    fehlt, kaputte Datei), wird das Original unveraendert geschickt.
    """
    roh = pfad.read_bytes()
    try:
        import io

        from PIL import Image, ImageOps

        bild = Image.open(io.BytesIO(roh))
        # Handyfotos tragen die Drehung oft nur im EXIF - vor dem Skalieren anwenden.
        bild = ImageOps.exif_transpose(bild)
        if max(bild.size) > BILD_MAX_PX:
            bild.thumbnail((BILD_MAX_PX, BILD_MAX_PX))
        if bild.mode not in ("RGB", "L"):
            bild = bild.convert("RGB")
        puffer = io.BytesIO()
        bild.save(puffer, format="JPEG", quality=85)
        roh = puffer.getvalue()
    except Exception:
        log.warning("Bild-Verkleinerung fehlgeschlagen - sende Original", exc_info=True)
    return base64.b64encode(roh).decode("ascii")


def _parse_ergebnis(rohtext: str) -> dict:
    """Antwort des Modells defensiv in unser Zielformat ueberfuehren.

    Ungueltige/fehlende Werte werden uebersprungen statt den ganzen Auftrag
    scheitern zu lassen - ein teilweise brauchbares Ergebnis ist besser als
    gar keins.
    """
    daten = json.loads(rohtext)
    if not isinstance(daten, dict):
        raise ValueError("Antwort ist kein JSON-Objekt")

    def _text_oder_none(wert):
        if wert is None:
            return None
        wert = str(wert).strip()
        return wert or None

    haendler = _text_oder_none(daten.get("haendler"))
    datum = _text_oder_none(daten.get("datum"))

    positionen = []
    for p in (daten.get("positionen") or [])[:MAX_POSITIONEN]:
        if not isinstance(p, dict):
            continue
        text = _text_oder_none(p.get("text"))
        try:
            betrag = int(p.get("betrag_cent"))
        except (TypeError, ValueError):
            continue
        if not text or betrag == 0:
            continue
        positionen.append({"text": text, "betrag_cent": betrag})

    try:
        gesamt = daten.get("gesamt_cent")
        gesamt = int(gesamt) if gesamt is not None else None
    except (TypeError, ValueError):
        gesamt = None

    return {"haendler": haendler, "datum": datum, "positionen": positionen,
            "gesamt_cent": gesamt}


# ---------------------------------------------------------------------------
# Kategorien-Mapping je Position
# ---------------------------------------------------------------------------

def _kategorie_fuer_position(con: sqlite3.Connection, text: str, sparte_id):
    """Kategorie fuer eine Beleg-Position bestimmen.

    Reihenfolge (Sparte ist immer die feste Beleg-Sparte):
      1. Namensabgleich nur unter den Kategorien dieser Sparte
      2. Merkregeln - nur uebernehmen, wenn deren Zielkategorie zur
         Beleg-Sparte passt (kat_sparte_id == sparte_id)
    """
    if sparte_id is None:
        return None, None
    kategorien = [dict(r) for r in con.execute(
        "SELECT id, name, sparte_id FROM kategorie "
        "WHERE aktiv = 1 AND sparte_id = ?", (sparte_id,)
    ).fetchall()]
    text_lower = (text or "").lower()
    tokens = {t.lower() for t in _WORT_RE.findall(text or "")}
    treffer = _match_name(text_lower, tokens, kategorien)
    if treffer:
        return treffer["id"], treffer["name"]

    regel = finde_regel(con, text)
    if regel and regel["ziel_kategorie_id"] and regel["kat_sparte_id"] == sparte_id:
        row = con.execute(
            "SELECT name FROM kategorie WHERE id = ?", (regel["ziel_kategorie_id"],)
        ).fetchone()
        if row:
            return regel["ziel_kategorie_id"], row["name"]
    return None, None


# ---------------------------------------------------------------------------
# Auswertung eines einzelnen Auftrags
# ---------------------------------------------------------------------------

def _auswerten(con: sqlite3.Connection, beleg_id: int) -> dict:
    """Wertet den Beleg per Ollama aus und liefert das fertige Ergebnis-Dict.

    Wirft ValueError bei unwiederbringlichen Fehlern (falscher Dateityp,
    Datei fehlt, kaputte Modellantwort) - der Aufrufer setzt den Auftrag dann
    auf 'fehler'. urllib.error.URLError/OSError (Verbindung/Timeout) werden
    NICHT hier gefangen, sondern vom Aufrufer gesondert behandelt (Auftrag
    bleibt 'offen' und wird spaeter erneut versucht).
    """
    beleg = con.execute(
        "SELECT id, sparte_id, dateiname, pfad FROM beleg WHERE id = ?",
        (beleg_id,),
    ).fetchone()
    if not beleg:
        raise ValueError("Beleg nicht gefunden")

    endung = pathlib.Path(beleg["dateiname"] or "").suffix.lower().lstrip(".")
    if endung not in ERLAUBTE_ENDUNGEN:
        raise ValueError("Nur JPG/PNG/WebP-Fotos können lokal ausgewertet werden")

    pfad = pathlib.Path(beleg["pfad"])
    if not pfad.exists():
        raise ValueError("Belegdatei nicht gefunden")

    body = {
        "model": OLLAMA_MODEL,
        "stream": False,
        "format": "json",
        "messages": [{
            "role": "user",
            "content": PROMPT,
            "images": [_lade_bild_base64(pfad)],
        }],
    }
    antwort = _ollama_aufruf(OLLAMA_URL + "/api/chat", body)
    rohtext = (antwort.get("message") or {}).get("content")
    if not rohtext:
        raise ValueError("Ollama-Antwort enthält keinen Inhalt")
    ergebnis = _parse_ergebnis(rohtext)

    for p in ergebnis["positionen"]:
        kat_id, kat_name = _kategorie_fuer_position(con, p["text"], beleg["sparte_id"])
        p["kategorie_id"] = kat_id
        p["kategorie_name"] = kat_name

    return ergebnis


# ---------------------------------------------------------------------------
# Hintergrundschleife (Muster: app/backup.py::backup_schleife)
# ---------------------------------------------------------------------------

def _haengende_auftraege_zuruecksetzen() -> None:
    """Beim Serverstart: Auftraege, die beim letzten Absturz auf 'laeuft'
    stehen geblieben sind, wieder oeffnen - sonst blieben sie fuer immer
    haengen."""
    con = get_connection()
    try:
        con.execute(
            "UPDATE beleg_auswertung SET status = 'offen', "
            "aktualisiert = datetime('now') WHERE status = 'laeuft'"
        )
        con.commit()
    finally:
        con.close()


def _verarbeite_naechsten_auftrag() -> bool:
    """Holt den aeltesten offenen Auftrag und wertet ihn aus.

    Rueckgabe: True, wenn ein Auftrag bearbeitet wurde (egal mit welchem
    Ausgang), False wenn gerade nichts zu tun war.
    """
    con = get_connection()
    try:
        auftrag = con.execute(
            "SELECT id, beleg_id, versuche FROM beleg_auswertung "
            "WHERE status = 'offen' ORDER BY erstellt LIMIT 1"
        ).fetchone()
        if not auftrag:
            return False
        auftrag_id = auftrag["id"]
        con.execute(
            "UPDATE beleg_auswertung SET status = 'laeuft', "
            "aktualisiert = datetime('now') WHERE id = ?", (auftrag_id,)
        )
        con.commit()

        try:
            ergebnis = _auswerten(con, auftrag["beleg_id"])
        except (urllib.error.URLError, OSError) as exc:
            versuche = auftrag["versuche"] + 1
            if versuche >= MAX_VERSUCHE:
                con.execute(
                    "UPDATE beleg_auswertung SET status = 'fehler', versuche = ?, "
                    "fehler = ?, aktualisiert = datetime('now') WHERE id = ?",
                    (versuche,
                     f"Ollama nicht erreichbar unter {OLLAMA_URL} — "
                     f"Auftrag wartet ({versuche}/{MAX_VERSUCHE} Versuche, "
                     "danach abgebrochen)",
                     auftrag_id),
                )
            else:
                con.execute(
                    "UPDATE beleg_auswertung SET status = 'offen', versuche = ?, "
                    "fehler = ?, aktualisiert = datetime('now') WHERE id = ?",
                    (versuche,
                     f"Ollama nicht erreichbar unter {OLLAMA_URL} — "
                     f"Auftrag wartet (Versuch {versuche}/{MAX_VERSUCHE})",
                     auftrag_id),
                )
            con.commit()
            return True
        except Exception as exc:  # unwiederbringlicher Fehler
            con.execute(
                "UPDATE beleg_auswertung SET status = 'fehler', fehler = ?, "
                "aktualisiert = datetime('now') WHERE id = ?",
                (str(exc), auftrag_id),
            )
            con.commit()
            return True

        con.execute(
            "UPDATE beleg_auswertung SET status = 'fertig', "
            "ergebnis_json = ?, fehler = NULL, aktualisiert = datetime('now') "
            "WHERE id = ?",
            (json.dumps(ergebnis, ensure_ascii=False), auftrag_id),
        )
        con.commit()
        return True
    finally:
        con.close()


async def auswertung_schleife() -> None:
    """Hintergrundaufgabe: haengende Auftraege beim Start zuruecksetzen, dann
    alle ~15 s den aeltesten offenen Auftrag abarbeiten. Darf nie sterben -
    Fehler werden geloggt, die Schleife laeuft weiter."""
    try:
        await asyncio.to_thread(_haengende_auftraege_zuruecksetzen)
    except Exception:
        log.exception("Zuruecksetzen haengender Auswertungsauftraege fehlgeschlagen")

    while True:
        try:
            await asyncio.to_thread(_verarbeite_naechsten_auftrag)
        except Exception:
            log.exception("Fehler in der Beleg-Auswertungsschleife (laeuft weiter)")
        await asyncio.sleep(PRUEF_INTERVALL_SEKUNDEN)
