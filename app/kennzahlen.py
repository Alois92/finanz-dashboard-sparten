"""Berechnung eigener Kennzahlen aus den Buchungszeilen."""
import datetime as dt
import sqlite3


def _zeilen(con, kennzahl_id, jahr, filter_, term_id=None):
    sql = (
        "SELECT v.datum, v.typ, v.betrag_cent FROM kennzahl_term t "
        "JOIN v_einnahmen_ausgaben v ON v.kategorie_id=t.kategorie_id "
        "JOIN buchung b ON b.id=v.buchung_id "
        "JOIN sparte s ON s.id=b.sparte_id "
        "WHERE t.kennzahl_id=? AND strftime('%Y', v.datum)=? AND s.bereich_id=?"
    )
    params = [kennzahl_id, str(jahr), filter_.get("bereich_id", 1)]
    if term_id is not None:
        sql += " AND t.id=?"; params.append(term_id)
    if filter_.get("sparte_id") is not None:
        sql += " AND b.sparte_id=?"; params.append(filter_["sparte_id"])
    if filter_.get("von"):
        sql += " AND v.datum>=?"; params.append(filter_["von"])
    bis = filter_.get("bis")
    if bis:
        sql += " AND v.datum<=?"; params.append(bis)
    elif int(jahr) == dt.date.today().year:
        sql += " AND v.datum<=?"; params.append(dt.date.today().isoformat())
    if filter_.get("kategorie_id") is not None:
        sql += " AND v.kategorie_id=?"; params.append(filter_["kategorie_id"])
    return con.execute(sql, params).fetchall()


def wert(con: sqlite3.Connection, kennzahl_id: int, jahr: int, filter: dict | None = None) -> int:
    filter = dict(filter or {})
    terms = con.execute(
        "SELECT id, kategorie_id, messgroesse, vorzeichen FROM kennzahl_term WHERE kennzahl_id=?",
        (kennzahl_id,),
    ).fetchall()
    total = 0
    for term in terms:
        rows = [row for row in _zeilen(
            con, kennzahl_id, jahr,
            {**filter, "kategorie_id": term["kategorie_id"]}, term["id"]
        )]
        if term["messgroesse"] == "einnahmen":
            basis = sum(r["betrag_cent"] for r in rows if r["typ"] == "einnahme")
        elif term["messgroesse"] == "ausgaben":
            basis = sum(r["betrag_cent"] for r in rows if r["typ"] == "ausgabe")
        else:
            basis = sum(r["betrag_cent"] for r in rows if r["typ"] == "einnahme") - sum(
                r["betrag_cent"] for r in rows if r["typ"] == "ausgabe"
            )
        total += term["vorzeichen"] * basis
    return total


def monate_mit_daten(con, kennzahl_id: int, jahr: int, filter: dict | None = None) -> int:
    rows = _zeilen(con, kennzahl_id, jahr, dict(filter or {}))
    return len({row["datum"][:7] for row in rows})
