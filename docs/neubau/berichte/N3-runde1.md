# N3 Runde 1 – Kreditrate als eigene Spalte

Umgesetzt auf Zweig `fix/n3-kreditrate-spalte`; es wurden keine Commits oder Pushes erzeugt.

- `db/migrations/015_kredit_buchung.sql`: Ergänzt `buchung.kredit_id` mit Fremdschlüssel und Index, übernimmt numerische Altmarker und protokolliert Verweise auf fehlende Kredite idempotent.
- `db/schema.sql`: Zieht Spalte und Index der Migration im Sollschema nach.
- `app/routers/kredite.py`: Liest Raten über `kredit_id`, schreibt bei neuen Raten keine Marker-Notiz, liefert `kredit_id`, setzt Zuordnungen und bietet das Leeren über `/raten/loesen`.
- `app/routers/buchungen.py`: Liefert `kredit_id` in Listen- und Detailantworten; allgemeines Notiz-Editieren lässt die Zuordnung erhalten.
- `tests/test_kredit.py`: Prüft neue Raten, freie Notizen, Zuordnen/Lösen, Altmarker-Nachzug und Protokollierung fehlender Kredite.
- `tests/test_p20_migration.py`: Prüft Migration 015 zweimal sowie den exakten sqlite_master-Zustand aus dem Frischschema.
- `tests/test_auslagen.py`, `tests/test_bereiche_migration.py`, `tests/test_konten_bewegungen.py`, `tests/test_migrationsprotokoll.py`, `tests/test_saldoanker.py`, `tests/test_migrate.py`: Erwartungslisten und Zielversion auf 15 ergänzt.

Verifikation:

- Python-Syntaxprüfung für die geänderten Router: Exit 0.
- `git diff --check`: Exit 0.
- Isolierte Logik-/Migrationsprüfung: 2 Tests, 2 OK.
- Direkte SQLite-Nachzugsprobe: `apply1 [15]`, `apply2 []`; gültiger Marker wurde übernommen, fehlender Kredit als `kreditrate_ungeklaert` protokolliert.
- Vollständige vorgeschriebene Suite und `tests.test_kredit` konnten wegen des Windows-Sandbox-Temp-Rechtefehlers nicht grün durchlaufen: `sqlite3.OperationalError: unable to open database file` sowie `PermissionError: [WinError 5]` beim Aufräumen von `tempfile`-Verzeichnissen unter `%TEMP%`. Die betroffenen Testfälle wurden isoliert ausgewiesen; die temp-freie Logik-/Migrationsprüfung blieb grün.

Offen:

- Die vollständige Suite ist in dieser Sandbox nicht abschließend ausführbar, weil Python die von `tempfile` erzeugten Verzeichnisse weder öffnen noch löschen darf; dafür wurde kein Produktionscode und keine Abhängigkeit verändert.
