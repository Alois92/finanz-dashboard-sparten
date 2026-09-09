from __future__ import annotations

import argparse
import importlib.util
import logging
import pathlib
import re
import sqlite3
from collections.abc import Callable

BASE = pathlib.Path(__file__).resolve().parent.parent
MIGRATIONS_DIR = BASE / "db" / "migrations"
SCHEMA_VERSION_SQL = """
CREATE TABLE IF NOT EXISTS schema_version (
    version        INTEGER PRIMARY KEY,
    name           TEXT    NOT NULL,
    angewendet_am  TEXT    NOT NULL DEFAULT (datetime('now'))
)
"""

log = logging.getLogger("finanz.migrate")


class MigrationsFehler(Exception):
    def __init__(self, version: int, ursache: Exception):
        super().__init__(f"Migration {version} fehlgeschlagen: {ursache}")
        self.version = version
        self.ursache = ursache


def liste_migrationen() -> list[tuple[int, str, pathlib.Path]]:
    migrationen: list[tuple[int, str, pathlib.Path]] = []
    if not MIGRATIONS_DIR.exists():
        return migrationen
    for pfad in MIGRATIONS_DIR.iterdir():
        if pfad.suffix not in {".sql", ".py"}:
            continue
        treffer = re.fullmatch(r"(\d{3})_(.+)", pfad.stem)
        if treffer is None:
            continue
        migrationen.append((int(treffer.group(1)), treffer.group(2), pfad))
    migrationen.sort(key=lambda eintrag: eintrag[0])
    versionen = [version for version, _, _ in migrationen]
    if len(versionen) != len(set(versionen)):
        raise ValueError("Doppelte Migrationsversion gefunden")
    return migrationen


def _hat_schema_version(con: sqlite3.Connection) -> bool:
    return con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_version'"
    ).fetchone() is not None


def status(con) -> dict:
    if not _hat_schema_version(con):
        return {
            "aktuell": 0,
            "anstehend": [(version, name) for version, name, _ in liste_migrationen()],
            "basis": False,
        }
    rows = con.execute("SELECT version FROM schema_version").fetchall()
    angewendet = {int(row[0]) for row in rows}
    fach_versionen = [version for version in angewendet if version > 0]
    anstehend = [
        (version, name)
        for version, name, _ in liste_migrationen()
        if version not in angewendet
    ]
    return {
        "aktuell": max(fach_versionen, default=0),
        "anstehend": anstehend,
        "basis": 0 in angewendet,
    }


def basis_setzen(con) -> None:
    con.execute(SCHEMA_VERSION_SQL)
    con.execute(
        "INSERT OR IGNORE INTO schema_version(version, name) VALUES(0, 'basis')"
    )
    con.commit()


def alle_markieren(con) -> None:
    con.execute(SCHEMA_VERSION_SQL)
    for version, name, _ in liste_migrationen():
        con.execute(
            "INSERT OR IGNORE INTO schema_version(version, name) VALUES(?, ?)",
            (version, name),
        )
    con.commit()


def anwenden(
    con,
    sicherung: Callable[[], pathlib.Path | None] | None,
    sicherung_pflicht: bool = False,
) -> list[int]:
    if not _hat_schema_version(con):
        basis_setzen(con)
    anstehend = status(con)["anstehend"]
    if not anstehend:
        return []
    migrationen = {version: (name, pfad) for version, name, pfad in liste_migrationen()}
    if sicherung is not None:
        pfad = sicherung()
        if pfad is None and sicherung_pflicht:
            raise MigrationsFehler(
                anstehend[0][0],
                RuntimeError("Sicherung vor Nachzug fehlgeschlagen"),
            )
        log.info("DB-Sicherung vor Schema-Nachzug: %s", pfad)
    angewendet: list[int] = []
    for version, _name in anstehend:
        name, pfad = migrationen[version]
        try:
            if pfad.suffix == ".sql":
                script = pfad.read_text(encoding="utf-8")
                con.executescript(
                    "BEGIN;\n"
                    f"{script}\n"
                    "INSERT INTO schema_version(version, name) "
                    f"VALUES({version}, {repr(name)});\n"
                    "COMMIT;"
                )
            elif pfad.suffix == ".py":
                con.execute("BEGIN")
                _lade_python_migration(pfad).up(con)
                con.execute(
                    "INSERT INTO schema_version(version, name) VALUES(?, ?)",
                    (version, name),
                )
                con.commit()
            else:
                continue
        except Exception as exc:
            try:
                con.rollback()
            except sqlite3.Error:
                pass
            raise MigrationsFehler(version, exc) from exc
        angewendet.append(version)
    return angewendet


def _lade_python_migration(pfad: pathlib.Path):
    spec = importlib.util.spec_from_file_location(f"migration_{pfad.stem}", pfad)
    if spec is None or spec.loader is None:
        raise ImportError(f"Migration nicht ladbar: {pfad}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not hasattr(module, "up"):
        raise AttributeError(f"Migration ohne up(con): {pfad}")
    return module


def _sicherung_aus_backup() -> pathlib.Path:
    from . import backup

    pfad = backup.sichere_datenbank()
    return pathlib.Path(pfad) if pfad else pathlib.Path("")


def _main() -> int:
    from .db import get_connection

    parser = argparse.ArgumentParser()
    parser.add_argument("kommando", choices=["status", "apply"])
    args = parser.parse_args()

    con = get_connection()
    try:
        if args.kommando == "status":
            print(status(con))
            return 0
        from . import backup

        angewendet = anwenden(
            con, _sicherung_aus_backup, sicherung_pflicht=backup.DB_PERSISTENT
        )
        print(f"Angewendet: {angewendet}")
        return 0
    finally:
        con.close()


if __name__ == "__main__":
    raise SystemExit(_main())
