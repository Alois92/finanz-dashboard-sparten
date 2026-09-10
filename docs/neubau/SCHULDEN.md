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
| **A2neu** (Skript P61 fertig und gemergt; Lauf auf Prod-Kopie steht aus, Kopie liegt auf pve unter /tmp) | **Die Migrationsprobe auf einer Kopie der Produktionsdatenbank ist nur für 001–004 gefahren.** Für 005–009 (P12–P16) steht sie aus, entgegen der eigenen Prozessregel 1. Das ist die eigentliche Abnahme von M1. | **vor P20** |

### Wichtig, nicht sperrend

| Nr. | Befund | Fällig |
|---|---|---|
| N10 | Prozessregel 1 (Migrationsprobe in der Abnahme) wurde bei P12, P14, P15 und P16 nicht angewendet. | Prozess |

### Erledigt

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
