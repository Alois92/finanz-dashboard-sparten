# P02: Belege in die Sicherung, Manifest, Betriebsstatus

Meilenstein M0. Modell: `gpt-5.6-luna`, Aufwand medium. Branch `pkt/p02-sicherung-belege` von `neubau` (nach Merge von P00 und P01).

## 1. Ziel

Die tägliche Sicherung umfasst neben der Datenbank auch alle referenzierten Belegdateien, mit einem Manifest aus Dateinamen und Prüfsummen, und lässt sich als Ganzes wiederherstellen. Ein angemeldeter Endpoint zeigt den Zustand von Sicherung und Schema.

## 2. Kontext

Lies `docs/neubau/ARCHITEKTUR.md` Abschnitt 14, dann `app/backup.py` vollständig (Tageskopie, Zweitziel, Rotation, `backup_schleife`), `app/routers/belege.py` (wo Belegdateien liegen, Feld `beleg.pfad`), `app/migrate.py` (Status), `tests/test_backup.py`, `docs/BETRIEB-UND-ARCHITEKTUR.md` Abschnitt Sicherung.

## 3. Schnittstellen

Sicherungssatz je Tag im bestehenden Ordner `<DB-Ordner>/backup/`:

```
finanz-JJJJ-MM-TT.db                 (wie bisher, SQLite-Backup-API)
belege-JJJJ-MM-TT/                   (Kopien aller referenzierten Belegdateien, Originalnamen)
manifest-JJJJ-MM-TT.json             {"erstellt": ISO, "db": {"datei", "sha256", "bytes"},
                                      "belege": [{"beleg_id", "datei", "sha256", "bytes"}],
                                      "fehlend": [{"beleg_id", "pfad"}]}
```

`app/backup.py`:

```python
def sichere_belege(datum: str) -> dict          # kopiert referenzierte Belege, schreibt Manifest, gibt Zusammenfassung zurück
def sichere_datenbank() -> str | None          # unverändert im Verhalten; ruft danach sichere_belege auf, Fehler nur geloggt
def pruefe_sicherung(datum: str) -> dict        # {"db_ok": bool, "belege_ok": int, "belege_fehlend": int, "manifest_ok": bool}
```

- Belege werden nur kopiert, wenn sich Größe oder Prüfsumme gegenüber dem Vortag geändert haben; unveränderte Dateien werden aus dem Vortag verlinkt oder erneut kopiert (Windows und Linux, deshalb: kopieren, keine Symlinks).
- Rotation (30 Sätze) gilt für DB, Belegordner und Manifest gemeinsam.
- Zweitziel (`FINANZ_BACKUP_ZIEL2`) erhält den vollständigen Satz; Erfolg nur, wenn DB, Belegordner und Manifest angekommen sind.
- Während der Sicherung dürfen Belege nicht endgültig gelöscht werden: `DELETE /api/belege/{id}` wartet auf ein Sicherungs-Lock (`threading.Lock` in `app/backup.py`).

Endpoint `GET /api/betrieb/status` (angemeldet):

```json
{"schema": {"aktuell": 2, "anstehend": []},
 "sicherung": {"letzte": "2026-09-09", "db_ok": true, "belege_ok": 41, "belege_fehlend": 0, "zweitziel": "ok"|"fehlt"|"nicht konfiguriert"},
 "schreibgeschuetzt": false}
```

Keine Pfade, keine Geheimnisse in der Antwort.

## 4. Nicht-Ziele

Kein Frontend. Keine Änderung am Beleg-Upload. Keine Wiederherstellungs-Automatik (Anleitung in `docs/BETRIEB-UND-ARCHITEKTUR.md` ergänzen: DB zurückkopieren, Belegordner zurückkopieren, Manifest prüfen).

## 5. Schritte

1. Tests zuerst (siehe 6).
2. `sichere_belege`, Manifest, Rotation, Zweitziel-Erweiterung.
3. Lock gegen Löschen während der Sicherung.
4. `GET /api/betrieb/status`.
5. Doku-Abschnitt Wiederherstellung.
6. Gesamtlauf, Bericht.

## 6. Tests

`tests/test_backup.py` erweitern:
- Zwei Belege anlegen (Dateien in einem Wegwerf-Belegordner), Sicherung ausführen: Belegordner und Manifest vorhanden, Prüfsummen stimmen mit den Originalen überein.
- Beleg-Datei fehlt auf der Platte: Manifest listet sie unter `fehlend`, Sicherung gilt trotzdem als erfolgreich für die DB.
- Zweiter Lauf am selben Tag ändert nichts (Idempotenz).
- Rotation entfernt DB, Belegordner und Manifest des 31. Tages gemeinsam.
- `pruefe_sicherung` erkennt eine manipulierte Belegkopie (Prüfsumme falsch).
- `GET /api/betrieb/status` liefert die Felder, ohne Pfade.

## 7. Fertig heißt

- [ ] Alle Tests grün, Ausgabe im Bericht.
- [ ] Wiederherstellung einmal von Hand auf einer Wegwerf-Kopie nachvollzogen (Schritte im Bericht).
- [ ] Keine Geheimnisse, keine neuen Abhängigkeiten (nur Standardbibliothek: `hashlib`, `shutil`, `json`).
- [ ] Bericht geschrieben.

## 8. Bericht zurück

Geänderte und neue Dateien mit je einem Satz. Vollständige Testausgabe. Offene Punkte mit Grund. Keine Commits, kein Push.
