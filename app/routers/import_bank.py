"""Bank-CSV-Import mit Dublettenschutz und Kontostand-Abgleich.

Verarbeitet deutsche Bank-Export-CSVs (Trennzeichen ';', Zahlen '1.234,56',
Datum 'TT.MM.JJJJ'). Betraege werden durchgaengig in Cent gespeichert.

Endpunkte:
  GET  /api/bankkonten                    - aktive Konten auflisten
  POST /api/bankkonten                    - Konto anlegen
  POST /api/import/csv                    - CSV importieren (multipart)
  GET  /api/bankumsaetze                  - Umsaetze auflisten (offene mit Vorschlag)
  POST /api/bankumsaetze/{id}/verbuchen   - Umsatz als Buchung uebernehmen
  PATCH /api/bankumsaetze/{id}            - offen <-> ignoriert umschalten
"""
import csv
import hashlib
import io
import sqlite3
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from ..db import db_dep

router = APIRouter(tags=["import"])


# ---------------------------------------------------------------------------
# Spaltenerkennung (Header case-insensitiv, Umlaute/Einheiten tolerant)
# ---------------------------------------------------------------------------

# Schluesselwoerter je Zielspalte. Reihenfolge = Prioritaet.
SPALTEN_DATUM = ("buchungstag", "buchungsdatum", "datum", "belegdatum")
SPALTEN_VALUTA = ("valutadatum", "valuta", "wertstellung")
SPALTEN_BETRAG = ("betrag", "umsatz", "soll/haben")
SPALTEN_TEXT = ("verwendungszweck", "buchungstext", "vorgang", "beschreibung",
                "text")
SPALTEN_SALDO = ("saldo", "kontostand")
SPALTEN_GEGENPARTEI = ("beguenstigter", "begünstigter", "zahlungspflichtiger",
                       "auftraggeber", "empfaenger", "empfänger",
                       "zahlungsbeteiligter", "gegenpartei", "name")
SPALTEN_IBAN = ("iban", "kontonummer")


def _norm(kopf: str) -> str:
    """Header normalisieren: Kleinbuchstaben, ohne Rand-Leerzeichen/BOM."""
    return kopf.strip().lstrip("﻿").lower()


def _finde_spalte(kopf_norm: list[str], kandidaten: tuple[str, ...]) -> Optional[int]:
    """Index der ersten passenden Spalte (erst exakt, dann Teilstring)."""
    for kand in kandidaten:
        for i, k in enumerate(kopf_norm):
            if k == kand:
                return i
    for kand in kandidaten:
        for i, k in enumerate(kopf_norm):
            if kand in k:
                return i
    return None


# ---------------------------------------------------------------------------
# Wertkonvertierung (deutsches Format -> Cent / ISO-Datum)
# ---------------------------------------------------------------------------

def _betrag_zu_cent(text: str) -> int:
    """'1.234,56' / '-1.234,56' / '1234,56-' -> Cent (int, vorzeichenbehaftet)."""
    s = text.strip().replace(" ", "").replace(" ", "")
    s = s.replace("EUR", "").replace("€", "")
    if not s:
        raise ValueError("leerer Betrag")
    negativ = False
    if s.startswith("+"):
        s = s[1:]
    if s.startswith("-"):
        negativ = True
        s = s[1:]
    if s.endswith("-"):
        negativ = True
        s = s[:-1]
    # Deutsches Format: Tausenderpunkt entfernen, Dezimalkomma -> Punkt.
    s = s.replace(".", "").replace(",", ".")
    cent = round(float(s) * 100)
    return -cent if negativ else cent


def _datum_zu_iso(text: str) -> str:
    """'TT.MM.JJJJ' (auch JJ) -> 'YYYY-MM-DD'. ISO-Eingabe wird durchgereicht."""
    s = text.strip()
    if "." in s:
        teile = s.split(".")
        if len(teile) != 3 or not all(teile):
            raise ValueError(f"ungueltiges Datum: {text!r}")
        tag, monat, jahr = teile
        if len(jahr) == 2:
            jahr = "20" + jahr
        return f"{int(jahr):04d}-{int(monat):02d}-{int(tag):02d}"
    if "-" in s and len(s) >= 8:  # bereits ISO
        return s
    raise ValueError(f"ungueltiges Datum: {text!r}")


def _dekodiere(rohdaten: bytes) -> str:
    """CSV-Bytes dekodieren: erst UTF-8 (mit BOM), sonst cp1252 (Windows/dt. Banken)."""
    for kodierung in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return rohdaten.decode(kodierung)
        except UnicodeDecodeError:
            continue
    return rohdaten.decode("utf-8", errors="replace")


# ---------------------------------------------------------------------------
# Pydantic-Modelle
# ---------------------------------------------------------------------------

class BankkontoIn(BaseModel):
    name: str
    sparte_id: Optional[int] = None
    iban: Optional[str] = None
    bank: Optional[str] = None
    inhaber: Optional[str] = None


class UmsatzVerbuchenIn(BaseModel):
    sparte_id: int
    kategorie_id: int
    text: Optional[str] = None       # ueberschreibt den Umsatztext der Buchung
    regel_merken: bool = False       # Zuordnung als Regel fuer die Zukunft speichern


class UmsatzStatusIn(BaseModel):
    importstatus: str                # 'offen' oder 'ignoriert'


# ---------------------------------------------------------------------------
# Bankkonten
# ---------------------------------------------------------------------------

@router.get("/bankkonten")
def list_bankkonten(con: sqlite3.Connection = Depends(db_dep)):
    rows = con.execute(
        "SELECT id, sparte_id, inhaber, name, iban, bank, aktiv "
        "FROM bankkonto WHERE aktiv = 1 ORDER BY name"
    ).fetchall()
    return [dict(r) for r in rows]


@router.post("/bankkonten", status_code=201)
def create_bankkonto(k: BankkontoIn, con: sqlite3.Connection = Depends(db_dep)):
    name = k.name.strip()
    if not name:
        raise HTTPException(400, "Name darf nicht leer sein")
    if k.sparte_id is not None and not con.execute(
            "SELECT 1 FROM sparte WHERE id = ?", (k.sparte_id,)).fetchone():
        raise HTTPException(404, "Sparte nicht gefunden")
    cur = con.execute(
        "INSERT INTO bankkonto(sparte_id, inhaber, name, iban, bank) "
        "VALUES(?,?,?,?,?)",
        (k.sparte_id, k.inhaber, name, k.iban, k.bank),
    )
    con.commit()
    row = con.execute(
        "SELECT id, sparte_id, inhaber, name, iban, bank, aktiv "
        "FROM bankkonto WHERE id = ?", (cur.lastrowid,)
    ).fetchone()
    return dict(row)


# ---------------------------------------------------------------------------
# CSV-Import
# ---------------------------------------------------------------------------

@router.post("/import/csv")
def import_csv(
    bankkonto_id: int = Form(...),
    datei: UploadFile = File(...),
    con: sqlite3.Connection = Depends(db_dep),
):
    # Sync-Endpoint (wie die uebrigen Router): sqlite-Verbindung und Handler
    # laufen im selben Threadpool-Thread. Datei daher synchron ueber .file lesen.
    if not con.execute("SELECT 1 FROM bankkonto WHERE id = ?",
                       (bankkonto_id,)).fetchone():
        raise HTTPException(404, "Bankkonto nicht gefunden")

    rohdaten = datei.file.read()
    if not rohdaten:
        raise HTTPException(400, "Datei ist leer")
    text = _dekodiere(rohdaten)

    leser = csv.reader(io.StringIO(text), delimiter=";")
    zeilen = [z for z in leser if any(feld.strip() for feld in z)]
    if not zeilen:
        raise HTTPException(400, "CSV enthaelt keine Daten")

    kopf = zeilen[0]
    kopf_norm = [_norm(feld) for feld in kopf]

    idx_datum = _finde_spalte(kopf_norm, SPALTEN_DATUM)
    idx_betrag = _finde_spalte(kopf_norm, SPALTEN_BETRAG)
    idx_text = _finde_spalte(kopf_norm, SPALTEN_TEXT)
    idx_valuta = _finde_spalte(kopf_norm, SPALTEN_VALUTA)
    idx_saldo = _finde_spalte(kopf_norm, SPALTEN_SALDO)
    idx_gegen = _finde_spalte(kopf_norm, SPALTEN_GEGENPARTEI)
    idx_iban = _finde_spalte(kopf_norm, SPALTEN_IBAN)

    fehlend = []
    if idx_datum is None:
        fehlend.append("Datum")
    if idx_betrag is None:
        fehlend.append("Betrag")
    if idx_text is None:
        fehlend.append("Text/Verwendungszweck")
    if fehlend:
        raise HTTPException(
            400,
            "Pflichtspalte(n) nicht gefunden: " + ", ".join(fehlend)
            + f". Gefundene Spalten: {kopf}",
        )

    def _feld(zeile: list[str], idx: Optional[int]) -> Optional[str]:
        if idx is None or idx >= len(zeile):
            return None
        wert = zeile[idx].strip()
        return wert or None

    # Datenzeilen parsen (Zeilennummer merken fuer Fehlermeldungen).
    posten = []  # dicts mit den Feldern + csv_zeile
    for nr, zeile in enumerate(zeilen[1:], start=2):
        datum_roh = _feld(zeile, idx_datum)
        betrag_roh = _feld(zeile, idx_betrag)
        if datum_roh is None or betrag_roh is None:
            # Zeile ohne Datum/Betrag (z. B. Saldo-Fusszeile) ueberspringen.
            continue
        try:
            datum = _datum_zu_iso(datum_roh)
            betrag_cent = _betrag_zu_cent(betrag_roh)
        except ValueError as e:
            raise HTTPException(400, f"Zeile {nr}: {e}")
        saldo_roh = _feld(zeile, idx_saldo)
        saldo_cent = None
        if saldo_roh is not None:
            try:
                saldo_cent = _betrag_zu_cent(saldo_roh)
            except ValueError as e:
                raise HTTPException(400, f"Zeile {nr} (Saldo): {e}")
        umsatztext = _feld(zeile, idx_text) or ""
        posten.append({
            "csv_zeile": nr,
            "datum": datum,
            "valuta": _feld(zeile, idx_valuta),
            "betrag_cent": betrag_cent,
            "saldo_cent": saldo_cent,
            "text": umsatztext,
            "gegenpartei": _feld(zeile, idx_gegen),
            "iban_gegenpartei": _feld(zeile, idx_iban),
        })

    if not posten:
        raise HTTPException(400, "Keine gueltigen Umsatzzeilen gefunden")

    # Kontostand-Abgleich: saldo[n] - saldo[n-1] == betrag[n] (in Datei-Reihenfolge).
    saldo_ok, saldo_hinweis = _saldo_pruefen(posten, idx_saldo is not None)

    # import_batch anlegen (Zaehler spaeter aktualisieren).
    cur = con.execute(
        "INSERT INTO import_batch(bankkonto_id, dateiname, anzahl_zeilen, quelle) "
        "VALUES(?,?,?,?)",
        (bankkonto_id, datei.filename, len(posten), "csv"),
    )
    batch_id = cur.lastrowid

    neu = 0
    dubletten = 0
    for p in posten:
        import_hash = hashlib.sha256(
            f"{bankkonto_id}|{p['datum']}|{p['betrag_cent']}|{p['text']}".encode("utf-8")
        ).hexdigest()
        # INSERT OR IGNORE: verstoesst gegen UNIQUE(bankkonto_id, import_hash) -> uebersprungen.
        c = con.execute(
            "INSERT OR IGNORE INTO bankumsatz("
            "bankkonto_id, import_batch_id, datum, valuta, betrag_cent, "
            "saldo_nachher_cent, text, gegenpartei, iban_gegenpartei, import_hash) "
            "VALUES(?,?,?,?,?,?,?,?,?,?)",
            (bankkonto_id, batch_id, p["datum"], p["valuta"], p["betrag_cent"],
             p["saldo_cent"], p["text"], p["gegenpartei"], p["iban_gegenpartei"],
             import_hash),
        )
        if c.rowcount == 1:
            neu += 1
        else:
            dubletten += 1

    con.execute(
        "UPDATE import_batch SET anzahl_neu = ?, anzahl_dubletten = ? WHERE id = ?",
        (neu, dubletten, batch_id),
    )
    con.commit()

    return {
        "batch_id": batch_id,
        "neu": neu,
        "dubletten": dubletten,
        "gesamt": len(posten),
        "saldo_ok": saldo_ok,
        "saldo_hinweis": saldo_hinweis,
    }


def _saldo_pruefen(posten: list[dict], hat_saldo: bool):
    """Prueft die Saldo-Kette. Rueckgabe (saldo_ok, hinweis).

    Ohne Saldo-Spalte: (None, None). Passt saldo[n]-saldo[n-1] nicht zu
    betrag[n], deutet das auf einen fehlenden oder doppelten Umsatz hin.
    """
    if not hat_saldo:
        return None, None
    mit_saldo = [p for p in posten if p["saldo_cent"] is not None]
    if len(mit_saldo) < 2:
        return None, "Zu wenige Saldo-Werte fuer einen Abgleich"
    for i in range(1, len(mit_saldo)):
        vorher = mit_saldo[i - 1]["saldo_cent"]
        nachher = mit_saldo[i]["saldo_cent"]
        erwartet = mit_saldo[i]["betrag_cent"]
        differenz = nachher - vorher
        if differenz != erwartet:
            luecke = (differenz - erwartet) / 100
            return False, (
                f"Saldo-Sprung in CSV-Zeile {mit_saldo[i]['csv_zeile']}: "
                f"Saldo aendert sich um {differenz / 100:.2f} EUR, "
                f"der Umsatz betraegt aber {erwartet / 100:.2f} EUR "
                f"(Differenz {luecke:.2f} EUR). "
                "Hinweis auf einen fehlenden oder doppelten Umsatz."
            )
    return True, None


# ---------------------------------------------------------------------------
# Umsaetze auflisten
# ---------------------------------------------------------------------------

@router.get("/bankumsaetze")
def list_bankumsaetze(
    bankkonto_id: Optional[int] = None,
    von: Optional[str] = None,
    bis: Optional[str] = None,
    status: Optional[str] = None,
    con: sqlite3.Connection = Depends(db_dep),
):
    sql = (
        "SELECT id, bankkonto_id, import_batch_id, datum, valuta, betrag_cent, "
        "saldo_nachher_cent, text, gegenpartei, iban_gegenpartei, importstatus "
        "FROM bankumsatz WHERE 1=1"
    )
    params: list = []
    if bankkonto_id is not None:
        sql += " AND bankkonto_id = ?"
        params.append(bankkonto_id)
    if von:
        sql += " AND datum >= ?"
        params.append(von)
    if bis:
        sql += " AND datum <= ?"
        params.append(bis)
    if status:
        sql += " AND importstatus = ?"
        params.append(status)
    sql += " ORDER BY datum DESC, id DESC"
    rows = [dict(r) for r in con.execute(sql, params).fetchall()]

    # Offenen Umsaetzen einen Zuordnungs-Vorschlag mitgeben (Regeln zuerst,
    # sonst die juengste Buchung mit gleicher Gegenpartei).
    offene = [r for r in rows if r["importstatus"] == "offen"]
    if offene:
        regeln = con.execute(
            "SELECT r.*, k.sparte_id AS kat_sparte_id FROM regel r "
            "LEFT JOIN kategorie k ON k.id = r.ziel_kategorie_id "
            "WHERE r.aktiv = 1 ORDER BY r.prioritaet, r.id"
        ).fetchall()
        for u in offene:
            u["vorschlag"] = _vorschlag_fuer_umsatz(con, u, regeln)
    return rows


def _vorschlag_fuer_umsatz(con, u: dict, regeln) -> Optional[dict]:
    """Zuordnungs-Vorschlag: erst Regeln (Prioritaet), dann Verlauf."""
    haystack = ((u["text"] or "") + " " + (u["gegenpartei"] or "")).lower()
    for r in regeln:
        if r["bankkonto_id"] is not None and r["bankkonto_id"] != u["bankkonto_id"]:
            continue
        if r["bedingung_text"] and r["bedingung_text"].lower() not in haystack:
            continue
        betrag = abs(u["betrag_cent"])
        if r["bedingung_betrag_von_cent"] is not None and betrag < r["bedingung_betrag_von_cent"]:
            continue
        if r["bedingung_betrag_bis_cent"] is not None and betrag > r["bedingung_betrag_bis_cent"]:
            continue
        sparte_id = r["ziel_sparte_id"] or r["kat_sparte_id"]
        if not sparte_id or not r["ziel_kategorie_id"]:
            continue
        return {"sparte_id": sparte_id, "kategorie_id": r["ziel_kategorie_id"],
                "quelle": "regel", "regel_name": r["name"]}
    # Verlauf: juengste uebernommene Buchung mit gleicher Gegenpartei
    if u["gegenpartei"]:
        row = con.execute(
            "SELECT b.sparte_id, z.kategorie_id FROM buchung b "
            "JOIN buchungszeile z ON z.buchung_id = b.id "
            "JOIN bankumsatz bu ON bu.id = b.bankumsatz_id "
            "WHERE bu.gegenpartei = ? ORDER BY b.datum DESC, b.id DESC LIMIT 1",
            (u["gegenpartei"],),
        ).fetchone()
        if row:
            return {"sparte_id": row["sparte_id"], "kategorie_id": row["kategorie_id"],
                    "quelle": "verlauf", "regel_name": None}
    return None


# ---------------------------------------------------------------------------
# Umsatz uebernehmen / ignorieren
# ---------------------------------------------------------------------------

@router.post("/bankumsaetze/{umsatz_id}/verbuchen", status_code=201)
def verbuche_umsatz(umsatz_id: int, body: UmsatzVerbuchenIn,
                    con: sqlite3.Connection = Depends(db_dep)):
    u = con.execute("SELECT * FROM bankumsatz WHERE id = ?", (umsatz_id,)).fetchone()
    if not u:
        raise HTTPException(404, "Umsatz nicht gefunden")
    if u["importstatus"] == "verbucht":
        raise HTTPException(400, "Umsatz ist bereits verbucht")
    krow = con.execute(
        "SELECT sparte_id FROM kategorie WHERE id = ? AND aktiv = 1",
        (body.kategorie_id,),
    ).fetchone()
    if not krow:
        raise HTTPException(404, "Kategorie nicht gefunden")
    if krow["sparte_id"] != body.sparte_id:
        raise HTTPException(400, "Kategorie gehoert nicht zur gewaehlten Sparte")

    typ = "ausgabe" if u["betrag_cent"] < 0 else "einnahme"
    betrag = abs(u["betrag_cent"])
    if betrag == 0:
        raise HTTPException(400, "Umsatz mit Betrag 0 kann nicht verbucht werden")
    text = (body.text or u["text"] or u["gegenpartei"] or "").strip() or None

    try:
        cur = con.execute(
            "INSERT INTO buchung(sparte_id, datum, typ, zahlungsart, bankkonto_id, "
            "bankumsatz_id, buchungsstatus, text) VALUES(?,?,?,?,?,?, 'zugeordnet', ?)",
            (body.sparte_id, u["datum"], typ, "bank", u["bankkonto_id"],
             umsatz_id, text),
        )
        buchung_id = cur.lastrowid
        con.execute(
            "INSERT INTO buchungszeile(buchung_id, kategorie_id, betrag_cent) "
            "VALUES(?,?,?)",
            (buchung_id, body.kategorie_id, betrag),
        )
        con.execute(
            "UPDATE bankumsatz SET importstatus = 'verbucht' WHERE id = ?",
            (umsatz_id,),
        )
        regel_angelegt = False
        if body.regel_merken:
            muster = (u["gegenpartei"] or (u["text"] or "")[:40]).strip()
            if muster:
                # Nur anlegen, wenn es noch keine gleichlautende Regel gibt.
                if not con.execute(
                        "SELECT 1 FROM regel WHERE bedingung_text = ? "
                        "AND ziel_kategorie_id = ? AND aktiv = 1",
                        (muster, body.kategorie_id)).fetchone():
                    con.execute(
                        "INSERT INTO regel(name, bedingung_text, ziel_sparte_id, "
                        "ziel_kategorie_id, ziel_typ) VALUES(?,?,?,?,?)",
                        (f"Auto: {muster}", muster, body.sparte_id,
                         body.kategorie_id, typ),
                    )
                    regel_angelegt = True
        con.commit()
    except sqlite3.IntegrityError as e:
        con.rollback()
        raise HTTPException(400, f"Datenbankfehler: {e}")

    return {"buchung_id": buchung_id, "typ": typ, "betrag_cent": betrag,
            "regel_angelegt": regel_angelegt}


@router.patch("/bankumsaetze/{umsatz_id}")
def setze_umsatzstatus(umsatz_id: int, body: UmsatzStatusIn,
                       con: sqlite3.Connection = Depends(db_dep)):
    if body.importstatus not in ("offen", "ignoriert"):
        raise HTTPException(400, "importstatus muss 'offen' oder 'ignoriert' sein")
    u = con.execute("SELECT importstatus FROM bankumsatz WHERE id = ?",
                    (umsatz_id,)).fetchone()
    if not u:
        raise HTTPException(404, "Umsatz nicht gefunden")
    if u["importstatus"] == "verbucht":
        raise HTTPException(400, "Verbuchte Umsaetze zuerst ueber die Buchung loesen "
                                 "(Buchung loeschen oeffnet den Umsatz wieder)")
    con.execute("UPDATE bankumsatz SET importstatus = ? WHERE id = ?",
                (body.importstatus, umsatz_id))
    con.commit()
    return {"id": umsatz_id, "importstatus": body.importstatus}
