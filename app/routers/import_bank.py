"""Bank-CSV-Import mit Dublettenschutz und Kontostand-Abgleich.

Verarbeitet deutsche Bank-Export-CSVs (Trennzeichen ';', Zahlen '1.234,56',
Datum 'TT.MM.JJJJ'). Betraege werden durchgaengig in Cent gespeichert.

Endpunkte:
  POST /api/import/csv                    - CSV importieren (multipart)
  GET  /api/bankumsaetze                  - Umsaetze auflisten (offene mit Vorschlag)
  POST /api/bankumsaetze/{id}/verbuchen   - Umsatz als Buchung uebernehmen
  PATCH /api/bankumsaetze/{id}            - offen <-> ignoriert umschalten
"""
import csv
import hashlib
import io
import re
import sqlite3
import unicodedata
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Literal, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from ..db import db_dep
from ..bewegungen import import_bewegung, synchronisiere_buchung
from ..bereiche import (
    Bereich, BereichDep, pruefe_sparte, pruefe_kategorie, pruefe_konto,
    pruefe_umsatz, pruefe_regel,
)
from ..regeln import aktive_regeln, normalisiere_regeltext

router = APIRouter(tags=["import"])


# ---------------------------------------------------------------------------
# Robuster CSV-Parser (P01)
# ---------------------------------------------------------------------------

SPALTEN_VALUTA = ("valutadatum", "valuta", "wertstellung")

def _norm_p01(wert: str) -> str:
    text = unicodedata.normalize("NFKD", (wert or "").strip().lstrip("\ufeff"))
    return "".join(c for c in text.lower() if c.isalnum())


def dekodiere(rohbytes: bytes) -> tuple[str, str]:
    if rohbytes.startswith(b"\xff\xfe"):
        return rohbytes.decode("utf-16"), "utf-16"
    if rohbytes.startswith(b"\xfe\xff"):
        return rohbytes.decode("utf-16"), "utf-16"
    if rohbytes.startswith(b"\xef\xbb\xbf"):
        return rohbytes.decode("utf-8-sig"), "utf-8"
    for kodierung in ("utf-8", "cp1252"):
        try:
            return rohbytes.decode(kodierung), kodierung
        except UnicodeDecodeError:
            continue
    return rohbytes.decode("cp1252"), "cp1252"


def erkenne_trennzeichen(text: str) -> str:
    zeilen = text.splitlines()
    kandidaten = (";", ",", "\t")
    gueltig = []
    for position, kandidat in enumerate(kandidaten):
        anzahl = [len(next(csv.reader([zeile], delimiter=kandidat))) for zeile in zeilen if zeile.strip()]
        if anzahl and len(set(anzahl)) == 1:
            gueltig.append((anzahl[0], -position, kandidat))
    return max(gueltig)[2] if gueltig else ";"


def _finde_p01(kopf: list[str], kandidaten: tuple[str, ...], ausgeschlossen: set[int] = set()):
    norm = [_norm_p01(wert) for wert in kopf]
    kandidaten_norm = [_norm_p01(wert) for wert in kandidaten]
    for kandidat in kandidaten_norm:
        for i, wert in enumerate(norm):
            if i not in ausgeschlossen and wert == kandidat:
                return i
    for kandidat in kandidaten_norm:
        for i, wert in enumerate(norm):
            if i not in ausgeschlossen and kandidat in wert:
                return i
    return None


def erkenne_spalten(kopf: list[str]) -> dict:
    norm = [_norm_p01(wert) for wert in kopf]
    eigene_name = {i for i, wert in enumerate(norm) if wert == "eigenerkontoname"}
    eigene_iban = {i for i, wert in enumerate(norm) if wert == "eigeneiban"}
    result = {
        "datum": _finde_p01(kopf, ("buchungsdatum", "datum", "valuta", "date", "booking date", "buchungstag", "valutadatum")),
        "betrag": _finde_p01(kopf, ("betrag", "amount", "umsatz", "soll/haben")),
        "text": _finde_p01(kopf, ("buchungs-details", "buchungsdetails", "details", "verwendungszweck", "buchungstext", "umsatztext", "description", "memo", "text", "vorgang", "beschreibung")),
        "gegenpartei": _finde_p01(kopf, ("partnername", "partner", "empfänger", "auftraggeber", "payee", "name", "beguenstigter", "zahlungspflichtiger", "zahlungsbeteiligter", "gegenpartei"), eigene_name),
        "iban": _finde_p01(kopf, ("partner iban", "iban gegenpartei", "gegen-iban", "iban", "kontonummer"), eigene_iban),
        "waehrung": _finde_p01(kopf, ("währung", "waehrung", "currency")),
    }
    result["saldo"] = _finde_p01(
        kopf, ("saldo", "kontostand", "balance"),
        {i for i, wert in enumerate(norm) if "eigene" in wert},
    )
    return result


def parse_betrag_cent(wert: str) -> int:
    s = (wert or "").strip().replace(" ", "").replace("\u00a0", "")
    s = re.sub(r"(?:EUR|€)$", "", s, flags=re.IGNORECASE)
    if s.endswith("-"):
        s = "-" + s[:-1]
    if not s or not re.fullmatch(r"[+-]?[0-9.,]+", s):
        raise ValueError(f"ungueltiger Betrag: {wert!r}")
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") else s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return int((Decimal(s) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    except InvalidOperation:
        raise ValueError(f"ungueltiger Betrag: {wert!r}") from None


def parse_datum(wert: str) -> str:
    for format_ in ("%d.%m.%Y", "%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime((wert or "").strip(), format_).date().isoformat()
        except ValueError:
            pass
    raise ValueError(f"ungueltiges Datum: {wert!r}")


def _norm_hash(wert) -> str:
    return " ".join(str(wert or "").strip().lower().split())


def fingerabdruck(konto_id, datum, betrag_cent, text, gegenpartei, iban, vorkommen: int) -> str:
    werte = (konto_id, datum, betrag_cent, _norm_hash(text), _norm_hash(gegenpartei), _norm_hash(iban), vorkommen)
    return hashlib.sha256("|".join(map(str, werte)).encode("utf-8")).hexdigest()



# ---------------------------------------------------------------------------
# Pydantic-Modelle
# ---------------------------------------------------------------------------

class UmsatzVerbuchenIn(BaseModel):
    sparte_id: int
    kategorie_id: int
    typ: Optional[Literal["einnahme", "ausgabe", "umbuchung"]] = None
    text: Optional[str] = None       # ueberschreibt den Umsatztext der Buchung
    regel_merken: bool = False       # Zuordnung als Regel fuer die Zukunft speichern


class UmsatzStatusIn(BaseModel):
    importstatus: str                # 'offen' oder 'ignoriert'


class RegelPatchIn(BaseModel):
    aktiv: Literal[0, 1]


class VorschlaegeUebernehmenIn(BaseModel):
    umsatz_ids: list[int]


# ---------------------------------------------------------------------------
# CSV-Import
# ---------------------------------------------------------------------------

@router.post("/import/csv")
def import_csv(
    bankkonto_id: int = Form(...),
    datei: UploadFile = File(...),
    con: sqlite3.Connection = Depends(db_dep),
    bereich: BereichDep = Bereich(1),
):
    pruefe_konto(con, bankkonto_id, bereich)
    if con.execute("SELECT art FROM bankkonto WHERE id=?", (bankkonto_id,)).fetchone()[0] == 'kassa':
        raise HTTPException(422, 'Kassenkonten sind vom CSV-Import ausgeschlossen')
    rohbytes = datei.file.read()
    if not rohbytes:
        raise HTTPException(400, "Datei ist leer")
    text, kodierung = dekodiere(rohbytes)
    trennzeichen = erkenne_trennzeichen(text)
    zeilen = [z for z in csv.reader(io.StringIO(text), delimiter=trennzeichen) if any(feld.strip() for feld in z)]
    if not zeilen:
        raise HTTPException(400, "CSV enthaelt keine Daten")
    kopf = zeilen[0]
    spalten = erkenne_spalten(kopf)
    fehlend = [name for name in ("datum", "betrag") if spalten[name] is None]
    erkannt_basis = {"kodierung": kodierung, "trennzeichen": trennzeichen, "spalten": spalten}
    if fehlend:
        raise HTTPException(400, f"Pflichtspalte(n) nicht gefunden: {', '.join('Datum' if n == 'datum' else 'Betrag' for n in fehlend)}. Kodierung: {kodierung}; Trennzeichen: {trennzeichen!r}; Gefundene Spalten: {kopf}")

    def feld(zeile, idx):
        return zeile[idx].strip() if idx is not None and idx < len(zeile) and zeile[idx].strip() else None

    posten, ungueltig = [], []
    vorkommen = {}
    for nr, zeile in enumerate(zeilen[1:], start=2):
        try:
            datum = parse_datum(feld(zeile, spalten["datum"]) or "")
            betrag = parse_betrag_cent(feld(zeile, spalten["betrag"]) or "")
        except ValueError as exc:
            ungueltig.append({"zeile": nr, "grund": str(exc)})
            continue
        eintrag = {
            "csv_zeile": nr, "datum": datum, "valuta": feld(zeile, _finde_p01(kopf, SPALTEN_VALUTA)),
            "betrag_cent": betrag, "saldo_cent": None, "text": feld(zeile, spalten["text"]) or "",
            "gegenpartei": feld(zeile, spalten["gegenpartei"]), "iban_gegenpartei": feld(zeile, spalten["iban"]),
        }
        if spalten["saldo"] is not None:
            try:
                eintrag["saldo_cent"] = parse_betrag_cent(feld(zeile, spalten["saldo"]) or "")
            except ValueError as exc:
                ungueltig.append({"zeile": nr, "grund": f"Saldo: {exc}"})
                continue
        schluessel = (datum, betrag, _norm_hash(eintrag["text"]), _norm_hash(eintrag["gegenpartei"]), _norm_hash(eintrag["iban_gegenpartei"]))
        eintrag["vorkommen"] = vorkommen.get(schluessel, 0)
        vorkommen[schluessel] = eintrag["vorkommen"] + 1
        posten.append(eintrag)
    if not posten:
        raise HTTPException(400, "Keine gueltigen Umsatzzeilen gefunden")

    saldo_ok, saldo_hinweis = _saldo_pruefen(posten, spalten["saldo"] is not None)
    batch = con.execute(
        "INSERT INTO import_batch(bankkonto_id, dateiname, anzahl_zeilen, quelle, dateihash, parser_version, zeitraum_von, zeitraum_bis, anzahl_ungueltig) VALUES(?,?,?,?,?,?,?,?,?)",
        (bankkonto_id, datei.filename, len(zeilen) - 1, "csv", hashlib.sha256(rohbytes).hexdigest(), 2, min(p["datum"] for p in posten), max(p["datum"] for p in posten), len(ungueltig)),
    )
    batch_id, neu, dubletten = batch.lastrowid, 0, 0
    for p in posten:
        neuer_hash = fingerabdruck(bankkonto_id, p["datum"], p["betrag_cent"], p["text"], p["gegenpartei"], p["iban_gegenpartei"], p["vorkommen"])
        alter_hash = hashlib.sha256(f"{bankkonto_id}|{p['datum']}|{p['betrag_cent']}|{p['text']}".encode("utf-8")).hexdigest()
        if con.execute("SELECT 1 FROM bankumsatz WHERE bankkonto_id = ? AND import_hash IN (?, ?)", (bankkonto_id, neuer_hash, alter_hash)).fetchone():
            dubletten += 1
            continue
        cur = con.execute(
            "INSERT INTO bankumsatz(bankkonto_id, import_batch_id, datum, valuta, betrag_cent, saldo_nachher_cent, text, gegenpartei, iban_gegenpartei, import_hash) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (bankkonto_id, batch_id, p["datum"], p["valuta"], p["betrag_cent"], p["saldo_cent"], p["text"], p["gegenpartei"], p["iban_gegenpartei"], neuer_hash),
        )
        neu += cur.rowcount
        import_bewegung(con, cur.lastrowid, bereich)
    con.execute("UPDATE import_batch SET anzahl_neu = ?, anzahl_dubletten = ? WHERE id = ?", (neu, dubletten, batch_id))
    if spalten["saldo"] is not None:
        letzter = max(posten, key=lambda posten: (posten["datum"], posten["csv_zeile"]))
        con.execute(
            "INSERT OR IGNORE INTO kontostand_anker(konto_id,stichtag,saldo_cent,quelle,notiz) "
            "VALUES(?,?,?,'import',?)",
            (bankkonto_id, letzter["datum"], letzter["saldo_cent"],
             f"CSV-Import {datei.filename}"),
        )
    con.commit()
    erkannt = {**erkannt_basis, "zeilen_gesamt": len(zeilen) - 1, "zeilen_ungueltig": ungueltig}
    return {"batch_id": batch_id, "neu": neu, "dubletten": dubletten, "gesamt": len(posten), "saldo_ok": saldo_ok, "saldo_hinweis": saldo_hinweis, "erkannt": erkannt}


def _saldo_pruefen(posten: list[dict], hat_saldo: bool):
    """Prueft die Saldo-Kette. Rueckgabe (saldo_ok, hinweis).

    Ohne Saldo-Spalte: (None, Hinweis). Passt saldo[n]-saldo[n-1] nicht zu
    betrag[n], deutet das auf einen fehlenden oder doppelten Umsatz hin.
    """
    if not hat_saldo:
        return None, "Keine Saldospalte vorhanden."
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

def _regel_text(umsatz) -> str:
    """Empfaenger bevorzugen, sonst den ersten brauchbaren Verwendungszweck."""
    gegenpartei = normalisiere_regeltext(umsatz["gegenpartei"])
    if gegenpartei:
        return gegenpartei
    for teil in re.split(r"[|;/\n]+", umsatz["text"] or ""):
        kandidat = normalisiere_regeltext(teil)
        if len(kandidat) >= 3:
            return kandidat
    return ""


def _regel_haystack(umsatz) -> str:
    return normalisiere_regeltext(
        f"{umsatz['gegenpartei'] or ''} {umsatz['text'] or ''}"
    )


@router.get("/regeln")
def list_regeln(con: sqlite3.Connection = Depends(db_dep),
                       bereich: BereichDep = Bereich(1)):
    rows = con.execute(
        "SELECT id, name, aktiv, prioritaet, bedingung_text, ziel_sparte_id, "
        "ziel_kategorie_id, ziel_typ FROM regel WHERE bereich_id = ? ORDER BY prioritaet, id",
        (bereich.id,),
    ).fetchall()
    return [dict(row) for row in rows]


@router.patch("/regeln/{regel_id}")
def patch_regel(
    regel_id: int,
    body: RegelPatchIn,
    con: sqlite3.Connection = Depends(db_dep),
    bereich: BereichDep = Bereich(1),
):
    pruefe_regel(con, regel_id, bereich)
    con.execute("UPDATE regel SET aktiv = ? WHERE id = ?", (body.aktiv, regel_id))
    con.commit()
    return next(row for row in list_regeln(con, bereich) if row["id"] == regel_id)


@router.delete("/regeln/{regel_id}", status_code=204)
def delete_regel(regel_id: int, con: sqlite3.Connection = Depends(db_dep),
                       bereich: BereichDep = Bereich(1)):
    pruefe_regel(con, regel_id, bereich)
    cur = con.execute("DELETE FROM regel WHERE id = ?", (regel_id,))
    if cur.rowcount == 0:
        raise HTTPException(404, "Regel nicht gefunden")
    con.commit()


@router.get("/bankumsaetze")
def list_bankumsaetze(
    bankkonto_id: Optional[int] = None,
    von: Optional[str] = None,
    bis: Optional[str] = None,
    status: Optional[str] = None,
    con: sqlite3.Connection = Depends(db_dep),
    bereich: BereichDep = Bereich(1),
):
    sql = (
        "SELECT id, bankkonto_id, import_batch_id, datum, valuta, betrag_cent, "
        "saldo_nachher_cent, text, gegenpartei, iban_gegenpartei, importstatus "
        "FROM bankumsatz WHERE bankkonto_id IN "
        "(SELECT id FROM bankkonto WHERE bereich_id = ?)"
    )
    params: list = [bereich.id]
    if bankkonto_id is not None:
        pruefe_konto(con, bankkonto_id, bereich)
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

    # Offenen Umsaetzen den ersten passenden aktiven Regelvorschlag mitgeben.
    offene = [r for r in rows if r["importstatus"] == "offen"]
    if offene:
        regeln = aktive_regeln(con, bereich.id)
        for u in offene:
            u["vorschlag"] = _vorschlag_fuer_umsatz(con, u, regeln)
    return rows


def _vorschlag_fuer_umsatz(con, u: dict, regeln) -> Optional[dict]:
    """Ersten passenden aktiven Regelvorschlag liefern."""
    haystack = _regel_haystack(u)
    for r in regeln:
        if r["bankkonto_id"] is not None and r["bankkonto_id"] != u["bankkonto_id"]:
            continue
        if not r["bedingung_text"] or normalisiere_regeltext(r["bedingung_text"]) not in haystack:
            continue
        betrag = abs(u["betrag_cent"])
        if r["bedingung_betrag_von_cent"] is not None and betrag < r["bedingung_betrag_von_cent"]:
            continue
        if r["bedingung_betrag_bis_cent"] is not None and betrag > r["bedingung_betrag_bis_cent"]:
            continue
        sparte_id = r["ziel_sparte_id"] or r["kat_sparte_id"]
        if not sparte_id or not r["ziel_kategorie_id"]:
            continue
        return {
            "sparte_id": sparte_id,
            "kategorie_id": r["ziel_kategorie_id"],
            "typ": r["ziel_typ"] or ("ausgabe" if u["betrag_cent"] < 0 else "einnahme"),
            "regel_id": r["id"],
            "regel_name": r["name"],
        }
    return None


@router.post("/bankumsaetze/vorschlaege-uebernehmen")
def uebernehme_vorschlaege(
    body: VorschlaegeUebernehmenIn,
    con: sqlite3.Connection = Depends(db_dep),
    bereich: BereichDep = Bereich(1),
):
    # Alle expliziten Kennungen pruefen, bevor die erste Einzelbuchung committet.
    for umsatz_id in body.umsatz_ids:
        pruefe_umsatz(con, umsatz_id, bereich)
    verbucht = 0
    uebersprungen = 0
    for umsatz_id in body.umsatz_ids:
        umsatz = con.execute(
            "SELECT * FROM bankumsatz WHERE id = ? AND importstatus = 'offen'",
            (umsatz_id,),
        ).fetchone()
        if not umsatz:
            uebersprungen += 1
            continue
        vorschlag = _vorschlag_fuer_umsatz(
            con, dict(umsatz), aktive_regeln(con, bereich.id),
        )
        if not vorschlag:
            uebersprungen += 1
            continue
        try:
            verbuche_umsatz(
                umsatz_id,
                UmsatzVerbuchenIn(
                    sparte_id=vorschlag["sparte_id"],
                    kategorie_id=vorschlag["kategorie_id"],
                    typ=vorschlag["typ"],
                ),
                con,
                bereich,
            )
            verbucht += 1
        except (HTTPException, sqlite3.Error):
            con.rollback()
            uebersprungen += 1
    return {"verbucht": verbucht, "uebersprungen": uebersprungen}


# ---------------------------------------------------------------------------
# Umsatz uebernehmen / ignorieren
# ---------------------------------------------------------------------------

@router.post("/bankumsaetze/{umsatz_id}/verbuchen", status_code=201)
def verbuche_umsatz(umsatz_id: int, body: UmsatzVerbuchenIn,
                    con: sqlite3.Connection = Depends(db_dep),
                       bereich: BereichDep = Bereich(1)):
    pruefe_umsatz(con, umsatz_id, bereich)
    pruefe_sparte(con, body.sparte_id, bereich)
    pruefe_kategorie(con, body.kategorie_id, bereich)
    u = con.execute("SELECT * FROM bankumsatz WHERE id = ?", (umsatz_id,)).fetchone()
    if not u:
        raise HTTPException(404, "Umsatz nicht gefunden")
    if u["importstatus"] == "verbucht":
        raise HTTPException(400, "Umsatz ist bereits verbucht")
    typ = body.typ or ("ausgabe" if u["betrag_cent"] < 0 else "einnahme")
    krow = con.execute(
        "SELECT sparte_id, richtung FROM kategorie WHERE id = ? AND aktiv = 1",
        (body.kategorie_id,),
    ).fetchone()
    if not krow:
        raise HTTPException(404, "Kategorie nicht gefunden")
    if krow["sparte_id"] != body.sparte_id:
        raise HTTPException(400, "Kategorie gehoert nicht zur gewaehlten Sparte")
    if typ == "umbuchung" and krow["richtung"] != "beides":
        raise HTTPException(
            400, "Umbuchung erfordert eine Kategorie mit Richtung 'beides'"
        )
    if typ in ("einnahme", "ausgabe") and krow["richtung"] not in (typ, "beides"):
        raise HTTPException(400, "Kategorie-Richtung passt nicht zum gewaehlten Typ")

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
        synchronisiere_buchung(con, buchung_id, bereich)
        regel_angelegt = False
        muster = _regel_text(u)
        if muster:
            vorhanden = con.execute(
                "SELECT id FROM regel WHERE LOWER(bedingung_text) = ? AND bereich_id = ? ORDER BY id LIMIT 1",
                (muster, bereich.id),
            ).fetchone()
            if vorhanden:
                con.execute(
                    "UPDATE regel SET name = ?, aktiv = 1, ziel_sparte_id = ?, "
                    "ziel_kategorie_id = ?, ziel_typ = ? WHERE id = ?",
                    (muster, body.sparte_id, body.kategorie_id, typ, vorhanden["id"]),
                )
            else:
                con.execute(
                    "INSERT INTO regel(name, bedingung_text, ziel_sparte_id, "
                    "ziel_kategorie_id, ziel_typ, bereich_id) VALUES(?,?,?,?,?,?)",
                    (muster, muster, body.sparte_id, body.kategorie_id, typ, bereich.id),
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
                       con: sqlite3.Connection = Depends(db_dep),
                       bereich: BereichDep = Bereich(1)):
    pruefe_umsatz(con, umsatz_id, bereich)
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
