"""Dauerhafte Hinweise zu nicht eindeutig aufgeloesten Bestandsmigrationen."""
import sqlite3


SQL = """
CREATE TABLE IF NOT EXISTS migrationsprotokoll (
    id INTEGER PRIMARY KEY,
    version INTEGER NOT NULL,
    zeitpunkt TEXT NOT NULL DEFAULT (datetime('now')),
    art TEXT NOT NULL,
    objektkennung TEXT NOT NULL,
    hinweis TEXT NOT NULL,
    UNIQUE (version, art, objektkennung)
);
CREATE INDEX IF NOT EXISTS idx_migrationsprotokoll_zeitpunkt
    ON migrationsprotokoll (zeitpunkt, id);
"""


def _eintrag(con, art, objektkennung, hinweis):
    con.execute(
        "INSERT OR IGNORE INTO migrationsprotokoll(version, art, objektkennung, hinweis) "
        "VALUES(4, ?, ?, ?)", (art, objektkennung, hinweis),
    )


def up(con: sqlite3.Connection):
    for statement in SQL.split(';'):
        if statement.strip():
            con.execute(statement)

    for row in con.execute("""
        SELECT b.id FROM buchung b
        WHERE b.zahlungsart='bar' AND b.typ IN ('einnahme','ausgabe')
          AND b.bankumsatz_id IS NULL
          AND NOT EXISTS (SELECT 1 FROM buchung_bewegung x WHERE x.buchung_id=b.id)
          AND (SELECT count(*) FROM bankkonto k
               WHERE k.art='kassa' AND k.sparte_id=b.sparte_id) <> 1
    """):
        _eintrag(con, 'barbuchung_ungeklaert', f"buchung:{row[0]}",
                 f"Buchung {row[0]}: Barbuchung konnte keiner eindeutigen Kassa zugeordnet werden.")

    gruppen = con.execute("""
        SELECT DISTINCT transfer_gruppe_id FROM buchung
        WHERE typ='umbuchung' AND transfer_gruppe_id IS NOT NULL
    """).fetchall()
    for gruppe_row in gruppen:
        gruppe = gruppe_row[0]
        paar = con.execute(
            "SELECT betrag_cent, datum, bankkonto_id FROM buchung "
            "WHERE transfer_gruppe_id=? ORDER BY id", (gruppe,)
        ).fetchall()
        eindeutig = (
            len(paar) == 2 and paar[0][0] > 0 and paar[0][0] == paar[1][0]
            and paar[0][1] == paar[1][1] and all(row[2] is not None for row in paar)
        )
        if not eindeutig:
            _eintrag(con, 'umbuchung_ungeklaert', f"umbuchungsgruppe:{gruppe}",
                     f"Umbuchungsgruppe {gruppe}: Die Buchungen konnten nicht eindeutig aufgeloest werden.")

    for row in con.execute("""
        SELECT id FROM buchung
        WHERE zahlungsart IN ('bank','karte') AND bankumsatz_id IS NULL
          AND typ IN ('einnahme','ausgabe') ORDER BY id
    """):
        _eintrag(con, 'zahlung_ungeklaert', f"buchung:{row[0]}",
                 f"Buchung {row[0]}: Bank- oder Kartenbuchung ohne zugehoerigen Umsatz.")
