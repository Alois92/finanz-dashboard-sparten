# Schuldenliste Neubau

Offene Punkte aus Abnahmen und aus dem unabhängigen Prüfbericht (Fable, 9. September 2026).
**Vor dem Produktivwechsel (M6) muss diese Liste leer sein.**

## Sperrend für den Produktivwechsel

| Nr. | Befund | Fällig in |
|---|---|---|
| **A1** | **Die Sicherung vor dem Schema-Nachzug ist nur die Tageskopie.** `backup.sichere_datenbank()` legt pro Tag höchstens eine Kopie an; existiert sie, wird nichts kopiert. Wird abends deployt, stammt die „Sicherung vor Nachzug" vom Morgen — alles, was tagsüber gebucht wurde, fehlt im Rückweg. `tests/test_migrate.py` schreibt dieses Verhalten sogar fest. Fehler der Karte P00, nicht von Codex. Erwartung: eigener Dateiname `finanz-JJJJ-MM-TT-vor-nachzug-<version>.db`, immer frisch, nie übersprungen, nicht rotiert, im Manifest vermerkt. | **sofort** (Kopf, nicht Codex) |
| **A2** | **Migration 003 ist auf echten Daten ungeprobt und kann ZINA still in den Hauptbereich legen.** Objekte ohne `sparte_id` (Belege dürfen das, Bankkonten auch) bleiben in Bereich 1. Eine ZINA-Buchung, die so ein Objekt referenziert, ist danach nicht mehr bearbeitbar (404 aus `pruefe_beleg`). Hat die echte ZINA-Sparte nicht `typ='verein'`, bleibt ZINA komplett im Hauptbereich — die zentrale Anforderung wäre still verfehlt. Erwartung: Zählungen ins Log, lauter Abbruch bei Bereich-2-Objekt mit Bereich-1-Referenz, und Probe auf einer Kopie der Produktionsdatenbank mit Summenvergleich je Sparte und Jahr. | **vor M6, Probe sofort** |
| **B4** | **`auto_verbuchen` darf für Bestandsregeln nicht auf 1 stehen.** P15 setzt gelernte Regeln auf automatisches Verbuchen. Gelernte Regeln entstehen aus jeder Buchung mit Text ab drei Zeichen, Treffer ist Teilzeichenkette. Der erste George-Jahresimport nach dem Umzug erzeugte damit massenhaft automatische, teils falsche Buchungen. Erwartung: Migrations-Vorgabe `auto_verbuchen = 0`, Freigabe je Regel durch den Nutzer. | **in der Abnahme P15** |
| **A6/§10** | Migrationsfehler und Sicherungsstatus sind in keiner Oberfläche sichtbar. Startet die App schreibgeschützt, sieht der Nutzer nur „Speichern geht nicht". | **P30** |
| — | **Rückweg dokumentiert und einmal geprobt:** neue Datenbankversion zurück auf die alte App, samt Belegen. | **P62** |

## Wichtig, nicht sperrend

| Nr. | Befund | Fällig in |
|---|---|---|
| A3 | Zwei Runner-Semantiken in `app/migrate.py`: SQL-Migrationen laufen mit Fremdschlüsselprüfung und sauberem Anweisungs-Splitting, Python-Migrationen bekommen nichts davon. Migration 004 (P11) bettet SQL in Python ein und splittet mit `SQL.split(';')` — genau die Schwäche, die für SQL-Dateien schon behoben ist. | P20 |
| A4 | `app/db.py` enthält weiterhin Ad-hoc-Schemanachrüstungen außerhalb des Versionsmechanismus (Sparten-Farben, `beleg_auswertung`). Karte P00 hatte versprochen, dass sie in Migrationen wandern. | P20 |
| A5 | `app/backup.py` kopiert jeden Tag alle Belege vollständig, ohne Deduplizierung über Tage, und schiebt alle sechs Stunden den ganzen Belegordner übers Netz aufs Zweitziel — alles unter dem Sicherungs-Lock, das währenddessen Löschungen und den Start blockiert. Betriebsproblem, das erst mit echten Mengen auffällt. | vor M6 |
| A6 | Fehlgeschlagene Beleg- oder Zweitziel-Sicherung wird nur geloggt; `sichere_datenbank()` meldet trotzdem Erfolg. Am Zweitziel wird nur Existenz geprüft, keine Prüfsummen. | vor M6 |
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
| **N1** | **Kennzahlen vervielfachen Beträge.** `app/kennzahlen.py:6-13` verbindet Buchungszeilen über `kennzahl_term.kategorie_id`, ohne auf den einzelnen Term einzuschränken. Kommt dieselbe Kategorie in zwei Termen derselben Kennzahl vor (etwa „Einnahmen Milch" +1 und „netto Milch" −1), liefert die Abfrage jede Zeile doppelt — und das zweimal, also Faktor vier. Weder Migration 008 noch `_pruefe_terme` verhindern die Doppelnennung. | **vor P20** |
| **N2** | **Kreditraten zuordnen löscht fremde Buchungszeilen.** `app/routers/kredite.py:326-341` löscht alle Zeilen der Buchung und schreibt zwei neue. Eine Buchung „Kreditrate 500 + Kontoführung 5" verliert die Kontoführung, und die gesamte Buchung wird neutral — 505 € verschwinden aus jeder Ausgabenauswertung, ohne Hinweis. | **vor P20** |
| **A2neu** | **Die Migrationsprobe auf einer Kopie der Produktionsdatenbank ist nur für 001–004 gefahren.** Für 005–009 (P12–P16) steht sie aus, entgegen der eigenen Prozessregel 1. Das ist die eigentliche Abnahme von M1. | **vor P20** |

### Wichtig, nicht sperrend

| Nr. | Befund | Fällig |
|---|---|---|
| N3 | Kreditraten werden über den Freitext `buchung.notiz = 'Kreditrate:<id>'` erkannt. Bearbeitet der Nutzer die Notiz, fällt die Rate still aus der Zinsverteilung. Eigene Spalte statt Marker. | vor M6, spätestens P50 |
| N4 | **Kontostand zählt doppelt**, solange eine manuell erfasste Bankbuchung und der später importierte Umsatz nicht einander zugeordnet sind (`app/bewegungen.py:97-108` gegen `import_bank.py:275`). Die Karte P42 braucht deshalb einen **Backend**-Anteil (Kandidatensuche über Betrag und Datum, Zuordnungs-Endpunkt), nicht nur Frontend. | vor P42 |
| N5 | Der Import-Anker nimmt bei absteigend sortierten CSVs die falsche Zeile (`import_bank.py:280-286`); `INSERT OR IGNORE` verhindert die spätere Korrektur. Heute latent, weil die George-Fixture keine Saldospalte hat. Test mit absteigender CSV plus Saldo fehlt. | vor M6 |
| N6 | Migration 004 protokolliert ungeklärte Fälle (Umbuchungen ohne eindeutige Konten, Bankbuchungen ohne Umsatz) nur ins Log. Nach dem Deploy gibt es keine Liste. Ergebnis persistieren. | vor M6 |
| N8 | Die Kassazählung legt beim ersten Buchen je Sparte eine Kategorie „Kassadifferenz" an, die dann gar nicht verwendet wird (`routers/konten.py:264-269`). | klein |
| N9 | Migration 008 etikettiert **alle** Bestandsregeln als „gelernt", auch die Stichwortregeln der alten App. Eine spätere Freigabe-Oberfläche zeigt sie damit falsch. | vor M4 |
| N10 | Prozessregel 1 (Migrationsprobe in der Abnahme) wurde bei P12, P14, P15 und P16 nicht angewendet. | Prozess |

### Erledigt

- **B4** (`auto_verbuchen` für Bestandsregeln) — behoben in Migration 008, Vorgabe und Nachzug stehen auf 0.
- **B6, Teil `client_request_id`** — hat `bereich_id` seit Migration 005.
- **B6, Teil Währung** — jede Bewegung erbt die Währung ihres Kontos; die Summe über Konten muss P20 je Währung bilden.

### Verschärft

- **B2 (drei Wahrheiten für „Verein")**: `app/auslagen.py:67-71` nutzt zusätzlich `sparte.typ='privat'` als Regel. **Vor P20 entscheiden: `bereich_id` ist maßgeblich**, sonst entsteht eine vierte Stelle.
- **B3 (Umbuchungen doppelt)**: `create_umbuchung` schreibt jetzt Buchungspaar **und** Transfer samt Bewegungen. Festlegung für P20: Summen aus `v_einnahmen_ausgaben`, Kontostände aus `bewegung`.
