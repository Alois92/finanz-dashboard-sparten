# F-N4 – Runde 1

Stand: 10. September 2026. Arbeitsverzeichnis `C:\Users\lblet\dev\wt-n4-abgleich`,
Zweig `fix/n4-abgleich-backend`.

## Umsetzung

Die vier Endpunkte aus F-N4 sind implementiert. Die Fachlogik liegt in
`app/abgleich.py`, die Endpunkte in den vorhandenen Import- und Kontenroutern.
Alle verwenden `BereichDep` und prüfen referenzierte Kennungen gegen den Bereich.
Schema und Migrationen bleiben unverändert; Schema 14 enthält alle benötigten
Felder. Keine neuen Abhängigkeiten, kein Frontend, keine Commits, kein Push.

Zuordnen setzt `buchung.bankumsatz_id`, erhöht die Buchungsversion und setzt den
Umsatz auf `verbucht`. Die ursprüngliche manuelle Bewegung wird storniert, ihre
Verknüpfung bleibt als Rücknahmereferenz erhalten. Die aktive Importbewegung wird
zusätzlich verknüpft. Dadurch zählt ausschließlich die importierte Bewegung.
Das Lösen entfernt diese Importverknüpfung, aktiviert dieselbe manuelle Bewegung,
leert die Umsatzreferenz und setzt den Umsatz auf `offen`. Die Importbewegung
bleibt aktiv. Beide Schreibvorgänge laufen vollständig in einer Transaktion mit
`BEGIN IMMEDIATE`; konkurrierende Zuordnungen werden serialisiert.

Wiederholte Zuordnung desselben Paars und wiederholtes Lösen liefern jeweils
HTTP 200 mit identischer Antwort und ohne zusätzliche Bewegungen oder
Versionsänderungen. Buchungszeilen, Kategorien und Kosten werden nicht durch
den Abgleich verändert. Die ursprüngliche Übernahme als neue Buchung über
`/verbuchen` bleibt erhalten.

Ein bestehendes PUT behält die Rücknahmereferenz. Nach einer nachträglichen
Betrags-, Text- oder Datumskorrektur aktiviert das Lösen die manuelle Bewegung
mit den aktuellen Buchungswerten. Die importierte Bankbewegung wird niemals
umgeschrieben. Konto oder Zahlungsweg dürfen bei bestehendem Abgleich nicht
inkompatibel geändert werden: zuerst lösen, andernfalls 409. Die beiden
PUT-Wechselwirkungen wurden im unabhängigen Review gefunden, durch rote
Regressionstests reproduziert und korrigiert.

## API-Vertrag und getroffene Festlegungen für P42

- Kandidaten sind bestehende Bank-/Kartenbuchungen desselben Kontos und Bereichs
  ohne Umsatzreferenz, mit passendem signiertem Betrag und aktiver manueller
  Bewegung. Datumsfenster: inklusive minus/plus fünf Kalendertage. Sortierung:
  Abstand, Datum, Buchungs-ID. Bei `verbucht` oder `ignoriert`: leere Liste.
- `betrag_cent` ist in beiden neuen Listen **signiert**, wie beim Bankumsatz;
  Ausgabe daher negativ. Buchungsköpfe speichern weiterhin positive Beträge.
- Das Datumsfenster dient der Vorschlagsliste. Eine ausdrückliche Zuordnung
  außerhalb des Fensters bleibt bei übereinstimmendem Konto/Betrag zulässig.
- Zuordnen erhält `{"buchung_id":3}`. Kennung muss eine positive ganze JSON-Zahl
  sein; Strings, Boolean, Float, null und null/fehlender Body werden mit 422
  abgewiesen. Fremde oder unbekannte Kennungen liefern 404.
- Betrag/Vorzeichen, Konto, bereits belegte Buchung/Umsatz/Bewegung, ignorierter
  Umsatz oder fehlende/mehrdeutige manuelle Bewegung liefern 409 mit `detail`.
  Ein Abgleich ist eine vollständige Eins-zu-eins-Zuordnung, keine Teilzuordnung.
- Lösen erhält keinen Body. `buchung_id:null` beschreibt den resultierenden
  Zustand ohne Zuordnung. Ein bereits offener Umsatz ohne Buchung ist ein
  erfolgreicher Leerlauf. Eine über `/verbuchen` neu erzeugte Buchung besitzt
  keine manuelle Rücknahmereferenz; dieser neue Endpunkt lehnt ihre Rücknahme
  mit 409 ab. Der bisherige Löschweg bleibt unverändert.
- Offene Abgleiche liefert getrennte Anzahlen und Listen. `manuelle_anzahl`
  zählt aktive manuelle Bewegungen ohne Umsatz, einschließlich separat erfasster
  Bewegungen ohne Buchung, ohne Transfers. `umsaetze_anzahl` zählt ausschließlich
  offene Umsätze mit mindestens einem Kandidaten. Diese Zahlen sind keine Anzahl
  eindeutiger Paare: Mehrfachkandidaten sind möglich und werden nicht automatisch
  zugeordnet. `kandidaten_anzahl` macht diese Mehrdeutigkeit sichtbar.

## Wörtliche Antworten

Die folgenden JSON-Blöcke wurden aus den tatsächlichen ASGI-Antwortbytes auf
einer Wegwerf-Datenbank erfasst. Beispieldaten: Konto 1, Buchung 3 vom 2. Januar,
Importumsatz 1 vom 3. Januar, jeweils Ausgabe 150 Cent. Alle vier Endpunkte sind
enthalten; zusätzlich sind Wiederholung und leere Übersicht dokumentiert.

### GET /api/bankumsaetze/1/kandidaten

HTTP 200

```json
{"kandidaten":[{"buchung_id":3,"datum":"2026-01-02","betrag_cent":-150,"text":"Lernmarker","abstand_tage":1}]}
```

### GET /api/konten/1/offene-abgleiche

HTTP 200

```json
{"konto_id":1,"manuelle_anzahl":1,"manuelle_bewegungen":[{"bewegung_id":1,"datum":"2026-01-02","betrag_cent":-150,"text":"Lernmarker"}],"umsaetze_anzahl":1,"offene_umsaetze":[{"bankumsatz_id":1,"datum":"2026-01-03","betrag_cent":-150,"text":"Banktest","kandidaten_anzahl":1}]}
```

### POST /api/bankumsaetze/1/zuordnen

HTTP 200

```json
{"bankumsatz_id":1,"buchung_id":3,"importstatus":"verbucht"}
```

### POST /api/bankumsaetze/1/zuordnen

HTTP 200

```json
{"bankumsatz_id":1,"buchung_id":3,"importstatus":"verbucht"}
```

### GET /api/konten/1/offene-abgleiche

HTTP 200

```json
{"konto_id":1,"manuelle_anzahl":0,"manuelle_bewegungen":[],"umsaetze_anzahl":0,"offene_umsaetze":[]}
```

### POST /api/bankumsaetze/1/zuordnung-loesen

HTTP 200

```json
{"bankumsatz_id":1,"buchung_id":null,"importstatus":"offen"}
```


## Tests und Prüfung

Die Tests verwenden den vorgegebenen Interpreter
`C:\Users\lblet\dev\finanz-dashboard-sparten\.venv\Scripts\python.exe` und
`FINANZ_DB` unter `%TEMP%`. Die vollständigen Ausgaben stehen in `N4-tests.txt`.
Der reproduzierbare Sandbox-Teststarter liegt in `N4-testlauf.py`.

Abgedeckt sind tatsächlicher CSV-Import und ASGI-Endpunkte, Doppelzählung und
ankergestützter Kontostand, identitätserhaltende Rücknahme, Idempotenz, positiver
und negativer Betrag, Datumssortierung und beide Fenstergrenzen, falsches Konto,
Bereich 2 gegen Bereich 1, unbekannte IDs, Bodyvalidierung, belegte Referenzen,
ignorierte Umsätze, eigenständige manuelle Bewegungen, vorhandenes Verbuchen,
PUT mit Versionsprüfung, geänderte Buchungsbeträge, neue Datenbankverbindung,
parallele Zuordnungen sowie vollständiger Rollback bei absichtlich ausgelösten
SQL-Fehlern beim Zuordnen und Lösen.

### Sandbox

Der unveränderte Kartenbefehl scheiterte bereits beim Testaufbau an
`sqlite3.OperationalError: unable to open database file` und
`PermissionError: [WinError 5]`: `TemporaryDirectory()` erzeugt unter diesem
Windows-Python mit Modus 0700 eine DACL, die den Sandbox-Prozess aussperrt.
Dieser Befund ist bereits in `A1-runde1.md` dokumentiert. Der Teststarter lässt
nur neue temporäre Testordner unter `%TEMP%` die vorhandenen Rechte erben.
Ein bestehender Kredit-Test verlangt ausdrücklich `C:\Users\lblet\dev` als
temporären Basispfad; nur dieser Testpfad wird nach `%TEMP%` umgeleitet.
Es werden keine Assertions, Authentifizierungsprüfungen oder Produktivdateien
dafür geändert. Das optionale Backup-Zweitziel bleibt im Teststarter leer.
Die vorhandene Windows-Testbereinigung ließ Uvicorn-Kindprozesse zurück.
Nach dem erfolgreichen Suite-Ende wurden ausschließlich die über Prozessabstammung
und Kommandozeile identifizierten Kinder dieses N4-Testlaufs beendet; andere
Server und Testläufe blieben unberührt.

### Ergebnis

- Gesamtsuite: **273 Tests in 262,235 Sekunden, OK (skipped=1), Exitcode 0**.
  Enth?lt s?mtliche bestehenden Suites einschlie?lich Auth sowie die ersten elf
  Abgleichtests. Die drei danach erg?nzten Tests sind im finalen Fokuslauf enthalten.
- Finaler Fokuslauf: **25 Tests in 16,413 Sekunden, OK, Exitcode 0**;
  alle 14 Tests in `test_abgleich.py` und elf bestehende Kontentests.
- Vor der Implementierung: f?nf erwartete Fehler durch fehlende Endpunkte.
  Die beiden PUT-Regressionen wurden jeweils zuerst rot nachgewiesen.
- Der einzige Skip ist der vorhandene `test_store_setzt_dateimodus_0600`
  (`POSIX-Dateirechte`), unter Windows nicht anwendbar. Kein neuer Skip.
- Erwartete Tracebacks aus absichtlich fehlerhaften Backup-/Bilddaten sind Teil
  der bestehenden Negativtests; die jeweiligen Tests sind gr?n.
- Syntaxpr?fung aller sechs betroffenen Python-Dateien und `git diff --check`
  bestanden. Git meldet lediglich die konfigurierte sp?tere LF/CRLF-Konvertierung.
- Der direkte Gesamtlauf ohne Sandbox-Starter endete ohne unittest-Abschluss mit
  Tool-Prozess-Exitcode 1. Der identische Testaufbaufehler wurde danach isoliert
  vollst?ndig protokolliert (14 Tests, 28 Setup-/Cleanup-Fehler). Derselbe
  Fachtestbestand l?uft mit dem dokumentierten Starter vollst?ndig gr?n.

Reproduktion im Arbeitsverzeichnis:

```powershell
& C:/Users/lblet/dev/finanz-dashboard-sparten/.venv/Scripts/python.exe docs/neubau/berichte/N4-testlauf.py
& C:/Users/lblet/dev/finanz-dashboard-sparten/.venv/Scripts/python.exe docs/neubau/berichte/N4-testlauf.py test_abgleich.py test_konten_bewegungen.py
git diff --check
```

Der Starter setzt `FINANZ_DB` selbst auf eine neue Wegwerf-Datei unter `%TEMP%`.
Die Logdatei enth?lt die vollst?ndige Ausgabe der isolierten Sandboxdiagnose,
des erfolgreichen Gesamtlaufs und des finalen Fokuslaufs.

Offen: keine fachlichen Punkte aus F-N4. Der rohe Kartenbefehl bleibt in dieser
Sandbox durch die beschriebenen Dateirechte eingeschr?nkt; f?r reproduzierbare
Pr?fungen ist hier der beigef?gte Teststarter erforderlich.

## Fertig heißt

- [x] Tests gr?n; vollst?ndige Ausgabe in `docs/neubau/berichte/N4-tests.txt`
  (dokumentierter Sandbox-Teststarter und bestehender Windows-Skip).
- [x] W?rtliches Antwort-JSON aller vier neuen Endpunkte in diesem Bericht.
- [x] Keine Geheimnisse und keine neuen Abh?ngigkeiten; ausschlie?lich synthetische Testdaten.
- [x] Bericht `docs/neubau/berichte/N4-runde1.md` erstellt.
- [x] Keine Migration, kein Frontend, keine Commits, kein Push.
