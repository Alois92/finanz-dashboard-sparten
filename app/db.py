"""Datenbankzugriff: Verbindung, Speicherort-Aufloesung, Initialisierung.

Speicherort der Datenbank (Prioritaet):
  1. Umgebungsvariable FINANZ_DB
  2. lokale Konfigurationsdatei  instance/db_location.txt  (pro Rechner, NICHT in Git)
  3. Fallback: ephemere Datenbank im Temp-Ordner (keine dauerhaften Daten)

So bleibt dieser Rechner datenfrei: ohne Konfiguration wird nur eine temporaere
Test-DB benutzt. Der echte Speicherort (z. B. privater Ordner am Heim-PC) wird
pro Rechner ueber FINANZ_DB oder instance/db_location.txt gesetzt.
"""
import logging
import os
import pathlib
import sqlite3
import tempfile

log = logging.getLogger("finanz.db")

BASE = pathlib.Path(__file__).resolve().parent.parent
SCHEMA = BASE / "db" / "schema.sql"
SEED = BASE / "db" / "seed.sql"
CONFIG_FILE = BASE / "instance" / "db_location.txt"


def _resolve_db_path() -> tuple[pathlib.Path, bool]:
    """Liefert (Pfad, ist_dauerhaft)."""
    env = os.environ.get("FINANZ_DB")
    if env and env.strip():
        return pathlib.Path(env.strip()), True
    if CONFIG_FILE.exists():
        configured = CONFIG_FILE.read_text(encoding="utf-8").strip()
        if configured:
            return pathlib.Path(configured), True
    tmp = pathlib.Path(tempfile.gettempdir()) / "finanz-dashboard-temp" / "finanz.db"
    return tmp, False


DB_PATH, DB_PERSISTENT = _resolve_db_path()
_warned = False


def get_connection() -> sqlite3.Connection:
    global _warned
    if not DB_PERSISTENT and not _warned:
        log.warning(
            "Kein dauerhafter DB-Speicherort konfiguriert - nutze temporaere DB: %s "
            "(Daten NICHT dauerhaft). Fuer echten Betrieb FINANZ_DB oder "
            "instance/db_location.txt setzen.", DB_PATH)
        _warned = True
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    # check_same_thread=False: FastAPI reicht sync-Requests durch einen Threadpool,
    # wobei Dependency (Verbindungsaufbau) und Endpoint auf verschiedenen Threads
    # laufen koennen. Jeder Request bekommt weiterhin eine eigene, kurzlebige
    # Verbindung (db_dep) und schliesst sie wieder - es wird also nie EINE
    # Verbindung gleichzeitig aus mehreren Threads benutzt.
    con = sqlite3.connect(DB_PATH, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


# Feste Kennfarben je Sparte (Kuerzel -> Hex). Neue DBs bekommen sie ueber
# seed.sql; bestehende DBs werden in init_db() einmalig nachgeruestet.
SPARTEN_FARBEN = {
    "PV": "#6AA9FF", "ZVH": "#2DD4BF", "HOF": "#C084FC",
    "VER": "#F472B6", "AL": "#FB923C", "FR": "#818CF8",
}
# Fallback-Palette fuer selbst angelegte/umbenannte Sparten (nach Sortierung).
SPARTEN_PALETTE = ["#6AA9FF", "#2DD4BF", "#C084FC", "#F472B6", "#FB923C",
                   "#818CF8", "#F59E0B", "#34D399"]


def init_db() -> None:
    """Legt Schema + Seed an, falls die Datenbank noch leer ist."""
    con = get_connection()
    try:
        exists = con.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='sparte'"
        ).fetchone()
        if not exists:
            con.executescript(SCHEMA.read_text(encoding="utf-8"))
            con.executescript(SEED.read_text(encoding="utf-8"))
            con.commit()
        else:
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
            vergeben = {r["farbe"] for r in con.execute(
                "SELECT farbe FROM sparte WHERE farbe IS NOT NULL AND farbe != ''")}
            frei = [f for f in SPARTEN_PALETTE if f not in vergeben]
            offen = con.execute(
                "SELECT id FROM sparte WHERE farbe IS NULL OR farbe = '' "
                "ORDER BY sortierung, id").fetchall()
            for i, row in enumerate(offen):
                farbe = (frei[i] if i < len(frei)
                         else SPARTEN_PALETTE[i % len(SPARTEN_PALETTE)])
                con.execute("UPDATE sparte SET farbe = ? WHERE id = ?",
                            (farbe, row["id"]))
            con.commit()

        # Nachruestung: beleg_auswertung fehlt in Bestands-DBs (aeltere
        # Schema-Version) - idempotent nachziehen, damit Feature B (lokale
        # Foto-Auswertung) auch ohne Neuanlage der DB funktioniert.
        con.execute(
            "CREATE TABLE IF NOT EXISTS beleg_auswertung ("
            "id INTEGER PRIMARY KEY, "
            "beleg_id INTEGER NOT NULL REFERENCES beleg(id) ON DELETE CASCADE, "
            "status TEXT NOT NULL DEFAULT 'offen' "
            "  CHECK (status IN ('offen','laeuft','fertig','fehler','verbucht','verworfen')), "
            "ergebnis_json TEXT, "
            "fehler TEXT, "
            "versuche INTEGER NOT NULL DEFAULT 0, "
            "erstellt TEXT NOT NULL DEFAULT (datetime('now')), "
            "aktualisiert TEXT"
            ")"
        )
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_beleg_auswertung_status "
            "ON beleg_auswertung (status)"
        )
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_beleg_auswertung_beleg "
            "ON beleg_auswertung (beleg_id)"
        )
        con.commit()
    finally:
        con.close()


def db_dep():
    """FastAPI-Dependency: eine Verbindung pro Request."""
    con = get_connection()
    try:
        yield con
    finally:
        con.close()
