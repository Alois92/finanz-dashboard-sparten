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
import hashlib
import json
import logging
import os
import shutil
import sqlite3
import threading
import uuid
from pathlib import Path

from .db import DB_PATH, DB_PERSISTENT, get_connection

log = logging.getLogger("finanz.backup")

BACKUP_AUFBEWAHREN = 30          # so viele Tageskopien bleiben liegen
PRUEF_INTERVALL_SEKUNDEN = 6 * 3600  # laeuft der Server tagelang: alle 6 h pruefen

_ziel2_env = os.environ.get("FINANZ_BACKUP_ZIEL2")
BACKUP_ZIEL2 = Path(_ziel2_env.strip()) if _ziel2_env and _ziel2_env.strip() else None
sicherungs_lock = threading.Lock()


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


def _sha256(pfad: Path) -> str:
    digest = hashlib.sha256()
    with pfad.open("rb") as datei:
        for block in iter(lambda: datei.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _manifest_pfad(ordner: Path, datum: str) -> Path:
    return ordner / f"manifest-{datum}.json"


def _belegordner(ordner: Path, datum: str) -> Path:
    return ordner / f"belege-{datum}"


def _datei_info(pfad: Path) -> dict:
    return {"sha256": _sha256(pfad), "bytes": pfad.stat().st_size}


def _beleg_sicherungsdatei(quellpfad: Path, beleg_id: int, dateiname: str, wurzel: Path) -> str:
    """Gibt den sicheren relativen Manifestpfad fuer eine Belegkopie zurueck."""
    try:
        relativ = quellpfad.resolve().relative_to(wurzel.resolve())
    except ValueError:
        relativ = Path("fremd") / f"{beleg_id}_{Path(dateiname).name}"
    return relativ.as_posix()


def _beleg_ziel(zielordner: Path, datei: str) -> Path | None:
    """Loest einen Manifestpfad nur innerhalb des Belegordners auf."""
    ziel = zielordner / Path(datei)
    try:
        ziel.resolve().relative_to(zielordner.resolve())
    except ValueError:
        return None
    return ziel


def _sichere_belege(datum: str) -> dict:
    ordner = DB_PATH.parent / "backup"
    belege = []
    fehlend = []
    con = get_connection()
    try:
        rows = con.execute("SELECT id, dateiname, pfad FROM beleg ORDER BY id").fetchall()
    finally:
        con.close()
    zielordner = _belegordner(ordner, datum)
    zielordner.mkdir(parents=True, exist_ok=True)
    belege_wurzel = DB_PATH.parent / "belege"

    manifest_ziel = _manifest_pfad(ordner, datum)
    if manifest_ziel.is_file():
        try:
            alt = json.loads(manifest_ziel.read_text(encoding="utf-8"))
            alt_belege = {str(e["beleg_id"]): e for e in alt["belege"]}
            alt_fehlend = {str(e["beleg_id"]): e for e in alt["fehlend"]}
            unveraendert = True
            for row in rows:
                beleg_id, dateiname, quellpfad = row[0], row[1], row[2]
                quelle = Path(quellpfad) if quellpfad else None
                if quelle is None or not quelle.is_file():
                    unveraendert &= str(beleg_id) in alt_fehlend and alt_fehlend[str(beleg_id)]["pfad"] == str(quellpfad)
                    continue
                info = _datei_info(quelle)
                eintrag = alt_belege.get(str(beleg_id))
                ziel = _beleg_ziel(zielordner, _beleg_sicherungsdatei(quelle, beleg_id, dateiname, belege_wurzel))
                unveraendert &= bool(
                    eintrag
                    and ziel is not None
                    and eintrag["datei"] == _beleg_sicherungsdatei(quelle, beleg_id, dateiname, belege_wurzel)
                    and eintrag["sha256"] == info["sha256"]
                    and eintrag["bytes"] == info["bytes"]
                    and ziel.is_file()
                    and ziel.stat().st_size == info["bytes"]
                )
            if unveraendert and len(alt_belege) + len(alt_fehlend) == len(rows):
                return {"belege": alt["belege"], "fehlend": alt["fehlend"], "manifest": str(manifest_ziel)}
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            pass
    for row in rows:
        beleg_id, dateiname, quellpfad = row[0], row[1], row[2]
        quelle = Path(quellpfad) if quellpfad else None
        if quelle is None or not quelle.is_file():
            fehlend.append({"beleg_id": beleg_id, "pfad": str(quellpfad)})
            continue
        name = _beleg_sicherungsdatei(quelle, beleg_id, dateiname, belege_wurzel)
        ziel = zielordner / name
        ziel.parent.mkdir(parents=True, exist_ok=True)
        info = _datei_info(quelle)
        if not ziel.is_file() or _datei_info(ziel) != info:
            shutil.copyfile(quelle, ziel)
        belege.append({"beleg_id": beleg_id, "datei": name, **info})

    db = DB_PATH.parent / "backup" / f"finanz-{datum}.db"
    manifest = {
        "erstellt": dt.datetime.now().astimezone().isoformat(),
        "db": {"datei": db.name, **_datei_info(db)} if db.is_file() else None,
        "belege": belege,
        "fehlend": fehlend,
    }
    temp_manifest = _temp_pfad(manifest_ziel)
    try:
        temp_manifest.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        temp_manifest.replace(manifest_ziel)
    finally:
        temp_manifest.unlink(missing_ok=True)
    _rotiere(ordner)
    return {"belege": belege, "fehlend": fehlend, "manifest": str(manifest_ziel)}


def sichere_belege(datum: str) -> dict:
    """Kopiert referenzierte Belege und schreibt das Manifest des Sicherungssatzes."""
    with sicherungs_lock:
        return _sichere_belege(datum)


def _vollstaendiger_satz(ordner: Path, datum: str) -> bool:
    db = ordner / f"finanz-{datum}.db"
    manifest = _manifest_pfad(ordner, datum)
    belege = _belegordner(ordner, datum)
    return db.is_file() and _ist_gueltige_sqlite_datei(db) and manifest.is_file() and belege.is_dir()


def pruefe_sicherung(datum: str) -> dict:
    """Prueft Datenbank, Manifest und jede gesicherte Belegkopie."""
    ordner = DB_PATH.parent / "backup"
    db = ordner / f"finanz-{datum}.db"
    manifest_pfad = _manifest_pfad(ordner, datum)
    ergebnis = {"db_ok": False, "belege_ok": 0, "belege_fehlend": 0, "manifest_ok": False}
    if not _ist_gueltige_sqlite_datei(db) or not manifest_pfad.is_file():
        return ergebnis
    try:
        manifest = json.loads(manifest_pfad.read_text(encoding="utf-8"))
        db_info = manifest["db"]
        ergebnis["db_ok"] = (
            db_info["datei"] == db.name
            and db_info["bytes"] == db.stat().st_size
            and db_info["sha256"] == _sha256(db)
        )
        zielordner = _belegordner(ordner, datum)
        for eintrag in manifest["belege"]:
            ziel = _beleg_ziel(zielordner, eintrag["datei"])
            if ziel is not None and ziel.is_file() and eintrag["bytes"] == ziel.stat().st_size and eintrag["sha256"] == _sha256(ziel):
                ergebnis["belege_ok"] += 1
            else:
                ergebnis["belege_fehlend"] += 1
        ergebnis["belege_fehlend"] += len(manifest["fehlend"])
        ergebnis["manifest_ok"] = ergebnis["db_ok"] and ergebnis["belege_fehlend"] == len(manifest["fehlend"])
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return ergebnis
    return ergebnis


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
    with sicherungs_lock:
        if not DB_PERSISTENT:
            return None
        if not DB_PATH.exists():
            return None
        datum = dt.date.today().isoformat()
        dateiname = f"finanz-{datum}.db"
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
        try:
            _sichere_belege(datum)
        except Exception:
            log.exception("Beleg-Sicherung fehlgeschlagen (DB-Sicherung bleibt gueltig)")
        if BACKUP_ZIEL2 is not None:
            _sichere_auf_zweitziel(ziel, datum)
        return str(ziel)


def _sichere_auf_zweitziel(erstkopie, datum: str) -> None:
    """Kopiert den vollstaendigen validierten Sicherungssatz auf FINANZ_BACKUP_ZIEL2.

    Rein additiv und robust gegenueber einem nicht erreichbaren Ziel (z. B.
    NAS gerade offline): jeder Fehler wird nur geloggt, niemals weitergereicht.
    """
    dateiname = erstkopie.name
    ziel2 = BACKUP_ZIEL2 / dateiname
    temp_ziel2 = _temp_pfad(ziel2)
    try:
        BACKUP_ZIEL2.mkdir(parents=True, exist_ok=True)
        if not ziel2.exists() or not _ist_gueltige_sqlite_datei(ziel2):
            shutil.copyfile(erstkopie, temp_ziel2)
            _abschliessen(temp_ziel2, ziel2, BACKUP_ZIEL2, "Zweitziel")
        quellordner = erstkopie.parent
        ziel_belege = _belegordner(BACKUP_ZIEL2, datum)
        shutil.copytree(_belegordner(quellordner, datum), ziel_belege, dirs_exist_ok=True)
        shutil.copyfile(_manifest_pfad(quellordner, datum), _manifest_pfad(BACKUP_ZIEL2, datum))
        _rotiere(BACKUP_ZIEL2)
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
            datum = alt.stem.removeprefix("finanz-")
            shutil.rmtree(_belegordner(ordner, datum), ignore_errors=True)
            _manifest_pfad(ordner, datum).unlink(missing_ok=True)
        except OSError:
            log.warning("Alte DB-Sicherung nicht loeschbar: %s", alt)


async def backup_schleife() -> None:
    """Hintergrundaufgabe: beim Start und dann regelmaessig sichern."""
    while True:
        await asyncio.to_thread(sichere_datenbank)
        await asyncio.sleep(PRUEF_INTERVALL_SEKUNDEN)
