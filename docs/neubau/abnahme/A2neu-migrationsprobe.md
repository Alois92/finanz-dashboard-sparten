# Abnahme A2neu — Migrationsprobe auf der Produktionskopie

Datum: 10. September 2026, 23:09. Abnehmer: Fable (Kopf). Lauf durch den Nutzer im Terminal
(Sicherheitsprüfung der Claude-App blockierte den Zugriff auf die Datenbankkopie), Auswertung durch den Kopf.
Skript: `scripts.migrationsprobe` (P61). Vollständiger Bericht (mit Summen) außerhalb des Repos:
`Z:\…\Finanz Dashboard Lois\outputs\datenrettung\A2neu-migrationsprobe-bericht-2026-09-10.json`.

## Ergebnis: bestanden. Alle 15 Migrationen laufen auf der echten Datenbank sauber durch, Summen unverändert.

## Quelle

| | |
|---|---|
| Herkunft | CT 101, per `pct pull` auf `pve:/tmp/finanz-prod-kopie.db` (Task „CT 101 - Pull file“ 10.09. 20:57), über kurzzeitigen `http.server` auf den PC geholt |
| Ablage | `outputs/datenrettung/finanz-prod-kopie-2026-09-10.db` (Z:) und lokale Arbeitskopie `C:\Users\lblet\dev\` |
| Größe | 176.128 Bytes, SHA256 `b02a8ee1…fa79d9`, vorher und nachher identisch (Quelle unverändert) |
| Stand vorher | `schema_version` fehlt (aktuell 0, `basis: false`), 25 Buchungen, 34 Buchungszeilen, nur Jahr 2026 |

## Prüfungen

| Prüfung | Ergebnis |
|---|---|
| Angewendete Migrationen | 1–15 vollständig, zweiter Lauf leer (idempotent) |
| Summen je Sparte und Jahr vorher/nachher | gleich, Abweichungen leer (fünf Sparten mit Werten, 2026) |
| Anzahl Buchungen / Zeilen | 25 / 34 vorher und nachher |
| Bereichszuordnung | korrekt: Sparte 4 (ZINA) → Bereich 2, alle anderen Bereich 1 |
| `foreign_key_check` | leer |
| `integrity_check` | ok |
| Ungeklärte Transfers | 0 |
| Ungeklärte Barbuchungen | 0 |
| Kostenstorno-Spalten (Altbestand) | nicht vorhanden, wie erwartet |
| Sicherung vor Nachzug | `sicherung.db` im Arbeitsordner angelegt (A1) |

## Befunde, dem Nutzer zu nennen

1. **Migration 003 hat eine fremde Zuordnung still entfernt** („Entfernte fremde Zuordnungen
   auswertungsgruppe_sparte: 1“). Eine Auswertungsgruppe enthielt eine Sparte des anderen Bereichs
   (mutmaßlich ZINA in einer Privat-Gruppe). Nach dem Produktivwechsel fehlt diese Sparte in der Gruppe.
   Das ist der Kern von Schuld A2 (stille Bereinigung statt lautem Abbruch). Bei 25 Buchungen ist der
   Effekt überschaubar; der Nutzer entscheidet, ob die Gruppe nach dem Wechsel manuell angepasst wird.
2. **Vier Buchungen „Zahlung unbekannt“** (IDs 2, 4, 17, 24: Bank- oder Kartenbuchung ohne zugehörigen
   Bankumsatz). Migration 004 hat sie nicht in Kontobewegungen übersetzt, Migration 012 hat sie dauerhaft
   ins Migrationsprotokoll geschrieben (N6). Sie zählen in den Sparten-Summen weiter, fehlen aber in den
   Kontoständen, bis sie im Bankimport (P42) einem Umsatz zugeordnet oder auf Bar umgestellt werden.
   Nach dem Produktivwechsel als erste Aufgabe des Nutzers in der App sichtbar machen (Betriebsstatus).

## Nicht geprüft

- Die Probe lief auf dem Stand `neubau` **vor** dem Merge von B7 und P30b (beide ohne Migration, also ohne Einfluss).
- Der Datenbestand ist klein (25 Buchungen, ein Jahr). Pfade wie Kreditraten, Auslagen-Ausgleich und
  Umbuchungen hatten in der echten Datenbank keine oder kaum Daten; sie sind nur durch die Testsuite gedeckt.

## Folge

Schuld A2neu ist erledigt. Prozessregel 1 gilt weiter: vor jeder weiteren Migration (ab 016) erneut
`scripts.migrationsprobe` auf einer frischen Produktionskopie fahren.
