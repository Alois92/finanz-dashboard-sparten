# F-N4 Umsetzungsplan

Ziel: Die vier Endpunkte der Paketkarte auf Schema 14 umsetzen. Keine Migration,
Abhängigkeiten, Frontendänderungen, Commits oder Pushes. Umsetzung im vorgegebenen
Worktree und Zweig; offene Fragen werden gemäß Auftrag im Bericht festgehalten.

Entwurf: `app/abgleich.py` bündelt Kandidatensuche, Zuordnung und Rücknahme.
Die Router in `app/routers/import_bank.py` und `app/routers/konten.py` verwenden
`BereichDep`. Schreibvorgänge sperren vor dem Lesen mit `BEGIN IMMEDIATE`, prüfen
Konto, Bereich, signierten Betrag und exklusive Bewegungszuordnung. Die manuelle
Bewegung bleibt mit der Buchung verknüpft, aber storniert. So bleibt ihre Identität
ohne zusätzliche Tabelle erhalten. Die importierte Bewegung bleibt stets aktiv.
`synchronisiere_buchung` erhält diese Rücknahmereferenz auch bei späterem PUT.
Eine separate Zuordnungstabelle würde eine unnötige Migration verlangen; bloßes
Neuerzeugen beim Lösen würde die ursprüngliche Bewegungsidentität verlieren.

- [x] `tests/test_abgleich.py`: echte ASGI-Anfragen, CSV-Import und Wegwerf-Schema;
  Doppelstand, Kandidaten und Datumsgrenzen, signierte Beträge, Rücknahme,
  Idempotenz, belegte Referenzen, Bereiche, bestehendes Verbuchen und PUT prüfen.
- [x] Neue Tests vor Implementierung mit dem Karteninterpreter ausführen;
  fehlende Endpunkte müssen als Ursache sichtbar sein.
- [x] Fachlogik und vier Routerfunktionen implementieren; gezielte Tests ausführen.
- [x] Gesamte unittest-Suite mit FINANZ_DB unter TEMP ausführen; Ausgabe vollständig
  in `N4-tests.txt` sichern. Eventuelle Auth-Sandboxprobleme isoliert nachprüfen.
- [x] Diff prüfen; tatsächliche Antworten aller vier Endpunkte und Grenzen in
  `N4-runde1.md` dokumentieren, keine Geheimnisse oder fachfremden Änderungen.
