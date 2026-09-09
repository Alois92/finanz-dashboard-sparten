# P52: Kredit-Oberfläche

Meilenstein M5. Modell: `gpt-5.6-luna`, Aufwand medium. Branch `pkt/p52-kredit-oberflaeche` von `neubau` (nach P14, P30).

## 1. Ziel

Der Nutzer trägt einmal im Jahr Zins und Restschuld aus dem Kredit-Kontoauszug ein und sieht danach für jede Rate, wie viel davon Zinsen (Ausgabe) und wie viel Tilgung (mindert die Schuld, zählt nicht als Ausgabe) war. Die Oberfläche macht die bestehende Kredit-Logik aus P14 bedienbar, ohne sie zu verändern.

## 2. Kontext

Lies `docs/neubau/pakete/P14-kredit.md` vollständig (Endpunkte, Verteilung, Schätzung, Zuordnen bestehender Buchungen), `docs/neubau/ARCHITEKTUR.md` Abschnitt 6 und 11, `docs/neubau/pakete/P30-frontend-geruest.md` (Gerüst, Router, Zustand, Beleg-Hochladen falls im Gerüst bereits vorhanden, sonst bestehenden Beleg-Upload aus `static-studio/app.js` als Vorlage), `app/routers/kredite.py` (sobald P14 umgesetzt ist), `app/routers/belege.py`. Fachliche Vorgabe: Fixzins-Annuität, monatlich gleiche Rate, jährlicher Kredit-Kontoauszug mit Zinsen und Restschuld; Abweichungen (fehlende Raten, andere Ratenbeträge) werden angezeigt, nie stillschweigend übernommen.

## 3. Schnittstellen

Kein neuer Backend-Endpunkt; dieses Paket ruft ausschließlich die in P14 definierten Endpunkte auf: `GET /api/kredite`, `POST /api/kredite`, `PATCH /api/kredite/{id}`, `PUT /api/kredite/{id}/jahre/{jahr}`, `POST /api/kredite/{id}/raten`, `GET /api/kredite/{id}/raten?jahr=`, `POST /api/kredite/{id}/raten/zuordnen`.

Neue Seite `static-neu/pages/kredit.js` (`export function render(root, state)`):
- Liste der Kredite der aktuell gewählten Sparte (leer → Hinweis „Kein Kredit erfasst" mit Formular „Kredit anlegen": Name, Monatsrate, Beginn, Zinssatz optional, Kategorie Zinsen, Kategorie Tilgung aus den Kategorien der Sparte).
- Je Kredit eine Jahresübersicht (Jahre aus `jahre` des Kredits plus laufendes Jahr): pro Jahr Status-Pille „geschätzt"/„bestätigt", Zinsbetrag, Restschuld; Klick öffnet „Jahr bestätigen": Eingabe Jahreszins und Restschuld (beides in Euro, wie im Prototyp `parseBetrag`/`fmtEur`), optional einen bereits hochgeladenen Beleg verknüpfen (bestehende Beleg-Auswahl/-Upload-Komponente aus dem Gerüst); nach dem Speichern zeigt die Antwort `raten`, `verteilt_cent` und `abweichungen` — Abweichungen werden als Warnliste angezeigt, nicht verschluckt.
- Je Jahr eine Ratentabelle (`GET .../raten?jahr=`): Datum, Rate gesamt, Zinsanteil, Tilgungsanteil, Status (geschätzt/bestätigt), analog zur Buchungsliste aus P50 aber mit den zwei zusätzlichen Spalten Zins/Tilgung.
- „Rate erfassen": Formular für `POST /api/kredite/{id}/raten` (Datum, Betrag mit Vorschlag `monatsrate_cent`).
- „Bestehende Buchungen zuordnen": Liste der Buchungen der Sparte mit der Kategorie `kategorie_rate_id`, die noch keine Kredit-Rate sind (clientseitiger Abgleich gegen die geladene Ratenliste), Mehrfachauswahl, „Zuordnen" ruft `POST /api/kredite/{id}/raten/zuordnen` mit den ausgewählten `buchung_ids`; danach werden Ratentabelle und Buchungsliste neu geladen.
- Route `#/sparte/<id>/kredit` oder eigener Menüpunkt „Kredit" in der Sidebar-Navigation des Gerüsts (`app.js` ergänzen; Platzhalter aus P30 ersetzen).

Alle Beträge in der Oberfläche in Euro mit Komma, intern immer Cent als Ganzzahl (`format.js` aus P30 verwenden, keine eigene Rundung).

## 4. Nicht-Ziele

Keine Änderung an `app/routers/kredite.py` oder `app/kredite.py`. Keine Sondertilgungen, keine variablen Zinsen. Kein automatisches Erkennen von Kreditraten im Bankimport.

## 5. Schritte

1. `static-neu/pages/kredit.js`: Kredit-Liste, Anlegen-Formular.
2. Jahresübersicht mit „Jahr bestätigen"-Dialog und Abweichungs-Anzeige.
3. Ratentabelle, Rate-erfassen-Formular.
4. Zuordnen bestehender Buchungen.
5. Route/Navigation in `app.js`, Tests, Gesamtlauf, Bericht.

## 6. Tests

- `node --check static-neu/pages/kredit.js` fehlerfrei.
- `tests/test_static_neu.py` (aus P30) um einen Fall erweitern: Seite lädt unter der Kredit-Route serverseitig aus (HTML/JS ausgeliefert, kein 404).
- Kein Test gegen echte Netzwerk-/Browserinteraktion vorgeschrieben; falls eine Browserprüfung (Playwright) in der Sandbox möglich ist: Kredit anlegen, Jahr bestätigen mit abweichender Rate (11 statt 12 Raten) zeigt die Abweichungswarnung, Ratentabelle zeigt Zins und Tilgung getrennt — Schritte im Bericht, sonst ausdrücklich benannt, dass die Browserprüfung nicht möglich war.

## 7. Fertig heißt

- [ ] Syntaxprüfung und vorhandene Tests grün, Ausgabe im Bericht.
- [ ] Kredit anlegen, Jahr bestätigen, Rate erfassen, Zuordnen einmal im Browser gegen eine Wegwerf-Datenbank mit einem P14-Kredit-Seed durchgespielt (Schritte im Bericht) oder ausdrücklich benannt, falls nicht möglich.
- [ ] Keine Geheimnisse, keine echten Namen, keine neuen Abhängigkeiten, kein Build-Schritt.
- [ ] Bericht geschrieben.

## 8. Modell und Aufwand

`gpt-5.6-luna`, Aufwand medium: reine Oberfläche über bestehende, bereits spezifizierte Endpunkte, keine neue Fachlogik.

## 9. Bericht zurück

Geänderte und neue Dateien mit je einem Satz. Testausgabe. Was im Browser geprüft wurde oder nicht geprüft werden konnte. Offene Punkte mit Grund. Keine Commits, kein Push.
