# P20 Umsetzung

Verbindlich: P20-Karte einschließlich Abschnitt 10; Migration 014 laut Auftrag.
Architektur: `app/rechenbasis.py` enthält Filter, SQL-Prädikate, Summen,
Zeitvergleiche und Hinweise. Router adaptieren Antworten. Kontostände nutzen P13.
Keine neuen Abhängigkeiten, keine Änderungen an Auth, keine Commits.

- [x] Alte ASGI-Antworten als feste JSON-Snapshots erfassen und prüfen.
- [ ] Reproduzierbaren Seed und Tests für Abschnitt 10.1 sowie Filter,
  Erwartung, Matrix, Cursor und Hinweise vor der Implementierung anlegen.
- [ ] Rechenbasis und neue Routen implementieren, alte Routen delegieren lassen.
- [ ] Migration 014 und identisches Frischschema ergänzen; sämtliche
  Migrationslistenerwartungen prüfen und aktualisieren.
- [ ] 5.000-Buchungen-Seed messen, gezielte Tests und gesamte Suite ausführen.
- [ ] Diff prüfen und Bericht mit vollständiger Testausgabe schreiben.

Annahmen: Suche behält aus Kompatibilitätsgründen die bisherige Listenform und
200 Treffer, verwendet intern die neue Liste. Neue Liste paginiert standardmäßig
mit 100 Treffern. Ein gesetztes Jahr begrenzt aktuelle Zahlen auf den Stichtag;
historische Alt-Routen ohne Jahr behalten ihre bisherigen Datumsgrenzen.
