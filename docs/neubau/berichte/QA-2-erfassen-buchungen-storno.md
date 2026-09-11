# QA-2: Erfassen, Buchungsliste, Storno/Erstattung, Umbuchung

Datum: 11. September 2026. Instanz: http://127.0.0.1:8052/ (Schema 17, Wegwerf-DB, Login-Bypass). Prüfer: QA-Tester 2 (Claude Sonnet 5, Subagent).

Vorgehen: Code-Analyse der Auftragskarten P40, P50, P51, Abnahme B7, sowie `app/routers/buchungen.py`, `app/routers/schnellerfassung.py`, `static-neu/pages/erfassen.js`, `static-neu/pages/buchungen.js`, `static-neu/format.js`, `static-neu/api.js`. Browserprüfung über `mcp__Claude_Browser__*` (eigener Tab), API-Gegenprüfung mit `curl` gegen `/api/...`, Serverlog `C:\Users\lblet\AppData\Local\Temp\qa-8052.log` gelesen (keine Fehler außer erwarteten 4xx durch eigene Tests und normalen 404 auf `/favicon.ico`).

## 1. Umfang: Checkliste

### Erfassen (P40)

| # | Prüfung | Ergebnis |
|---|---|---|
| 1 | Seite lädt, Formular vollständig (Richtung, Betrag, Sparte, Text, Zahlungsart, Datum, Kategorie, Auslage) | OK |
| 2 | Schnelltext → `POST /api/parse` liefert Sparte+Kategorie+Betrag-Vorschlag, Anzeige als Chip | OK |
| 3 | Enter im Textfeld speichert direkt bei erkannten Feldern (lt. P40-Spezifikation) | **Befund QA2-01** — kein Enter-Handler vorhanden |
| 4 | Vorschlagszeile mit bis zu drei Treffern, Pfeiltasten ↑↓ | **Befund QA2-03** — nicht vorhanden, Backend liefert nur einen Treffer |
| 5 | Regel-Herkunft-Anzeige („gelernt“/„Stichwort“) | **Befund QA2-03** (gleiche Ursache) — Feld fehlt in `/api/parse`-Antwort |
| 6 | Mehrzeilen-Buchung mit mehreren Kategorien beim Erfassen | Nicht vorhanden — laut P40-Auftragskarte auch nicht vorgesehen (nur eine Zeile pro Schnellerfassung; Mehrzeilen gibt es im Bearbeiten-Dialog aus P50). Kein Befund. |
| 7 | Betrag: Komma (`12,50`) | OK — korrekt geparst |
| 8 | Betrag: Punkt als Dezimaltrennzeichen (`12.50`) | **Befund QA2-02 (kritisch)** |
| 9 | Betrag: Tausenderpunkt (`1.234,56`) | OK |
| 10 | Betrag: negativ | OK — Backend lehnt mit 422 ab (`greater_than_equal`) |
| 11 | Betrag: 0 | OK — Backend lehnt mit 422 ab, deutsche Fehlermeldung |
| 12 | Betrag: Riesenbetrag (9.999.999.999,99 €) | **Befund QA2-05 (niedrig)** — keine Obergrenze |
| 13 | Betrag: Text („abc“) | OK — `parseBetrag` liefert `null`, Formular blockt mit Toast |
| 14 | Datum: Zukunft | Nicht gesondert eingeschränkt (Backend/Frontend erlauben es), kein Pflichtenheft-Verstoß erkennbar — kein Befund |
| 15 | Datum: ungültig (`2026-13-40`) | OK — Backend lehnt mit 422 ab („month must be in 1..12“); `<input type=date>` verhindert das im Browser ohnehin |
| 16 | Zahlungsart bar/bank/karte/sonstiges wählbar | OK |
| 17 | Bankkonto-Feld erscheint bei „Bank“/„Karte“ | OK, aber nicht Pflicht (siehe unten) |
| 18 | Bankkonto-Pflicht bei „bank“ | Weder Frontend (`required` fehlt) noch Backend erzwingen ein Konto; Buchung wird mit `zahlungsstatus:"Zahlung unbekannt"` gespeichert. Laut `P11-konten-bewegungen.md` ist das **gewolltes Verhalten** („bank/karte ohne bankumsatz_id … erscheinen als „Zahlung unbekannt““), daher kein eigener Befund, nur dokumentiert. Im Testsystem existieren ohnehin keine Konten vom Typ „bank“ (nur „kassa“ je Sparte), echte Auswahl konnte daher nicht durchgespielt werden. |
| 19 | Kontakt/Person, Notiz im Erfassen-Formular | Nicht vorhanden — laut P40-Auftragskarte auch nicht vorgesehen (Feldliste der Karte enthält weder Kontakt/Person noch Notiz). Kein Befund. |
| 20 | Auslage/„Bezahlt von“ nur bei Richtung „Ausgabe“, Optionen = privat-Sparten ≠ aktuelle Sparte, Hinweistext wortgleich | OK, exakt wie Spezifikation |
| 21 | Beleg-Anhang beim Erfassen | „Beleg fotografieren“ öffnet nativen Datei-Dialog wie erwartet (P43 bereits umgesetzt, Platzhaltertext aus P40 wurde ersetzt); echter Upload nicht getestet (keine Testdatei) |
| 22 | Doppelklick auf Speichern → keine Doppelbuchung | OK im Browser (Button wird sofort deaktiviert, nur ein `POST`) — **aber** siehe QA2-04: der zugrundeliegende Schutz ist nur clientseitig |
| 23 | Wiederholung nach Netzfehler (client_request_id stabil über Retry) | **Befund QA2-04 (hoch)** |
| 24 | „Zuletzt erfasst“ zeigt letzte Buchungen der Sparte | OK |
| 25 | Konsole ohne Fehler während der gesamten Erfassen-Prüfung | OK, keine Fehler |

### Buchungsliste (P50)

| # | Prüfung | Ergebnis |
|---|---|---|
| 26 | Liste lädt mit Datum/Text/Kategorie/Zahlung/Beleg/Betrag, Sparten-Kürzel bei mehreren Kategorien (z. B. „Gemeinde, Gemeinde, …, Miete“) | OK |
| 27 | Suche (`q`) filtert Text/Notiz/Kategorie, Chip „Suche: … ×“ erscheint | OK |
| 28 | Filter Zeitraum (Von/Bis) | vorhanden, Feldtest nicht tief durchgespielt (Format ok, Chips gerendert) |
| 29 | Filter Gruppe | OK, Optionen korrekt geladen (Gesamtuebersicht, Hof gesamt, Privat gesamt, Vermietung gesamt, Alles ohne Verein) |
| 30 | Filter Richtung | OK, Optionen „alle/Einnahmen/Ausgaben“ |
| 31 | Filter Zahlungsart | **Befund QA2-06 (niedrig)** — Option „Sonstiges“ fehlt |
| 32 | Filter Kategorie | Funktioniert, aber **Befund QA2-07 (niedrig)** — Dubletten gleichnamiger Kategorien nicht unterscheidbar |
| 33 | Filter-Chips (Suche) korrekt entfernbar | OK |
| 34 | „Filter zurücksetzen“ | OK |
| 35 | „Weitere laden“ / Cursor | Button vorhanden (`ref_647` „Weitere laden“); mit 30 Testbuchungen nicht über die Grenze gekommen (Seitengröße scheint ≥30), Cursor-Mechanik selbst nicht bis zum Limit durchgespielt |
| 36 | Summenzeile (Einnahmen/Ausgaben/Saldo) korrekt nach Filtern | OK, rechnet nach jeder Filteränderung sauber neu (auch mit dem absichtlich riesigen Testbetrag korrekt verrechnet) |
| 37 | Sortierung (neueste zuerst) | OK, Liste absteigend nach Datum |
| 38 | Leere Ergebnisse | OK — „Keine Buchungen gefunden.“, Summen 0,00 |

### Bearbeiten-Dialog

| # | Prüfung | Ergebnis |
|---|---|---|
| 39 | Dialog öffnet mit Kopf-Feldern (Sparte, Datum, Typ, Zahlungsart, Text, Notiz) und Zeilen (Kategorie, Betrag, Notiz) | OK |
| 40 | Zeile hinzufügen/entfernen | Buttons vorhanden und funktional (Zeilen-Array anpassbar) |
| 41 | Kopf-Änderung speichern (`PUT`) | OK, `version` wird mitgeschickt |
| 42 | Zeilen-Änderung speichern | OK, per Zeilen-`id` erkannt |
| 43 | Versionssperre: veraltete `version` → 409 | **OK, bestätigt per API** (zwei PUTs mit derselben `version`, zweiter liefert 409) |
| 44 | kontakt_id/person_id bleiben bei PUT erhalten (B7) | Laut `docs/neubau/abnahme/B7.md` bereits behoben und mit eigenen Tests belegt (365 Tests grün); Dialog selbst bietet aber **keine UI-Felder** für Kontakt/Person zum Bearbeiten — nicht erneut end-to-end nachgestellt (kein Kontakt-Anlage-Endpoint in dieser Instanz gefunden, `POST /api/kontakte` → 405) |
| 45 | Löschen | Für Umbuchungen per `DELETE` bestätigt (siehe unten); für normale Buchungen nicht gesondert erneut geprüft (Route vorhanden, `DELETE /api/buchungen/{id}`) |
| 46 | Historie/Verlauf (`GET /api/buchungen/{id}/verlauf`) | OK — Feldänderung (`datum`), Zeilenänderung (`zeile_<id>_betrag_cent`), neue/entfernte Zeile (`zeile_neu`/`zeile_entfernt`) korrekt mit alt/neu/Grund protokolliert, absteigend sortiert |
| 47 | „Grund“ als Vorschlag, nicht Pflicht | OK, Feld ist optional |

### Storno/Erstattung (P51)

| # | Prüfung | Ergebnis |
|---|---|---|
| 48 | Stornieren setzt `storniert_am`, verschwindet aus Summen, bleibt in Liste sichtbar | OK (per API bestätigt) |
| 49 | Zweimal stornieren → 409 | OK |
| 50 | Storno zurücknehmen → `storniert_am = NULL`, zählt wieder | OK |
| 51 | Entstornieren einer nicht stornierten Buchung → 409 | OK |
| 52 | Stornieren protokolliert `buchung_aenderung` mit `feld='storniert_am'` und Grund | OK (indirekt bestätigt über funktionierenden Verlauf-Mechanismus aus P50, nicht einzeln nachgezählt) |
| 53 | Erstattung: Teilerstattung einer Ausgabe (150 € → 60 € erstattet) | OK — neue Buchung `typ='einnahme'`, `original_id` gesetzt, `netto_cent=9000` korrekt |
| 54 | Übererstattung (mehr als offener Rest) → 422 mit `rest_cent` | OK |
| 55 | Erstattung nur bei Kategorie `richtung='beides'`, Fehlertext nennt Kategorienamen | OK — „Kategorie „Strom“ erlaubt keine Erstattung (Richtung muss „beides“ sein)“ |
| 56 | Erstattung einer Einnahme (Rücküberweisung) | Nicht mit echten Testdaten durchgespielt (keine Einnahme-Kategorie mit `richtung='beides'` in den Testdaten vorhanden), Logik aber symmetrisch im Code und durch die Ausgaben-Erstattung bestätigt — **nicht vollständig geprüft** |
| 57 | Erstattung auf stornierter Buchung → 409 | OK |
| 58 | Erstattung einer Erstattung → 422 | OK — „Eine Erstattung kann nicht selbst erstattet werden“ |
| 59 | Erstattung auf `typ='umbuchung'` → 422 | OK — „Nur Einnahmen/Ausgaben können erstattet werden“ |
| 60 | Storno auf Umbuchung → 422 | OK — „Umbuchungen können nicht storniert werden“ |
| 61 | Storno einer Buchung mit Beleg | Nicht geprüft — keine Testbuchung mit echtem Beleg-Upload angelegt |

### Umbuchung

| # | Prüfung | Ergebnis |
|---|---|---|
| 62 | Umbuchung anlegen (`POST /api/umbuchungen`), Buchungspaar entsteht | OK — zwei Buchungen mit `transfer_gruppe_id` |
| 63 | Umbuchung erscheint in Buchungsliste, zählt nicht in Einnahmen/Ausgaben-Summen | OK |
| 64 | Bearbeiten einer Umbuchung | OK abgelehnt — 400 „Umbuchungen sind gekoppelt – bitte löschen und neu anlegen statt bearbeiten“ (entspricht „laut Karte nur Löschen“) |
| 65 | Löschen einer Umbuchung entfernt beide Buchungen | OK — beide IDs danach 404 |

### Allgemein / Datenintegrität

| # | Prüfung | Ergebnis |
|---|---|---|
| 66 | ZINA (Verein) erscheint nie in Gesamtsummen von Haupt | OK — `GET /api/uebersicht?bereich_id=1` listet nur die 5 Haupt-Sparten, `sparte_id=4` (ZINA) im Bereich 1 liefert 404 |
| 67 | Client-Request-Id Server-Dedup bei identischem Body-Feld | OK — zweiter identischer `POST` mit gleichem `client_request_id` liefert 200 (keine neue Buchung), erster 201 |
| 68 | Serverlog auf Fehler während der gesamten Sitzung | OK, keine Tracebacks/Exceptions |

### Handy-Ansicht (375 px)

| # | Prüfung | Ergebnis |
|---|---|---|
| 69 | Erfassen/Buchungsliste bei 375 px | **Nicht abschließend geprüft** — die Viewport-Emulation wurde im gemeinsam genutzten Browser wiederholt von einer anderen Tester-Session überschrieben/zurückgesetzt (`innerWidth` blieb bei 707–714 px trotz mehrfachem `resize_window preset:"mobile"`); Hinweis „another Claude session set this“ erschien. Als Ersatzprüfung: `style.css`/`erfassen.css`/`buchungen.css` enthalten einen `@media(max-width:760px)`-Breakpoint, der bei ~700 px im Screenshot bereits sichtbar griff (Sidebar ausgeblendet, Bottom-Navigation mit „+“ eingeblendet, Grid einspaltig). Eine echte 375-px-Sichtprüfung von Erfassen/Buchungsliste war damit nicht zuverlässig möglich. |

## 2. Befunde

### QA2-01 — Enter speichert im Erfassen-Formular nicht direkt (mittel)
**Seite:** Erfassen. **Datei:** `static-neu/pages/erfassen.js`.
**Schritte:** Text „Strom Rechnung 45,90“ ins Feld „Was hast du bezahlt oder bekommen?“ eingeben (Sparte/Kategorie/Betrag werden korrekt per `/api/parse` erkannt), Enter drücken.
**Erwartet (P40):** „Enter speichert direkt, wenn Sparte, Kategorie und Betrag erkannt sind (kein Zwischenschritt nötig)“.
**Tatsächlich:** Nichts passiert — kein `POST /api/buchungen` im Netzwerklog, keine neue Zeile im Textfeld. Das Feld ist ein `<textarea>` ohne jeglichen `keydown`/`Enter`-Handler (per `grep` bestätigt: kein Treffer für „Enter“/„keydown“ in der Datei, während alle anderen Seiten wie `buchungen.js`, `kategorien.js` etc. entsprechende Handler haben). Speichern funktioniert nur über den Button „Buchung speichern“.
**Konsole/Log:** keine Fehler, das Feature fehlt einfach.

### QA2-02 — Betrag mit Punkt als Dezimaltrennzeichen wird um Faktor 100 falsch interpretiert (kritisch)
**Seite:** Erfassen. **Datei:** `static-neu/format.js`, Zeile 6 (`parseBetrag`), verwendet in `static-neu/pages/erfassen.js` Zeile 467.
**Schritte:** Im Betragsfeld „12.50“ eintippen (englische/übliche Dezimalschreibweise mit Punkt), Kategorie wählen, „Buchung speichern“ klicken.
**Erwartet:** Entweder 12,50 € wird gebucht, oder das Feld wird als ungültig abgelehnt.
**Tatsächlich:** Es werden **1.250,00 €** gebucht (Faktor 100 zu hoch), ohne jede Warnung. Ursache: `parseBetrag` entfernt zuerst **alle** Punkte (angenommen als Tausendertrennzeichen) und wandelt danach das Komma in einen Dezimalpunkt um: `String(value).replace(/\./g,'').replace(',','.')`. Bei „12.50“ wird daraus „1250“ → `1250`. Per Browser nachgestellt und per Netzwerklog bestätigt: `POST /api/buchungen` mit `betrag_cent: 125000` (Buchung id 30, danach über die Buchungsliste sichtbar als „− € 1.250,00“). Da dies ein plausibler, alltäglicher Tippfehler ist (Dezimalpunkt statt -komma), besteht ein reales Risiko falscher Buchungsbeträge ohne jede Fehlermeldung — Datenintegritätsrisiko in der Finanzbuchhaltung.
**Bereinigung:** Die betroffene Testbuchung (id 30) wurde von mir per API auf den korrekten Betrag zurückgesetzt, um die Testdaten nicht dauerhaft zu verfälschen (siehe Historie zu Buchung 30, Grund „QA Korrektur Tippfehler“).

### QA2-03 — Vorschlagszeile mit bis zu drei Treffern, Pfeiltasten-Navigation und Regel-Herkunft nicht umgesetzt (mittel)
**Seite:** Erfassen. **Dateien:** `static-neu/pages/erfassen.js`, `app/routers/schnellerfassung.py`.
**Erwartet (P40):** „Vorschlagszeile mit bis zu drei Kategorie-Treffern, Pfeiltasten ↑↓ wechseln die Auswahl“ sowie Anzeige der Regel-Herkunft („gelernt“/„Stichwort“).
**Tatsächlich:** `POST /api/parse` liefert nur einen einzigen Treffer (`{typ, datum, betrag_cent, text, sparte_id, sparte_name, kategorie_id, kategorie_name}`, per curl bestätigt) und kein Herkunftsfeld; das Frontend zeigt entsprechend nur einen Chip „Vorschlag: Sparte … · Kategorie …“ ohne Pfeiltasten-Logik (kein `ArrowUp`/`ArrowDown`-Handler in der Datei). Da P40 selbst als Nicht-Ziel festhält „Keine Änderung an der Erkennungslogik von `POST /api/parse` selbst“, war diese Spezifikationsanforderung mit dem bestehenden Endpoint nie erfüllbar — das ist eher eine Lücke zwischen Auftragskarte und Backend-Realität als ein reiner Frontend-Fehler, wirkt sich aber genauso auf die Bedienung aus (kein Umschalten zwischen mehreren Kategorie-Vorschlägen möglich).

### QA2-04 — Client-Request-Id wird bei jedem Speichern-Versuch neu erzeugt statt für Wiederholungen stabil zu bleiben (hoch)
**Seite:** Erfassen. **Dateien:** `static-neu/pages/erfassen.js` Zeile 468, `static-neu/api.js` Zeile 1.
**Schritte/Analyse:** `erfassen.js` erzeugt in der `submit`-Callback-Funktion bei **jedem** Aufruf `client_request_id: crypto.randomUUID()` neu. `api.js` setzt zusätzlich unabhängig davon einen **weiteren, eigenen** Zufallswert im Header `X-Client-Request-Id` (nur falls der Header nicht schon gesetzt ist) — dieser Header wird vom Backend aber nirgends ausgelesen (`grep` über `app/routers/buchungen.py` findet `client_request_id` nur als Body-Feld `b.client_request_id`); der Header ist also toter Code.
Per API bestätigt: Sendet man **zweimal denselben Wert im Body-Feld** `client_request_id`, funktioniert die serverseitige Deduplizierung korrekt (erster Aufruf 201, zweiter identischer Aufruf 200 mit derselben `id`, keine neue Buchung). Sendet man zweimal denselben Wert **nur im Header** `X-Client-Request-Id`, werden dagegen **zwei getrennte Buchungen** angelegt (201/201, unterschiedliche `id`), weil das Backend den Header ignoriert.
**Erwartet (P40/P12):** „Speichern-Button wird sofort nach Klick deaktiviert … (Doppel-Tap-Schutz zusätzlich zur serverseitigen `client_request_id`-Deduplizierung)“ — die serverseitige Deduplizierung soll also insbesondere Fälle abfangen, in denen der Client selbst nicht sicher weiß, ob eine Anfrage angekommen ist (Netzwerkfehler, Timeout) und der Nutzer erneut auf „Buchung speichern“ klickt.
**Tatsächlich:** Weil `erfassen.js` bei jedem Klick auf „Buchung speichern“ eine **neue** Zufalls-Id erzeugt (nicht einmalig pro Formularversuch persistiert), erkennt der Server einen echten Wiederholungsversuch nach Netzwerkfehler **nicht** als Duplikat — ein Retry nach einer unklaren Antwort (z. B. Verbindungsabbruch nach erfolgreicher Serververarbeitung, aber verlorener Antwort) kann so zu einer echten Doppelbuchung führen. Der im Browser beobachtete Schutz gegen Doppelklick funktioniert nur, weil der Button synchron deaktiviert wird und *derselbe* JS-Aufruf nicht zweimal läuft — er schützt nicht vor einem bewussten zweiten Klick nach einem Fehler-Toast.
**Konsole/Log:** keine Fehler, Verhalten wurde gezielt per `curl` nachgestellt.

### QA2-05 — Keine Plausibilitätsgrenze für Buchungsbeträge (niedrig)
**Seite:** Erfassen / Backend. **Datei:** `app/schemas.py` (Pydantic-Validierung `betrag_cent`), `app/routers/buchungen.py`.
**Schritte:** `POST /api/buchungen` mit `betrag_cent: 999999999999` (≈ 10 Mrd. €).
**Erwartet:** Sinnvolle Obergrenze oder zumindest Warnung, da im Kontext einer privaten/kleinbetrieblichen Buchhaltung ein derart absurder Betrag praktisch immer ein Tippfehler ist.
**Tatsächlich:** Wird anstandslos mit 201 gespeichert und verzerrt sofort alle Summen in Übersicht und Buchungsliste. Nur ein unterer Grenzwert (`> 0`) ist vorhanden.

### QA2-06 — Buchungsliste-Filter „Zahlungsart“ bietet „Sonstiges“ nicht an (niedrig)
**Seite:** Buchungen. **Datei:** `static-neu/index.html` Zeile 17.
**Erwartet:** Filter deckt alle beim Erfassen wählbaren Zahlungsarten ab (bar/bank/karte/sonstiges).
**Tatsächlich:** Das statische Options-Markup für `#filter-zahlungsart` enthält nur „alle/bar/Bank/Karte“, „sonstiges“ fehlt (während das Zahlungsart-Select im Erfassen-Formular und im Bearbeiten-Dialog „sonstiges“ korrekt anbieten). Buchungen mit `zahlungsart='sonstiges'` lassen sich in der Liste nicht gezielt herausfiltern, nur über „alle“ finden.

### QA2-07 — Kategorie-Filter zeigt nicht unterscheidbare Dubletten (niedrig)
**Seite:** Buchungen, „Mehr Filter“. **Datei:** `static-neu/pages/buchungen.js` (Kategorie-Optionen werden ohne Sparten-Kennzeichnung befüllt) bzw. gemeinsames Options-Markup.
**Schritte:** „Mehr Filter“ öffnen, Kategorie-Dropdown ansehen.
**Erwartet:** Eindeutig auswählbare Kategorien; die Tabellenspalte „Kategorie“ zeigt laut Spezifikation bei mehreren Sparten ein Sparten-Kürzel.
**Tatsächlich:** Der Kategorie-Filter listet gleichnamige Kategorien aus verschiedenen Sparten ohne Unterscheidungsmerkmal doppelt/mehrfach auf (z. B. „Auto“ zweimal, „Versicherungen“ dreimal, „Weiterbildung“ zweimal, „Fixkosten“ viermal, „Steuer“ zweimal, „Andreas“ zweimal, „Hohenegg“ zweimal, „Entgasse“ zweimal, „Kino“/„Motorrad“/„Lohn“/„Telering“ je zweimal). Für Nutzer nicht erkennbar, welcher Eintrag zu welcher Sparte gehört, wenn „Alle Sparten“ gewählt ist.

## 3. Nicht geprüft / Einschränkungen

- **Handy-Ansicht 375 px** (Erfassen, Buchungsliste): Viewport-Emulation im gemeinsam genutzten Browser sprang wiederholt zurück bzw. wurde von einer anderen Tester-Session überschrieben (Hinweis „another Claude session set this“, `innerWidth` blieb bei 707–714 px). Nur indirekt über den CSS-Breakpoint (`max-width:760px`) und ein Zwischenbreiten-Screenshot bestätigt, keine echte 375-px-Sichtprüfung.
- **Erstattung einer Einnahme (Rücküberweisung):** In den Testdaten existiert keine Einnahme-Kategorie mit `richtung='beides'`, daher nicht end-to-end mit echten Daten durchgespielt (Code-Pfad ist symmetrisch zur geprüften Ausgaben-Erstattung).
- **Storno einer Buchung mit Beleg:** Kein Beleg-Upload in dieser Sitzung durchgeführt (nur Datei-Dialog-Öffnung des „Beleg fotografieren“-Buttons bestätigt), daher dieser Spezialfall nicht geprüft.
- **kontakt_id/person_id-Erhalt bei PUT (B7):** Nicht erneut end-to-end nachgestellt, da der Bearbeiten-Dialog keine UI-Felder für Kontakt/Person bietet und `POST /api/kontakte` in dieser Instanz mit 405 abgelehnt wird (kein Anlage-Weg gefunden). Verlasse mich auf die dokumentierte Abnahme `docs/neubau/abnahme/B7.md` (3 gezielte Tests, Gesamtsuite 365 Tests grün).
- **„Weitere laden“/Cursor-Pagination:** Mit den 25 Bestands- plus meinen Testbuchungen (insgesamt 30) wurde die Seitengröße nicht überschritten, Button war vorhanden, aber die Cursor-Mechanik selbst nicht bis zur zweiten Seite durchgespielt.
- **Bankkonto-Pflicht bei Zahlungsart „bank“:** Testdatenbank enthält nur Kassa-Konten je Sparte, keine echten Bankkonten — die Auswahl eines konkreten Bankkontos im Dropdown konnte nicht getestet werden, nur das Fehlen einer Pflicht-Validierung (weder Frontend `required` noch Backend).
- **Foto-Übernahme (P43) inhaltlich:** Nur das Öffnen des Datei-Dialogs bestätigt, keine echte Foto-Auswertung getestet (außerhalb des eigenen Bereichs, da P43 separat abgenommen wird).
- Filter „Zeitraum“ (Von/Bis) und „Weitere laden“ wurden nur oberflächlich geprüft (Felder vorhanden, Werte übernehmbar), nicht mit gezielten Grenzfällen (z. B. Von > Bis).

## 4. Gesamturteil

Die Kernflüsse (Erfassen, Buchungsliste mit Suche/Filtern, Bearbeiten mit Versionssperre und Historie, Storno/Entstorno, Teil-/Übererstattung mit allen Randfällen, Umbuchung anlegen/löschen, Bereichstrennung Haupt/Verein) funktionieren größtenteils korrekt und robust — insbesondere die geld- und datenkritische Logik in P51 (Storno, Erstattung, Versionssperre) hat sich in allen Stichproben exakt an die Spezifikation gehalten. Am schwersten wiegt jedoch, dass die Betragseingabe „12.50“ eine Buchung um Faktor 100 verfälscht (QA2-02) und dass der Schutz gegen Doppelbuchungen nach Netzwerkfehlern nur scheinbar über eine stabile `client_request_id` läuft, tatsächlich aber bei jedem Speichern-Versuch neu gewürfelt wird (QA2-04) — beides sollte vor einem produktiven Einsatz behoben werden.
