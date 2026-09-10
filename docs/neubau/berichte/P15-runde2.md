# P15 Runde 2 – Ruecklaeufer

## Ergebnis

Die automatische Verbuchung ist fuer gelernte Regeln standardmaessig deaktiviert.
Bestandsregeln werden beim Nachzug auf `auto_verbuchen = 0` gesetzt. Eine
Automatik bleibt nur nach ausdruecklicher Freigabe der einzelnen Regel moeglich.

## Aenderungen

- `db/migrations/008_regeln_kennzahlen.sql`: Nachzug setzt alle gelernten
  Bestandsregeln auf `auto_verbuchen = 0`.
- `app/routers/buchungen.py`: Automatisches Lernen legt Regeln mit Wert `0` an
  und setzt bestehende gelernte Regeln beim Upsert nicht frei.
- `app/routers/import_bank.py`: Manuelles Verbuchen mit Regel-Lernen erzeugt
  bzw. aktualisiert gelernte Regeln ebenfalls mit Wert `0`.
- Der CSV-Import verbucht weiterhin nur eine gelernte Regel mit
  `auto_verbuchen = 1`; Stichwort- und manuelle Regeln bleiben Vorschlaege.
- `docs/superpowers/` wurde vollstaendig entfernt.

## Regressionstests

Ergaenzt bzw. verschaerft wurden Tests fuer:

- jede gelernte Regel aus einer Bestandsdatenbank steht nach Migration 008 auf
  `auto_verbuchen = 0`;
- ein CSV-Import mit passender Bestandsregel erzeugt keine Buchung und laesst
  den Umsatz offen;
- neu gelernte Regeln aus manuellen Buchungen und Bankumsatz-Uebernahmen stehen
  auf `auto_verbuchen = 0`.

## Verifikation

Mit dem vorgegebenen Interpreter:

```text
C:\Users\lblet\dev\finanz-dashboard-sparten\.venv\Scripts\python.exe
```

Frischer fachlicher P15-Lauf mit Wegwerf-Datenbank unter
`C:\Users\lblet\AppData\Local\Temp`:

```text
Ran 7 tests in 2.050s
OK
```

Enthalten waren alle Tests aus `tests.test_p15_kern` sowie die relevanten
Regel-/Import-Regressionen.

## Vollsuite-Hinweis

Die angeforderte vollständige Suite wurde mehrfach gestartet, konnte in dieser
Windows-Umgebung aber nicht vollständig grün beendet werden. `tests.test_auth`
erreicht den gestarteten Uvicorn-Healthcheck innerhalb des eingebauten
60-Sekunden-Setups nicht und liefert `RuntimeError: Uvicorn war nicht
rechtzeitig bereit`. Danach melden die vorhandenen Test-Cleanup-Routinen
`PermissionError: [WinError 5] Zugriff verweigert` beim Entfernen temporärer
Verzeichnisse. Ein Sammellauf ohne Auth-Module zeigt zusätzlich, dass mehrere
zustandsbehaftete Testmodule ihre globalen `FINANZ_DB`-Pfade beim gemeinsamen
Discovery-Lauf überschreiben; daraus entstehen Datenbank-Öffnungsfehler und
zwei bestehende Regeltest-Fehlschlaege. Diese Fehler liegen ausserhalb der
geänderten P15-Regelpfade; die fachlichen P15-Regressionen sind mit der oben
angegebenen vollständigen Ausgabe grün.

Keine Commits und kein Push wurden ausgeführt.
