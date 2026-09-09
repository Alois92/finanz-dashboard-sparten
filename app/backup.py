"""Automatische Sicherung der SQLite-Datenbank.

Beim Serverstart und danach regelmaessig wird eine Tageskopie in den Ordner
``<DB-Ordner>/backup/`` geschrieben (finanz-JJJJ-MM-TT.db). Pro Tag entsteht
hoechstens eine Kopie; aeltere Kopien werden nach BACKUP_AUFBEWAHREN Stueck
geloescht. Die Kopie laeuft ueber die SQLite-Backup-API und ist damit auch
bei laufendem Betrieb konsistent.

Die ephemere Test-DB (kein dauerhafter Speicherort konfiguriert) wird nicht
gesichert.

Ist die Umgebungsvariable FINANZ_BACKUP_ZIEL2 gesetzt, wird nach der
erfolgreichen Erstkopie zusaetzlich eine zweite Tageskopie in dieses
Verzeichnis geschrieben (z.B. ein NAS) - mit demselben Dateinamensschema und
derselben Aufbewahrung. Ein fehlendes/nicht erreichbares Zweitziel wird nur
geloggt und darf die Erstkopie niemals scheitern lassen.
"""
import asyncio
import datetime as dt
import logging
import os
import shutil
import sqlite3
import uuid
from pathlib import Path

from .db import DB_PATH, DB_PERSISTENT, get_connection

log = logging.getLogger("finanz.backup")

BACKUP_AUFBEWAHREN = 30          # so viele Tageskopien bleiben liegen
PRUEF_INTERVALL_SEKUNDEN = 6 * 3600  # laeuft der Server tagelang: alle 6 h pruefen

_ziel2_env = os.environ.get("FINANZ_BACKUP_ZIEL2")
BACKUP_ZIEL2 = Path(_ziel2_env.strip()) if _ziel2_env and _ziel2_env.strip() else None


def _ist_gueltige_sqlite_datei(pfad) -> bool:
    """Prueft eine geschlossene Sicherungsdatei, ohne sie zu veraendern."""
    con = None
    try:
        if pfad.stat().st_size == 0:
            return False
        con = sqlite3.connect(pfad)
        return con.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    except (OSError, sqlite3.Error):
        return False
    finally:
        if con is not None:
            con.close()


def _temp_pfad(ziel) -> Path:
    """Temporaerer Dateiname im selben Ordner wie ``ziel`` (fuer atomares Umbenennen)."""
    return ziel.with_name(f".{ziel.name}.{uuid.uuid4().hex}.tmp")


def _abschliessen(temp_ziel, ziel, ziel_ordner, beschreibung: str) -> None:
    """Validiert die geschriebene Temp-Datei und benennt sie atomar um.

    Wirft bei ungueltiger Datei eine Exception - der Aufrufer entscheidet,
    wie kritisch das ist (Erstziel: Fehlschlag, Zweitziel: nur Logging).
    """
    if not _ist_gueltige_sqlite_datei(temp_ziel):
        raise sqlite3.DatabaseError(f"Sicherungsdatei ({beschreibung}) ist nicht intakt")
    temp_ziel.replace(ziel)
    log.info("DB-Sicherung (%s) angelegt: %s", beschreibung, ziel)
    _rotiere(ziel_ordner)


def sichere_datenbank() -> str | None:
    """Legt die heutige Tageskopie an (falls noch nicht vorhanden).

    Rueckgabe: Pfad der Kopie oder None (uebersprungen/fehlgeschlagen).
    Fehler werden geloggt, aber nie zum Serverabbruch - eine fehlgeschlagene
    Sicherung darf die Buchhaltung nicht blockieren.

    Ist FINANZ_BACKUP_ZIEL2 gesetzt, wird danach zusaetzlich eine Kopie der
    validierten Erstkopie in dieses Verzeichnis geschrieben. Ein Fehlschlag
    dabei (z. B. NAS gerade nicht erreichbar) wird nur geloggt und aendert
    nichts am Rueckgabewert der Erstkopie.
    """
    if not DB_PERSISTENT:
        return None
    if not DB_PATH.exists():
        return None
    dateiname = f"finanz-{dt.date.today().isoformat()}.db"
    ziel_ordner = DB_PATH.parent / "backup"
    ziel = ziel_ordner / dateiname
    erst_erfolgreich = ziel.exists() and _ist_gueltige_sqlite_datei(ziel)
    if not erst_erfolgreich:
        temp_ziel = _temp_pfad(ziel)
        try:
            ziel_ordner.mkdir(parents=True, exist_ok=True)
            quelle = get_connection()
            try:
                kopie = sqlite3.connect(temp_ziel)
                try:
                    quelle.backup(kopie)
                finally:
                    kopie.close()
            finally:
                quelle.close()
            _abschliessen(temp_ziel, ziel, ziel_ordner, "Erstziel")
            erst_erfolgreich = True
        except Exception:
            temp_ziel.unlink(missing_ok=True)
            log.exception("DB-Sicherung fehlgeschlagen (Betrieb laeuft weiter)")
            return None
    if BACKUP_ZIEL2 is not None:
        _sichere_auf_zweitziel(ziel, dateiname)
    return str(ziel)


def _sichere_auf_zweitziel(erstkopie, dateiname: str) -> None:
    """Kopiert die bereits validierte Erstkopie zusaetzlich auf FINANZ_BACKUP_ZIEL2.

    Rein additiv und robust gegenueber einem nicht erreichbaren Ziel (z. B.
    NAS gerade offline): jeder Fehler wird nur geloggt, niemals weitergereicht.
    """
    ziel2 = BACKUP_ZIEL2 / dateiname
    temp_ziel2 = _temp_pfad(ziel2)
    try:
        if ziel2.exists() and _ist_gueltige_sqlite_datei(ziel2):
            return
        BACKUP_ZIEL2.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(erstkopie, temp_ziel2)
        _abschliessen(temp_ziel2, ziel2, BACKUP_ZIEL2, "Zweitziel")
    except Exception:
        try:
            temp_ziel2.unlink(missing_ok=True)
        except OSError:
            pass
        log.warning(
            "DB-Sicherung auf Zweitziel fehlgeschlagen, Erstkopie bleibt gueltig (%s)",
            BACKUP_ZIEL2,
            exc_info=True,
        )


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
