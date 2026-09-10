# Befund N1 – Runde 1

## Umsetzung

Die Kennzahlberechnung grenzt die Buchungszeilen jetzt je Auswertung auf den
konkreten `kennzahl_term` (`t.id`) ein. Dadurch kann ein Join nicht mehr die
Zeilen eines gleich kategorisierten anderen Terms vervielfachen.

Migration 010 (`010_kennzahl_eindeutigkeit.sql`) legt den idempotenten eindeutigen
Index `(kennzahl_id, kategorie_id, vorzeichen)` an. Damit sind doppelte
Zuordnungen derselben Kategorie mit demselben Vorzeichen innerhalb einer
Kennzahl ausgeschlossen. Unterschiedliche Vorzeichen sowie dieselbe Kategorie
in verschiedenen Kennzahlen bleiben erlaubt. Das Basisschema enthält dieselbe
Bedingung.

Der Kennzahl-Endpunkt prüft die Termliste vor dem Schreiben und antwortet bei
einer unzulässigen Doppelnennung mit HTTP 422 und einer fachlichen Fehlermeldung,
statt den Datenbankfehler durchzureichen. Die Prüfung gilt für Anlegen und
Ändern.

## Tests

Ergänzt wurden Regressionstests für:

- termgenaue Beträge ohne Vervierfachung bei historischen doppelten Terms,
- 422 bei doppelter Kategorie mit gleichem Vorzeichen,
- erlaubte Gegenzeichen und erlaubte Verwendung in verschiedenen Kennzahlen,
- Idempotenz von Migration 010.

Die erwarteten Migrationslisten und Schema-Versionen der bestehenden Tests
wurden von 009 auf 010 aktualisiert.

Vollständiger Lauf mit dem vorgegebenen Interpreter:

```text
Ran 220 tests in 275.719s

OK (skipped=1)
```

Der eine Skip betrifft den bestehenden POSIX-Dateirechte-Test unter Windows.
Keine Commits oder Pushes wurden ausgeführt.
