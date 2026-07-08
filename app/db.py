"""Datenbankzugriff: Verbindung, einmalige Initialisierung aus db/*.sql.

Die Datenbank liegt bewusst NICHT im Repo-Ordner (der auf einem Netzlaufwerk
liegt - SQLite/WAL vertraegt sich schlecht mit SMB), sondern lokal unter
%LOCALAPPDATA%\\finanz-dashboard. Ueber die Umgebungsvariable FINANZ_DB
kann ein anderer Pfad gesetzt werden.
"""
import os
import pathlib
import sqlite3

BASE = pathlib.Path(__file__).resolve().parent.parent
SCHEMA = BASE / "db" / "schema.sql"
SEED = BASE / "db" / "seed.sql"

_default_dir = pathlib.Path(os.environ.get("LOCALAPPDATA", pathlib.Path.home())) / "finanz-dashboard"
DB_PATH = pathlib.Path(os.environ.get("FINANZ_DB", str(_default_dir / "finanz.db")))


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


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
    finally:
        con.close()


def db_dep():
    """FastAPI-Dependency: eine Verbindung pro Request."""
    con = get_connection()
    try:
        yield con
    finally:
        con.close()
