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
