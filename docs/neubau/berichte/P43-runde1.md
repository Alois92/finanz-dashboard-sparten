# P43 – Runde 1

Stand: 2026-09-11. Worktree: `C:\Users\lblet\dev\wt-p43`, Branch: `pkt/p43-foto-uebernahme` (von `neubau`).

## Ergebnis

P43 ist umgesetzt. Ein fotografierter Beleg wird lokal per Ollama ausgewertet, der Nutzer prüft und korrigiert
Sparte/Kategorie/Beträge/Datum je Position im Prüf-Dialog und übernimmt mit einem Klick als eine Buchung mit
je einer Buchungszeile pro Position (Split), inklusive verknüpftem Beleg. Der Platzhalter-Knopf „Rechnung
fotografieren“ aus P40 (`pages/erfassen.js`) löst denselben Upload-Fluss aus, ohne die Erfassen-Seite zu
blockieren.

## Geänderte und neue Dateien

- `app/routers/buchungen.py`: Erstell-Logik aus `create_buchung` in eine neue Funktion `erstelle_buchung(con, bereich, *, sparte_id, datum, typ, zahlungsart, bezahlt_von_sparte_id, positionen, client_request_id, text=None, notiz=None, kontakt_id=None, person_id=None, bankkonto_id=None, bankumsatz_id=None)` herausgezogen (Rückgabe `(antwort, buchung_id)`, `buchung_id` ist `None` bei einem `client_request_id`-Treffer). `create_buchung` ruft sie jetzt mit denselben Werten wie zuvor auf; Verhalten unverändert (siehe Regressionslauf unten). Die zusätzlichen optionalen Parameter (`text`, `notiz`, `kontakt_id`, `person_id`, `bankkonto_id`, `bankumsatz_id`) waren nötig, damit `POST /api/buchungen` weiterhin alle seine Felder durchreichen kann – die Karte nennt nur die für die Übernahme nötige Teilmenge.
- `app/routers/beleg_auswertung.py`: neuer Endpunkt `POST /api/beleg-auswertungen/{id}/uebernehmen` am Dateiende. Prüft Auftrag/Sparte, Wiederholung (`client_request_id`) **vor** der Statusprüfung (damit ein wiederholter Aufruf nach dem Statuswechsel auf `verbucht` weiterhin dieselbe Antwort liefert statt fälschlich 409), Auftragsstatus `fertig`, Kategorie-Zugehörigkeit je Position, einheitlicher `typ` über alle Positionen, Datum-Fallback (Body → `ergebnis.datum` → heute). Ruft `erstelle_buchung` auf, verknüpft danach `buchung_beleg`, ruft `belege.py::_aktualisiere_belegstatus` auf und setzt `beleg_auswertung.status='verbucht'`. `request_wiederholung.art` lässt laut Schema nur `'buchung'`/`'ausgleich'` zu (keine Migration erlaubt) – die Wiederholungsprüfung der Übernahme nutzt deshalb denselben `'buchung'`-Topf wie `POST /api/buchungen`; da `client_request_id` ein pro Aktion vom Client erzeugter UUID ist, ist eine Kollision mit einer echten Buchungserfassung praktisch ausgeschlossen (im Bericht als bewusste Entscheidung benannt, siehe „Offene Punkte“).
- `static-neu/pages/belege.js`: ersetzt den P30-Platzhalter vollständig. Drei Karten: „Rechnung fotografieren“ (Datei-Input mit `capture="environment"`, Erreichbarkeitsprüfung über `GET /api/auswertung/status`, sonst Hinweis „Foto-Auswertung gerade nicht erreichbar“; Polling auf `GET /api/beleg-auswertungen?status=laeuft` alle 4 s, Obergrenze 3 min, danach Hinweis „dauert ungewöhnlich lange“), „Belege zur Prüfung“ (Kacheln aus `GET /api/beleg-auswertungen?status=fertig`, Klick öffnet Prüf-Dialog mit Sparte-Pflichtfeld, Positionen editierbar, client-seitiger Kategorie-Vorbefüllung analog `_match_name`, „Bezahlt von“, „Übernehmen“/„Verwerfen“), „Belege“ (Kacheln aus `GET /api/belege`, Klick öffnet `GET /api/belege/{id}/datei` in neuem Tab). Exportiert zusätzlich `pruefeErreichbarkeit`, `ladeBelegUndAuswerten`, `erreichbarkeitsHinweis` zur Wiederverwendung durch `erfassen.js`.
- `static-neu/pages/belege.css`: neues, page-eigenes Stylesheet (Kacheln, Prüf-Dialog-Positionszeilen), lädt sich selbst nach.
- `static-neu/pages/erfassen.js`: nur der Knopf „Rechnung fotografieren“ mit Verhalten gefüllt (Import aus `belege.js`, Erreichbarkeitsprüfung vor dem Öffnen des Datei-Dialogs, Upload+Auswertung ohne Seitenwechsel, Toast statt Blockierung). Sonst unverändert.
- `tests/test_p43_foto.py`: neue, eigene Testdatei (gemäß Nachtrag-Konfliktregel 3 – keine bestehende Testdatei verändert) mit sechs Tests, siehe unten.

## Router-Antworten (wörtlich, mit dem Testclient aufgezeichnet)

`POST /api/beleg-auswertungen/{id}/uebernehmen` mit zwei Positionen, Auftrag zuvor per SQL auf
`status='fertig'` gesetzt (Ollama nicht aufgerufen):

```json
{"buchung_id": 1, "version": 1}
```

(Status 201; bei `client_request_id`-Wiederholung mit identischen Daten identischer Body, Status 200.)

`GET /api/buchungen?sparte_id=<id>` danach (Auszug, echte Browserprüfung, Werte aus dem realen Ollama-Lauf):

```json
{
  "id": 1, "sparte_id": 5, "sparte_name": "Alois privat", "datum": "2026-09-10",
  "typ": "ausgabe", "version": 1, "betrag_cent": 450, "zahlungsart": "bar",
  "belegstatus": "beleg_vorhanden", "buchungsstatus": "offen",
  "zeilen": [
    {"id": 1, "kategorie_id": 1, "kategorie_name": "Lebensmittel", "betrag_cent": 300, "notiz": "Brot", "neutral": 0},
    {"id": 2, "kategorie_id": 1, "kategorie_name": "Lebensmittel", "betrag_cent": 150, "notiz": "Milch", "neutral": 0}
  ],
  "belege": [{"id": 1, "dateiname": "testrechnung.jpg"}],
  "zahlungsstatus": "verknuepft", "bezahlt_von_sparte_id": null
}
```

## Tests (`tests/test_p43_foto.py`)

Ollama wurde in den Tests nie echt aufgerufen: Aufträge werden direkt mit `status='fertig'` und festem
`ergebnis_json` in die Wegwerf-DB geschrieben (`app/auswertung.py` unangetastet). `FINANZ_DB` je Test auf
Wegwerf-DB unter `%TEMP%`.

- `test_belege_und_erfassen_js_haben_gueltige_syntax` — `node --check` für beide Dateien.
- `test_uebernehmen_zwei_positionen_erzeugt_split_buchung` — zwei Positionen → eine Buchung mit zwei
  Buchungszeilen, Summe = Summe der `betrag_cent`, Beleg über `buchung_beleg` verknüpft,
  `beleg_auswertung.status='verbucht'`.
- `test_uebernehmen_ohne_status_fertig_liefert_409` — Auftrag mit `status='laeuft'` → 409.
- `test_uebernehmen_sparte_aus_anderem_bereich_liefert_404` — `sparte_id` aus Bereich 2 (Verein) bei
  Standard-`bereich_id=1` → 404.
- `test_client_request_id_dedupe` — gleiche Daten zweimal → zweite Antwort 200 mit derselben `buchung_id`;
  andere Positionen mit derselben `client_request_id` → 409.
- `test_bezahlt_von_sparte_id_erzeugt_auslage` — `bezahlt_von_sparte_id` gesetzt → `auslage`-Zeile mit
  korrektem `zahler_sparte_id`/`betrag_cent`, genau wie bei `POST /api/buchungen`.

Isolierter Lauf: `discover -s tests -p test_p43_foto.py` → **6/6 grün**.

Regressionslauf (Gesamtsuite, `FINANZ_DB` auf Wegwerfdatei, ohne `FINANZ_TEST_AUTH_BYPASS`):

```
set FINANZ_DB=%TEMP%\p43-test.db
C:\Users\lblet\dev\finanz-dashboard-sparten\.venv\Scripts\python.exe -m unittest discover -s tests
```

```
----------------------------------------------------------------------
Ran 376 tests in 912.929s

OK (skipped=1)
```

Die im Rohprotokoll sichtbaren Tracebacks (simulierte Backup-Abbrüche, nicht erreichbares Zweitziel,
Bild-Verkleinerung an Test-Fixtures ohne echtes Bildformat, fehlende Auth-Datei für Recovery-Code) stammen aus
absichtlich simulierten Fehlerpfaden anderer, unveränderter Test-Suiten und enden jeweils mit `ok`; kein
Zusammenhang mit P43. `node --check` für `belege.js` und `erfassen.js` einzeln ebenfalls ohne Ausgabe
(Erfolg).

## Browserprüfung

App gestartet mit `FINANZ_DB=%TEMP%\p43-app.db`, `FINANZ_INSTANZ=test`, `FINANZ_AUTH_FILE=%TEMP%\p43-auth.json`,
`FINANZ_TEST_AUTH_BYPASS=1` (laut `app/auth.py::_test_bypass_enabled` nur wirksam, weil die DB unter `%TEMP%`
liegt), `python -m uvicorn app.main:app --port 8035`. Playwright-Tools verwendet.

Ollama lief lokal (`GET /api/tags` erreichbar), aber mit dem Modell `qwen3.5:4b` statt dem Standard-Vorgabewert
`qwen2.5vl:7b` aus `app/auswertung.py` — für die Browserprüfung wurde die App deshalb mit
`FINANZ_OLLAMA_MODEL=qwen3.5:4b` gestartet, damit `GET /api/auswertung/status` `modell_vorhanden=true` liefert
und ein **echter** Beleg-Upload mit echter lokaler Auswertung möglich war (kein SQL-Nachhelfen nötig). Das ist
eine reine Laufzeit-Umgebungsvariable für diese Prüfsitzung, keine Code-Änderung; `app/auswertung.py` ist
unverändert.

Geprüft unter `http://127.0.0.1:8035/neu/` (Desktop und Mobil 375×812):

- **Erfassen-Seite**: Sparte „Alois privat“ gewählt, „Beleg fotografieren“ geklickt → Erreichbarkeitsprüfung
  greift (Datei-Dialog öffnet sich, da `modell_vorhanden=true`), Testfoto (`outputs/testrechnung.jpg`,
  synthetisch erzeugter Kassenbon „Testmarkt Kirchbichl / Brot 3,00 / Milch 1,50 / Summe 4,50 EUR / Datum
  2026-09-10“) hochgeladen. Toast „Beleg wird lokal ausgewertet, das dauert ein paar Minuten. Ergebnis
  erscheint unter „Belege"." erscheint, die Seite bleibt bedienbar (kein Blockieren, „die App darf zu sein“).
- **Echte Ollama-Auswertung**: Hintergrundschleife hat den Auftrag nach rund 60 s ausgewertet
  (`status: 'laeuft'` → `'fertig'`). Das Vision-Modell hat Händler, Datum und beide Positionen korrekt aus dem
  Testfoto gelesen: `{"haendler":"Testmarkt Kirchbichl","datum":"2026-09-10","positionen":[{"text":"Brot","betrag_cent":300,...},{"text":"Milch","betrag_cent":150,...}],"gesamt_cent":450}`. Beide `kategorie_id` blieben serverseitig `null`
  (kein Namenstreffer „Brot“/„Milch“ gegen die einzige angelegte Kategorie „Lebensmittel“ und keine Merkregel) —
  erwartetes Verhalten von `_kategorie_fuer_position`.
- **Belege-Seite**: Kachel „Testmarkt Kirchbichl · 10.9.2026 · € 4,50“ unter „Belege zur Prüfung“, Kachel
  „testrechnung.jpg – · Alois privat“ unter „Belege“ (Datei-Download über `GET /api/belege/{id}/datei` mit
  `200 image/jpeg` bestätigt, zusätzlich direkt per HTTP geprüft).
- **Prüf-Dialog**: Sparte „Alois privat“ gewählt → `GET /api/kategorien?sparte_id=5` lädt „Lebensmittel“,
  „Auslage für andere Sparte“-Checkbox erscheint (weitere private Sparte „Theresia privat“ vorhanden), Text/
  Betrag je Position vorausgefüllt und editierbar, keine automatische Kategorie-Vorauswahl (erwartet, siehe
  oben). Beide Positionen auf „Lebensmittel“ gesetzt, „Übernehmen“ geklickt → Toast „Buchung angelegt.“,
  Dialog schließt, Kachel verschwindet aus „Belege zur Prüfung“.
- **Ergebnis-Verifikation über die API**: `GET /api/buchungen?sparte_id=5` zeigt die neue Buchung mit zwei
  Zeilen (300 + 150 = 450 Cent), `belegstatus: "beleg_vorhanden"`, verknüpftem Beleg, `zahlungsstatus:
  "verknuepft"` (siehe wörtliches JSON oben).
- **Mobil (375×812)**: Belege-Seite mit Bottom-Navigation, Karten gestapelt, Kacheln lesbar, keine
  horizontale Verschiebung.
- **Browser-Konsole**: keine Fehler außer dem erwarteten `404` auf `favicon.ico` (unabhängig von P43).

Server danach beendet (`Stop-Process`).

## Nicht-Ziele eingehalten

Keine Änderung an `app/auswertung.py`, `app/routers/belege.py` (nur Import/Aufruf von
`_aktualisiere_belegstatus`, keine Änderung der Datei selbst), `app.js`, `ui.js`, `api.js`. Keine Cloud-KI,
keine neue Abhängigkeit, keine Migration.

## Offene Punkte

- Die Wiederholungsprüfung (`client_request_id`) der Übernahme nutzt mangels erlaubtem `art`-Wert in
  `request_wiederholung` (Schema lässt nur `'buchung'`/`'ausgleich'` zu, keine Migration erlaubt) denselben
  `'buchung'`-Topf wie `POST /api/buchungen`. Da `client_request_id` clientseitig pro Aktion als UUID erzeugt
  wird, ist eine Kollision zwischen einer normalen Buchungserfassung und einer Foto-Übernahme praktisch
  ausgeschlossen — aber theoretisch nicht durch das Schema ausgeschlossen. Sollte bei einer künftigen
  Migration ein eigener `art`-Wert (z. B. `'beleg_uebernehmen'`) ergänzt werden, kann die Umstellung ohne
  Verhaltensänderung nachgezogen werden.
- Die „nicht erreichbar“-Anzeige (`GET /api/auswertung/status` liefert `erreichbar=false` oder
  `modell_vorhanden=false`) wurde nur über die zurückgegebenen Statuswerte und Code-Pfad geprüft, nicht
  eigens im Browser mit einem gestoppten Ollama-Server nachgestellt (die laufende Instanz stand für den
  echten Auswertungstest zur Verfügung und sollte dafür nicht gestoppt werden).
- Ein zweites, größeres Testfoto (z. B. mit mehr als zwei Positionen oder Netto/Brutto-Angleichung/`hinweis`)
  wurde in der Browserprüfung nicht zusätzlich getestet; die entsprechende Logik (`_brutto_abgleich`) ist
  unverändert und über bestehende Tests in `tests/test_beleg_auswertung.py` abgedeckt, die `hinweis`-Anzeige
  im Prüf-Dialog selbst ist unit-getestet nur indirekt (Markup-Zeile vorhanden), nicht per Browser-Klick
  verifiziert.

Keine Migrationen, keine Backend-Änderungen außerhalb der Karte, keine Commits außerhalb dieses Auftrags.
