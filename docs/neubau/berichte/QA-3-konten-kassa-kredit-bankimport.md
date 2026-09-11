# QA-3 — Konten, Kassa, Auslagen/Ausgleich, Abgleich, Bankimport, Kredit

Testinstanz: `http://127.0.0.1:8054/`, Bereich Haupt (id 1) und Verein (id 2), Wegwerf-DB Schema 17.
Werkzeuge: Browser (Claude Browser, eigener Tab), `curl` gegen `/api/...`, Serverlog
`C:\Users\lblet\AppData\Local\Temp\qa-8054.log`, Code-Referenz `C:\Users\lblet\dev\finanz-dashboard-sparten`.
Datum: 11. September 2026.

## 1. Umfang — Checkliste

### Konten (P41)

| # | Prüfung | Ergebnis |
|---|---|---|
| 1 | Kontenliste je Bereich (`GET /api/konten`), Gruppierung nach Art (Bank/Kassa/Depot-Wallet) im Frontend | OK |
| 2 | Bankkonto anlegen (Dialog, Pflichtfelder) | OK |
| 3 | Kassa ohne Sparte anlegen → 422 mit Feldfehler im Dialog, Dialog bleibt offen | OK |
| 4 | Zweite Kassa in derselben Sparte → 409 „Je Sparte ist nur eine Kassa erlaubt" | OK (per curl geprüft, Dialog zeigt Serverfehler analog zu #3) |
| 5 | Konto bearbeiten (Name/IBAN/Bank ändern) über die Oberfläche | **Nicht möglich** — siehe QA3-04 |
| 6 | Konto deaktivieren über die Oberfläche | **Nicht möglich** — siehe QA3-04 |
| 7 | Konto-Art/Währung/Sparte wechseln, wenn Bewegungen existieren → 409 | OK (per curl) |
| 8 | Konto-Art wechseln, wenn keine Bewegungen existieren → erlaubt | OK (per curl) |
| 9 | Währung-Validierung (`^[A-Z]{3}$`) | OK, 422 bei `"eur"` |
| 10 | Name leer/nur Leerzeichen → 422 | OK |
| 11 | Sparte aus anderem Bereich → 404 | OK |
| 12 | Depot/Wallet-Konto anlegen, eigene Gruppe im Frontend | OK |
| 13 | Kontostand aus Bewegungen (`stand_cent`), Datenstand-Badge „aktuell"/„unbekannt" | OK |
| 14 | Datenstand-Badge Titel-Attribut mit `hinweis`-Text | OK (per Markup geprüft) |
| 15 | Saldo-Anker setzen ohne vorherigen Anker | OK, „kein Anker" → Wert nach Setzen sichtbar |
| 16 | Saldo-Anker setzen mit vorherigem Anker, Differenz-Anzeige | OK, ungeschönt angezeigt (`Bisher gerechneter Stand … Differenz zum neuen Anker …`) |
| 17 | Zweimal denselben Stichtag ankern → 409 | Nicht im Browser geprüft, per Code (`UNIQUE`-Constraint → `IntegrityError` → 409) plausibel; nicht separat verifiziert |
| 18 | Anker löschen (`DELETE /api/konten/{id}/anker/{id}`) | Nur per API-Übersicht bestätigt vorhanden; keine Oberfläche dafür — Endpoint existiert, aber `konten.js` bietet keinen Lösch-Knopf für Anker |
| 19 | Kassazählung ohne Differenz | Nicht separat im Browser geprüft (Differenzfall geprüft, siehe #20); per Code klar (`toast('Kassa gezählt: keine Differenz.')`) |
| 20 | Kassazählung mit Differenz, Kategorie wählen, buchen, Stand aktualisiert sich sichtbar | OK |
| 21 | Kassazählung ohne vorherigen Anker → 422 „Kassenstand ist ohne Anker unbekannt" | Nicht im Browser geprüft, aber Backend-Regel klar aus `konten.py`; nicht separat verifiziert |
| 22 | „Kassadifferenz"-Kategorie-Vorauswahl | Kategorie „Kassadifferenz" existiert in den Testdaten nicht; Frontend fällt sauber auf die erste passende Kategorie zurück (kein Fehler) |
| 23 | Bewegungs-Liste mit Cursor (`GET /api/konten/{id}/bewegungen`) | OK (per curl, zwei Seiten korrekt, `naechster_cursor` funktioniert) |
| 24 | Kontostand mit Stichtag (`GET /api/konten/{id}/stand`) | OK |
| 25 | Währung wird korrekt angezeigt und mitgeführt | OK, aber doppelt dargestellt — siehe QA3-01 |
| 26 | Hinweis „offene Abgleiche" je Konto (N4-Integration) | OK, wird korrekt aktualisiert; auf Kassa-Konten fachlich sinnlos — siehe QA3-05 |

### Auslagen / Ausgleich (P41/P12)

| # | Prüfung | Ergebnis |
|---|---|---|
| 27 | Auslage „bezahlt von anderer Sparte" anlegen, erscheint gruppiert unter „Offene Auslagen" | OK |
| 28 | Drilldown „Buchungen" öffnet Liste der Einzelbuchungen | OK |
| 29 | Ausgleich-Dialog vorbefüllt (alle Auslagen angehakt, Zahlungsart bar, Datum heute, Betrag = Summe) | OK |
| 30 | Teilausgleich (Betrag kleiner als Summe) bar buchen | OK, FIFO-Zuordnung korrekt, Reststand aktualisiert |
| 31 | Ausgleich bei niedriger/negativer Kassa → Warnung „hat nur … €, danach negativ", Buchung geht trotzdem durch (201) | OK, exakt wie spezifiziert |
| 32 | Ausgleichs-Historie zeigt gebuchte Ausgleiche | OK |
| 33 | Ausgleich zurücknehmen (Dialog statt `confirm()`), Stand wieder wie vorher | OK |
| 34 | Bankausgleich ohne `von_konto_id`/`nach_konto_id` → 422 | OK (per curl) |
| 35 | Auslage doppelt in `auslage_ids` → serverseitig abgelehnt | Nicht im Browser geprüft; laut `field_validator eindeutige_auslagen` im Code abgedeckt |
| 36 | Datum vor ältester Auslage → 422 | Nicht separat geprüft, Codepfad vorhanden |

### Abgleich Bankumsatz ↔ Buchung (N4/P42)

| # | Prüfung | Ergebnis |
|---|---|---|
| 37 | `GET /api/bankumsaetze/{id}/kandidaten` findet passende manuelle Buchung (±5 Tage, exakter Betrag) | OK |
| 38 | `GET /api/konten/{id}/offene-abgleiche` liefert Anzahl + Liste manueller Bewegungen und offener Umsätze mit `kandidaten_anzahl` | OK |
| 39 | `POST /api/bankumsaetze/{id}/zuordnen` führt manuelle und importierte Bewegung zusammen; manuelle Bewegung storniert, importierte bleibt, Kontostand zählt danach nur einfach | OK, exakt geprüft (Bewegungsliste vor/nach kontrolliert) |
| 40 | Wiederholte Zuordnung ist idempotent | OK |
| 41 | `POST /api/bankumsaetze/{id}/zuordnung-loesen` macht Zuordnung rückgängig | OK |
| 42 | Falscher Betrag bei Zuordnen → 409 mit Grund | OK |
| 43 | Zuordnung über Bereichsgrenze (Umsatz aus Bereich 1 mit `bereich_id=2` abgefragt) → 404 | OK |
| 44 | „Zusammenführen"-Vorschlag im Bankimport-Frontend nach Upload, Klick führt zusammen, Umsatz verschwindet aus „offen" | OK |
| 45 | „Getrennt lassen" blendet Vorschlag nur clientseitig aus | Nicht im Browser geprüft (nur „Zusammenführen" getestet), Code vorhanden |
| 46 | `GET /api/bankumsaetze` liefert für verbuchte Umsätze weder Buchungstyp noch Regel-Herkunft | Bestätigt, bereits als bekannte Schuld P42b dokumentiert |

### Bankimport (P42/N5/P01)

| # | Prüfung | Ergebnis |
|---|---|---|
| 47 | CSV-Import UTF-16, Komma-getrennt, Komma-Dezimalzahlen (George-Fixture) | OK, 8 neu, 0 ungültig, Kodierung/Trennzeichen korrekt erkannt |
| 48 | Duplikat-Import derselben Datei → Dublettenschutz | OK, 0 neu, 8 Dubletten |
| 49 | CSV UTF-8, Semikolon, Saldo-Spalte, absteigend sortiert | OK, `saldo_ok: true`, Anker aus Saldo korrekt gesetzt |
| 50 | Kaputte CSV ohne Pflichtspalten → 400 mit verständlicher Meldung (Kodierung/Trennzeichen/Spalten im Text) | OK |
| 51 | Leere Datei → 400 „Datei ist leer" | OK |
| 52 | CSV mit einzelnen ungültigen Zeilen (Datum/Betrag) → Import läuft, ungültige Zeilen landen in `zeilen_ungueltig` mit Grund | OK |
| 53 | Import auf Kassa-Konto → 422 „Kassenkonten sind vom CSV-Import ausgeschlossen" | OK |
| 54 | Je neuem Umsatz genau eine `bewegung` mit `quelle='import'` | OK |
| 55 | Umsatz „offen" → Formular „zuordnen", Sparte/Kategorie wählen, Speichern → `verbucht` | OK, Buchung wird angelegt |
| 56 | Sparte im Verbuchen-Formular vorbelegt mit der Sparte des Bankkontos | **Fehler** — siehe QA3-02 |
| 57 | „ignorieren" setzt `importstatus='ignoriert'` | OK |
| 58 | „Alle Vorschläge übernehmen" bei 0 Vorschlägen zeigt „(0)", kein Absturz | OK (Knopf vorhanden, Zähler korrekt, nicht ausgelöst da keine Regel-Vorschläge in den Testdaten griffen) |
| 59 | Konten-Karte (nur Bank/Karte, lesend) zeigt Stand, letzter Import, Link „Verwalten → Konten" | OK |
| 60 | Kassakonten erscheinen nicht in der Bankimport-Kontoauswahl | OK |
| 61 | Server-Log ohne 500er/Tracebacks während des gesamten Testlaufs | OK, geprüft |

### Kredit (P52/N3)

| # | Prüfung | Ergebnis |
|---|---|---|
| 62 | Kredit anlegen (Name, Monatsrate, Beginn, Zinssatz, Kategorie Zinsen/Tilgung), Sparte vorbelegt mit aktuell gewählter Sparte | OK |
| 63 | Rate erfassen, Betrag mit Monatsrate vorbefüllt, Zins/Tilgung-Aufteilung (ohne Vorjahres-Zinssatz: Zins 0, ganze Rate als Tilgung, mit Hinweis) | OK |
| 64 | Jahr bestätigen (Zins, Restschuld, optional Beleg), Abweichungswarnung bei fehlenden Raten (1 statt 12) sichtbar | OK, siehe QA3-06 zur Dialog-Bedienung |
| 65 | Ratentabelle zeigt Zins/Tilgung getrennt nach Jahr-Bestätigung neu berechnet | OK |
| 66 | Bestehende Buchungen (Kategorie = Ratekategorie, noch keine Rate) zuordnen | OK |
| 67 | `kredit_id`-Spalte statt Notiz-Marker (N3) | OK, per API bestätigt (`kredit_id` gesetzt, `notiz` bleibt `null`) |
| 68 | Raten lösen (`/raten/loesen`) setzt `kredit_id` zurück | OK |
| 69 | Kredit-Kachel/-Navigation über Sidebar „Kredit" | OK; direkte URL `#/sparte/<id>/kredit` funktioniert **nicht** — siehe QA3-07 |
| 70 | Kreditliste bei „Alle Sparten" zeigt alle Kredite des Bereichs ohne Sparten-Filter (bekannte Schuld P52b) | Bestätigt, Backend `list_kredite` filtert nicht nach Sparte |
| 71 | Beleg-Verknüpfung im „Jahr bestätigen"-Dialog (Auswahl vorhandener Belege) | OK, Dropdown mit vorhandenem Beleg sichtbar; kein Upload im Dialog (laut P52-Abnahme so vorgesehen) |

### Handy-Ansicht (375 px)

| # | Prüfung | Ergebnis |
|---|---|---|
| 72 | Konten-Seite mobil | Kein horizontales Scrollen feststellbar, Bottom-Navigation sichtbar, Karten stapeln sich korrekt |
| 73 | Bankimport-Seite mobil/Desktop | **Horizontaler Seiten-Overflow** durch Karten-Kopfzeile — siehe QA3-03 |
| 74 | Kredit-Seite mobil | Laut P52-Abnahme bereits geprüft („keine Überbreite"); von mir nicht erneut mit zuverlässiger 375-px-Emulation nachvollzogen, siehe Abschnitt 3 |
| 75 | Echte 375-px-CSS-Breite im Testwerkzeug | Nicht zuverlässig erreichbar (`window.innerWidth` blieb bei 834 px trotz bestätigtem `375x812`-Preset) — Einschränkung, siehe Abschnitt 3 |

## 2. Befunde

### QA3-01 — Doppelte Währungsangabe bei Kontostand (niedrig, kosmetisch)

- **Seite:** Konten (`/#/konten`), jede Kontozeile mit gesetztem Anker.
- **Schritte:** Konto mit Anker aufrufen, z. B. „Kassa Alois privat".
- **Erwartet:** Betrag mit einem Währungssymbol, z. B. „€ 1.600,00".
- **Tatsächlich:** „€ 1.600,00 EUR" — `fmtEur()` liefert bereits das €-Symbol (`Intl.NumberFormat` mit `style:'currency'`), `konten.js` Zeile 120 hängt zusätzlich `<span class="muted">{waehrung}</span>` an.
- **Datei:** `static-neu/pages/konten.js:120`.
- **Reproduktion:** browserunabhängig, auch mobil sichtbar (Screenshot geprüft).

### QA3-02 — Bankumsatz-Verbuchen-Formular wählt falsche Sparte vor (hoch)

- **Seite:** Bankimport (`/#/bankimport`), Formular „zuordnen"/„ändern" bei einem offenen Umsatz ohne Regel-Vorschlag.
- **Schritte:**
  1. Bankkonto „QA Testkonto Bank" (Sparte „Hechenegg Hof", `sparte_id=3`) anlegen und einen Kontoauszug importieren.
  2. Bei einem offenen Umsatz ohne Vorschlag auf „zuordnen" klicken.
  3. Kategorie auswählen (Standardauswahl belassen) und „Speichern" klicken, ohne die Sparte manuell zu ändern.
- **Erwartet:** Entweder ist die Sparte leer/muss aktiv gewählt werden, oder sie ist mit der Sparte des Bankkontos vorbelegt (analog zur Kredit-Seite, die korrekt die aktuell gewählte Sparte vorbelegt).
- **Tatsächlich:** Die Sparte ist immer mit der ersten Sparte aus `state.sparten` vorausgewählt (`state.sparten[0]?.id`), unabhängig vom Bankkonto. Im Test wurde ein Umsatz von Konto „QA Testkonto Bank" (Sparte Hechenegg Hof) anstandslos in Sparte „Vermietung Haus Münster" mit Kategorie „Miete" gebucht (Buchung-ID 29), obwohl das Bankkonto nie dieser Sparte zugeordnet war. Kein Warnhinweis, keine Bestätigung nötig — die Buchung ist sofort verbindlich verbucht.
- **Datei:** `static-neu/pages/bankimport.js:200-201` (`const ersteSparte = prefill?.sparte_id ?? state.sparten[0]?.id;`).
- **Auswirkung:** Reale Gefahr von Fehlbuchungen in eine falsche Sparte bei jedem manuellen Verbuchen ohne Regel-Vorschlag, insbesondere wenn der Nutzer die vorbelegte Sparte übersieht.

### QA3-03 — Horizontaler Seiten-Overflow durch `.card-head` auf der Bankimport-Seite (mittel)

- **Seite:** Bankimport (`/#/bankimport`), bereits bei Desktop-Breite 1024 px reproduzierbar, verschärft sich auf schmalen/mobilen Bildschirmen.
- **Schritte:** Bankimport-Seite mit einem Bankkonto öffnen (Kartenköpfe „Kontoauszug einspielen" und „Umsätze" enthalten lange Hinweistexte).
- **Erwartet:** Kein horizontales Scrollen der Gesamtseite; lange Hinweistexte im Kartenkopf brechen um.
- **Tatsächlich:** `document.documentElement.scrollWidth` (1106 px) > `innerWidth` (1024 px) bei Standardbreite. Ursache: `.card-head{display:flex;justify-content:space-between;...}` in `static-neu/style.css` hat weder `flex-wrap` noch `min-width:0` auf den Kindern; der `<span class="hint">`-Text („Kodierung, Trennzeichen und Spalten werden erkannt · du siehst zuerst den Prüfbericht" bzw. „gelernte Regeln verbuchen automatisch · Stichwort-Treffer sind nur Vorschläge · Unsicheres bleibt offen") verhindert wegen der Flexbox-Default-`min-width:auto` den Zeilenumbruch und drückt die ganze Karte (und damit `<body>`) über den Viewport hinaus.
- **Dateien:** `static-neu/style.css` (Regel `.card-head`), betroffene Hinweistexte in `static-neu/pages/bankimport.js`.
- **Hinweis:** `.card-head` ist eine geteilte Gerüst-Klasse (P30); andere Seiten mit kürzeren Hinweistexten sind davon nicht sichtbar betroffen, das Problem tritt aber bei jeder Karte mit langem Kopftext auf.

### QA3-04 — Bestehendes Konto kann im Frontend nicht bearbeitet oder deaktiviert werden (mittel)

- **Seite:** Konten (`/#/konten`).
- **Schritte:** Ein vorhandenes Bank-/Karten-/Depot-Konto suchen und versuchen, Name, IBAN, Bank oder den Aktiv-Status zu ändern.
- **Erwartet:** Laut Testauftrag und sinnvoller Fachlichkeit sollten Konten bearbeitet/deaktiviert werden können (Backend `PATCH /api/konten/{id}` unterstützt `name`, `iban`, `bank`, `kartenendnummer`, `aktiv`, `sortierung` vollständig).
- **Tatsächlich:** `static-neu/pages/konten.js` bietet ausschließlich „+ Konto anlegen", „Anfangsstand ändern" und „Kassa gezählt, Differenz buchen". Es gibt keinen „Bearbeiten"- oder „Deaktivieren"-Knopf für ein bestehendes Konto. Ein per `PATCH aktiv:0` deaktiviertes Konto wird von der Liste weiterhin ganz normal angezeigt (kein „inaktiv"-Badge, keine Sonderbehandlung) — für den Nutzer nicht von einem aktiven Konto zu unterscheiden.
- **Einordnung:** Das P41-Auftragspapier selbst spezifiziert für die Konten-Karte nur Anlegen/Anker/Kassazählung, kein Bearbeiten/Deaktivieren — insofern kein Abweichen vom Auftrag, aber eine Lücke gegenüber dem im QA-Auftrag genannten Prüfumfang und ein echtes Bedienbarkeits-Manko (IBAN-Tippfehler oder ein nicht mehr genutztes Konto lassen sich nur per API korrigieren).

### QA3-05 — „Offene Abgleiche"-Hinweis erscheint auch auf Kassakonten (niedrig)

- **Seite:** Konten (`/#/konten`), jede Kassa mit einer manuellen Bewegung ohne Bankumsatz (z. B. nach einer gebuchten Kassadifferenz).
- **Schritte:** Kassadifferenz buchen (erzeugt eine `bewegung` mit `quelle='manuell'`), Konten-Seite neu laden.
- **Erwartet:** Der Hinweis „X offene manuelle Bewegung(en) … zum Abgleichen" ist fachlich nur für Bankkonten sinnvoll, da CSV-Import auf Kassakonten ausgeschlossen ist (`import_csv` lehnt `art='kassa'` mit 422 ab) — ein Abgleich mit einem Bankumsatz kann auf einer Kassa nie stattfinden.
- **Tatsächlich:** Der Hinweis wird unterschiedslos für alle Kontoarten aus `GET /api/konten/{id}/offene-abgleiche` gerendert (`konten.js:123-127`), auch für Kassakonten, wo er nie „abgleichbar" wird und daher nur verwirrt.
- **Datei:** `static-neu/pages/konten.js:121-128`.

### QA3-06 — „Jahr bestätigen"-Dialog bleibt nach erfolgreichem Speichern offen und blockiert die Seite (niedrig)

- **Seite:** Kredit (`/#/kredit` bzw. Sidebar „Kredit"), Dialog „Jahr bestätigen".
- **Schritte:** Jahr bestätigen, Formular absenden.
- **Erwartet/Tatsächlich:** Das ist so gewollt (der Dialog zeigt bewusst die Abweichungswarnung und deaktiviert die Felder, schließt aber nicht automatisch — analog zum Ausgleich-Dialog in P41). Kein Fehlverhalten der App, aber in der Bedienung eine Falle: Der overlay-artige Dialog liegt weiterhin über der Seite und fängt Klicks auf darunterliegende Elemente ab (z. B. auf „Bestehende Buchungen zuordnen"), ohne dass das für den Nutzer offensichtlich ist — ein Klick „geht ins Leere", ohne Fehlermeldung. Erst „Schließen" gibt die Seite wieder frei.
- **Datei:** `static-neu/pages/kredit.js:173-175` (kein `closeDrill()` nach erfolgreichem Speichern).
- **Einordnung:** Kein harter Bug, aber dieselbe Falle würde vermutlich auch echte Nutzer treffen; niedrige Priorität, da mit „Schließen" lösbar.

### QA3-07 — Direkter Aufruf der Kredit-Route über URL-Hash funktioniert nicht (niedrig)

- **Seite:** `http://127.0.0.1:8054/#/sparte/3/kredit` (aus der P52-Auftragskarte als vorgeschlagene Route genannt).
- **Schritte:** Diese URL direkt aufrufen bzw. neu laden.
- **Erwartet:** Kredit-Seite für Sparte 3 öffnet sich.
- **Tatsächlich:** Es öffnet sich die normale Sparte-Übersichtsseite (`#/sparte`), keine Kredit-Ansicht. Die tatsächliche Route lautet offenbar schlicht `#/kredit` (über den Sidebar-Punkt „Kredit" erreichbar, sparten-gefiltert über den globalen Sparten-Filter oben, nicht über den URL-Pfad). Kein Datenverlust, nur ein Navigations-/Lesezeichen-Problem: Ein gespeichertes Lesezeichen oder ein Tiefenlink auf einen bestimmten Kredit-Bereich funktioniert nicht wie in der Auftragskarte P52 als Möglichkeit skizziert.
- **Datei:** vermutlich Router in `static-neu/app.js` (Route wurde laut P52-Abnahme „eine Zeile … Route kredit in app.js" ergänzt, offenbar ohne den `sparte/<id>/kredit`-Pfad).

## 3. Nicht geprüft / Einschränkungen

- **Mobile-Emulation unzuverlässig:** `resize_window` (Preset „mobile" bzw. explizit 375×812) bestätigte zwar `outerWidth: 375`, aber `window.innerWidth` blieb im Testwerkzeug konstant bei ca. 834 px, unabhängig von Tab/Neustart. Die App liefert selbst ein korrektes `<meta name="viewport" content="width=device-width,initial-scale=1">`; das Problem liegt im Testwerkzeug/der gemeinsam genutzten Browser-Instanz dieser Session, nicht nachweisbar in der App. Eine echte 375-px-CSS-Prüfung der Kredit- und Konten-Seite war damit nur eingeschränkt möglich (kein Overflow bei ~834 px feststellbar, für Bankimport aber schon — siehe QA3-03, das Problem wird bei echten 375 px vermutlich eher schlimmer). Eine Nachprüfung auf einem echten Gerät oder mit funktionierender Emulation wird empfohlen.
- **Datei-Upload im Browser:** Für den CSV-Upload wurde direkt `curl -F` gegen `/api/import/csv` verwendet (wie im Auftrag als Ausweichlösung vorgesehen), nicht der Drag-&-Drop/Datei-Dialog im Browser-Werkzeug selbst. Die Bedienung des `bi-drop`-Elements (Drag&Drop-Zone) im Browser wurde damit nicht überprüft, nur die serverseitige Verarbeitung und die Ergebnisanzeige.
- **Regeln (Stichwort/gelernt) und automatisches Verbuchen beim Import:** Wegen eines Zeichensatz-Problems in meinem eigenen curl-Aufruf (Umlaut in `bedingung_text`) konnte ich keine eigene Regel mit Umlauten anlegen und den automatischen Verbuchungspfad beim Import (`quelle='gelernt'`, `auto_verbuchen=1`) nicht gezielt end-to-end durchspielen; die vorhandenen Regeln aus den Testdaten griffen bei den importierten Testzeilen nicht. Die Logik selbst ist Bestandteil von P15 und war nicht mein Prüfbereich.
- **Anker-Löschen (`DELETE /api/konten/{id}/anker/{id}`), doppelter Stichtag → 409, Kassazählung ohne Anker → 422, Auslage doppelt in `auslage_ids`, Datum vor ältester Auslage:** Aus Zeitgründen nur anhand des Codes nachvollzogen, nicht live gegen die Instanz verifiziert (Endpunkte/Validatoren sind eindeutig im Code sichtbar, siehe Tabelle oben für die jeweilige Zeile).
- **„Getrennt lassen"-Knopf** bei Zusammenführen-Vorschlägen im Bankimport nur im Code gelesen, nicht im Browser geklickt.
- **Excel-Import** (`POST /api/import/excel`, in `openapi.json` sichtbar) ist nicht Teil des Auftrags und wurde nicht geprüft.
- **Kredit-Handy-Ansicht** wurde wegen der oben genannten Emulations-Einschränkung nicht eigenständig neu verifiziert; ich stütze mich hier auf die bereits im P52-Abnahmebericht dokumentierte Browserprüfung („keine Überbreite, Bottom-Navigation sichtbar").
- **Kein Nutzertest, keine Rückfragen** wie im Auftrag vorgegeben; alle Annahmen (z. B. Wahl von Testbeträgen/-daten) wurden eigenständig getroffen und sind oben dokumentiert.

## 4. Gesamturteil

Die Kernflüsse in allen sechs Prüfbereichen funktionieren korrekt und decken sich mit den Auftragskarten und bekannten Schulden (P42b, P52b) — Kontostand, Anker, Kassazählung, Auslagen/Ausgleich samt Warnung und Rücknahme, der komplette N4-Abgleich (Kandidaten/Zuordnen/Lösen inkl. Idempotenz und Bereichsisolation) sowie CSV-Import mit UTF-16/Komma-Dezimal, Dublettenschutz und Kredit-Jahr/Raten-Logik liefen im Test ohne Serverfehler durch. Der schwerwiegendste Fund ist QA3-02: Das Bankimport-Verbuchen-Formular wählt beim Fehlen eines Regel-Vorschlags unbemerkt die falsche Sparte vor und lässt sich anstandslos in eine fachlich falsche Sparte verbuchen — das sollte vor der Freigabe behoben werden, die übrigen Befunde sind kosmetisch bis mittelschwer und können nachgezogen werden.
