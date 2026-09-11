# Schuldenliste Neubau

Offene Punkte aus Abnahmen und aus dem unabhängigen Prüfbericht (Fable, 9. September 2026).
**Vor dem Produktivwechsel (M6) muss diese Liste leer sein.**

## Sperrend für den Produktivwechsel

| Nr. | Befund | Fällig in |
|---|---|---|
| **A2** | **Migration 003 ist auf echten Daten ungeprobt und kann ZINA still in den Hauptbereich legen.** Objekte ohne `sparte_id` (Belege dürfen das, Bankkonten auch) bleiben in Bereich 1. Eine ZINA-Buchung, die so ein Objekt referenziert, ist danach nicht mehr bearbeitbar (404 aus `pruefe_beleg`). Hat die echte ZINA-Sparte nicht `typ='verein'`, bleibt ZINA komplett im Hauptbereich — die zentrale Anforderung wäre still verfehlt. Erwartung: Zählungen ins Log, lauter Abbruch bei Bereich-2-Objekt mit Bereich-1-Referenz, und Probe auf einer Kopie der Produktionsdatenbank mit Summenvergleich je Sparte und Jahr. | **vor M6, Probe sofort** |
| **B4** | **`auto_verbuchen` darf für Bestandsregeln nicht auf 1 stehen.** P15 setzt gelernte Regeln auf automatisches Verbuchen. Gelernte Regeln entstehen aus jeder Buchung mit Text ab drei Zeichen, Treffer ist Teilzeichenkette. Der erste George-Jahresimport nach dem Umzug erzeugte damit massenhaft automatische, teils falsche Buchungen. Erwartung: Migrations-Vorgabe `auto_verbuchen = 0`, Freigabe je Regel durch den Nutzer. | **in der Abnahme P15** |
| **A6/§10** | Migrationsfehler und Sicherungsstatus sind in keiner Oberfläche sichtbar. Startet die App schreibgeschützt, sieht der Nutzer nur „Speichern geht nicht". | **P30** |
| — | **Rückweg dokumentiert und einmal geprobt:** neue Datenbankversion zurück auf die alte App, samt Belegen. | **P62** |

## Wichtig, nicht sperrend

| Nr. | Befund | Fällig in |
|---|---|---|
| A3 | Zwei Runner-Semantiken in `app/migrate.py`: SQL-Migrationen laufen mit Fremdschlüsselprüfung und sauberem Anweisungs-Splitting, Python-Migrationen bekommen nichts davon. Migration 004 (P11) bettet SQL in Python ein und splittet mit `SQL.split(';')` — genau die Schwäche, die für SQL-Dateien schon behoben ist. | P20 |
| B2 | Drei Wahrheiten für „Verein": `sparte.typ`, `sparte.geschuetzt`, `sparte.bereich_id`. Die Architektur legt nicht fest, dass `bereich_id` maßgeblich ist. | P20 |
| B3 | Umbuchungen existieren doppelt: altes Buchungspaar mit `transfer_gruppe_id` und neues `transfer` + `bewegung`. Quelle der Wahrheit ist nicht festgelegt. | P20 |
| B6 | `bewegung.waehrung` ohne Umrechnung (Kontostand summiert blind über Währungen), `client_request_id` ohne Bereichs- oder Zeitbezug, `hinweis_aus` ohne Bereich. | vor M6 |

## Prozessregeln, ab sofort

1. Jede Migration wird **in der Abnahme** auf einer Kopie der Produktionsdatenbank gefahren, mit
   Summenvergleich vorher/nachher. Kein „bestanden" ohne diesen Lauf.
2. Ein Bericht ohne alle Kästchen aus „Fertig heißt" geht ungelesen zurück.
3. Der Kopf prüft nicht nur, ob Codex die Karte erfüllt, sondern ob die **Karte richtig ist** —
   bei Sicherung und Migration am Ernstfall durchgespielt („Tag X, 18 Uhr, Deploy: welche Datei
   ist die Sicherung?").
4. Frontend-Karten erst schreiben und bauen, wenn der zugehörige Endpunkt gemergt ist und die
   Karte das echte Antwort-JSON enthält.
5. Akzeptierte Abweichungen kommen in diese Liste, nicht nur ins Protokoll.

---

## Ergänzungen aus der zweiten Kontrolle (Fable, 10. September 2026)

### Sperrend vor dem Produktivwechsel

| Nr. | Befund | Fällig |
|---|---|---|
| — | Derzeit keine sperrende Schuld offen. A2neu am 10.09. abends erledigt, siehe unten. | — |

### Wichtig, nicht sperrend

| Nr. | Befund | Fällig |
|---|---|---|
| N10 | Prozessregel 1 (Migrationsprobe in der Abnahme) wurde bei P12, P14, P15 und P16 nicht angewendet. | Prozess |

### Erledigt

- **A2neu** — Migrationsprobe 001–015 auf der echten Produktionskopie vom 10.09. bestanden: Summen je Sparte unverändert, Integrität ok, zweiter Lauf leer (Abnahme A2neu-migrationsprobe.md). Zwei Befunde dem Nutzer genannt: Migration 003 entfernte eine fremde Sparte aus einer Auswertungsgruppe; vier Bank-/Kartenbuchungen ohne Umsatz stehen im Migrationsprotokoll.
- **P30b** — Gerüst-Lücken geschlossen: `state.filter` mit `setFilter()`, Jahr/Sparte/Kategorie rendern zentral neu, `wizard()` in `ui.js`, Kassa-Zählung darauf umgestellt (gemergt 10.09., Abnahme P30b.md). P32/P33 freigegeben.
- **B7** — `_update_buchung` erhält `kontakt_id`/`person_id` über `model_fields_set` wie `bankkonto_id`; drei Tests (gemergt 10.09., Abnahme B7.md).
- **A5** — Belege inhaltsadressiert im Store, Zweitziel inkrementell mit Prüfsumme, Übertragung außerhalb des Locks (gemergt 10.09., Abnahme A5-A6.md).
- **A6** — `sichere_datenbank()` liefert Ergebnisobjekt, Betriebsstatus zeigt es, nur voll erfolgreicher Lauf gilt als gesichert (gemergt 10.09.).
- **N3** — Kreditraten über `buchung.kredit_id`, Migration 015, Altmarker nachgezogen (gemergt 10.09., Abnahme N3.md).
- **N4** — Backend-Abgleich: Kandidaten, Zuordnen, Lösen, offene Abgleiche; Kontostand zählt nach Zuordnung einfach (gemergt 10.09., Abnahme N4.md). Frontend-Teil in P42.
- **B2** — entschieden in P20: Verein-Ausschluss ausschließlich über `sparte.bereich_id`; `typ` und `geschuetzt` sind informativ (gemergt 10.09.).
- **B3** — entschieden in P20: Summen aus `v_einnahmen_ausgaben`, Kontostände aus `bewegung` (gemergt 10.09.).
- **A1** — eigene frische Sicherung `…-vor-nachzug-<version>.db` vor jedem Nachzug (Zweig fix/a1, gemergt 10.09.).
- **A4** — Ad-hoc-Schema aus `db.py` in Migration 011 überführt (gemergt 10.09.).
- **N1** — Kennzahlen zählen je Term genau einmal, Eindeutigkeit per Migration 013 (gemergt 10.09.).
- **N2** — Kreditraten-Zuordnung erhält fremde Buchungszeilen (gemergt 10.09.).
- **N5** — Import-Anker erkennt Sortierrichtung, Upsert statt `INSERT OR IGNORE`, Test mit absteigender CSV plus Saldo (gemergt 10.09.).
- **N6** — ungeklärte Fälle der Bestandsübernahme dauerhaft in Migrationsprotokoll, Migration 012 (gemergt 10.09.).
- **N8** — keine unbestellte Kategorie „Kassadifferenz" mehr (gemergt 10.09.).
- **N9** — Bestandsregeln tragen ihre echte Herkunft, Migration 010 (gemergt 10.09.).

- **B4** (`auto_verbuchen` für Bestandsregeln) — behoben in Migration 008, Vorgabe und Nachzug stehen auf 0.
- **B6, Teil `client_request_id`** — hat `bereich_id` seit Migration 005.
- **B6, Teil Währung** — jede Bewegung erbt die Währung ihres Kontos; die Summe über Konten muss P20 je Währung bilden.

### Verschärft

- **B2 (drei Wahrheiten für „Verein")**: `app/auslagen.py:67-71` nutzt zusätzlich `sparte.typ='privat'` als Regel. **Vor P20 entscheiden: `bereich_id` ist maßgeblich**, sonst entsteht eine vierte Stelle.
- **B3 (Umbuchungen doppelt)**: `create_umbuchung` schreibt jetzt Buchungspaar **und** Transfer samt Bewegungen. Festlegung für P20: Summen aus `v_einnahmen_ausgaben`, Kontostände aus `bewegung`.

---

## Ergänzungen aus den Frontend-Abnahmen (Fable, 10. September 2026, abends)

Gemergt: P31, P40, P41, P42, P50, P60 (Umsetzung durch Claude Sonnet, Codex war gesperrt). Protokolle in `abnahme/`.

| Nr. | Befund | Fällig |
|---|---|---|
| **B7** | `_update_buchung` in `app/routers/buchungen.py` setzt `kontakt_id`/`person_id` bei PUT ohne diese Felder auf NULL (kein `model_fields_set`-Schutz wie bei `bankkonto_id`). Belegt durch P50-Team. Der Bearbeiten-Dialog lässt die Felder deshalb vorerst unangetastet. | **vor P50b** |
| ~~P50b~~ | erledigt 11.09. (Migration 016, Abnahme P51.md). | — |
| ~~P31b~~ | erledigt 11.09. (Abnahme P60b-P31b-P32b.md): Hinweise liefern Euro-Text und `wert_cent`. | — |
| P40b | `POST /api/parse` liefert nur einen Kategorietreffer ohne Herkunft; Karte P40 wollte bis zu drei mit Regel-Herkunft. | M4 |
| P42b | `GET /api/bankumsaetze` liefert für verbuchte Umsätze weder Buchungstyp noch Regel-Herkunft. | M4 |
| ~~P60b~~ | erledigt 11.09. (Abnahme P60b-P31b-P32b.md): `jahr` nur ohne Profil Pflicht, Ausschluss-Dialog per Cursor. | — |
| — | Handy-Ansicht von Übersicht, Konten, Bankimport, Export im Browser noch nicht geprüft (nur Erfassen und Buchungsliste). | vor CT 102 |

---

## Ergänzungen aus den Abnahmen vom 11. September 2026 (Fable, nachts)

Gemergt: **P32 Sparte, P33 Kategorien, P43 Foto-Übernahme, P52 Kredit** (Umsetzung Claude Sonnet, Abnahme mit
gebündelter Browserprüfung auf einer Testinstanz aus `neubau`). Protokolle `abnahme/P32.md`, `P33.md`, `P43.md`, `P52.md`.
B7 aus der Tabelle oben ist erledigt (siehe „Erledigt“). M3 ist damit vollständig, M4 vollständig, M5 fehlt P51/P50b, M6 fehlt P62.

Vom Kopf während der Abnahmen behoben (kein Eintrag nötig): `GET /api/kennzahlen` war seit P15 defekt (ambiguous
column), Kategoriefilter-Cache nach Umbenennung, Kreditliste ohne Kategorie-IDs, Übernahme ohne gemeinsame
Transaktion, Sparten-Kachel ohne Kopf-/Sidebar-Render, Belege-Hinweis „nicht erreichbar“ bei fehlendem Modell,
Prüf-Dialog ohne Vorbelegung, Qwen-3-Denkmodus (`think: false`).

| Nr. | Befund | Fällig |
|---|---|---|
| ~~P43b~~ | erledigt 11.09. (Migration 016, eigener Wert `beleg_uebernahme`, Abnahme P51.md). | — |
| P43c | **Entschieden 11.09.: `qwen3.5:4b`** (6 von 7 Testbildern richtig, Vergleich in `outputs/modelltest/ERGEBNIS.md`). Quer liegende Bilder dreht die App jetzt vor dem Aufruf (`FINANZ_BILD_QUER_DREHEN`). Offen: Modell in CT 101 laden, Drop-In setzen, CPU-Laufzeit messen; Schritt im Umstellungsablauf (Betriebsdoku 11.4). | bei der Umstellung |
| ~~P32b~~ | erledigt 11.09. (Abnahme P60b-P31b-P32b.md): Gruppen-Hash gewinnt, Kopf-Wahl verlässt die Gruppe. | — |
| P52b | Bei „Alle Sparten“ listet die Kreditseite alle Kredite des Bereichs; kein Beleg-Upload im Dialog „Jahr bestätigen“, nur Verknüpfung vorhandener Belege. | klein |
| — | Handy-Ansicht: Kredit bei 375 px geprüft; Sparte, Kategorien, Belege nur durch die Agenten (Viewport-Emulation des Werkzeugs sprang). | vor CT 102 |

---

## Ergänzungen vom 11. September 2026, nachmittags (Fable)

Gemergt: **P50b + P51** (Migrationen 016/017, Abnahme `P51.md`, Migrationsprobe auf der Prod-Kopie bestanden),
**P62** (Umstellungsablauf, Prüfskript, `FINANZ_FRONTEND`, Abnahme `P62.md`), Test-Nachzug `F-tests-017`.
**Alle 26 Pakete sind gebaut.** Offen sind nur noch die Ausführung der Umstellung nach Betriebsdoku Abschnitt 11
und der Modellwechsel P43c.

**Vorgabe des Nutzers (11.09.):** Vor der Umstellung prüft ein Testagent die gesamte App auf der Testinstanz
**so unabhängig und vollständig wie möglich** („jeden Hebel, jeden Drücker, jede Einstellung“, Belege inklusive),
kein Nutzertest. Zuschnitt: vier Tester mit je eigener Instanz auf der migrierten Prod-Kopie, Berichte
`berichte/QA-1…4-*.md`, Befunde danach vom Kopf behoben. Erster Anlauf abgebrochen, wird neu gestartet.

| Nr. | Befund | Fällig |
|---|---|---|
| ~~P51b~~ | erledigt 11.09. nachmittags (Kopf): Storno-Bestätigung und Grund im App-Dialog `#drill` (`static-neu/pages/buchungen.js`), Enter löst aus, Knopf während des Aufrufs gesperrt. Browserprüfung im QA-Durchlauf (QA-2). | — |
| ~~P51c~~ | erledigt 11.09. nachmittags (Kopf): 422-Text nennt den Kategorienamen. | — |
| ~~P61b~~ | erledigt 11.09. nachmittags (Kopf): `summen_neu` und `kostenstorno_spalten` prüfen nur noch `buchungszeile`. Suite 454 grün. | — |
| — | Testsuite: zweiter Lauf auf derselben `FINANZ_DB`-Datei verfälscht `test_auto_kategorien`; Wegwerfdatei immer vorher löschen (Kopf-Läufe tun das). | Prozess |

---

## QA-Durchlauf und Nachträge vom 11. September 2026, abends (Fable)

**QA-Durchlauf abgeschlossen:** vier Sonnet-Tester auf eigenen Instanzen (Prod-Kopie Schema 17), rund 200 Prüfpunkte,
Berichte `berichte/QA-1…4-*.md`, 27 Befunde plus QA4-08. Behoben durch zwei Sonnet-Fixer (`berichte/QA-fix-A.md`,
`QA-fix-B.md`, je ein Commit je Befund, gemergt `06c362f`/`f0aa80a`): kritisch QA2-02 (Betrag „12.50“ → 1250) und
QA1-02 (Drilldown-Saldo 0), hoch QA2-04 (Client-Request-Id je Klick) und QA3-02 (Bankimport riet die Sparte), mittel
QA1-01/03, QA2-01, QA3-03/04, QA4-05 (fehlendes Commit im Wiederholungs-Topf), niedrig QA1-04/05/06, QA2-05/06/07,
QA3-01/05/06/07. Foto-Auswertung sendet jetzt `temperature 0` (`FINANZ_OLLAMA_TEMPERATUR`). Login-Fluss ohne Bypass
live bestätigt (QA-4 Nachtrag). Gesamtsuite danach **561 Tests grün**.

**Neue Pakete (Nutzerwunsch 11.09.):** **P70** KI-Kategorievorschlag als Rückfallebene (Abnahme `P70.md`, Merge
`346d633`), **P71** Rechnungen als Text-PDF (`pypdf==6.18.1`, Abnahme `P71.md`, Merge `f830696`). Kern von P40b
damit erledigt (`/api/parse` liefert `quelle`/`regel_name`).

| Nr. | Befund | Fällig |
|---|---|---|
| QA2-03 | Erfassen zeigt weiterhin nur einen Kategorietreffer (P40 wollte bis zu drei mit Pfeiltasten); Herkunft ist jetzt im `quelle`-Feld vorhanden, Anzeige fehlt. | klein |
| QA2-05b | Betrags-Obergrenze nur bei `ZeileIn.betrag_cent`; `UmbuchungIn`, `ErstattenZeileIn`, Auslagen/Konten/Kredite/Beleg-Übernahme ohne Limit. | klein |
| QA4-06 | Kein manueller Sicherungs-Auslöser und keine Betriebsseite im neuen Frontend; Entscheidung des Nutzers, ob gewünscht. | Entscheidung |
| ~~QA4-08~~ | erledigt: Betriebsdoku nennt Neustartpflicht nach Änderung der Auth-Datei. | — |
| P43c | Modellwechsel in CT 101 auf `qwen3.5:4b` und CPU-Laufzeit messen — Teil der Umstellung (Abschnitt 11). | Umstellung |
| — | Handy-Ansicht 375 px: alle vier Tester meldeten eine springende Viewport-Emulation des Werkzeugs; nur Kredit, Belege, Export verlässlich geprüft. | vor CT 102 |
| — | P70: Laufzeit des Textaufrufs auf der CPU von CT 101 offen (GPU: 2–3 s). | Umstellung |
