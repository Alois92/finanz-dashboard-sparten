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
import datetime as dt
import json
import logging
import os
import pathlib
import re
import sqlite3
import urllib.error
import urllib.request

from .db import get_connection
from .bereiche import Bereich, bereich_dep, pruefe_sparte
from .regeln import finde_regel
from .routers.schnellerfassung import _match_name, _WORT_RE

log = logging.getLogger("finanz.auswertung")

OLLAMA_URL = os.environ.get("FINANZ_OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
OLLAMA_MODEL = os.environ.get("FINANZ_OLLAMA_MODEL", "qwen2.5vl:7b")

# Bildformate gehen als Base64 ans Vision-Modell, PDF wird stattdessen per
# Textebene ausgewertet (siehe _pdf_text/_auswerten, Paket P71).
ERLAUBTE_ENDUNGEN = {"jpg", "jpeg", "png", "webp", "pdf"}
MAX_VERSUCHE = 5
MAX_POSITIONEN = 50
PRUEF_INTERVALL_SEKUNDEN = 15
# Auf langsamer CPU (Token-Generierung teils <1 Token/s) braucht ein Bon mit
# vielen Positionen laenger als 10 min - Timeout deshalb per ENV anpassbar.
OLLAMA_TIMEOUT_SEKUNDEN = int(os.environ.get("FINANZ_OLLAMA_TIMEOUT", "600"))
# Deterministische Auswertung: der Modellvergleich im Gewinnermodell-Umstieg
# lief mit temperature=0 und lieferte spuerbar bessere Datumswerte als der
# Ollama-Standard (temperature=0.8) - siehe SCHULDEN.md/QA4-01..04.
OLLAMA_TEMPERATUR = float(os.environ.get("FINANZ_OLLAMA_TEMPERATUR", "0"))

# Gemeinsamer Regelteil fuer Foto- und Text-Prompt (P71): nur die Einleitung
# unterscheidet sich, die JSON-Vorgaben sollen niemals auseinanderlaufen.
_PROMPT_KERN = (
    "Antworte AUSSCHLIESSLICH mit einem JSON-Objekt in genau diesem Format, "
    "ohne weiteren Text davor oder danach: "
    '{"haendler": string oder null, "datum": "JJJJ-MM-TT" oder null, '
    '"positionen": [{"text": string, "betrag_cent": integer, '
    '"mwst_prozent": Zahl oder null}], '
    '"gesamt_cent": integer oder null}. '
    "Betraege sind ganze Zahlen in Cent (z. B. 5,50 EUR -> 550). "
    "betrag_cent ist der BRUTTO-Endpreis der Position inklusive MwSt, so wie er "
    "zu zahlen ist. Weist der Beleg Netto-Preise und MwSt getrennt aus, gib "
    "trotzdem den Brutto-Betrag an. "
    "mwst_prozent ist der MwSt-Satz der Position als Zahl (z. B. 10, 13, 20), "
    "falls auf dem Beleg ersichtlich, sonst null. "
    "gesamt_cent ist der zu zahlende Brutto-Gesamtbetrag. "
    "Rabatte und Abzuege werden als negative Betraege angegeben. "
    "Ist der Beleg unleserlich oder kein Kassenbon/keine Rechnung, liefere "
    "eine leere Positionsliste (\"positionen\": [])."
)

PROMPT = "Analysiere den abgebildeten Kassenbon oder die Rechnung. " + _PROMPT_KERN

# Fuer PDFs mit Textebene (P71): kein Bild, sondern der extrahierte Text wird
# nach diesem Prompt angehaengt (siehe _auswerten: PROMPT_TEXT + "\n\n" + text).
PROMPT_TEXT = "Hier ist der Text einer Rechnung: " + _PROMPT_KERN

# Obergrenzen fuer die PDF-Textextraktion (siehe _pdf_text): so bleibt der
# Prompt auf der CPU beherrschbar, siehe Entscheidung des Kopfs in der
# Auftragskarte P71.
PDF_MAX_SEITEN = 5
PDF_MAX_ZEICHEN = 12000
PDF_MIN_ZEICHEN = 40


# ---------------------------------------------------------------------------
# Ollama-Aufruf (eigene Funktion, damit Tests sie monkeypatchen koennen)
# ---------------------------------------------------------------------------

def _denkmodus_abschalten(modell: str) -> bool:
    """True fuer Modellfamilien mit Denk-Modus (Qwen 3.x), bei denen Ollama ohne
    `think: false` den Inhalt ins thinking-Feld schreibt. Steuerbar ueber
    FINANZ_OLLAMA_THINK=0|1; ohne Angabe entscheidet der Modellname."""
    vorgabe = os.environ.get("FINANZ_OLLAMA_THINK")
    if vorgabe in ("0", "1"):
        return vorgabe == "0"
    return modell.lower().startswith("qwen3")


def _ollama_aufruf(url: str, body: dict, timeout: int | None = None) -> dict:
    """POST gegen die Ollama-API, synchron (im Async-Kontext ueber
    asyncio.to_thread aufrufen). Wirft urllib.error.URLError/OSError bei
    Verbindungsproblemen oder Timeout - das ist fuer den Aufrufer der Signal,
    den Auftrag wieder auf 'offen' zu setzen statt endgueltig fehlzuschlagen.

    ``timeout`` optional in Sekunden fuer Aufrufer mit eigener Zeitsperre
    (z. B. app/ki_vorschlag.py: Textaufrufe sind viel schneller als die
    Foto-Auswertung und sollen nicht deren langes OLLAMA_TIMEOUT_SEKUNDEN
    erben). Ohne Angabe gilt weiterhin OLLAMA_TIMEOUT_SEKUNDEN.
    """
    daten = json.dumps(body).encode("utf-8")
    request = urllib.request.Request(
        url, data=daten, method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(
        request, timeout=timeout if timeout is not None else OLLAMA_TIMEOUT_SEKUNDEN
    ) as resp:
        return json.loads(resp.read().decode("utf-8"))


# Laengste Bildkante fuer den Ollama-Aufruf. Der Vision-Encoder skaliert mit
# der Pixelzahl: ein 12-MP-Handyfoto braucht auf 2 CPU-Kernen >10 min, auf
# ~1280 px verkleinert nur einen Bruchteil davon - fuer Kassenbons reicht das.
BILD_MAX_PX = int(os.environ.get("FINANZ_BILD_MAX_PX", "1280"))
# Quer liegende Bilder vor dem Modellaufruf auf Hochformat drehen (FINANZ_BILD_QUER_DREHEN=0 schaltet ab).
QUER_DREHEN = os.environ.get("FINANZ_BILD_QUER_DREHEN", "1") != "0"


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
        # Quer liegende Bilder ohne EXIF-Drehung (typisch nach Messenger-Versand) auf
        # Hochformat drehen: Belege und Rechnungen sind praktisch immer hochkant, und
        # der Modellvergleich vom 11.09.2026 zeigte, dass die Ausrichtung mehr
        # ausmacht als die Modellwahl (outputs/modelltest/ERGEBNIS.md).
        if QUER_DREHEN and bild.width > bild.height:
            bild = bild.transpose(Image.Transpose.ROTATE_270)
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


def _pdf_text(pfad: pathlib.Path) -> tuple[str, bool]:
    """Text aus der Textebene eines PDFs extrahieren (P71, kein OCR/Rendering).

    Liest hoechstens die ersten PDF_MAX_SEITEN Seiten, normalisiert Leerraum
    und schneidet nach PDF_MAX_ZEICHEN ab. Liefert (text, gekuerzt).

    Wirft ValueError (unwiederbringlich, siehe _auswerten-Doku):
      - pypdf fehlt (Paket nicht installiert),
      - die Datei ist kein lesbares PDF,
      - weniger als PDF_MIN_ZEICHEN sichtbarer Text vorhanden ist (Scan ohne
        Textebene - der Nutzer soll das Foto stattdessen hochladen).
    """
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise ValueError(
            "PDF-Auswertung nicht möglich – Paket 'pypdf' fehlt"
        ) from exc

    try:
        reader = PdfReader(str(pfad))
        seiten_text = [
            (seite.extract_text() or "") for seite in reader.pages[:PDF_MAX_SEITEN]
        ]
    except Exception as exc:
        raise ValueError(f"PDF konnte nicht gelesen werden: {exc}") from exc

    text = re.sub(r"\s+", " ", " ".join(seiten_text)).strip()
    if len(text) < PDF_MIN_ZEICHEN:
        raise ValueError("PDF ohne Textebene – bitte als Foto hochladen")

    gekuerzt = len(text) > PDF_MAX_ZEICHEN
    if gekuerzt:
        text = text[:PDF_MAX_ZEICHEN]
    return text, gekuerzt


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
    if datum is not None:
        # Modelle liefern gelegentlich unmoegliche Daten (z. B. Monat 14) -
        # dann lieber None, damit das UI auf "heute" zurueckfaellt.
        try:
            dt.date.fromisoformat(datum)
        except ValueError:
            datum = None

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
        # MwSt-Satz defensiv uebernehmen: nur plausible Werte 0-30, sonst None.
        mwst = p.get("mwst_prozent")
        try:
            mwst = float(mwst) if mwst is not None else None
        except (TypeError, ValueError):
            mwst = None
        if mwst is not None and not (0 <= mwst <= 30):
            mwst = None
        positionen.append({"text": text, "betrag_cent": betrag,
                           "mwst_prozent": mwst})

    try:
        gesamt = daten.get("gesamt_cent")
        gesamt = int(gesamt) if gesamt is not None else None
    except (TypeError, ValueError):
        gesamt = None

    return {"haendler": haendler, "datum": datum, "positionen": positionen,
            "gesamt_cent": gesamt}


# ---------------------------------------------------------------------------
# Netto->Brutto-Korrektur (rein deterministisch, ohne Modell)
# ---------------------------------------------------------------------------

def _euro(cent: int) -> str:
    """Cent-Betrag als deutschen Euro-String formatieren (z. B. 1234 -> '12,34 €')."""
    return f"{cent / 100:.2f} €".replace(".", ",")


def _angleichen(positionen: list, neu: list, gesamt: int) -> None:
    """Neue Betraege setzen und die Rundungs-Restdifferenz zum Gesamtbetrag auf
    die betragsgroesste Position schlagen, sodass die Summe exakt gesamt ergibt."""
    for p, n in zip(positionen, neu):
        p["betrag_cent"] = n
    diff = gesamt - sum(neu)
    if diff and positionen:
        idx = max(range(len(positionen)),
                  key=lambda i: positionen[i]["betrag_cent"])
        positionen[idx]["betrag_cent"] += diff


def _brutto_aufschlagen(positionen: list, gesamt: int) -> None:
    """Netto-Positionen auf Brutto hochrechnen und exakt an gesamt angleichen.

    Bevorzugt die auf dem Beleg ausgewiesenen MwSt-Saetze je Position; nur wenn
    diese fehlen oder das Ergebnis zu stark abweicht, wird proportional (ueber
    den gemeinsamen Faktor gesamt/summe) skaliert.
    """
    alle_mwst = positionen and all(
        p.get("mwst_prozent") is not None for p in positionen)
    if alle_mwst:
        neu = [round(p["betrag_cent"] * (1 + p["mwst_prozent"] / 100))
               for p in positionen]
        if abs(sum(neu) - gesamt) <= 2:
            _angleichen(positionen, neu, gesamt)
            return

    # Fallback: proportional ueber den Gesamtfaktor skalieren.
    faktor = gesamt / sum(p["betrag_cent"] for p in positionen)
    neu = [round(p["betrag_cent"] * faktor) for p in positionen]
    _angleichen(positionen, neu, gesamt)


def _brutto_abgleich(ergebnis: dict) -> dict:
    """Positionsbetraege gegen den Gesamtbetrag abgleichen.

    Manche Belege weisen Netto-Positionspreise und die MwSt separat aus, waehrend
    gesamt_cent bereits brutto ist. Diese Funktion erkennt den Fall deterministisch
    und rechnet die Positionen auf Brutto hoch (siehe Faelle A/B/C im Code).
    """
    positionen = ergebnis.get("positionen") or []
    gesamt = ergebnis.get("gesamt_cent")
    summe = sum(p["betrag_cent"] for p in positionen)

    # Fall A: kein Gesamtbetrag oder Summe passt bereits (Rundungstoleranz 2 Cent).
    if gesamt is None or abs(summe - gesamt) <= 2:
        return ergebnis

    faktor = gesamt / summe if summe > 0 else 0

    # Fall B: Positionen wirken netto (Gesamt liegt bis 32 % ueber der Summe).
    if summe > 0 and 1.0 < faktor <= 1.32:
        _brutto_aufschlagen(positionen, gesamt)
        ergebnis["hinweis"] = (
            "Netto-Preise erkannt — MwSt automatisch aufgeschlagen "
            "(Summe an Gesamtbetrag angeglichen). Bitte prüfen.")
        ergebnis["brutto_aufgeschlagen"] = True
        return ergebnis

    # Fall C: Abweichung unplausibel (Modell hat sich wohl verlesen) — Betraege
    # unveraendert lassen, nur zur Pruefung markieren.
    if not (0.99 < faktor <= 1.32):
        ergebnis["hinweis"] = (
            f"Summe der Positionen ({_euro(summe)}) weicht vom Gesamtbetrag "
            f"({_euro(gesamt)}) ab — bitte prüfen.")
    return ergebnis


# ---------------------------------------------------------------------------
# Kategorien-Mapping je Position
# ---------------------------------------------------------------------------

def _kategorie_fuer_position(con: sqlite3.Connection, text: str, sparte_id, bereich_id: int):
    """Kategorie fuer eine Beleg-Position bestimmen.

    Reihenfolge (Sparte ist immer die feste Beleg-Sparte):
      1. Namensabgleich nur unter den Kategorien dieser Sparte
      2. Merkregeln - nur uebernehmen, wenn deren Zielkategorie zur
         Beleg-Sparte passt (kat_sparte_id == sparte_id)
    """
    if sparte_id is None:
        return None, None
    pruefe_sparte(con, sparte_id, Bereich(bereich_id))
    kategorien = [dict(r) for r in con.execute(
        "SELECT id, name, sparte_id FROM kategorie "
        "WHERE aktiv = 1 AND sparte_id = ?", (sparte_id,)
    ).fetchall()]
    text_lower = (text or "").lower()
    tokens = {t.lower() for t in _WORT_RE.findall(text or "")}
    treffer = _match_name(text_lower, tokens, kategorien)
    if treffer:
        return treffer["id"], treffer["name"]

    regel = finde_regel(con, text, bereich_id=bereich_id, sparte_id=sparte_id)
    if regel and not regel.get("konflikt") and regel["ziel_kategorie_id"] and regel["kat_sparte_id"] == sparte_id:
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
        "SELECT id, sparte_id, dateiname, pfad, bereich_id FROM beleg WHERE id = ?",
        (beleg_id,),
    ).fetchone()
    if not beleg:
        raise ValueError("Beleg nicht gefunden")

    bereich = bereich_dep(beleg["bereich_id"], con)
    if beleg["sparte_id"] is not None:
        pruefe_sparte(con, beleg["sparte_id"], bereich)
    endung = pathlib.Path(beleg["dateiname"] or "").suffix.lower().lstrip(".")
    if endung not in ERLAUBTE_ENDUNGEN:
        raise ValueError(
            "Nur JPG/PNG/WebP-Fotos oder PDF-Rechnungen können lokal ausgewertet werden"
        )

    pfad = pathlib.Path(beleg["pfad"])
    if not pfad.exists():
        raise ValueError("Belegdatei nicht gefunden")

    gekuerzt = False
    if endung == "pdf":
        text, gekuerzt = _pdf_text(pfad)
        body = {
            "model": OLLAMA_MODEL,
            "stream": False,
            "format": "json",
            "messages": [{
                "role": "user",
                "content": PROMPT_TEXT + "\n\n" + text,
            }],
        }
    else:
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
    # Deterministische Antworten (QA4-01..04): gilt fuer Foto- und PDF-Weg.
    body["options"] = {"temperature": OLLAMA_TEMPERATUR}
    if _denkmodus_abschalten(OLLAMA_MODEL):
        # Qwen-3-Modelle antworten sonst nur im "thinking"-Feld und liefern leeren Inhalt
        # (auf CPU ausserdem minutenlanges Denken vor der eigentlichen Antwort).
        body["think"] = False
    antwort = _ollama_aufruf(OLLAMA_URL + "/api/chat", body)
    rohtext = (antwort.get("message") or {}).get("content")
    if not rohtext:
        raise ValueError("Ollama-Antwort enthält keinen Inhalt")
    ergebnis = _parse_ergebnis(rohtext)
    ergebnis = _brutto_abgleich(ergebnis)
    ergebnis["quelle"] = "pdf_text" if endung == "pdf" else "foto"
    if gekuerzt:
        zusatz = "Text war länger als 12.000 Zeichen und wurde gekürzt."
        vorhandener_hinweis = ergebnis.get("hinweis")
        ergebnis["hinweis"] = (
            f"{vorhandener_hinweis} {zusatz}" if vorhandener_hinweis else zusatz
        )

    for p in ergebnis["positionen"]:
        kat_id, kat_name = _kategorie_fuer_position(con, p["text"], beleg["sparte_id"], bereich.id)
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
