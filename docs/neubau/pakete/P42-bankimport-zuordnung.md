# P42: Bankimport mit Zuordnung zu Bewegungen

Meilenstein M4. Branch `pkt/p42-bankimport-zuordnung` von `neubau` (nach P11, P15, P30).

## 1. Ziel

Jeder neu importierte Bankumsatz bekommt genau eine Bewegung, wie in der Architektur vorgesehen — dieses Verdrahten für laufende Importe fehlt noch, P11 hat nur den einmaligen Nachzug bestehender Umsätze beschrieben. War die Zahlung schon manuell erfasst (vorläufige Bewegung), wird sie beim Import ersetzt statt verdoppelt. Der Nutzer sieht im neuen Frontend echte Umsätze mit Status, ordnet offene zu, übernimmt Vorschläge, ignoriert Rest und führt Doppelerfassungen zusammen.

## 2. Kontext

Lies `docs/neubau/ARCHITEKTUR.md` Abschnitt 3 („Ein importierter Bankumsatz erzeugt genau eine Bewegung … beim späteren Abgleich mit dem Import wird sie durch die importierte ersetzt, nicht addiert"), dann `docs/neubau/pakete/P11-konten-bewegungen.md` (Tabellen `bewegung`, `transfer`, `buchung_bewegung`, Regeln für Anlegen/Ändern/Löschen von Buchungen), `docs/neubau/pakete/P15-kategorien-regeln-kennzahlen.md` (Regel-Herkunft, `auto_verbuchen`, Stichwörter sind Vorschläge, Konflikt-Erkennung), `docs/neubau/pakete/P30-frontend-geruest.md`, `app/routers/import_bank.py` vollständig (CSV-Parser aus P01 unverändert lassen; `import_csv`, `list_bankumsaetze`, `_vorschlag_fuer_umsatz`, `verbuche_umsatz`, `uebernehme_vorschlaege`, `setze_umsatzstatus`), `app/bereiche.py` (`pruefe_bewegung`, `pruefe_umsatz`, `pruefe_konto` — von P10/P11 bereitgestellt), `tests/test_import_bank.py`. Vorlage für Wortlaut und Zustände (`auto`/`vor`/`offen`/`umb`): `docs/neubau/prototyp/prototyp.html`, Abschnitt „Bankimport" (Zeilen ~707–720) und `renderBank` (Zeilen ~1761–1784) — dort ist die Interaktion bewusst nur angedeutet, die echte Verdrahtung ist Aufgabe dieses Pakets.

## 3. Schnittstellen

Keine neue Migration; nutzt die Tabellen aus P11 unverändert.

Änderungen in `app/routers/import_bank.py`:

- `import_csv`: für jeden **neu** eingefügten `bankumsatz` (nicht für Dubletten) zusätzlich eine Zeile in `bewegung` anlegen: `konto_id=bankkonto_id`, `datum`, `betrag_signed_cent=betrag_cent`, `waehrung='EUR'`, `art='zahlung'`, `bankumsatz_id=<neue Umsatz-ID>`, `quelle='import'`. Anschließend je neuer Bewegung nach möglichen Doppelerfassungen suchen:
  ```sql
  SELECT id, datum FROM bewegung
  WHERE konto_id = ? AND quelle = 'manuell' AND bankumsatz_id IS NULL
    AND betrag_signed_cent = ? AND storniert_am IS NULL
    AND ABS(JULIANDAY(datum) - JULIANDAY(?)) <= 5
  ```
  Treffer werden als `abgleich_vorschlaege: [{bewegung_id, umsatz_id, datum, betrag_cent, buchung_id, buchung_text}]` in der Antwort von `POST /api/import/csv` mitgeliefert (Buchungstext/-ID über `buchung_bewegung` nachschlagen). Kein automatisches Zusammenführen — der Nutzer bestätigt.
- Neuer Endpoint `POST /api/bankumsaetze/{umsatz_id}/abgleichen` `{bewegung_id}`: prüft `pruefe_umsatz` und `pruefe_bewegung` (beide im selben Bereich), dass der Umsatz `importstatus='offen'` hat, die Bewegung `quelle='manuell'`, `bankumsatz_id IS NULL`, `storniert_am IS NULL`, `konto_id` gleich `bankumsatz.bankkonto_id`, `betrag_signed_cent` exakt gleich `bankumsatz.betrag_cent` und das Datum höchstens 5 Tage auseinander — sonst 422 mit Grund. Bei Erfolg wird **dieselbe** Bewegungszeile umgeschrieben (`quelle='import'`, `bankumsatz_id=umsatz_id`, `datum`/`betrag_signed_cent`/`text`/`gegenpartei` aus dem Umsatz übernommen), die neu aus dem Import angelegte Bewegung für diesen Umsatz wieder gelöscht (es entsteht nie eine zweite Bewegung für denselben Umsatz), `bankumsatz.importstatus='verbucht'` gesetzt. Antwort 200 `{umsatz_id, bewegung_id, buchung_id}`.
- `verbuche_umsatz`: nach dem bestehenden Insert von `buchung`/`buchungszeile` zusätzlich `buchung_bewegung(buchung_id, bewegung_id, anteil_signed_cent)` einfügen — `bewegung_id` ist die beim Import für diesen `bankumsatz_id` angelegte Zeile, `anteil_signed_cent` = `betrag` mit Vorzeichen passend zu `typ` (Ausgabe negativ, Einnahme positiv). Die bestehenden Spalten `buchung.bankkonto_id`/`buchung.bankumsatz_id` bleiben unverändert gesetzt (Kompatibilität mit `static-studio`, das nicht angefasst wird).
- `uebernehme_vorschlaege` ruft weiterhin `verbuche_umsatz` auf und profitiert damit automatisch von der neuen Verknüpfung, ohne eigene Änderung.

Neues Modul-JS `static-neu/pages/bankimport.js` (ersetzt den P30-Platzhalter):

- Karte „Konten" (nur Bank/Karte, lesend): `GET /api/konten` clientseitig auf `art in ('bank','karte')` gefiltert, je Zeile Name, Art, Stand, letzter Import, Link „Verwalten → Konten" (`#/konten`, aus P41). Kein eigener Anlege-Dialog hier, um Doppelarbeit mit P41 zu vermeiden.
- Karte „Kontoauszug einspielen": Drop-Zone/Datei-Auswahl → `POST /api/import/csv` (multipart, `bankkonto_id` aus der Konten-Auswahl). Zeigt den Prüfbericht wörtlich wie im Prototyp beschrieben (Kodierung, Trennzeichen, neu/Dubletten, `saldo_hinweis`, ungültige Zeilen). Enthält die Antwort `abgleich_vorschlaege`, erscheint darüber eine eigene Liste „Diese Zahlungen wurden schon erfasst — zusammenführen?" mit je einem Vorschlag: Buchungstext, Datum, Betrag, Knopf „Zusammenführen" (→ `POST /api/bankumsaetze/{id}/abgleichen`) und „Getrennt lassen" (blendet den Vorschlag nur clientseitig aus, der Umsatz bleibt normal `offen`).
- Karte „Umsätze": `GET /api/bankumsaetze?bankkonto_id=` echte Daten, Spalten wie im Prototyp (Datum, Bank-Text, Betrag, Status, Zuordnung, Warum). Status-Badges: `verbucht` mit `regel_id`-Herkunft `'gelernt'` und `auto_verbuchen=1` als „automatisch verbucht"; `offen` mit `vorschlag` als „Vorschlag" (Knöpfe „übernehmen" öffnet ein kleines Formular vorbefüllt mit `vorschlag.sparte_id`/`vorschlag.kategorie_id`, „ändern" öffnet dasselbe Formular leer) → `POST /api/bankumsaetze/{id}/verbuchen`; `offen` ohne `vorschlag` als „offen" (Knöpfe „zuordnen" gleiches Formular leer, „ignorieren" → `PATCH {importstatus:'ignoriert'}`); `verbucht` mit `typ='umbuchung'` als „Umbuchung" (nur „öffnen", read-only Info, keine neue Erkennungslogik). Formular-Absenden zeigt Serverfehler (400/422) als Feldtext, kein stilles Scheitern.

## 4. Nicht-Ziele

Keine Änderung an der Regel-Auswahl-, Lern- oder Konflikt-Logik aus P15. Keine automatische Eigenkonto-/IBAN-Erkennung für Umbuchungen über das hinaus, was `_vorschlag_fuer_umsatz` bereits liefert. Kein Konto-Anlegen-Dialog auf dieser Seite (liegt bei P41). Keine Änderung am CSV-Parser (P01) oder an der Saldo-Prüfung. Keine neue Migration.

## 5. Schritte

1. `import_csv`: Bewegung je neuem Umsatz anlegen, Abgleich-Vorschläge berechnen und zurückgeben.
2. Endpoint `POST /api/bankumsaetze/{id}/abgleichen`.
3. `verbuche_umsatz`: `buchung_bewegung`-Verknüpfung ergänzen.
4. `pages/bankimport.js`: Konten-Übersicht (lesend), Upload mit Prüfbericht und Zusammenführen-Liste, Umsätze-Tabelle mit allen vier Zuständen.
5. Tests, Gesamtlauf, Browserprüfung, Bericht.

## 6. Tests

Testinterpreter `C:\Users\lblet\dev\finanz-dashboard-sparten\.venv\Scripts\python.exe`, `FINANZ_DB` auf eine Wegwerf-Datenbank unter `C:\Users\lblet\AppData\Local\Temp` (nie die echte Datenbank), Tests über `tempfile.TemporaryDirectory()`, schreiben nie in den Arbeitsbaum. Bereichsdependency (`bereich_dep`) bleibt an `/api/import/csv`, `/api/bankumsaetze*` und `/api/bankkonten` — niemals an `/api/auth/*`, `/api/health`, `/api/schema`, `/api/betrieb/status`.

`tests/test_import_bank.py` erweitern:
- CSV-Import mit zwei neuen Umsätzen: je Umsatz genau eine `bewegung` mit `quelle='import'` und passendem `betrag_signed_cent`; zweiter Import derselben Datei (Dublettenschutz) erzeugt keine weitere Bewegung.
- Manuelle Bar-/Bankbuchung anlegen (über `POST /api/buchungen`, `zahlungsart='bank'`, kein `bankumsatz_id`) → vorläufige Bewegung `quelle='manuell'`; danach CSV-Import mit passendem Betrag/Datum → `abgleich_vorschlaege` enthält genau diesen Fall; `POST /api/bankumsaetze/{id}/abgleichen` führt zusammen: genau eine Bewegung bleibt (`quelle='import'`, `bankumsatz_id` gesetzt), `buchung_bewegung` zeigt weiterhin auf dieselbe (jetzt umgeschriebene) Bewegung, Kontostand ändert sich durch das Zusammenführen nicht, `bankumsatz.importstatus='verbucht'`.
- `abgleichen` mit falschem Betrag oder Bewegung aus anderem Bereich → 422 bzw. 404.
- `verbuche_umsatz` (ohne vorherigen Abgleich): Buchung, Buchungszeile und `buchung_bewegung` mit korrektem Vorzeichen; Kontostand des Bankkontos ändert sich um genau den Umsatzbetrag, kein zweites Mal.
- `uebernehme_vorschlaege` bleibt aus Bestandstests grün (Regressionstest ausführen, nicht neu schreiben).
- Bestehende Tests aus P11/P15 bleiben grün.

`node --check static-neu/pages/bankimport.js`.

Browserprüfung (Playwright, falls verfügbar, sonst ausdrücklich vermerken): CSV mit einer bereits manuell erfassten Zahlung hochladen → Zusammenführen-Vorschlag sichtbar, „Zusammenführen" klicken → Umsatz verschwindet aus „offen", Buchungsliste zeigt weiterhin nur eine Buchung; einen offenen Umsatz zuordnen (Formular ausfüllen, speichern) → erscheint als „automatisch verbucht" oder mit korrekter Kategorie; „ignorieren" setzt Status um; Konsole ohne Fehler.

## 7. Fertig heißt

- [ ] Alle Tests grün, vollständige Ausgabe im Bericht.
- [ ] Keine neue Migration nötig — bestätigen, dass `schema.sql` unverändert bleibt.
- [ ] Playwright-Ergebnis im Bericht oder ausdrücklicher Grund, warum nicht möglich.
- [ ] Kein toter Code, keine neue Abhängigkeit, keine Abschwächung von Validierung.
- [ ] Keine Geheimnisse, keine echten Namen im Code.
- [ ] Bericht geschrieben.

## 8. Modell und Aufwand

Modell: `gpt-6-astra`, Aufwand medium.

## 9. Bericht zurück

Geänderte und neue Dateien mit je einem Satz. Vollständige Testausgabe. Was im Browser geprüft wurde oder nicht geprüft werden konnte, mit Grund. Offene Punkte mit Grund. Keine Commits, kein Push.
