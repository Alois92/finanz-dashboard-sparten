import sqlite3


def up(con: sqlite3.Connection) -> None:
    spalten = {
        row[1] for row in con.execute("PRAGMA table_info(import_batch)")
    }
    neue_spalten = (
        ("dateihash", "TEXT"),
        ("parser_version", "INTEGER NOT NULL DEFAULT 2"),
        ("zeitraum_von", "TEXT"),
        ("zeitraum_bis", "TEXT"),
        ("anzahl_ungueltig", "INTEGER"),
    )
    for name, definition in neue_spalten:
        if name not in spalten:
            con.execute(f"ALTER TABLE import_batch ADD COLUMN {name} {definition}")
