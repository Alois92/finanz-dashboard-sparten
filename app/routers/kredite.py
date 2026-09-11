"""Kreditstammdaten, Jahreszinsbestaetigungen und Kreditraten."""
import sqlite3
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ..schemas import BETRAG_CENT_MAX
from ..bereiche import (Bereich, BereichDep, pruefe_beleg, pruefe_buchung,
                        pruefe_kategorie, pruefe_konto, pruefe_sparte, pruefe_umsatz)
from ..bewegungen import synchronisiere_buchung
from ..db import db_dep
from ..kredite import verteile_zins

router = APIRouter(tags=["kredite"])


class KreditIn(BaseModel):
    sparte_id: int
    konto_id: int | None = None
    name: str = Field(min_length=1)
    monatsrate_cent: int = Field(gt=0, le=BETRAG_CENT_MAX, strict=True)
    zinssatz: float | None = None
    beginn: date
    kategorie_zins_id: int
    kategorie_rate_id: int


class KreditPatch(BaseModel):
    sparte_id: int | None = None
    konto_id: int | None = None
    name: str | None = Field(default=None, min_length=1)
    monatsrate_cent: int | None = Field(default=None, gt=0, le=BETRAG_CENT_MAX, strict=True)
    zinssatz: float | None = None
    beginn: date | None = None
    kategorie_zins_id: int | None = None
    kategorie_rate_id: int | None = None
    aktiv: int | None = Field(default=None, ge=0, le=1, strict=True)


class JahreszinsIn(BaseModel):
    zins_cent: int = Field(ge=0, le=BETRAG_CENT_MAX, strict=True)
    restschuld_cent: int | None = Field(default=None, ge=0, le=BETRAG_CENT_MAX, strict=True)
    beleg_id: int | None = None


class RateIn(BaseModel):
    datum: date
    betrag_cent: int | None = Field(default=None, gt=0, le=BETRAG_CENT_MAX, strict=True)
    bankumsatz_id: int | None = None
    client_request_id: str | None = None


class ZuordnenIn(BaseModel):
    buchung_ids: list[int] = Field(min_length=1)


def _kredit(con, kredit_id: int, bereich: Bereich):
    row = con.execute(
        "SELECT * FROM kredit k JOIN sparte s ON s.id=k.sparte_id "
        "WHERE k.id=? AND s.bereich_id=?", (kredit_id, bereich.id)
    ).fetchone()
    if row is None:
        raise HTTPException(404, "Kredit nicht gefunden")
    return row


def _pruefe_kredit_referenzen(con, daten: dict, bereich: Bereich) -> None:
    pruefe_sparte(con, daten["sparte_id"], bereich)
    for feld in ("kategorie_zins_id", "kategorie_rate_id"):
        pruefe_kategorie(con, daten[feld], bereich)
        row = con.execute("SELECT sparte_id FROM kategorie WHERE id=?", (daten[feld],)).fetchone()
        if row[0] != daten["sparte_id"]:
            raise HTTPException(422, "Kategorie gehoert nicht zur Sparte des Kredits")
    if daten.get("konto_id") is not None:
        pruefe_konto(con, daten["konto_id"], bereich)
        konto = con.execute("SELECT sparte_id FROM bankkonto WHERE id=?", (daten["konto_id"],)).fetchone()
        if konto[0] not in (None, daten["sparte_id"]):
            raise HTTPException(422, "Konto gehoert nicht zur Sparte des Kredits")


def _jahresstatus(con, kredit_id: int, jahr: int):
    row = con.execute(
        "SELECT status, zins_cent FROM kredit_jahr WHERE kredit_id=? AND jahr=?",
        (kredit_id, jahr),
    ).fetchone()
    return (row["status"], row["zins_cent"]) if row else ("geschaetzt", 0)


def _raten(con, kredit_id: int, jahr: int | None = None):
    sql = """SELECT b.id, b.kredit_id, b.datum, b.betrag_cent,
                     COALESCE((SELECT z.betrag_cent FROM buchungszeile z
                               WHERE z.buchung_id=b.id AND z.neutral=0 LIMIT 1), 0) zins_cent,
                     COALESCE((SELECT z.betrag_cent FROM buchungszeile z
                               WHERE z.buchung_id=b.id AND z.neutral=1 LIMIT 1), 0) tilgung_cent
              FROM buchung b WHERE b.kredit_id=?"""
    params: list = [kredit_id]
    if jahr is not None:
        sql += " AND strftime('%Y', b.datum)=?"
        params.append(str(jahr))
    sql += " ORDER BY b.datum, b.id"
    rows = []
    for row in con.execute(sql, params):
        status, _ = _jahresstatus(con, kredit_id, int(row["datum"][:4]))
        item = dict(row)
        item["status"] = status
        rows.append(item)
    return rows


def _listeintrag(con, row):
    return {
        "id": row["id"], "name": row["name"], "sparte_id": row["sparte_id"],
        "monatsrate_cent": row["monatsrate_cent"], "beginn": row["beginn"],
        "kategorie_zins_id": row["kategorie_zins_id"], "kategorie_rate_id": row["kategorie_rate_id"],
        "jahre": [dict(j) for j in con.execute(
            "SELECT jahr, zins_cent, restschuld_cent, status FROM kredit_jahr "
            "WHERE kredit_id=? ORDER BY jahr", (row["id"],)
        )],
    }


@router.get("/kredite")
def list_kredite(con=Depends(db_dep), bereich: BereichDep = Bereich(1)):
    rows = con.execute(
        "SELECT k.* FROM kredit k JOIN sparte s ON s.id=k.sparte_id "
        "WHERE s.bereich_id=? ORDER BY k.id", (bereich.id,)
    ).fetchall()
    return [_listeintrag(con, row) for row in rows]


@router.post("/kredite", status_code=201)
def create_kredit(k: KreditIn, con=Depends(db_dep), bereich: BereichDep = Bereich(1)):
    daten = k.model_dump()
    daten["beginn"] = daten["beginn"].isoformat()
    _pruefe_kredit_referenzen(con, daten, bereich)
    if not k.name.strip():
        raise HTTPException(422, "Name darf nicht leer sein")
    with con:
        kredit_id = con.execute(
            "INSERT INTO kredit(sparte_id,konto_id,name,monatsrate_cent,zinssatz,beginn,"
            "kategorie_zins_id,kategorie_rate_id) VALUES(?,?,?,?,?,?,?,?)",
            tuple(daten[field] for field in (
                "sparte_id", "konto_id", "name", "monatsrate_cent", "zinssatz", "beginn",
                "kategorie_zins_id", "kategorie_rate_id")),
        ).lastrowid
    return _listeintrag(con, con.execute("SELECT * FROM kredit WHERE id=?", (kredit_id,)).fetchone())


@router.patch("/kredite/{kredit_id}")
def patch_kredit(kredit_id: int, patch: KreditPatch, con=Depends(db_dep), bereich: BereichDep = Bereich(1)):
    alt = _kredit(con, kredit_id, bereich)
    daten = patch.model_dump(exclude_unset=True)
    if not daten:
        return _listeintrag(con, alt)
    neu = dict(alt)
    neu.update(daten)
    if isinstance(neu["beginn"], date):
        neu["beginn"] = neu["beginn"].isoformat()
    _pruefe_kredit_referenzen(con, neu, bereich)
    if "name" in daten and not neu["name"].strip():
        raise HTTPException(422, "Name darf nicht leer sein")
    with con:
        con.execute(
            "UPDATE kredit SET " + ",".join(f"{feld}=?" for feld in daten) + " WHERE id=?",
            (*[neu[feld] for feld in daten], kredit_id),
        )
    return _listeintrag(con, con.execute("SELECT * FROM kredit WHERE id=?", (kredit_id,)).fetchone())


@router.put("/kredite/{kredit_id}/jahre/{jahr}")
def confirm_year(kredit_id: int, jahr: int, data: JahreszinsIn,
                 con=Depends(db_dep), bereich: BereichDep = Bereich(1)):
    kredit = _kredit(con, kredit_id, bereich)
    if data.beleg_id is not None:
        pruefe_beleg(con, data.beleg_id, bereich)
    rates = _raten(con, kredit_id, jahr)
    if not rates:
        abweichungen = [f"Keine Raten im Jahr {jahr}"]
        with con:
            con.execute(
                "INSERT INTO kredit_jahr(kredit_id,jahr,zins_cent,restschuld_cent,status,beleg_id) "
                "VALUES(?,?,?,?, 'bestaetigt',?) ON CONFLICT(kredit_id,jahr) DO UPDATE SET "
                "zins_cent=excluded.zins_cent, restschuld_cent=excluded.restschuld_cent, "
                "status='bestaetigt', beleg_id=excluded.beleg_id, aktualisiert_am=datetime('now')",
                (kredit_id, jahr, data.zins_cent, data.restschuld_cent, data.beleg_id),
            )
        return {"raten": 0, "verteilt_cent": 0, "abweichungen": abweichungen}
    zinsen = verteile_zins(data.zins_cent, len(rates))
    abweichungen = []
    if len(rates) != 12:
        abweichungen.append(f"{len(rates)} Raten im Jahr {jahr} statt 12")
    if any(rate["betrag_cent"] != kredit["monatsrate_cent"] for rate in rates):
        abweichungen.append("Ratenbetrag weicht von der Monatsrate ab")
    with con:
        con.execute(
            "INSERT INTO kredit_jahr(kredit_id,jahr,zins_cent,restschuld_cent,status,beleg_id) "
            "VALUES(?,?,?,?, 'bestaetigt',?) ON CONFLICT(kredit_id,jahr) DO UPDATE SET "
            "zins_cent=excluded.zins_cent, restschuld_cent=excluded.restschuld_cent, "
            "status='bestaetigt', beleg_id=excluded.beleg_id, aktualisiert_am=datetime('now')",
            (kredit_id, jahr, data.zins_cent, data.restschuld_cent, data.beleg_id),
        )
        for rate, zins in zip(rates, zinsen):
            tilgung = rate["betrag_cent"] - zins
            if tilgung < 0:
                raise HTTPException(422, "Jahreszins ist groesser als eine Rate")
            con.execute(
                "UPDATE buchungszeile SET betrag_cent=? WHERE buchung_id=? AND neutral=0",
                (zins, rate["id"]),
            )
            con.execute(
                "UPDATE buchungszeile SET betrag_cent=? WHERE buchung_id=? AND neutral=1",
                (tilgung, rate["id"]),
            )
    return {"raten": len(rates), "verteilt_cent": sum(zinsen), "abweichungen": abweichungen}


def _rate_schaetzung(con, kredit, jahr: int) -> tuple[int, str]:
    row = con.execute(
        "SELECT zins_cent, jahr FROM kredit_jahr WHERE kredit_id=? AND jahr<? "
        "AND status='bestaetigt' ORDER BY jahr DESC LIMIT 1", (kredit["id"], jahr)
    ).fetchone()
    if row:
        anzahl = con.execute(
            "SELECT count(*) FROM buchung WHERE kredit_id=? AND strftime('%Y',datum)=?",
            (kredit["id"], str(row["jahr"])),
        ).fetchone()[0]
        return (row["zins_cent"] // anzahl if anzahl else 0), "geschaetzt"
    if kredit["zinssatz"] is not None:
        rest = con.execute(
            "SELECT restschuld_cent FROM kredit_jahr WHERE kredit_id=? AND restschuld_cent IS NOT NULL "
            "ORDER BY jahr DESC LIMIT 1", (kredit["id"],)
        ).fetchone()
        if rest:
            return int(round(kredit["zinssatz"] * rest[0] / 12)), "geschaetzt"
    return 0, "geschaetzt"


@router.post("/kredite/{kredit_id}/raten", status_code=201)
def create_rate(kredit_id: int, data: RateIn, con=Depends(db_dep), bereich: BereichDep = Bereich(1)):
    kredit = _kredit(con, kredit_id, bereich)
    if data.bankumsatz_id is not None:
        pruefe_umsatz(con, data.bankumsatz_id, bereich)
        umsatz = con.execute(
            "SELECT bankkonto_id, betrag_cent FROM bankumsatz WHERE id=?",
            (data.bankumsatz_id,),
        ).fetchone()
        if kredit["konto_id"] is not None and umsatz["bankkonto_id"] != kredit["konto_id"]:
            raise HTTPException(422, "Bankumsatz gehoert nicht zum Kreditkonto")
        amount = data.betrag_cent or abs(umsatz["betrag_cent"])
    else:
        amount = data.betrag_cent or kredit["monatsrate_cent"]
    zins, status = _rate_schaetzung(con, kredit, data.datum.year)
    jahr_status, jahreszins = _jahresstatus(con, kredit_id, data.datum.year)
    if jahr_status == "bestaetigt":
        bisher = con.execute(
            "SELECT count(*) FROM buchung WHERE kredit_id=? AND strftime('%Y',datum)=?",
            (kredit_id, str(data.datum.year)),
        ).fetchone()[0]
        zins = verteile_zins(jahreszins, bisher + 1)[-1]
        status = "bestaetigt"
    if zins > amount:
        raise HTTPException(422, "Geschaetzter Zins ist groesser als die Rate")
    tilgung = amount - zins
    with con:
        bid = con.execute(
            "INSERT INTO buchung(sparte_id,datum,typ,betrag_cent,bankkonto_id,zahlungsart,"
            "buchungsstatus,text,notiz,bankumsatz_id,kredit_id) VALUES(?,?, 'ausgabe', ?, ?, 'bank', 'zugeordnet', ?, NULL, ?, ?)",
            (kredit["sparte_id"], data.datum.isoformat(), amount, kredit["konto_id"],
             kredit["name"], data.bankumsatz_id, kredit_id),
        ).lastrowid
        con.execute(
            "INSERT INTO buchungszeile(buchung_id,kategorie_id,betrag_cent,neutral) VALUES(?,?,?,0)",
            (bid, kredit["kategorie_zins_id"], zins),
        )
        con.execute(
            "INSERT INTO buchungszeile(buchung_id,kategorie_id,betrag_cent,neutral) VALUES(?,?,?,1)",
            (bid, kredit["kategorie_rate_id"], tilgung),
        )
        synchronisiere_buchung(con, bid, bereich)
        con.execute(
            "INSERT OR IGNORE INTO kredit_jahr(kredit_id,jahr,zins_cent,status) VALUES(?,?,?,'geschaetzt')",
            (kredit_id, data.datum.year, zins * 12),
        )
        if status == "bestaetigt":
            rates = _raten(con, kredit_id, data.datum.year)
            for rate, rate_zins in zip(rates, verteile_zins(jahreszins, len(rates))):
                con.execute(
                    "UPDATE buchungszeile SET betrag_cent=? WHERE buchung_id=? AND neutral=0",
                    (rate_zins, rate["id"]),
                )
                con.execute(
                    "UPDATE buchungszeile SET betrag_cent=? WHERE buchung_id=? AND neutral=1",
                    (rate["betrag_cent"] - rate_zins, rate["id"]),
                )
    return {"id": bid, "kredit_id": kredit_id, "datum": data.datum.isoformat(), "betrag_cent": amount,
            "zins_cent": zins, "tilgung_cent": tilgung, "status": status,
            "hinweis": None if zins else "Zinsanteil unbekannt, ganze Rate vorlaeufig als Tilgung"}


@router.get("/kredite/{kredit_id}/raten")
def list_rates(kredit_id: int, jahr: int | None = Query(default=None),
               con=Depends(db_dep), bereich: BereichDep = Bereich(1)):
    _kredit(con, kredit_id, bereich)
    return _raten(con, kredit_id, jahr)


@router.post("/kredite/{kredit_id}/raten/zuordnen")
def assign_rates(kredit_id: int, data: ZuordnenIn,
                 con=Depends(db_dep), bereich: BereichDep = Bereich(1)):
    kredit = _kredit(con, kredit_id, bereich)
    ids = list(dict.fromkeys(data.buchung_ids))
    for bid in ids:
        pruefe_buchung(con, bid, bereich)
        row = con.execute("SELECT * FROM buchung WHERE id=?", (bid,)).fetchone()
        if row["sparte_id"] != kredit["sparte_id"] or row["typ"] != "ausgabe":
            raise HTTPException(422, "Buchung ist keine Ausgabe der Kreditsparte")
        zeilen = con.execute(
            "SELECT COUNT(*) FROM buchungszeile WHERE buchung_id=?", (bid,)
        ).fetchone()[0]
        if zeilen > 1:
            raise HTTPException(
                422, "Buchung enthaelt weitere Positionen, bitte zuerst aufteilen"
            )
        total = con.execute(
            "SELECT COALESCE(SUM(betrag_cent),0) FROM buchungszeile WHERE buchung_id=? AND kategorie_id=?",
            (bid, kredit["kategorie_rate_id"]),
        ).fetchone()[0]
        if total <= 0:
            raise HTTPException(422, "Buchung enthaelt nicht die Ratekategorie")
    with con:
        for bid in ids:
            total = con.execute(
                "SELECT COALESCE(SUM(betrag_cent),0) FROM buchungszeile WHERE buchung_id=?",
                (bid,),
            ).fetchone()[0]
            con.execute("DELETE FROM buchungszeile WHERE buchung_id=?", (bid,))
            con.execute(
                "INSERT INTO buchungszeile(buchung_id,kategorie_id,betrag_cent,neutral) VALUES(?,?,?,0)",
                (bid, kredit["kategorie_zins_id"], 0),
            )
            con.execute(
                "INSERT INTO buchungszeile(buchung_id,kategorie_id,betrag_cent,neutral) VALUES(?,?,?,1)",
                (bid, kredit["kategorie_rate_id"], total),
            )
            con.execute("UPDATE buchung SET kredit_id=? WHERE id=?", (kredit_id, bid))
    return {"raten": len(ids), "buchung_ids": ids}


@router.post("/kredite/{kredit_id}/raten/loesen")
def release_rates(kredit_id: int, data: ZuordnenIn,
                  con=Depends(db_dep), bereich: BereichDep = Bereich(1)):
    _kredit(con, kredit_id, bereich)
    ids = list(dict.fromkeys(data.buchung_ids))
    for bid in ids:
        pruefe_buchung(con, bid, bereich)
        row = con.execute("SELECT kredit_id FROM buchung WHERE id=?", (bid,)).fetchone()
        if row["kredit_id"] != kredit_id:
            raise HTTPException(422, "Buchung ist diesem Kredit nicht zugeordnet")
    with con:
        for bid in ids:
            con.execute("UPDATE buchung SET kredit_id=NULL WHERE id=?", (bid,))
    return {"raten": len(ids), "buchung_ids": ids}
