"""Automatische Sicherung der SQLite-Datenbank.

Beim Serverstart und danach regelmaessig wird eine Tageskopie in den Ordner
``<DB-Ordner>/backup/`` geschrieben (finanz-JJJJ-MM-TT.db). Pro Tag entsteht
hoechstens eine Kopie; aeltere Kopien werden nach BACKUP_AUFBEWAHREN Stueck
geloescht. Die Kopie laeuft ueber die SQLite-Backup-API und ist damit auch
bei laufendem Betrieb konsistent.

Die ephemere Test-DB (kein dauerhafter Speicherort konfiguriert) wird nicht
gesichert.
"""
import asyncio
import datetime as dt
import logging
import sqlite3

from .db import DB_PATH, DB_PERSISTENT, get_connection

log = logging.getLogger("finanz.backup")

BACKUP_AUFBEWAHREN = 30          # so viele Tageskopien bleiben liegen
PRUEF_INTERVALL_SEKUNDEN = 6 * 3600  # laeuft der Server tagelang: alle 6 h pruefen


def sichere_datenbank() -> str | None:
    """Legt die heutige Tageskopie an (falls noch nicht vorhanden).

    Rueckgabe: Pfad der Kopie oder None (uebersprungen/fehlgeschlagen).
    Fehler werden geloggt, aber nie zum Serverabbruch - eine fehlgeschlagene
    Sicherung darf die Buchhaltung nicht blockieren.
    """
    if not DB_PERSISTENT:
        return None
    if not DB_PATH.exists():
        return None
    ziel_ordner = DB_PATH.parent / "backup"
    ziel = ziel_ordner / f"finanz-{dt.date.today().isoformat()}.db"
    if ziel.exists():
        return str(ziel)
    try:
        ziel_ordner.mkdir(parents=True, exist_ok=True)
        quelle = get_connection()
        try:
            kopie = sqlite3.connect(ziel)
            try:
                quelle.backup(kopie)
            finally:
                kopie.close()
        finally:
            quelle.close()
        log.info("DB-Sicherung angelegt: %s", ziel)
        _rotiere(ziel_ordner)
        return str(ziel)
    except Exception:
        log.exception("DB-Sicherung fehlgeschlagen (Betrieb laeuft weiter)")
        return None


def _rotiere(ordner) -> None:
    kopien = sorted(ordner.glob("finanz-????-??-??.db"))
    for alt in kopien[:-BACKUP_AUFBEWAHREN]:
        try:
            alt.unlink()
            log.info("Alte DB-Sicherung entfernt: %s", alt.name)
        except OSError:
            log.warning("Alte DB-Sicherung nicht loeschbar: %s", alt)


async def backup_schleife() -> None:
    """Hintergrundaufgabe: beim Start und dann regelmaessig sichern."""
    while True:
        await asyncio.to_thread(sichere_datenbank)
        await asyncio.sleep(PRUEF_INTERVALL_SEKUNDEN)
