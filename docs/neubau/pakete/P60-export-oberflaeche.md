# P60: Export-Oberfläche für das Steuerpaket

Meilenstein M6. Modell: `gpt-5.6-luna`, Aufwand medium. Branch `pkt/p60-export-oberflaeche` von `neubau` (nach P16, P30).

## 1. Ziel

Der Nutzer wählt Sparte und Jahr, schließt einzelne Kategorien oder Buchungen vom Steuer-Export aus, sieht vorher exakt, was im Paket landet und was an Belegen fehlt, und lädt danach ein ZIP herunter, dessen Inhalt zur Vorschau passt. Die bestehenden Rohexporte (XLSX, Jahresbericht) bleiben erreichbar.

## 2. Kontext

Lies `docs/neubau/pakete/P16-export-steuerpaket.md` vollständig (Endpunkte, Revision, ZIP-Inhalt, Fehlerfälle), `docs/neubau/ARCHITEKTUR.md` Abschnitt 9 und 11, `docs/neubau/pakete/P30-frontend-geruest.md` (Gerüst, `api.js`-Fehlerbehandlung für 409/422), `app/routers/export.py` (sobald P16 umgesetzt ist), `docs/neubau/prototyp/prototyp.html` für Tabellen- und Dialogmuster (Checkbox-Listen, Toast, `esc`/`fmtEur`).

## 3. Schnittstellen

Kein neuer Backend-Endpunkt; dieses Paket ruft ausschließlich die in P16 definierten Endpunkte auf: `GET /api/export/profil`, `PUT /api/export/profil/{id}`, `POST /api/export/profil/{id}/uebernehmen-vom-vorjahr`, `POST /api/export/vorschau`, `POST /api/export/paket`, sowie weiterhin `GET /api/export/xlsx` und `GET /export/bericht`.

Neue Seite `static-neu/pages/export.js` (`export function render(root, state)`):
- Kopfzeile: Sparten-Auswahl (oder „Alle Sparten des Bereichs"), Jahr, Profilname (Standard „Steuer"); lädt bei Änderung `GET /api/export/profil?...` (legt bei Bedarf serverseitig ein leeres Profil an).
- „Vom Vorjahr übernehmen": Button, sichtbar wenn ein Vorjahresprofil existiert; ruft `POST .../uebernehmen-vom-vorjahr`, lädt danach neu.
- Buchungsliste des Jahres/der Sparte mit Checkbox je Zeile (Buchungs-Ausschluss) und einer zweiten Ebene „Kategorie ganz ausschließen" (Checkbox auf Kategorie-Ebene, deaktiviert die Einzel-Checkboxen ihrer Zeilen); Änderungen sammeln sich clientseitig und werden gebündelt mit `PUT /api/export/profil/{id}` gespeichert (nicht bei jedem Klick einzeln).
- Suchfeld mit Schalter „Suche wirkt auf den Export" (`nur_suchtreffer`); ohne Schalter grenzt die Suche nur die angezeigte Liste ein, wirkt sich aber laut P16 nicht auf den Export aus — das macht die Oberfläche sichtbar (Hinweistext neben dem Schalter).
- Vorschau-Panel: ruft `POST /api/export/vorschau` nach jeder gespeicherten Änderung; zeigt Anzahl Buchungen, Einnahmen, Ausgaben, ausgeschlossene Kategorien/Buchungen, Liste fehlender Belege (mit Buchungslink); merkt sich die zurückgegebene `revision`.
- „Paket erzeugen": ruft `POST /api/export/paket` mit der zuletzt gesehenen `revision`; bei 409 („revision stimmt nicht mehr") lädt die Seite die Vorschau neu und informiert per Toast, ohne den Download zu starten; bei 422 (fehlende Belege) öffnet einen Bestätigungsdialog „trotzdem exportieren" (`trotz_fehlender_belege=true`); bei Erfolg wird der ZIP-Stream als Datei-Download ausgelöst (`Content-Disposition` auswerten, `Blob`-Download ohne Bibliothek).
- Abschnitt „Weitere Exporte": Links/Buttons für `GET /api/export/xlsx` (Download) und `GET /export/bericht?jahr=` (öffnet in neuem Tab, druckbereit).
- Route `#/export` in `app.js` ergänzen (Platzhalter aus P30 ersetzen), Menüpunkt in der Sidebar.

## 4. Nicht-Ziele

Keine Änderung an `app/routers/export.py`. Keine PDF-Erzeugung, keine Bildumwandlung (unverändert aus P16). Kein Versand des Pakets.

## 5. Schritte

1. `static-neu/pages/export.js`: Kopfzeile, Profil laden/anlegen, Vorjahr übernehmen.
2. Buchungsliste mit Ausschluss-Checkboxen (Kategorie und Einzelbuchung), gebündeltes Speichern.
3. Vorschau-Panel, Revision, fehlende Belege.
4. Paket erzeugen mit 409/422-Behandlung und Download.
5. Weitere Exporte, Route/Navigation, Tests, Gesamtlauf, Bericht.

## 6. Tests

- `node --check static-neu/pages/export.js` fehlerfrei.
- `tests/test_static_neu.py` (aus P30) um die Export-Route erweitern (Seite wird ausgeliefert, kein 404).
- Falls eine Browserprüfung (Playwright) in der Sandbox möglich ist: Kategorie ausschließen ändert die Vorschau-Summe sichtbar; Paket-Download mit veralteter Revision zeigt den Hinweis statt eines stillen Fehlers; fehlender Beleg löst den Bestätigungsdialog aus — Schritte im Bericht, sonst ausdrücklich benannt, dass die Browserprüfung nicht möglich war.

## 7. Fertig heißt

- [ ] Syntaxprüfung und vorhandene Tests grün, Ausgabe im Bericht.
- [ ] Einmal im Browser gegen eine Wegwerf-Datenbank mit einem P16-Seed (Kategorie-Ausschluss, fehlender Beleg, veraltete Revision) durchgespielt (Schritte im Bericht) oder ausdrücklich benannt, falls nicht möglich.
- [ ] Keine Geheimnisse, keine echten Namen, keine neuen Abhängigkeiten, kein Build-Schritt.
- [ ] Bericht geschrieben.

## 8. Modell und Aufwand

`gpt-5.6-luna`, Aufwand medium: reine Oberfläche über bestehende, bereits spezifizierte Endpunkte; die Fehlerfälle (409/422) sind klar vorgegeben.

## 9. Bericht zurück

Geänderte und neue Dateien mit je einem Satz. Testausgabe. Was im Browser geprüft wurde oder nicht geprüft werden konnte. Offene Punkte mit Grund. Keine Commits, kein Push.
