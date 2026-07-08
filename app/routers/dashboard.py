"""Dashboard: Kennzahlen auf Basis von v_einnahmen_ausgaben (Umbuchungen ausgeblendet)."""
import sqlite3

from fastapi import APIRouter, Depends

from ..db import db_dep

router = APIRouter(tags=["dashboard"])


def _where(sparte_id, von, bis):
    sql, params = " WHERE 1=1", []
    if sparte_id is not None:
        sql += " AND v.sparte_id = ?"; params.append(sparte_id)
    if von:
        sql += " AND v.datum >= ?"; params.append(von)
    if bis:
        sql += " AND v.datum <= ?"; params.append(bis)
    return sql, params


@router.get("/dashboard")
def dashboard(sparte_id: int | None = None,
              von: str | None = None,
              bis: str | None = None,
              con: sqlite3.Connection = Depends(db_dep)):
    where, params = _where(sparte_id, von, bis)

    summe = con.execute(
        "SELECT "
        "COALESCE(SUM(CASE WHEN v.typ='einnahme' THEN v.betrag_cent END),0) AS einnahmen_cent, "
        "COALESCE(SUM(CASE WHEN v.typ='ausgabe'  THEN v.betrag_cent END),0) AS ausgaben_cent "
        "FROM v_einnahmen_ausgaben v" + where,
        params,
    ).fetchone()
    einnahmen = summe["einnahmen_cent"]
    ausgaben = summe["ausgaben_cent"]

    per_kategorie = [dict(r) for r in con.execute(
        "SELECT k.name AS kategorie, v.typ, SUM(v.betrag_cent) AS betrag_cent "
        "FROM v_einnahmen_ausgaben v JOIN kategorie k ON k.id = v.kategorie_id" + where +
        " GROUP BY k.id, v.typ ORDER BY betrag_cent DESC",
        params,
    ).fetchall()]

    per_sparte = [dict(r) for r in con.execute(
        "SELECT s.name AS sparte, "
        "COALESCE(SUM(CASE WHEN v.typ='einnahme' THEN v.betrag_cent END),0) AS einnahmen_cent, "
        "COALESCE(SUM(CASE WHEN v.typ='ausgabe'  THEN v.betrag_cent END),0) AS ausgaben_cent "
        "FROM v_einnahmen_ausgaben v JOIN sparte s ON s.id = v.sparte_id" + where +
        " GROUP BY s.id ORDER BY s.sortierung",
        params,
    ).fetchall()]

    return {
        "einnahmen_cent": einnahmen,
        "ausgaben_cent": ausgaben,
        "saldo_cent": einnahmen - ausgaben,
        "per_kategorie": per_kategorie,
        "per_sparte": per_sparte,
    }
