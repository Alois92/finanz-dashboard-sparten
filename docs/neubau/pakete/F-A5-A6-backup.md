# F-A5/A6: Belegsicherung ohne tägliche Vollkopie, ehrlicher Erfolgsstatus

Fix aus der Schuldenliste (A5, A6). Modell `gpt-5.6-luna`, Aufwand medium. Arbeitsort `C:\Users\lblet\dev\wt-a5-backup`, Zweig `fix/a5-a6-backup` (auf `neubau`). Keine Commits, kein Push, keine Migration. Betroffen nur `app/backup.py`, `app/routers/betrieb.py` (Betriebsstatus) und Tests.

## Befund

- A5: `_sichere_belege` kopiert jeden Tag alle Belege vollständig; `_sichere_auf_zweitziel` schiebt alle sechs Stunden den ganzen Belegordner per `copytree` übers Netz, und zwar unter dem Sicherungs-Lock, der währenddessen Löschungen und den Start blockiert.
- A6: Scheitert die Beleg- oder Zweitziel-Sicherung, wird nur geloggt; `sichere_datenbank()` meldet trotzdem Erfolg. Am Zweitziel wird nur die Existenz geprüft, keine Prüfsumme.

## Ziel

- Belege **inhaltsadressiert** sichern: jede Datei liegt genau einmal unter `belege-store/<sha256[:2]>/<sha256>.<ext>` im Sicherungsordner; das Tagesmanifest verweist auf Hash und Originalnamen. Vorhandener Hash → kein Kopieren. Die Rotation löscht Store-Dateien nur, wenn kein verbleibendes Manifest sie referenziert.
- Zweitziel: nur fehlende Store-Dateien und das neue Manifest übertragen, nach dem Kopieren Prüfsumme vergleichen, Fehler nicht verschlucken.
- `sichere_datenbank()` gibt ein Ergebnisobjekt zurück: `{"datenbank": "ok", "belege": "ok" | {"fehler": text}, "zweitziel": "ok" | {"fehler": text} | "nicht_konfiguriert"}`. Der Betriebsstatus-Endpunkt zeigt das letzte Ergebnis. Nur ein voll erfolgreicher Lauf gilt als gesichert (`pruefe_sicherung`).
- Die Netzkopie aufs Zweitziel läuft **außerhalb** des Locks, der die Datenbank schützt. Der Lock gilt nur für die lokale Kopie.
- Bestehende Sicherungen im alten Format bleiben lesbar (`pruefe_sicherung` versteht beide Manifestformen). Die A1-Sicherungen `…-vor-nachzug-…` bleiben unangetastet.

## Tests

`tests/test_backup.py` erweitern: zweiter Lauf am Folgetag kopiert unveränderte Belege nicht erneut; geänderter Beleg landet als neuer Hash; Zweitziel-Fehler → Status `fehler` und Tag nicht gesichert; Prüfsummenabweichung am Zweitziel wird erkannt; Rotation behält referenzierte Store-Dateien; altes Manifest bleibt prüfbar.

## Interpreter

`C:\Users\lblet\dev\finanz-dashboard-sparten\.venv\Scripts\python.exe -m unittest discover -s tests`, vorher `FINANZ_DB` auf eine Wegwerf-Datei unter `%TEMP%`. Sandbox-Probleme mit der Auth-Suite im Bericht nennen und `tests/test_backup.py` isoliert grün zeigen.

## Fertig heißt

- [ ] Tests grün, Ausgabe in `docs/neubau/berichte/A5-tests.txt`
- [ ] Ergebnisobjekt wörtlich im Bericht
- [ ] Keine Geheimnisse, keine neuen Abhängigkeiten
- [ ] Bericht `docs/neubau/berichte/A5-runde1.md`
