# P01: Bank-CSV-Import robust (George UTF-16, Trennzeichen, Spalten, Fingerabdruck)

Meilenstein M0. Modell: `gpt-5.6-luna`, Aufwand medium. Branch `pkt/p01-csv-import` von `neubau` (nach Merge von P00).

## 1. Ziel

Der Jahres- oder Monatsexport von George (Sparkasse, UTF-16 LE mit BOM, Komma-getrennt, Spalte „Buchungs-Details") lässt sich einspielen, ohne dass das bisherige Semikolon-Format bricht. Wiederholte oder überlappende Importe erzeugen keine Dubletten, und die Fehlermeldung sagt, was erkannt wurde.

## 2. Kontext

Lies `docs/neubau/ARCHITEKTUR.md` Abschnitt 1 und 10, dann `app/routers/import_bank.py` (vollständig: `_dekodiere`, Spaltenerkennung, Fingerabdruck, `POST /api/import/csv`), `tests/test_import_bank.py`, `beispiele/bank_beispiel.csv`, `db/schema.sql` (Tabellen `bankumsatz`, `import_batch`). Hintergrund der Analyse: George-Datei mit 13 Spalten `Eigener Kontoname, Eigene IBAN, Buchungsdatum, Partnername, Partner IBAN, BIC/SWIFT, Partner Kontonummer, Bankleitzahl, Betrag, Währung, Buchungs-Details, Empfänger-Überprüfung, Diese IBAN ist registriert auf`; Betrag im Format `-1.234,56`; Datum absteigend; manche Zeilen ohne Text oder Partner; einige Beträge `0,00`; keine Saldospalte. Der bisherige Decoder rät `cp1252`, das nie einen Fehler wirft, deshalb wird UTF-16 stillschweigend zu Müll.

## 3. Schnittstellen

Parser-Funktionen in `app/routers/import_bank.py` (oder neues Modul `app/csv_erkennung.py`, das der Router nutzt):

```python
def dekodiere(rohbytes: bytes) -> tuple[str, str]        # (text, kodierung) — BOM-Prüfung UTF-16 LE/BE und UTF-8 VOR dem Raten; danach utf-8 strict, dann cp1252
def erkenne_trennzeichen(text: str) -> str               # ';' ',' oder '\t' anhand der Kopfzeile (häufigstes Zeichen, das in allen Datenzeilen gleich oft vorkommt)
def erkenne_spalten(kopf: list[str]) -> dict             # {"datum": idx, "betrag": idx, "text": idx|None, "gegenpartei": idx|None, "iban": idx|None, "waehrung": idx|None}
def parse_betrag_cent(wert: str) -> int                  # '-1.234,56' → -123456; '1234.56' → 123456; '1,234.56' → 123456; '0,00' → 0; ungültig → ValueError
def parse_datum(wert: str) -> str                        # '31.12.2025', '2025-12-31', '12/31/2025' → '2025-12-31'; ungültig → ValueError
def fingerabdruck(konto_id, datum, betrag_cent, text, gegenpartei, iban, vorkommen: int) -> str
```

Spaltenkatalog mit Prioritäten (Vergleich in Kleinbuchstaben, ohne Sonderzeichen; genaue Treffer vor Teilstring):
- Datum: `buchungsdatum`, `datum`, `valuta`, `date`, `booking date`
- Betrag: `betrag`, `amount`
- Text: `buchungs-details`, `buchungsdetails`, `details`, `verwendungszweck`, `buchungstext`, `umsatztext`, `description`, `memo`
- Gegenpartei: `partnername`, `partner`, `empfänger`, `auftraggeber`, `payee`, `name` — aber nie `eigener kontoname`
- IBAN: `partner iban`, `iban gegenpartei`, `gegen-iban`, `iban` — aber nie `eigene iban`
- Währung: `währung`, `waehrung`, `currency`

Fingerabdruck: `sha256(konto_id|datum|betrag_cent|norm(text)|norm(gegenpartei)|norm(iban)|vorkommen)`. `vorkommen` ist die laufende Nummer identischer Merkmale innerhalb derselben Datei (erste Zeile 0, zweite identische 1). Kompatibilität: beim Import wird zusätzlich der **alte** Fingerabdruck (`sha256(konto|datum|betrag|text)`, wie bisher) geprüft; existiert er bereits, gilt die Zeile als bekannt und wird nicht erneut angelegt. Neue Zeilen erhalten nur den neuen Fingerabdruck.

`POST /api/import/csv` behält Signatur und Antwortform; die Antwort bekommt zusätzlich `erkannt: {"kodierung", "trennzeichen", "spalten": {...}, "zeilen_gesamt", "zeilen_ungueltig": [{"zeile": n, "grund": "..."}]}`. Bei nicht erkennbaren Pflichtspalten (Datum, Betrag): HTTP 400 mit `detail`, das Kodierung, Trennzeichen und die gefundene Kopfzeile nennt. Zeilen mit Betrag 0 werden importiert und bleiben offen. `import_batch` bekommt neue Spalten `dateihash TEXT`, `parser_version INTEGER NOT NULL DEFAULT 2`, `zeitraum_von TEXT`, `zeitraum_bis TEXT`, `anzahl_ungueltig INTEGER` per Migration `db/migrations/002_import_batch_erkennung.sql` (und in `db/schema.sql`).

## 4. Nicht-Ziele

Kein Frontend. Keine Änderung an Vorschlägen, Regeln oder Verbuchung. Keine xlsx-Unterstützung, kein SwissBorg, kein Orderbuch. Kein PDF.

## 5. Schritte

1. Tests zuerst: Fixture `tests/fixtures/george_2025_auszug.csv` selbst erzeugen (UTF-16 LE mit BOM, Komma, die 13 George-Spalten, 8 Zeilen: normale Ausgabe, Einnahme, Zeile ohne Text, Zeile ohne Partner, Betrag `0,00`, zwei identische Zeilen, eine mit Umlauten). Keine echten Namen oder IBANs, erfundene Werte.
2. `dekodiere`, `erkenne_trennzeichen`, `erkenne_spalten`, `parse_betrag_cent`, `parse_datum` umsetzen.
3. Fingerabdruck mit Vorkommensnummer und Alt-Hash-Kompatibilität.
4. Migration 002 und `schema.sql`.
5. Router anpassen, Antwort erweitern, Fehlermeldung.
6. Gesamtlauf, Bericht.

## 6. Tests

`tests/test_import_bank.py` erweitern (bestehende Tests bleiben):
- George-Fixture: 8 Zeilen, alle 8 importiert, Kodierung `utf-16`, Trennzeichen `,`, Text aus „Buchungs-Details", Gegenpartei aus „Partnername" (nicht „Eigener Kontoname"), IBAN aus „Partner IBAN".
- Zwei identische Zeilen ergeben zwei Umsätze (Vorkommen 0 und 1); erneuter Import derselben Datei ergibt 0 neue, 8 Dubletten.
- Bestehendes Semikolon-Beispiel `beispiele/bank_beispiel.csv` importiert wie bisher (Anzahl wie im bestehenden Test).
- Alt-Hash-Kompatibilität: Umsatz mit altem Fingerabdruck in der DB anlegen, dieselbe Zeile im neuen Format importieren → 0 neue.
- `parse_betrag_cent`: `-1.234,56`, `1234.56`, `1,234.56`, `0,00`, `abc` (ValueError).
- `parse_datum`: drei Formate, ungültig.
- Datei ohne Betragsspalte → 400, `detail` enthält „Betrag".
- Migration 002 auf einer Datenbank ohne die neuen Spalten läuft und ist idempotent (zweiter Lauf über den Runner aus P00 tut nichts).

## 7. Fertig heißt

- [ ] Alle Tests grün, vollständige Ausgabe im Bericht.
- [ ] Migration 002 zweimal über `python -m app.migrate apply` auf einer Wegwerf-DB gelaufen.
- [ ] `schema.sql` und Nachzug ergeben dieselben Spalten in `import_batch`.
- [ ] Keine Geheimnisse, keine echten Namen oder IBANs in Fixtures.
- [ ] Bericht geschrieben.

## 8. Bericht zurück

Geänderte und neue Dateien mit je einem Satz. Vollständige Testausgabe. Offene Punkte mit Grund. Keine Commits, kein Push.
