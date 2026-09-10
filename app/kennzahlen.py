"""Berechnung eigener Kennzahlen aus den Buchungszeilen."""
import sqlite3

from .rechenbasis import Filter, where_zeilen, stichtag_heute


def _filter(jahr, filter):
    values = dict(filter or {})
    values['jahr'] = jahr
    if not values.get('bis') and jahr == int(stichtag_heute()[:4]):
        values.setdefault('stichtag', stichtag_heute())
    return Filter(**{key: value for key, value in values.items() if key in Filter.__dataclass_fields__})


def wert(con: sqlite3.Connection, kennzahl_id: int, jahr: int, filter: dict | None = None) -> int:
    where, params = where_zeilen(con, _filter(jahr, filter))
    return con.execute(
        "SELECT COALESCE(SUM(t.vorzeichen * CASE "
        "WHEN t.messgroesse='einnahmen' AND v.typ='einnahme' THEN v.betrag_cent "
        "WHEN t.messgroesse='ausgaben' AND v.typ='ausgabe' THEN v.betrag_cent "
        "WHEN t.messgroesse='netto' THEN v.betrag_signed_cent ELSE 0 END),0) "
        "FROM kennzahl_term t JOIN v_einnahmen_ausgaben v ON v.kategorie_id=t.kategorie_id" +
        where + ' AND t.kennzahl_id=?', [*params, kennzahl_id]).fetchone()[0]


def monate_mit_daten(con, kennzahl_id: int, jahr: int, filter: dict | None = None) -> int:
    where, params = where_zeilen(con, _filter(jahr, filter))
    return con.execute(
        "SELECT COUNT(DISTINCT substr(v.datum,1,7)) FROM kennzahl_term t "
        "JOIN v_einnahmen_ausgaben v ON v.kategorie_id=t.kategorie_id" +
        where + ' AND t.kennzahl_id=?', [*params, kennzahl_id]).fetchone()[0]
