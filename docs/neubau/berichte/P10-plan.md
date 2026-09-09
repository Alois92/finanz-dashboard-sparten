# P10 Umsetzung

Verbindliche Grundlage: `docs/neubau/pakete/P10-bereiche.md`, Architektur Abschnitte 2 und 8. Branch `pkt/p10-bereiche` ist identisch mit `neubau`; keine Commits oder Pushes.

- [x] Migration 003, Schema und Seed: sechs Bereichsspalten, feste Bereiche, deterministische Gruppenzuordnung mit Log; idempotenter allgemeiner Runner und Schema-Abgleich.
- [x] Zentrale Dependency und Kennungsprüfungen; Stammdaten mit API-Tests auf echtem Schema und Seed.
- [x] Buchungen und Umbuchungen: Filter, fremde Referenzen mit 404, bereichsgebundenes Lernen; API-Tests.
- [x] Gruppen: Listen, Änderungen und alle Zuordnungen im Bereich; API-Tests.
- [x] Dashboard und Exporte: Bereich in allen Summen und Filtern; API-Tests einschließlich XLSX-Inhalt.
- [x] Belege und Fotoaufträge: Bereich bei Upload, Dubletten, Downloads und Verknüpfungen; API-Tests.
- [x] Bank- und Excel-Import: Konten, Umsätze, Regeln und Sammelübernahme prüfen; API-Tests.
- [x] Schnellerfassung und Fotoverarbeitung: gefilterte Namen/Regeln, Belegbereich weiterreichen; Tests.
- [x] Frontend zentral um `bereich_id=1` ergänzen; Endpunktinventar auf Lücken prüfen.
- [x] Gesamtsuite mit FINANZ_DB außerhalb Repo, doppelter Nachzug auf Bestandskopie, vollständiger Bericht `P10-runde1.md`.

Tests verwenden `tempfile.TemporaryDirectory()`. Auth und bestehende Validierungen bleiben verbindlich; keine neuen Abhängigkeiten, keine Konten-/Bewegungsänderungen.
