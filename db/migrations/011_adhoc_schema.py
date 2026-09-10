"""Versioniert die bisherigen Start-Nachruestungen; vorhandene Daten bleiben erhalten."""
import sqlite3


SPARTEN_FARBEN = {
    "PV": "#6AA9FF", "ZVH": "#2DD4BF", "HOF": "#C084FC",
    "VER": "#F472B6", "AL": "#FB923C", "FR": "#818CF8",
}
# Fallback-Palette fuer selbst angelegte/umbenannte Sparten (nach Sortierung).
SPARTEN_PALETTE = ["#6AA9FF", "#2DD4BF", "#C084FC", "#F472B6", "#FB923C",
                   "#818CF8", "#F59E0B", "#34D399"]


def up(con: sqlite3.Connection) -> None:
    # Nachruestung: fehlende Sparten-Farben setzen (idempotent, greift
    # nur bei NULL/leer - selbst gewaehlte Farben bleiben unberuehrt).
    for kuerzel, farbe in SPARTEN_FARBEN.items():
        con.execute(
            "UPDATE sparte SET farbe = ? "
            "WHERE kuerzel = ? AND (farbe IS NULL OR farbe = '')",
            (farbe, kuerzel),
        )
    # Selbst angelegte Sparten (unbekanntes Kuerzel): Palette nach
    # Sortierung, moeglichst ohne bereits vergebene Farben.
    vergeben = {r[0] for r in con.execute(
        "SELECT farbe FROM sparte WHERE farbe IS NOT NULL AND farbe != ''")}
    frei = [f for f in SPARTEN_PALETTE if f not in vergeben]
    offen = con.execute(
        "SELECT id FROM sparte WHERE farbe IS NULL OR farbe = '' "
        "ORDER BY sortierung, id").fetchall()
    for i, row in enumerate(offen):
        farbe = (frei[i] if i < len(frei)
                 else SPARTEN_PALETTE[i % len(SPARTEN_PALETTE)])
        con.execute("UPDATE sparte SET farbe = ? WHERE id = ?",
                    (farbe, row[0]))

    con.execute("""
        CREATE TABLE IF NOT EXISTS beleg_auswertung (
            id             INTEGER PRIMARY KEY,
            beleg_id       INTEGER NOT NULL REFERENCES beleg(id) ON DELETE CASCADE,
            status         TEXT    NOT NULL DEFAULT 'offen'
                               CHECK (status IN ('offen','laeuft','fertig','fehler',
                                                'verbucht','verworfen')),
            ergebnis_json  TEXT,
            fehler         TEXT,
            versuche       INTEGER NOT NULL DEFAULT 0,
            erstellt       TEXT    NOT NULL DEFAULT (datetime('now')),
            aktualisiert   TEXT
        )
    """)
    con.execute("""
        CREATE INDEX IF NOT EXISTS idx_beleg_auswertung_status ON beleg_auswertung (status)
    """)
    con.execute("""
        CREATE INDEX IF NOT EXISTS idx_beleg_auswertung_beleg  ON beleg_auswertung (beleg_id)
    """)
