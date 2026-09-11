"""XLSX-Export und druckoptimierter Jahresbericht."""
import datetime as dt
import hashlib
import html
import io
import pathlib
import re
import sqlite3
import zipfile
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from pydantic import BaseModel, Field
from ..db import db_dep
from ..bereiche import (Bereich, BereichDep, pruefe_buchung, pruefe_kategorie,
                        pruefe_sparte, sparten_ids)

router = APIRouter(tags=["export"])
EURO_FORMAT = '#.##0,00 \u20ac'

def _xlsx_text(value):
    """Schreibt nutzerkontrollierte Texte als Literal statt als Excel-Formel."""
    text = "" if value is None else str(value)
    if text.startswith(("=", "+", "-", "@")):
        return "'" + text
    return text


def _validate(con, von=None, bis=None, sparte_id=None):
    dates = []
    for value, field in ((von, "von"), (bis, "bis")):
        if not value:
            dates.append(None)
            continue
        try:
            dates.append(dt.date.fromisoformat(value).isoformat())
        except ValueError:
            raise HTTPException(400, f"{field} muss ein gueltiges Datum im Format JJJJ-MM-TT sein")
    von, bis = dates
    if von and bis and von > bis:
        raise HTTPException(400, "von darf nicht nach bis liegen")
    if sparte_id is not None and not con.execute(
            "SELECT 1 FROM sparte WHERE id=?", (sparte_id,)).fetchone():
        raise HTTPException(404, "Sparte nicht gefunden")
    return von, bis

def _where(von, bis, sparte_id, bereich, alias="v"):
    clauses = [f"{alias}.sparte_id IN (SELECT id FROM sparte WHERE bereich_id = ?)"]
    params = [bereich.id]
    for value, expression in ((von, f"{alias}.datum>=?"), (bis, f"{alias}.datum<=?"),
                              (sparte_id, f"{alias}.sparte_id=?")):
        if value is not None:
            clauses.append(expression)
            params.append(value)
    return (" WHERE " + " AND ".join(clauses) if clauses else ""), params

def _sheet(sheet, headers, widths, euro_from=None):
    sheet.insert_rows(1)
    for index, value in enumerate(headers, 1):
        sheet.cell(1, index, value)
    fill = PatternFill("solid", fgColor="1E6E4E")
    for cell in sheet[1]:
        cell.font = Font(color="FFFFFF", bold=True)
        cell.fill = fill
    sheet.freeze_panes = "A2"
    for index, width in enumerate(widths, 1):
        sheet.column_dimensions[chr(64 + index)].width = width
    if euro_from:
        for row in sheet.iter_rows(min_row=2):
            for index in range(euro_from, len(headers) + 1):
                row[index - 1].number_format = EURO_FORMAT
    sheet.auto_filter.ref = sheet.dimensions

@router.get("/api/export/xlsx")
def export_xlsx(von: str | None = None, bis: str | None = None,
                sparte_id: int | None = None, profil_id: int | None = None,
                con: sqlite3.Connection = Depends(db_dep), bereich: BereichDep = Bereich(1)):
    if profil_id is not None:
        profil = _profil(con, profil_id, bereich)
        rows = _auswahl_rows(con, profil, bereich)
        stream = io.BytesIO(_export_workbook(rows)); stream.seek(0)
        return StreamingResponse(stream,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": 'attachment; filename="finanz-export.xlsx"'})
    if sparte_id is not None:
        pruefe_sparte(con, sparte_id, bereich)
    von, bis = _validate(con, von, bis, sparte_id)
    where, params = _where(von, bis, sparte_id, bereich)
    rows = con.execute(
        "SELECT v.datum,s.name sparte,k.name kategorie,v.typ,COALESCE(b.text,'') text,"
        "COALESCE(ko.name,'') kontakt,v.betrag_cent FROM v_einnahmen_ausgaben v "
        "JOIN buchung b ON b.id=v.buchung_id JOIN sparte s ON s.id=v.sparte_id "
        "JOIN kategorie k ON k.id=v.kategorie_id LEFT JOIN kontakt ko ON ko.id=b.kontakt_id" +
        where + " ORDER BY v.datum,v.buchung_id,v.zeile_id", params).fetchall()
    months = con.execute(
        "SELECT strftime('%Y-%m',v.datum) monat,"
        "COALESCE(SUM(CASE WHEN v.typ='einnahme' THEN v.betrag_cent END),0) ein,"
        "COALESCE(SUM(CASE WHEN v.typ='ausgabe' THEN v.betrag_cent END),0) aus "
        "FROM v_einnahmen_ausgaben v" + where + " GROUP BY monat ORDER BY monat",
        params).fetchall()
    cats = con.execute(
        "SELECT s.name sparte,k.name kategorie,"
        "COALESCE(SUM(CASE WHEN v.typ='einnahme' THEN v.betrag_cent END),0) ein,"
        "COALESCE(SUM(CASE WHEN v.typ='ausgabe' THEN v.betrag_cent END),0) aus "
        "FROM v_einnahmen_ausgaben v JOIN sparte s ON s.id=v.sparte_id "
        "JOIN kategorie k ON k.id=v.kategorie_id" + where +
        " GROUP BY s.id,k.id ORDER BY s.sortierung,k.sortierung,k.name", params).fetchall()
    wb = Workbook(); bookings = wb.active; bookings.title = "Buchungen"
    skipped = 0
    for row in rows:
        try:
            bookings.append([_xlsx_text(row["datum"]), _xlsx_text(row["sparte"]),
                             _xlsx_text(row["kategorie"]), _xlsx_text(row["typ"]),
                             _xlsx_text(row["text"]), _xlsx_text(row["kontakt"]), row["betrag_cent"]/100])
        except (TypeError, ValueError):
            skipped += 1
    _sheet(bookings, ["Datum","Sparte","Kategorie","Typ","Text","Kontakt","Betrag \u20ac"],
           (12,24,28,12,36,24,16), 7)
    monthly = wb.create_sheet("Monatssummen")
    for row in months:
        income, expense = row["ein"] or 0, row["aus"] or 0
        monthly.append([row["monat"],income/100,expense/100,(income-expense)/100])
    _sheet(monthly, ["Monat","Einnahmen","Ausgaben","Saldo"], (14,18,18,18), 2)
    category = wb.create_sheet("Kategorien"); totals, overall = {}, [0, 0]
    for row in cats:
        income, expense = row["ein"] or 0, row["aus"] or 0
        category.append([_xlsx_text(row["sparte"]), _xlsx_text(row["kategorie"]),
                         income/100, expense/100, (income-expense)/100])
        total = totals.setdefault(row["sparte"], [0, 0])
        total[0] += income; total[1] += expense
        overall[0] += income; overall[1] += expense
    for name, (income, expense) in totals.items():
        category.append([_xlsx_text(name),"Gesamt",income/100,expense/100,(income-expense)/100])
    category.append(["Gesamt","Gesamt",overall[0]/100,overall[1]/100,
                     (overall[0]-overall[1])/100])
    _sheet(category, ["Sparte","Kategorie","Einnahmen","Ausgaben","Saldo"],
           (24,30,18,18,18), 3)
    wb.properties.description = f"Uebersprungene Datensaetze: {skipped}"
    stream = io.BytesIO(); wb.save(stream); stream.seek(0)
    return StreamingResponse(stream,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="finanz-export.xlsx"'})

def _euro(cents):
    value = f"{abs(cents)/100:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return ("-" if cents < 0 else "") + value + " \u20ac"

def _sums(con, start, end, sid, bereich):
    where, params = _where(start, end, sid, bereich)
    row = con.execute(
        "SELECT COALESCE(SUM(CASE WHEN v.typ='einnahme' THEN v.betrag_cent END),0) ein,"
        "COALESCE(SUM(CASE WHEN v.typ='ausgabe' THEN v.betrag_cent END),0) aus "
        "FROM v_einnahmen_ausgaben v" + where, params).fetchone()
    return row["ein"] or 0, row["aus"] or 0

@router.get("/export/bericht", response_class=HTMLResponse)
def jahresbericht(jahr: str | None = None, sparte_id: int | None = None,
                  profil_id: int | None = None,
                  con: sqlite3.Connection = Depends(db_dep), bereich: BereichDep = Bereich(1)):
    if profil_id is not None:
        profil = _profil(con, profil_id, bereich)
        return HTMLResponse(_profil_bericht(_preview(con, profil, bereich), profil))
    if not jahr or not re.fullmatch(r"\d{4}", jahr) or not 1900 <= int(jahr) <= 9999:
        raise HTTPException(400, "jahr muss vierstellig sein")
    start, end = f"{jahr}-01-01", f"{jahr}-12-31"
    if sparte_id is not None:
        pruefe_sparte(con, sparte_id, bereich)
    _validate(con, start, end, sparte_id)
    if sparte_id is None:
        ids = sparten_ids(con, bereich)
        marks = ",".join("?" for _ in ids) or "NULL"
        divisions = con.execute(
            f"SELECT id,name FROM sparte WHERE aktiv=1 AND id IN ({marks}) ORDER BY sortierung,name", ids).fetchall()
    else:
        divisions = con.execute("SELECT id,name FROM sparte WHERE id=?", (sparte_id,)).fetchall()
    total_in, total_out = _sums(con, start, end, sparte_id, bereich)
    sections = []
    for division in divisions:
        income, expense = _sums(con, start, end, division["id"], bereich)
        monthly = con.execute(
            "SELECT CAST(strftime('%m',v.datum) AS INTEGER) monat,"
            "COALESCE(SUM(CASE WHEN v.typ='einnahme' THEN v.betrag_cent END),0) ein,"
            "COALESCE(SUM(CASE WHEN v.typ='ausgabe' THEN v.betrag_cent END),0) aus "
            "FROM v_einnahmen_ausgaben v WHERE v.datum>=? AND v.datum<=? "
            "AND v.sparte_id=? GROUP BY monat ORDER BY monat",
            (start,end,division["id"])).fetchall()
        by_month = {row["monat"]:(row["ein"] or 0,row["aus"] or 0) for row in monthly}
        month_html = "".join(
            f"<tr><td>{month:02d}</td><td>{_euro(by_month.get(month,(0,0))[0])}</td>"
            f"<td>{_euro(by_month.get(month,(0,0))[1])}</td>"
            f"<td>{_euro(by_month.get(month,(0,0))[0]-by_month.get(month,(0,0))[1])}</td></tr>"
            for month in range(1,13))
        cats = con.execute(
            "SELECT k.name,COALESCE(SUM(CASE WHEN v.typ='einnahme' THEN v.betrag_cent END),0) ein,"
            "COALESCE(SUM(CASE WHEN v.typ='ausgabe' THEN v.betrag_cent END),0) aus "
            "FROM v_einnahmen_ausgaben v JOIN kategorie k ON k.id=v.kategorie_id "
            "WHERE v.datum>=? AND v.datum<=? AND v.sparte_id=? "
            "GROUP BY k.id ORDER BY k.sortierung,k.name",(start,end,division["id"])).fetchall()
        cat_html = "".join(
            f"<tr><td>{html.escape(row['name'])}</td><td>{_euro(row['ein'] or 0)}</td>"
            f"<td>{_euro(row['aus'] or 0)}</td>"
            f"<td>{_euro((row['ein'] or 0)-(row['aus'] or 0))}</td></tr>"
            for row in cats) or '<tr><td colspan="4">Keine Buchungen</td></tr>'
        sections.append(
            f'<section class="division"><h2>{html.escape(division["name"])}</h2>'
            f'<p><b>Einnahmen {_euro(income)}</b> &middot; <b>Ausgaben {_euro(expense)}</b> &middot; '
            f'<b>Saldo {_euro(income-expense)}</b></p><h3>Monatssummen</h3>'
            f'<table><tr><th>Monat</th><th>Einnahmen</th><th>Ausgaben</th><th>Saldo</th></tr>'
            f'{month_html}</table><h3>Kategorien</h3><table><tr><th>Kategorie</th>'
            f'<th>Einnahmen</th><th>Ausgaben</th><th>Saldo</th></tr>{cat_html}</table></section>')
    page = f"""<!doctype html><html lang="de"><head><meta charset="utf-8">
<title>Jahresbericht {jahr}</title><style>
body{{font:14px Arial;color:#17221c;margin:32px}}h1{{font-size:34px}}
table{{width:100%;border-collapse:collapse}}
th,td{{border-bottom:1px solid #ccd5d0;padding:6px;text-align:right}}
th:first-child,td:first-child{{text-align:left}}
.cover{{min-height:90vh;display:flex;flex-direction:column;justify-content:center}}
.division{{page-break-before:always}}.toolbar{{position:fixed;right:24px;top:18px}}
@page{{size:A4;margin:16mm}}@media print{{.toolbar{{display:none}}body{{margin:0}}}}
</style></head><body>
<div class="toolbar"><button onclick="window.print()">Drucken / Als PDF speichern</button></div>
<section class="cover"><h1>Jahresbericht {jahr}</h1><p>Finanz-Dashboard Hohenegg</p>
<p><b>Einnahmen {_euro(total_in)}</b> &middot; <b>Ausgaben {_euro(total_out)}</b> &middot;
<b>Saldo {_euro(total_in-total_out)}</b></p></section>
{''.join(sections)}</body></html>"""
    return HTMLResponse(page)


class ExportProfilAenderung(BaseModel):
    kategorie_ids: list[int] = Field(default_factory=list)
    buchung_ids: list[int] = Field(default_factory=list)


class ExportAuswahl(BaseModel):
    profil_id: int
    revision: str | None = None
    nur_suchtreffer: bool = False
    q: str | None = None
    trotz_fehlender_belege: bool = False


def _jahr(jahr: int) -> None:
    if not 1900 <= jahr <= 9999:
        raise HTTPException(400, "jahr muss vierstellig sein")


def _profil(con, profil_id, bereich):
    row = con.execute("SELECT * FROM export_profil WHERE id=? AND bereich_id=?", (profil_id, bereich.id)).fetchone()
    if not row:
        raise HTTPException(404, "Export-Profil nicht gefunden")
    return row


def _ausschluesse(con, profil_id):
    rows = con.execute("SELECT kategorie_id,buchung_id FROM export_profil_ausschluss WHERE profil_id=? ORDER BY kategorie_id,buchung_id", (profil_id,)).fetchall()
    return [r[0] for r in rows if r[0] is not None], [r[1] for r in rows if r[1] is not None]


def _profilantwort(con, profil, bereich):
    kategorien, buchungen = _ausschluesse(con, profil["id"])
    revision = _revision(con, profil, bereich)
    return {**dict(profil), "kategorie_ids": kategorien, "buchung_ids": buchungen,
            "ausschluesse": [{"kategorie_id": k, "buchung_id": b} for k, b in
                              con.execute("SELECT kategorie_id,buchung_id FROM export_profil_ausschluss WHERE profil_id=? ORDER BY kategorie_id,buchung_id", (profil["id"],))],
            "revision": revision}


def _revision(con, profil, bereich):
    rows = _auswahl_rows(con, profil, bereich)
    kategorien, buchungen = _ausschluesse(con, profil["id"])
    material = [(r["buchung_id"], r["geaendert_am"], r["text"], r["buchung_betrag_cent"]) for r in rows]
    material += [("k", value) for value in kategorien] + [("b", value) for value in buchungen]
    material += [("p", profil["id"], profil["aktualisiert_am"])]
    return hashlib.sha256(repr(material).encode("utf-8")).hexdigest()


def _auswahl_rows(con, profil, bereich, q=None, nur_suchtreffer=False):
    clauses = ["v.datum>=?", "v.datum<=?", "s.bereich_id=?", "b.typ IN ('einnahme','ausgabe')"]
    params = [f"{profil['jahr']}-01-01", f"{profil['jahr']}-12-31", bereich.id]
    if profil["sparte_id"] is not None:
        clauses.append("v.sparte_id=?"); params.append(profil["sparte_id"])
    kategorien, buchungen = _ausschluesse(con, profil["id"])
    if kategorien:
        clauses.append("v.kategorie_id NOT IN (" + ",".join("?" for _ in kategorien) + ")"); params.extend(kategorien)
    if buchungen:
        clauses.append("v.buchung_id NOT IN (" + ",".join("?" for _ in buchungen) + ")"); params.extend(buchungen)
    if nur_suchtreffer and q:
        clauses.append("(LOWER(COALESCE(b.text,'')) LIKE ? OR LOWER(k.name) LIKE ?)")
        needle = "%" + q.lower() + "%"; params.extend([needle, needle])
    return con.execute(
        "SELECT v.*,b.geaendert_am,b.text,b.betrag_cent buchung_betrag_cent,s.name sparte,k.name kategorie "
        "FROM v_einnahmen_ausgaben v JOIN buchung b ON b.id=v.buchung_id "
        "JOIN sparte s ON s.id=v.sparte_id JOIN kategorie k ON k.id=v.kategorie_id "
        "WHERE " + " AND ".join(clauses) + " ORDER BY v.datum,v.buchung_id,v.zeile_id", params).fetchall()


def _fehlende_belege(con, rows):
    result = []
    seen = set()
    for row in rows:
        for beleg in con.execute("SELECT be.id,be.dateiname,be.pfad FROM beleg be JOIN buchung_beleg bb ON bb.beleg_id=be.id WHERE bb.buchung_id=? ORDER BY be.id", (row["buchung_id"],)):
            key = (row["buchung_id"], beleg["id"])
            if key not in seen and (not beleg["pfad"] or not pathlib.Path(beleg["pfad"]).exists()):
                result.append({"buchung_id": row["buchung_id"], "beleg_id": beleg["id"], "dateiname": beleg["dateiname"]})
                seen.add(key)
    return result


def _preview(con, profil, bereich, q=None, nur_suchtreffer=False):
    rows = _auswahl_rows(con, profil, bereich, q, True)
    zeilen = []
    einnahmen = ausgaben = 0
    for row in rows:
        amount = row["betrag_cent"]
        if row["typ"] == "einnahme": einnahmen += amount
        else: ausgaben += amount
        belege = [r[0] for r in con.execute("SELECT beleg_id FROM buchung_beleg WHERE buchung_id=? ORDER BY beleg_id", (row["buchung_id"],))]
        zeilen.append({"buchung_id": row["buchung_id"], "datum": row["datum"], "text": row["text"] or "",
                       "kategorie": row["kategorie"], "betrag_cent": amount,
                       "anteil_cent": amount, "belege": belege})
    kategorien, buchungen = _ausschluesse(con, profil["id"])
    return {"revision": _revision(con, profil, bereich), "zeilen": zeilen,
            "summen": {"anzahl": len(zeilen), "einnahmen_cent": einnahmen, "ausgaben_cent": ausgaben},
            "ausgeschlossen": {"kategorien": len(kategorien), "buchungen": len(buchungen)},
            "belege_fehlend": _fehlende_belege(con, rows)}


def _profil_bericht(preview, profil):
    zeilen = "".join(f"<tr><td>{html.escape(row['datum'])}</td><td>{html.escape(row['kategorie'])}</td><td>{html.escape(row['text'])}</td><td>{row['betrag_cent'] / 100:.2f} EUR</td></tr>" for row in preview["zeilen"])
    sums = preview["summen"]
    return (f"<!doctype html><html lang='de'><head><meta charset='utf-8'><title>Export {profil['jahr']}</title></head><body>"
            f"<h1>Export-Profil {html.escape(profil['name'])}</h1><p>Jahr {profil['jahr']} – Einnahmen {sums['einnahmen_cent']} Cent, Ausgaben {sums['ausgaben_cent']} Cent</p>"
            f"<table><tr><th>Datum</th><th>Kategorie</th><th>Text</th><th>Betrag</th></tr>{zeilen}</table></body></html>")


@router.get("/api/export/profil")
def export_profil(jahr: int, sparte_id: int | None = None,
                  con: sqlite3.Connection = Depends(db_dep), bereich: BereichDep = Bereich(1)):
    _jahr(jahr)
    if sparte_id is not None:
        pruefe_sparte(con, sparte_id, bereich)
    profil = con.execute("SELECT * FROM export_profil WHERE bereich_id=? AND sparte_id IS ? AND jahr=? AND name='Steuer'", (bereich.id, sparte_id, jahr)).fetchone()
    if not profil:
        cur = con.execute("INSERT INTO export_profil(bereich_id,sparte_id,jahr) VALUES(?,?,?)", (bereich.id, sparte_id, jahr))
        con.commit(); profil = con.execute("SELECT * FROM export_profil WHERE id=?", (cur.lastrowid,)).fetchone()
    return _profilantwort(con, profil, bereich)


@router.put("/api/export/profil/{profil_id}")
def export_profil_setzen(profil_id: int, aenderung: ExportProfilAenderung,
                         con: sqlite3.Connection = Depends(db_dep), bereich: BereichDep = Bereich(1)):
    profil = _profil(con, profil_id, bereich)
    for kid in set(aenderung.kategorie_ids): pruefe_kategorie(con, kid, bereich)
    for bid in set(aenderung.buchung_ids): pruefe_buchung(con, bid, bereich)
    con.execute("DELETE FROM export_profil_ausschluss WHERE profil_id=?", (profil_id,))
    con.executemany("INSERT INTO export_profil_ausschluss(profil_id,kategorie_id) VALUES(?,?)", [(profil_id, k) for k in set(aenderung.kategorie_ids)])
    con.executemany("INSERT INTO export_profil_ausschluss(profil_id,buchung_id) VALUES(?,?)", [(profil_id, b) for b in set(aenderung.buchung_ids)])
    con.execute("UPDATE export_profil SET aktualisiert_am=datetime('now') WHERE id=?", (profil_id,)); con.commit()
    return _profilantwort(con, con.execute("SELECT * FROM export_profil WHERE id=?", (profil_id,)).fetchone(), bereich)


@router.post("/api/export/profil/{profil_id}/uebernehmen-vom-vorjahr")
def export_profil_vorjahr(profil_id: int, con: sqlite3.Connection = Depends(db_dep), bereich: BereichDep = Bereich(1)):
    profil = _profil(con, profil_id, bereich)
    vorher = con.execute("SELECT * FROM export_profil WHERE bereich_id=? AND sparte_id IS ? AND jahr=? AND name=?", (bereich.id, profil["sparte_id"], profil["jahr"] - 1, profil["name"])).fetchone()
    con.execute("DELETE FROM export_profil_ausschluss WHERE profil_id=? AND kategorie_id IS NOT NULL", (profil_id,))
    if vorher:
        con.executemany("INSERT INTO export_profil_ausschluss(profil_id,kategorie_id) VALUES(?,?)", [(profil_id, r[0]) for r in con.execute("SELECT kategorie_id FROM export_profil_ausschluss WHERE profil_id=? AND kategorie_id IS NOT NULL", (vorher["id"],))])
    con.execute("UPDATE export_profil SET aktualisiert_am=datetime('now') WHERE id=?", (profil_id,)); con.commit()
    return _profilantwort(con, con.execute("SELECT * FROM export_profil WHERE id=?", (profil_id,)).fetchone(), bereich)


@router.post("/api/export/vorschau")
def export_vorschau(auswahl: ExportAuswahl, con: sqlite3.Connection = Depends(db_dep), bereich: BereichDep = Bereich(1)):
    profil = _profil(con, auswahl.profil_id, bereich)
    return _preview(con, profil, bereich, auswahl.q, auswahl.nur_suchtreffer)


def _export_workbook(rows):
    wb = Workbook(); sheet = wb.active; sheet.title = "Buchungen"
    for row in rows:
        sheet.append([_xlsx_text(row["datum"]), _xlsx_text(row["sparte"]), _xlsx_text(row["kategorie"]), _xlsx_text(row["typ"]), _xlsx_text(row["text"] or ""), row["betrag_cent"] / 100])
    _sheet(sheet, ["Datum", "Sparte", "Kategorie", "Typ", "Text", "Anteil"], (12, 24, 28, 12, 36, 16), 6)
    monthly = wb.create_sheet("Monatssummen")
    monat = {}
    for row in rows:
        values = monat.setdefault(row["datum"][:7], [0, 0])
        values[0 if row["typ"] == "einnahme" else 1] += row["betrag_cent"]
    for key, (income, expense) in sorted(monat.items()):
        monthly.append([key, income / 100, expense / 100, (income - expense) / 100])
    _sheet(monthly, ["Monat", "Einnahmen", "Ausgaben", "Saldo"], (14, 18, 18, 18), 2)
    category = wb.create_sheet("Kategorien")
    grouped = {}
    for row in rows:
        key = (row["sparte"], row["kategorie"])
        values = grouped.setdefault(key, [0, 0])
        values[0 if row["typ"] == "einnahme" else 1] += row["betrag_cent"]
    for (division, name), (income, expense) in sorted(grouped.items()):
        category.append([_xlsx_text(division), _xlsx_text(name), income / 100, expense / 100, (income - expense) / 100])
    _sheet(category, ["Sparte", "Kategorie", "Einnahmen", "Ausgaben", "Saldo"], (24, 30, 18, 18, 18), 3)
    stream = io.BytesIO(); wb.save(stream); return stream.getvalue()


@router.post("/api/export/paket")
def export_paket(auswahl: ExportAuswahl, con: sqlite3.Connection = Depends(db_dep), bereich: BereichDep = Bereich(1)):
    profil = _profil(con, auswahl.profil_id, bereich)
    suchtext = auswahl.q if auswahl.nur_suchtreffer else None
    preview = _preview(con, profil, bereich, suchtext, auswahl.nur_suchtreffer)
    if auswahl.revision != preview["revision"]:
        raise HTTPException(409, "Revision des Export-Profils oder der Buchungen stimmt nicht mehr")
    if preview["belege_fehlend"] and not auswahl.trotz_fehlender_belege:
        raise HTTPException(422, "Belege fehlen")
    rows = _auswahl_rows(con, profil, bereich, suchtext, auswahl.nur_suchtreffer)
    sparte = "Alle" if profil["sparte_id"] is None else con.execute("SELECT name FROM sparte WHERE id=?", (profil["sparte_id"],)).fetchone()[0]
    dateiname = f"Buchungen_{re.sub(r'[^A-Za-z0-9_-]+', '_', sparte)}_{profil['jahr']}.xlsx"
    files = []
    content = io.BytesIO()
    with zipfile.ZipFile(content, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(dateiname, _export_workbook(rows))
        for row in rows:
            for beleg in con.execute("SELECT DISTINCT be.id,be.dateiname,be.pfad FROM beleg be JOIN buchung_beleg bb ON bb.beleg_id=be.id WHERE bb.buchung_id=? ORDER BY be.id", (row["buchung_id"],)):
                if not beleg["pfad"] or not pathlib.Path(beleg["pfad"]).exists() or beleg["id"] in files: continue
                amount = row["buchung_betrag_cent"]
                stem = f"{row['datum']}_{amount // 100},{abs(amount) % 100:02d}_EUR_B{row['buchung_id']}_Beleg{beleg['id']}{pathlib.Path(beleg['dateiname']).suffix.lower()}"
                archive.writestr("Belege/" + stem, pathlib.Path(beleg["pfad"]).read_bytes()); files.append(beleg["id"])
        missing = "\n".join(f"Buchung {r['buchung_id']}: Beleg {r['beleg_id']} {r['dateiname']}" for r in preview["belege_fehlend"]) or "Keine"
        archive.writestr("INHALT.txt", f"Erstellt am: {dt.datetime.now().isoformat(timespec='seconds')}\nBereich: {bereich.id}\nSparte: {sparte}\nJahr: {profil['jahr']}\nProfilname: {profil['name']}\nRevision: {preview['revision']}\nAnzahl Buchungen: {preview['summen']['anzahl']}\nEinnahmen: {preview['summen']['einnahmen_cent']} Cent\nAusgaben: {preview['summen']['ausgaben_cent']} Cent\nNur Suchtreffer: {'ja' if auswahl.nur_suchtreffer else 'nein'}\nFehlende Belege:\n{missing}\n")
    content.seek(0)
    return StreamingResponse(content, media_type="application/zip", headers={"Content-Disposition": 'attachment; filename="export-paket.zip"'})
