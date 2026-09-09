# P33: Seite Kategorienpflege

Meilenstein M3. Modell: `gpt-5.6-luna`, Aufwand medium. Branch `pkt/p33-seite-kategorien` von `neubau` (nach P31, P32).

## 1. Ziel

`static-neu/pages/kategorien.js` zeigt je Sparte die Kategorien mit Buchungssumme, erlaubt Umbenennen und Stilllegen/Aktivieren, verwaltet Stichwörter (Merkregeln) als echte `regel`-Datensätze, zeigt spartenübergreifende Kategoriegruppen und die Liste der gelernten Merkregeln — alles mit echten Endpoints, keine Demo-Daten und keine Platzhalter-Buttons mehr wie im Prototyp.

## 2. Kontext

Lies zuerst `docs/neubau/pakete/P31-seite-uebersicht.md` (Seiten-Anbindungslogik, Wiederverwendung von P30) und `docs/neubau/pakete/P15-kategorien-regeln-kennzahlen.md` (vollständige Schnittstelle für `PATCH /api/kategorien/{id}`, `GET /api/kategorien?nur_aktive=`, `GET/POST/PATCH /api/regeln`), dann `app/routers/stammdaten.py` und `app/routers/gruppen.py` (heutiger Stand von `/api/kategorien`, `/api/globalgruppen` — Response-Form dort exakt ablesen, sie ändert sich durch P15 nur um die in P15 beschriebenen Felder), `docs/neubau/pakete/P20-auswertungen-filtervertrag.md` (`GET /api/jahresmatrix`, `GET /api/buchungen`). Im Prototyp `docs/neubau/prototyp/prototyp.html`: `<section class="page" id="page-kategorien">` (Zeile ~677) für Markup, im Skript `renderKategorien` (Zeile ~1731) für Aufbau. Die dort mit `toast("Im Prototyp nur angedeutet")` markierten Aktionen (Regeln „abschalten", Regel „ändern"/„übernehmen" im Bankimport) werden in dieser Karte für die Kategorien-Seite **echt** umgesetzt (Regel abschalten = `PATCH /api/regeln/{id} {aktiv: false}`); die Bankimport-Seite selbst ist nicht Teil dieser Karte. Die Stichwort-Chips im Prototyp (`k.kw`, ein Array direkt an der Kategorie) gibt es im echten Modell nicht: Ein Stichwort ist ein eigener `regel`-Datensatz mit `quelle='stichwort'`, `bedingung_text`, `ziel_kategorie_id`. Die Chip-Liste je Kategorie wird deshalb aus den geladenen Regeln gefiltert, nicht aus einem Kategorie-Feld gelesen.

## 3. Schnittstellen

Datei `static-neu/pages/kategorien.js`, `export function render(root, state)`.

```
GET  /api/sparten?bereich_id=                                    (Reiter oben, wie Sidebar aus P30, aber eigene Reiterleiste laut Prototyp)
GET  /api/kategorien?bereich_id=&sparte_id=<aktiver Reiter>&nur_aktive=false
 → [{id, sparte_id, parent_id, name, richtung, aktiv, sortierung}]
GET  /api/jahresmatrix?bereich_id=&sparte_id=<aktiver Reiter>&jahre=<laufendes Jahr>
 → zeilen: [{kategorie_id, werte: {"<jahr>": {einnahmen_cent, ausgaben_cent}}, ...}]   -- liefert die Summenspalten der Tabelle in einem Aufruf statt je Kategorie einzeln
GET  /api/regeln?bereich_id=&quelle=stichwort                    (einmal für die ganze Seite laden, dann client-seitig nach ziel_kategorie_id filtern —
                                                                    das vermeidet Unklarheit darüber, wie der sparte_id-Parameter von /api/regeln
                                                                    Regeln nach Zielkategorie vs. Eingabesparte filtert)
 → [{id, name, bedingung_text, ziel_kategorie_id, quelle, auto_verbuchen, aktiv, erstellt_am, bankkonto_id, eingabe_sparte_id}]
GET  /api/regeln?bereich_id=&quelle=gelernt                       (für die Tabelle „Gelernte Merkregeln", ebenfalls einmal laden)
POST /api/regeln {name: <wort>, bedingung_text: <wort>, ziel_kategorie_id, quelle: 'stichwort'}   → 201   (Stichwort hinzufügen)
PATCH /api/regeln/{id} {aktiv: false}                             → Stichwort/Regel entfernen (×) bzw. „abschalten"
PATCH /api/regeln/{id} {aktiv: true}                              → Regel wieder aktivieren
PATCH /api/kategorien/{id} {name: <neuer Name>}                   → umbenennen
PATCH /api/kategorien/{id} {aktiv: false|true}                    → stilllegen/aktivieren
GET  /api/globalgruppen?bereich_id=                               → [{id, name, beschreibung, kategorie_ids}]
GET  /api/jahresmatrix?bereich_id=&jahre=<laufendes Jahr>          (ohne sparte_id: alle Sparten des Bereichs, für den Gruppen-Balken;
                                                                     ein zweiter, seltener Aufruf beim ersten Laden der Seite, nicht je Reiterwechsel)
```

Aufbau der Seite (Klassen/IDs aus dem Prototyp):

- **Reiter** (`#k-tabs`): ein Reiter je Sparte aus `GET /api/sparten` mit `farbe` als Punktfarbe; Wechsel lädt `GET /api/kategorien` und `GET /api/jahresmatrix` neu für die gewählte Sparte.
- **Kategorientabelle** (`#k-table`): Zeile je Kategorie des aktiven Reiters. Spalten: Name (inline umbenennen wie im Prototyp: Klick auf „umbenennen" ersetzt den Text durch ein Eingabefeld, Enter/Blur speichert über `PATCH`, Escape verwirft), Richtung (nur Anzeige: `einnahme`/`ausgabe`/`beides`), Stichwörter (Chips aus den geladenen Stichwort-Regeln mit `ziel_kategorie_id === kategorie.id`, `×` deaktiviert die Regel, Eingabefeld „+ Stichwort" legt eine neue Stichwort-Regel an — Wort vor dem Speichern `.trim().toLowerCase()`, wie im Prototyp), Buchungen/Summe/Ø je Monat aus der passenden Zeile in `jahresmatrix.zeilen` (`einnahmen_cent + ausgaben_cent` als Summe, Anzahl der Monate mit Daten nicht verfügbar — Spalte „Buchungen" entfällt gegenüber dem Prototyp ersatzlos, da keine Zählung ohne zusätzlichen Aufruf je Kategorie geliefert wird; stattdessen nur Summe und Ø je Monat zeigen), Stilllegen/Aktivieren-Knopf. Stillgelegte Kategorien mit Pille „stillgelegt" wie im Prototyp, bleiben in der Liste (`nur_aktive=false`).
- **+ Neue Kategorie** (`#k-new`): öffnet die Erfassen-Seite mit vorbelegter Sparte und geöffnetem „Neue Kategorie"-Formular, wie im Prototyp (`go("erfassen")` aus P30-Router, dann das dortige Formular öffnen — die genaue Verdrahtung mit `pages/erfassen.js` ist nicht Teil dieser Karte; ein einfacher Seitenwechsel mit Sparten-Vorbelegung im Zustand genügt, das Formular selbst kommt aus einer anderen Karte).
- **Gruppen über Sparten hinweg** (`#k-gruppen`): ein Balken je Eintrag aus `GET /api/globalgruppen`, Wert = Summe `ausgaben_cent` der Zeilen aus dem bereichsweiten `jahresmatrix`-Aufruf, deren `kategorie_id` in `kategorie_ids` der Gruppe liegt.
- **Gelernte Merkregeln** (`#k-regeln`): Tabelle aus den Regeln mit `quelle='gelernt'`: Bedingungstext, Zielkategorie (Name aus den geladenen Kategorien der jeweiligen Sparte — bei Kategorien außerhalb des aktiven Reiters zusätzlich den Spartennamen zeigen, dafür `GET /api/kategorien?bereich_id=` einmal ohne `sparte_id` für die ganze Seite laden, nicht je Reiter neu), Konto (`bankkonto_id`, falls vorhanden — Name aus `GET /api/konten?bereich_id=` einmal laden), „gelernt am" (`erstellt_am`, `fmtDate`), Knopf „abschalten" ruft `PATCH /api/regeln/{id} {aktiv:false}` und blendet die Zeile aus (Filter `aktiv=1` beim Rendern).

Keine neuen Backend-Endpoints; alle verwendeten Endpoints stammen aus P15/P10/P20.

## 4. Nicht-Ziele

Kein Löschen von Kategorien oder Regeln (nur stilllegen/deaktivieren). Kein Zusammenlegen von Kategorien. Keine Änderung an `app/routers/stammdaten.py`, `app/routers/gruppen.py`, `app/regeln.py` über das in P15 bereits Festgelegte hinaus. Keine Bankimport-Seite (`pages/bankimport.js`), auch wenn dort ebenfalls Regeln vorkommen — getrennte Karte. Kein Editor für Kategoriegruppen (`#k-gruppen` ist reine Anzeige).

## 5. Schritte

1. `pages/kategorien.js` schreiben: Reiter, Kategorientabelle mit Umbenennen/Stilllegen.
2. Stichwort-Verwaltung über Regel-Endpoints.
3. Gruppen-Balken und Tabelle der gelernten Regeln.
4. Node-Syntaxprüfung, Tests.
5. Browserprüfung, Bericht.

## 6. Tests

Testinterpreter `C:\Users\lblet\dev\finanz-dashboard-sparten\.venv\Scripts\python.exe`, `FINANZ_DB` je Test über `tempfile.TemporaryDirectory()` auf eine Wegwerf-Datenbank unter `C:\Users\lblet\AppData\Local\Temp`, niemals die echte Datenbank. Fixtures mit echter Struktur (mehrere Sparten, Kategorien mit `aktiv=0` und `aktiv=1`, Stichwort-Regeln, eine gelernte Regel, eine globale Kategoriegruppe mit Kategorien aus zwei Sparten).

Neue Datei `tests/test_static_neu_kategorien.py`:
- `GET /neu/pages/kategorien.js` liefert 200 und JavaScript-Text, der auf `api.js` und die Endpoints aus 3 referenziert.
- `node --check static-neu/pages/kategorien.js` (überspringen mit Meldung, wenn `node` fehlt).
- `PATCH /api/kategorien/{id} {name: "Neuer Name"}` ändert nur den Namen, bestehende Regeln und Kennzahlen zeigen weiter auf dieselbe ID (Kontrolle, dass die Seite keine ID-Änderung voraussetzt).
- Stichwort anlegen (`POST /api/regeln {quelle:'stichwort', ...}`) und wieder entfernen (`PATCH {aktiv:false}`): `GET /api/regeln?quelle=stichwort` zeigt das Stichwort danach nicht mehr als aktiv.
- Globale Kategoriegruppe mit Kategorien aus zwei Sparten: Summe aus `jahresmatrix` (ohne `sparte_id`) über `kategorie_ids` ergibt denselben Wert wie die einzelnen Sparten-Summen zusammen (Kontrolle des in 3. beschriebenen Aggregationswegs).
- Antwortform der verwendeten Endpoints enthält alle Felder, die `pages/kategorien.js` laut 3. verwendet (Vertragstest wie in P31/P32).

Browserprüfung (Playwright, falls möglich, sonst im Bericht begründen): Kategorienseite lädt ohne Konsolenfehler, Reiterwechsel lädt neu, Umbenennen und Stilllegen funktionieren sichtbar, Stichwort hinzufügen/entfernen funktioniert, Gruppen-Balken und Regel-Tabelle zeigen Daten, „abschalten" entfernt eine Regelzeile.

## 7. Fertig heißt

- [ ] Alle Tests grün, vollständige Ausgabe im Bericht (oder begründet übersprungen).
- [ ] Kein `toast("Im Prototyp nur angedeutet")` mehr für Aktionen, die in dieser Karte spezifiziert sind (Regel abschalten, Stichwort entfernen).
- [ ] Keine Geheimnisse, keine echten Namen.
- [ ] Bericht geschrieben.

## 8. Modell und Aufwand

`gpt-5.6-luna`, Aufwand medium. Anbindung bestehender, bereits spezifizierter Endpoints; die Umwandlung der Prototyp-Stichwort-Chips in echte Regel-Datensätze ist die größte gedankliche Umstellung, aber ohne neue Rechenlogik oder neues Datenmodell. Effort **nicht** high.

## 9. Bericht zurück

Geänderte und neue Dateien mit je einem Satz. Vollständige Testausgabe. Was im Browser geprüft wurde oder nicht geprüft werden konnte, mit Grund. Offene Punkte. Keine Commits, kein Push.
