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
import re
import shutil
import sqlite3
import threading
import uuid
from pathlib import Path

from .db import DB_PATH, DB_PERSISTENT, get_connection

log = logging.getLogger("finanz.backup")

BACKUP_AUFBEWAHREN = 30          # so viele Tageskopien bleiben liegen
NACHZUG_AUFBEWAHREN = 10         # unabhaengig von den Tageskopien
PRUEF_INTERVALL_SEKUNDEN = 6 * 3600  # laeuft der Server tagelang: alle 6 h pruefen

_ziel2_env = os.environ.get("FINANZ_BACKUP_ZIEL2")
BACKUP_ZIEL2 = Path(_ziel2_env.strip()) if _ziel2_env and _ziel2_env.strip() else None
sicherungs_lock = threading.Lock()
_letztes_ergebnis = None


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


def _store_pfad(ordner: Path, sha256: str, dateiname: str) -> Path:
    suffix = Path(dateiname).suffix
    return ordner / "belege-store" / sha256[:2] / f"{sha256}{suffix}"


def _sichere_belege(datum: str) -> dict:
    ordner = DB_PATH.parent / "backup"
    belege = []
    fehlend = []
    con = get_connection()
    try:
        rows = con.execute("SELECT id, dateiname, pfad FROM beleg ORDER BY id").fetchall()
    finally:
        con.close()
    manifest_ziel = _manifest_pfad(ordner, datum)
    for row in rows:
        beleg_id, dateiname, quellpfad = row[0], row[1], row[2]
        quelle = Path(quellpfad) if quellpfad else None
        if quelle is None or not quelle.is_file():
            fehlend.append({"beleg_id": beleg_id, "pfad": str(quellpfad)})
            continue
        info = _datei_info(quelle)
        ziel = _store_pfad(ordner, info["sha256"], dateiname)
        ziel.parent.mkdir(parents=True, exist_ok=True)
        if not ziel.is_file() or _datei_info(ziel) != info:
            shutil.copyfile(quelle, ziel)
        belege.append({"beleg_id": beleg_id, "dateiname": Path(dateiname).name, **info})

    db = DB_PATH.parent / "backup" / f"finanz-{datum}.db"
    manifest = {
        "version": 2,
        "erstellt": dt.datetime.now().astimezone().isoformat(),
        "db": {"datei": db.name, **_datei_info(db)} if db.is_file() else None,
        "belege": belege,
        "fehlend": fehlend,
    }
    if manifest_ziel.is_file():
        try:
            vorhanden = json.loads(manifest_ziel.read_text(encoding="utf-8"))
            if (
                vorhanden.get("version", 1) >= 2
                and vorhanden.get("db") == manifest["db"]
                and vorhanden.get("belege") == manifest["belege"]
                and vorhanden.get("fehlend") == manifest["fehlend"]
            ):
                return {"belege": vorhanden["belege"], "fehlend": vorhanden["fehlend"], "manifest": str(manifest_ziel)}
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            pass
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
    return pruefe_sicherung_in_ordner(ordner, datum)["manifest_ok"]


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
        neu = manifest.get("version", 1) >= 2
        for eintrag in manifest["belege"]:
            ziel = (
                _store_pfad(ordner, eintrag["sha256"], eintrag["dateiname"])
                if neu else _beleg_ziel(zielordner, eintrag["datei"])
            )
            if ziel is not None and ziel.is_file() and eintrag["bytes"] == ziel.stat().st_size and eintrag["sha256"] == _sha256(ziel):
                ergebnis["belege_ok"] += 1
            else:
                ergebnis["belege_fehlend"] += 1
        ergebnis["belege_fehlend"] += len(manifest["fehlend"])
        ergebnis["manifest_ok"] = ergebnis["db_ok"] and ergebnis["belege_fehlend"] == 0
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


def _sichere_vor_nachzug(zielversion: int) -> str | None:
    """Schreibt unter sicherungs_lock immer einen neuen Stand vor dem Nachzug."""
    ziel_ordner = DB_PATH.parent / "backup"
    name = f"finanz-{dt.datetime.now():%Y-%m-%d-%H%M}-vor-nachzug-v{zielversion}"
    ziel = None
    temp_ziel = None
    erfolgreich = False
    try:
        ziel_ordner.mkdir(parents=True, exist_ok=True)
        nummer = 1
        for vorhanden in ziel_ordner.glob(f"{name}*.db"):
            zusatz = vorhanden.stem.removeprefix(name)
            if not zusatz:
                nummer = max(nummer, 2)
            elif zusatz.startswith("-") and zusatz[1:].isdigit():
                nummer = max(nummer, int(zusatz[1:]) + 1)
        while True:
            zusatz = "" if nummer == 1 else f"-{nummer}"
            kandidat = ziel_ordner / f"{name}{zusatz}.db"
            try:
                # Exklusiv reservieren: auch ein weiterer Prozess darf keine
                # bereits vorhandene Nachzugssicherung ueberschreiben.
                with kandidat.open("xb"):
                    pass
                ziel = kandidat
                break
            except FileExistsError:
                nummer += 1
        temp_ziel = _temp_pfad(ziel)
        quelle = get_connection()
        try:
            kopie = sqlite3.connect(temp_ziel)
            try:
                quelle.backup(kopie)
            finally:
                kopie.close()
        finally:
            quelle.close()
        if not _ist_gueltige_sqlite_datei(temp_ziel):
            raise sqlite3.DatabaseError("Sicherung vor Nachzug ist nicht intakt")
        temp_ziel.replace(ziel)
        erfolgreich = True
        log.info("DB-Sicherung vor Schema-Nachzug angelegt: %s", ziel)
        _rotiere_nachzug(ziel_ordner)
        return str(ziel)
    except Exception:
        log.exception("DB-Sicherung vor Schema-Nachzug fehlgeschlagen")
        return None
    finally:
        for rest in (temp_ziel, ziel if not erfolgreich else None):
            if rest is not None:
                try:
                    rest.unlink(missing_ok=True)
                except OSError:
                    log.warning("Unvollstaendige Nachzugssicherung nicht loeschbar: %s", rest)


def _rotiere_nachzug(ordner: Path) -> None:
    """Behaelt die zehn zuletzt geschriebenen Nachzugssicherungen."""
    kopien = []
    for pfad in ordner.glob("finanz-????-??-??-????-vor-nachzug-v*.db"):
        treffer = re.fullmatch(
            r"finanz-(\d{4}-\d{2}-\d{2}-\d{4})-vor-nachzug-v(\d+)(?:-(\d+))?\.db",
            pfad.name,
        )
        if treffer is not None:
            zeit, version, nummer = treffer.groups()
            kopien.append((pfad.stat().st_mtime_ns, zeit, int(version), int(nummer or 1), pfad))
    for *_, alt in sorted(kopien)[:-NACHZUG_AUFBEWAHREN]:
        try:
            alt.unlink()
            log.info("Alte Nachzugssicherung entfernt: %s", alt.name)
        except OSError:
            log.warning("Alte Nachzugssicherung nicht loeschbar: %s", alt)


def sichere_datenbank(vor_nachzug_version: int | None = None):
    """Legt die heutige Tageskopie an (falls noch nicht vorhanden).

    Rueckgabe: Ergebnisobjekt mit getrennten Statuswerten fuer DB, Belege und
    Zweitziel. Fehler werden geloggt, aber nie zum Serverabbruch.

    Ist FINANZ_BACKUP_ZIEL2 gesetzt, werden fehlende Store-Dateien und das
    Manifest ausserhalb des lokalen Sicherungs-Locks uebertragen.

    Mit vor_nachzug_version wird stattdessen immer eine eigene frische
    Datenbankkopie erstellt; davon bleiben die letzten zehn erhalten.
    Dieser Modus erstellt weder Tagesmanifest noch Beleg- oder Zweitkopie.
    """
    global _letztes_ergebnis
    if vor_nachzug_version is not None:
        with sicherungs_lock:
            if not DB_PERSISTENT or not DB_PATH.exists():
                return None
            return _sichere_vor_nachzug(vor_nachzug_version)
    ergebnis = {"datenbank": "ok", "belege": "ok", "zweitziel": "nicht_konfiguriert"}
    if not DB_PERSISTENT or not DB_PATH.exists():
        ergebnis["datenbank"] = {"fehler": "keine persistente Datenbank konfiguriert"}
        _letztes_ergebnis = ergebnis
        return ergebnis
    datum = dt.date.today().isoformat()
    ziel_ordner = DB_PATH.parent / "backup"
    ziel = ziel_ordner / f"finanz-{datum}.db"
    with sicherungs_lock:
        try:
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
                finally:
                    temp_ziel.unlink(missing_ok=True)
        except Exception as exc:
            log.exception("Lokale Sicherung fehlgeschlagen (Betrieb laeuft weiter)")
            ergebnis["datenbank"] = {"fehler": str(exc)}
        else:
            try:
                beleg_ergebnis = _sichere_belege(datum)
                if beleg_ergebnis["fehlend"]:
                    ergebnis["belege"] = {"fehler": f"{len(beleg_ergebnis['fehlend'])} Beleg(e) fehlen"}
            except Exception as exc:
                log.exception("Beleg-Sicherung fehlgeschlagen (Betrieb laeuft weiter)")
                ergebnis["belege"] = {"fehler": str(exc)}
    if ergebnis["datenbank"] == "ok" and BACKUP_ZIEL2 is not None:
        try:
            _sichere_auf_zweitziel(ziel, datum)
        except Exception as exc:
            log.warning("Sicherung auf Zweitziel fehlgeschlagen", exc_info=True)
            ergebnis["zweitziel"] = {"fehler": str(exc)}
        else:
            ergebnis["zweitziel"] = "ok"
    _letztes_ergebnis = ergebnis
    return ergebnis


def _sichere_auf_zweitziel(erstkopie, datum: str) -> None:
    """Kopiert den vollstaendigen validierten Sicherungssatz auf FINANZ_BACKUP_ZIEL2.

    Rein additiv und robust gegenueber einem nicht erreichbaren Ziel (z. B.
    NAS gerade offline): jeder Fehler wird nur geloggt, niemals weitergereicht.
    """
    dateiname = erstkopie.name
    ziel2 = BACKUP_ZIEL2 / dateiname
    BACKUP_ZIEL2.mkdir(parents=True, exist_ok=True)
    quellordner = erstkopie.parent
    manifest = json.loads(_manifest_pfad(quellordner, datum).read_text(encoding="utf-8"))
    if not ziel2.is_file() or _sha256(ziel2) != _sha256(erstkopie):
        temp_ziel2 = _temp_pfad(ziel2)
        try:
            shutil.copyfile(erstkopie, temp_ziel2)
            if _sha256(temp_ziel2) != _sha256(erstkopie):
                raise IOError("Pruefsumme der Zweitkopie stimmt nicht")
            temp_ziel2.replace(ziel2)
        finally:
            temp_ziel2.unlink(missing_ok=True)
    for eintrag in manifest.get("belege", []):
        if manifest.get("version", 1) < 2:
            continue
        quelle = _store_pfad(quellordner, eintrag["sha256"], eintrag["dateiname"])
        ziel = _store_pfad(BACKUP_ZIEL2, eintrag["sha256"], eintrag["dateiname"])
        ziel.parent.mkdir(parents=True, exist_ok=True)
        if not ziel.is_file() or _datei_info(ziel) != {"sha256": eintrag["sha256"], "bytes": eintrag["bytes"]}:
            shutil.copyfile(quelle, ziel)
        if _datei_info(ziel) != {"sha256": eintrag["sha256"], "bytes": eintrag["bytes"]}:
            raise IOError(f"Pruefsumme der Belegkopie stimmt nicht: {ziel}")
    manifest_ziel = _manifest_pfad(BACKUP_ZIEL2, datum)
    manifest_ziel.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if not _pruefe_zweitziel(datum):
        raise IOError("Pruefung der Zweitzielsicherung fehlgeschlagen")
    _rotiere(BACKUP_ZIEL2)


def _pruefe_zweitziel(datum: str) -> bool:
    return pruefe_sicherung_in_ordner(BACKUP_ZIEL2, datum)["manifest_ok"]


def pruefe_sicherung_in_ordner(ordner: Path, datum: str) -> dict:
    db = ordner / f"finanz-{datum}.db"
    manifest_pfad = _manifest_pfad(ordner, datum)
    if not db.is_file() or not manifest_pfad.is_file() or not _ist_gueltige_sqlite_datei(db):
        return {"manifest_ok": False}
    try:
        manifest = json.loads(manifest_pfad.read_text(encoding="utf-8"))
        if manifest["db"]["sha256"] != _sha256(db):
            return {"manifest_ok": False}
        if manifest.get("fehlend"):
            return {"manifest_ok": False}
        for eintrag in manifest.get("belege", []):
            ziel = (_store_pfad(ordner, eintrag["sha256"], eintrag["dateiname"])
                    if manifest.get("version", 1) >= 2
                    else _beleg_ziel(_belegordner(ordner, datum), eintrag["datei"]))
            if ziel is None or not ziel.is_file() or _datei_info(ziel) != {"sha256": eintrag["sha256"], "bytes": eintrag["bytes"]}:
                return {"manifest_ok": False}
        return {"manifest_ok": True}
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return {"manifest_ok": False}


def _rotiere(ordner) -> None:
    kopien = sorted(ordner.glob("finanz-????-??-??.db"))
    for alt in kopien[:-BACKUP_AUFBEWAHREN]:
        try:
            alt.unlink()
            log.info("Alte DB-Sicherung entfernt: %s", alt.name)
            datum = alt.stem.removeprefix("finanz-")
            shutil.rmtree(_belegordner(ordner, datum), ignore_errors=True)
            _manifest_pfad(ordner, datum).unlink(missing_ok=True)
            _bereinige_store(ordner)
        except OSError:
            log.warning("Alte DB-Sicherung nicht loeschbar: %s", alt)


def _bereinige_store(ordner: Path) -> None:
    referenzen = set()
    for manifest_pfad in ordner.glob("manifest-????-??-??.json"):
        try:
            manifest = json.loads(manifest_pfad.read_text(encoding="utf-8"))
            if manifest.get("version", 1) >= 2:
                referenzen.update(
                    (eintrag["sha256"], eintrag["dateiname"])
                    for eintrag in manifest.get("belege", [])
                )
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            continue
    store = ordner / "belege-store"
    if not store.is_dir():
        return
    for pfad in store.rglob("*"):
        if pfad.is_file() and (pfad.stem, pfad.name[len(pfad.stem):]) not in referenzen:
            try:
                pfad.unlink()
            except OSError:
                log.warning("Alte Store-Datei nicht loeschbar: %s", pfad)


async def backup_schleife() -> None:
    """Hintergrundaufgabe: beim Start und dann regelmaessig sichern."""
    while True:
        await asyncio.to_thread(sichere_datenbank)
        await asyncio.sleep(PRUEF_INTERVALL_SEKUNDEN)
