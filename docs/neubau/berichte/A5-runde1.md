# A5/A6 Runde 1 – Belegsicherung und ehrlicher Erfolgsstatus

Umgesetzt auf Zweig `fix/a5-a6-backup`, ohne Commit, Push, Migration oder neue Abhängigkeit.

## Ergebnisobjekt

Wörtliches Ergebnisobjekt eines vollständig erfolgreichen Laufs:

```python
{'datenbank': 'ok', 'belege': 'ok', 'zweitziel': 'nicht_konfiguriert'}
```

Bei Fehlern wird das betroffene Feld stattdessen als `{'fehler': '<Text>'}` geführt. Das letzte Ergebnis wird im Betriebsstatus mit ausgegeben. Ein Lauf mit fehlenden Belegen oder fehlerhaftem Zweitziel gilt nicht als vollständig gesichert.

## Umsetzung

- Belege liegen dedupliziert unter `belege-store/<sha256[:2]>/<sha256>.<ext>`.
- Tagesmanifeste (Version 2) enthalten Hash, Größe und Originalnamen; unveränderte Hashes werden am Folgetag nicht erneut kopiert.
- Zweitzielkopie überträgt nur fehlende bzw. beschädigte Store-Dateien und das Manifest; DB- und Belegprüfsummen werden danach verglichen.
- Die Zweitzielkopie läuft außerhalb des Locks der lokalen DB-/Belegsicherung.
- Rotation entfernt Store-Dateien nur, wenn kein verbleibendes Version-2-Manifest sie referenziert.
- Alte Manifestformate bleiben in `pruefe_sicherung` lesbar.
- `_sicherung_aus_backup` und der `vor_nachzug_version`-Pfad für A1 wurden nicht verändert.

## Fertig heißt

- [x] Tests grün für `tests/test_backup.py` und `tests/test_backup_nachzug.py`.
- [x] Vollständige relevante Testausgabe in `A5-tests.txt`.
- [x] Ergebnisobjekt wörtlich dokumentiert.
- [x] Keine Geheimnisse, keine neuen Abhängigkeiten.
- [x] Keine Migration und kein Frontend geändert.

## Offenes / Umgebung

Der komplette Discover-Lauf `python -m unittest discover -s tests` stößt in der Windows-Sandbox bereits in der Auth-/Anwendungssuite auf wiederholte `E`-Fehler und terminiert nicht innerhalb des Prüfzeitfensters. Er wurde deshalb nach 30 Sekunden beendet. Die von der Karte verlangten isolierten Backup- und Nachzugtests sind mit dem vorgegebenen Interpreter grün; die vollständige Ausgabe einschließlich des Sandbox-Hinweises steht in `A5-tests.txt`.

