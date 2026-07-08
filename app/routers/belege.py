"""Belege: Upload (mit Dublettenschutz), Liste, Download, Loeschen und
Verknuepfung mit Buchungen. Grundlage fuer den Eingangskorb.

Dateiablage: ``DB_PATH.parent / "belege" / <sparte_id oder "ohne">``.
So folgt die Ablage automatisch dem DB-Speicherort und bleibt bei der
temporaeren Test-DB ebenfalls ephemer.
"""
import hashlib
import mimetypes
import pathlib
import sqlite3

from fastapi import (APIRouter, Depends, File, Form, HTTPException, UploadFile)
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ..db import DB_PATH, db_dep

router = APIRouter(tags=["belege"])

# Nur Bilder und PDF zulassen (Endung, klein geschrieben, ohne Punkt).
ERLAUBTE_ENDUNGEN = {"jpg", "jpeg", "png", "heic", "webp", "pdf"}

# Fallback-Medientypen fuer Endungen, die mimetypes evtl. nicht kennt (z. B. HEIC).
MEDIENTYP_FALLBACK = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "heic": "image/heic",
    "webp": "image/webp",
    "pdf": "application/pdf",
}


class BelegVerknuepfung(BaseModel):
    beleg_id: int


def _belege_verzeichnis(sparte_id: int | None) -> pathlib.Path:
    """Zielordner fuer die physische Ablage; legt ihn bei Bedarf an."""
    unterordner = str(sparte_id) if sparte_id is not None else "ohne"
    ziel = DB_PATH.parent / "belege" / unterordner
    ziel.mkdir(parents=True, exist_ok=True)
    return ziel


def _endung(dateiname: str) -> str:
    return pathlib.Path(dateiname).suffix.lower().lstrip(".")


def _medientyp(dateiname: str) -> str:
    endung = _endung(dateiname)
    typ, _ = mimetypes.guess_type(dateiname)
    return typ or MEDIENTYP_FALLBACK.get(endung, "application/octet-stream")


@router.post("/belege", status_code=201)
def upload_beleg(
    datei: UploadFile = File(...),
    sparte_id: int | None = Form(None),
    con: sqlite3.Connection = Depends(db_dep),
):
    original = datei.filename or "unbenannt"
    endung = _endung(original)
    if endung not in ERLAUBTE_ENDUNGEN:
        raise HTTPException(
            400,
            f"Dateityp '.{endung}' nicht erlaubt. Zulaessig: "
            f"{', '.join(sorted(ERLAUBTE_ENDUNGEN))}",
        )

    if sparte_id is not None and not con.execute(
        "SELECT 1 FROM sparte WHERE id = ?", (sparte_id,)
    ).fetchone():
        raise HTTPException(404, "Sparte nicht gefunden")

    inhalt = datei.file.read()
    sha256 = hashlib.sha256(inhalt).hexdigest()

    # Dublettenschutz: existiert bereits ein Beleg mit gleichem Hash,
    # geben wir den vorhandenen zurueck (kein Doppel, keine neue Datei).
    vorhanden = con.execute(
        "SELECT id, dateiname, sparte_id, sha256_hash, pfad FROM beleg "
        "WHERE sha256_hash = ?",
        (sha256,),
    ).fetchone()
    if vorhanden:
        result = dict(vorhanden)
        result["dublette"] = True
        return result

    # Zuerst die Zeile anlegen, um eine eindeutige ID fuer den Dateinamen zu
    # bekommen; danach die Datei physisch schreiben und den Pfad nachtragen.
    try:
        cur = con.execute(
            "INSERT INTO beleg(sparte_id, dateiname, pfad, sha256_hash) "
            "VALUES(?,?,?,?)",
            (sparte_id, original, "", sha256),
        )
        beleg_id = cur.lastrowid

        ziel = _belege_verzeichnis(sparte_id) / f"{beleg_id}_{original}"
        ziel.write_bytes(inhalt)

        con.execute(
            "UPDATE beleg SET pfad = ? WHERE id = ?", (str(ziel), beleg_id)
        )
        con.commit()
    except sqlite3.IntegrityError as e:
        con.rollback()
        # Das aktuelle DB-Schema (db/schema.sql, anderer Track) erzwingt
        # beleg.sparte_id NOT NULL. Ein echter Eingangskorb ohne Sparte ist
        # damit (noch) nicht speicherbar; sobald die Spalte NULL zulaesst,
        # funktioniert dieser Pfad unveraendert.
        if sparte_id is None:
            raise HTTPException(
                400,
                "Upload ohne sparte_id derzeit nicht moeglich: Das DB-Schema "
                "verlangt eine Sparte (beleg.sparte_id NOT NULL). Bitte "
                "sparte_id angeben.",
            )
        raise HTTPException(400, f"Datenbankfehler: {e}")

    return {
        "id": beleg_id,
        "dateiname": original,
        "sparte_id": sparte_id,
        "sha256_hash": sha256,
        "pfad": str(ziel),
        "dublette": False,
    }


@router.get("/belege")
def list_belege(
    sparte_id: int | None = None,
    con: sqlite3.Connection = Depends(db_dep),
):
    sql = (
        "SELECT id, dateiname, sparte_id, belegdatum, betrag_erkannt_cent, "
        "sha256_hash FROM beleg WHERE 1=1"
    )
    params: list = []
    if sparte_id is not None:
        sql += " AND sparte_id = ?"
        params.append(sparte_id)
    sql += " ORDER BY id DESC"
    return [dict(r) for r in con.execute(sql, params).fetchall()]


@router.get("/belege/{beleg_id}/datei")
def download_beleg(beleg_id: int, con: sqlite3.Connection = Depends(db_dep)):
    row = con.execute(
        "SELECT dateiname, pfad FROM beleg WHERE id = ?", (beleg_id,)
    ).fetchone()
    if not row:
        raise HTTPException(404, "Beleg nicht gefunden")
    pfad = pathlib.Path(row["pfad"])
    if not pfad.exists():
        raise HTTPException(404, "Belegdatei nicht gefunden")
    return FileResponse(
        pfad, media_type=_medientyp(row["dateiname"]), filename=row["dateiname"]
    )


@router.delete("/belege/{beleg_id}", status_code=204)
def delete_beleg(beleg_id: int, con: sqlite3.Connection = Depends(db_dep)):
    row = con.execute(
        "SELECT pfad FROM beleg WHERE id = ?", (beleg_id,)
    ).fetchone()
    if not row:
        raise HTTPException(404, "Beleg nicht gefunden")
    con.execute("DELETE FROM beleg WHERE id = ?", (beleg_id,))  # Verknuepfungen via CASCADE
    con.commit()
    # Datei nach erfolgreichem DB-Loeschen entfernen (falls vorhanden).
    if row["pfad"]:
        pfad = pathlib.Path(row["pfad"])
        if pfad.exists():
            pfad.unlink()


# ---------------------------------------------------------------------------
# Verknuepfung Buchung <-> Beleg (n:m ueber buchung_beleg)
# ---------------------------------------------------------------------------


@router.post("/buchungen/{buchung_id}/belege", status_code=201)
def verknuepfe_beleg(
    buchung_id: int,
    body: BelegVerknuepfung,
    con: sqlite3.Connection = Depends(db_dep),
):
    if not con.execute(
        "SELECT 1 FROM buchung WHERE id = ?", (buchung_id,)
    ).fetchone():
        raise HTTPException(404, "Buchung nicht gefunden")
    if not con.execute(
        "SELECT 1 FROM beleg WHERE id = ?", (body.beleg_id,)
    ).fetchone():
        raise HTTPException(404, "Beleg nicht gefunden")

    # Idempotent: bei bereits bestehender Verknuepfung kein Fehler.
    con.execute(
        "INSERT OR IGNORE INTO buchung_beleg(buchung_id, beleg_id) VALUES(?,?)",
        (buchung_id, body.beleg_id),
    )
    con.commit()
    return {"buchung_id": buchung_id, "beleg_id": body.beleg_id, "verknuepft": True}


@router.delete(
    "/buchungen/{buchung_id}/belege/{beleg_id}", status_code=204
)
def loese_verknuepfung(
    buchung_id: int,
    beleg_id: int,
    con: sqlite3.Connection = Depends(db_dep),
):
    con.execute(
        "DELETE FROM buchung_beleg WHERE buchung_id = ? AND beleg_id = ?",
        (buchung_id, beleg_id),
    )
    con.commit()


@router.get("/buchungen/{buchung_id}/belege")
def belege_der_buchung(
    buchung_id: int, con: sqlite3.Connection = Depends(db_dep)
):
    if not con.execute(
        "SELECT 1 FROM buchung WHERE id = ?", (buchung_id,)
    ).fetchone():
        raise HTTPException(404, "Buchung nicht gefunden")
    rows = con.execute(
        "SELECT b.id, b.dateiname, b.sparte_id, b.belegdatum, "
        "b.betrag_erkannt_cent, b.sha256_hash "
        "FROM beleg b JOIN buchung_beleg bb ON bb.beleg_id = b.id "
        "WHERE bb.buchung_id = ? ORDER BY b.id DESC",
        (buchung_id,),
    ).fetchall()
    return [dict(r) for r in rows]
