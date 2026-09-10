# P20 – gemeinsame Rechenbasis und Auswertungen

Arbeitsverzeichnis: `C:\Users\lblet\dev\wt-p20`, Branch `pkt/p20-rechenbasis`.
Grundlage ist die vollständig gelesene P20-Karte einschließlich des vorrangigen
Nachtrags 10. Migration **014** entspricht der ausdrücklichen Auftragskorrektur.
Keine Commits, kein Push, keine neuen Abhängigkeiten und kein Frontend-Umbau.

## Umsetzung

Die neue Rechenbasis verwendet `v_einnahmen_ausgaben` für Einnahmen/Ausgaben
und die vorhandene P13-Berechnung aus `bewegung` für Kontostände. Die Bereichsgrenze
verläuft ausschließlich über `sparte.bereich_id`; `typ` und `geschuetzt` spielen
bei den Auswertungen keine Rolle. Gruppenmitgliedschaften werden über Mengen bzw.
Unterabfragen ausgewertet. Richtung bedeutet Buchungstyp, unabhängig von der
Kategorierichtung.

Ist endet am Stichtag. Erwartung addiert ausschließlich den Rest des Vorjahres
nach dem entsprechenden Stichtag; der 29. Februar wird auf den 28. Februar
abgebildet. Zukünftige Buchungen werden nicht zusätzlich eingerechnet.
Matrixzeilen behalten getrennte Einnahmen und Ausgaben, inaktive Kategorien
und Kategorien mit ausschließlich Vorjahresdaten. Ohne Vorjahresdaten ist
die Erwartung gleich Ist und `ohne_vorjahr` gesetzt.

Die Buchungsliste liefert Seiten mit Gesamtsummen über alle Treffer. Die Cursor
beider Listen sind Base64 von `datum|id`, absteigend nach Datum und ID.
Ein Buchungsfeld `storniert_am` wurde weder eingeführt noch getestet.

## Endpunkte und Bereichsprüfung

| Endpunkt | Änderung und Bereichsprüfung |
|---|---|
| `GET /api/uebersicht` | Neu; `filter_dep` → `bereich_dep`, Zugehörigkeitsprüfungen für Sparte, Kategorie und beide Gruppenarten; Bereichsprädikate für Buchungen, Konten, Auslagen und Imports. |
| `GET /api/jahresmatrix` | Neu; dieselbe Filterdependency und Zugehörigkeitsprüfungen; alle Jahresabfragen behalten den Bereichsfilter. |
| `GET /api/hinweise/aus` | Neu; `BereichDep` → `bereich_dep`, SQL ausschließlich für diesen Bereich. |
| `POST /api/hinweise/aus` | Neu; `BereichDep` → `bereich_dep`, Upsert auf `UNIQUE(bereich_id, schluessel)`. |
| `GET /api/buchungen` | Erweiterter Seitenvertrag; `filter_dep` → `bereich_dep`, gleiche fachliche Filter und Zugehörigkeitsprüfungen. |
| `GET /api/buchungen/suche` | Kompatibler Listenadapter über dieselbe Berechnung; `BereichDep` und `filter_dep` mit Bereichsprüfung. |
| `GET /api/konten/{konto_id}/bewegungen` | Vereinheitlichter Cursor; vorhandene `BereichDep` und `pruefe_konto` bleiben erhalten. |
| `GET /api/dashboard`, `/api/jahresvergleich`, `/api/verlauf` | Bisherige Antwortformate bleiben bestehen; gemeinsame Filterbasis, vorhandene Bereichsdependency. |

Auth, Validierung und öffentliche beziehungsweise betriebliche Ausnahmen wurden
nicht abgeschwächt. An `/api/auth/*`, `/api/health`, `/api/schema` und
`/api/betrieb/status` wurde keine Bereichsdependency ergänzt.

## Annahmen und Festlegungen

1. Die ausdrücklich geforderte Kompatibilität von `/buchungen/suche` hat Vorrang
   vor einer Umstellung dieser alten Route auf das neue Seitenobjekt: sie liefert
   weiterhin maximal 200 Treffer als Liste und ohne expliziten Stichtag auch
   zukünftige Buchungen. `/buchungen` liefert standardmäßig 100 Treffer und erlaubt
   bis zu 1.000 pro Seite; Gesamtsummen beziehen sich immer auf alle Treffer.
2. Übersicht und neue Buchungsliste verwenden ohne Zeitfilter das Stichtagsjahr.
   Ein Monatsfilter bestimmt sein Jahr. Freie `von`/`bis`-Intervalle werden nicht
   zusätzlich auf das aktuelle Jahr eingeschränkt; ohne ausgewähltes Einzeljahr
   gibt es keine Jahreserwartung. Alte Auswertungsrouten behalten ihre bisherigen
   expliziten Datumsgrenzen und uneingeschränkten Standardzeitraum.
3. Umbuchungen und neutrale Zeilen bleiben zur Nachvollziehbarkeit in der
   Buchungsliste sichtbar, tragen aber nichts zu deren Einnahmen/Ausgabensummen
   bei. Die Liste enthält die vollständigen Splitzeilen; `filter_betrag_cent`
   zeigt bei Kategorie-/Globalgruppenfiltern nur den passenden nichtneutralen
   Kostenanteil.
4. `top` enthält maximal fünf Kategorien je Richtung. `anteil` ist ein Bruchteil
   zwischen 0 und 1. Monatsdurchschnitte der Matrix werden je Jahr und Richtung
   in ganzen Cent abgerundet: abgeschlossenes Jahr durch zwölf, Stichtagsjahr
   durch die Zahl der begonnenen Monate.
5. Konten werden nach Bereich und gegebenenfalls Spartenumfang ausgewählt,
   nicht nach Kategorie oder Kostenrichtung. `konten_je_waehrung` ist eine
   zusätzliche Antwortstruktur. Sobald ein Konto einer Währung keinen Anker hat,
   ist deren Gesamtstand unbekannt (`null`); `unbekannte_konten` erklärt dies.
   Es wird keine währungsübergreifende Summe gebildet.
6. Hinweiswerte werden als Text geliefert und im Schlüssel kodiert. Kostenanstieg
   wird in Fünf-Prozent-Schritten gerundet, Kategorieanteil in ganzen Prozent.
   Ein fehlendes `bis_wert` übernimmt den Wert aus dem Schlüssel. Ein geänderter
   Wert erzeugt einen wieder sichtbaren Hinweis. Ignorierte Bankumsätze zählen
   nicht als offen; der Bankhinweis bezieht sich auf den ausgewählten Kontenumfang
   bis zum Stichtag, da unzugeordnete Umsätze noch keine Kostenkategorie haben.
7. Eigene Kennzahlwerte werden nicht zusätzlich in die Spartenkacheln aufgenommen
   (laut Karte optional). Die bestehende Kennzahlberechnung und Monatszählung
   rechnen jedoch jeweils in einer SQL-Aggregation mit dem gemeinsamen Filter.
8. Erlaubte Jahre beginnen bei 2, weil der Jahresvergleich ein darstellbares
   Vorjahr benötigt. Jahreslisten sind auf 100 unterschiedliche Jahre begrenzt.

## Regression, Migration und Review

Die Snapshot-Datei wurde aus echten ASGI-Antworten mit echtem Schema und Seed
aufgezeichnet und erfolgreich geprüft, **bevor** Produktionslogik geändert wurde.
Sie enthält Dashboard, Jahresvergleich, Verlauf, Suche sowie Bereichs- und
Zeitraumvarianten. Die JSON-Erwartungen wurden beim Umbau nicht angepasst.

Jede der acht Zeilen aus Abschnitt 10.1 hat einen eigenen Test: normale Buchungen,
Umbuchung, neutrale Tilgung, Kreditzins, Auslage, Ausgleich, Kassadifferenz und
gelöschte Buchung. Weitere Tests prüfen 250 Buchungen mit gleichem Datum über drei
Cursorseiten, Split- und Gruppenfilter, inaktive Kategorien, Bereichsgrenzen trotz
vertauschter informativer Spartenmerkmale, Stichtage, Schaltjahr, Hinweiswerte,
fehlende Miete, Währungen und fehlende Anker.

Alle Treffer auf `migrate.anwenden` und `schema_version` in den Tests wurden
geprüft. Migrationslisten und Schema-Status erwarten jetzt 014. Ein eigener Test
entfernt 014 aus einem Bestandsstand, führt den allgemeinen Runner zweimal aus
und vergleicht alle benannten `sqlite_master`-Objekte einschließlich SQL mit dem
Frischschema. Die bestehende ältere Nachzugskette vergleicht zusätzlich Spalten,
Fremdschlüssel und Indizes; ihre Alt-Fixture enthält die neue Tabelle nicht mehr.
Auch das SQL der Migration wird nochmals direkt ausgeführt.

Das unabhängige Code-Review fand drei Randfälle, die mit Regressionstests behoben
wurden: Matrixkategorien mit ausschließlich Vorjahresrest, Zukunftstreffer der
kompatiblen Suche und ignorierte Bankumsätze. Das gezielte Nachreview bestätigte
die Korrekturen ohne weitere Befunde.

## Testumgebung und verbleibendes Umgebungsartefakt

Interpreter: `C:\Users\lblet\dev\finanz-dashboard-sparten\.venv\Scripts\python.exe`.
Arbeitsverzeichnis bleibt der genannte Worktree. `FINANZ_DB` zeigt auf
`C:\Users\lblet\AppData\Local\Temp\p20-wegwerf.db`; Fixtures verwenden eigene
`tempfile.TemporaryDirectory()`-Datenbanken unter dem lokalen Temp-Verzeichnis.
Der Teststarter ersetzt den Ausgangspfad vor der Discovery durch eine frische
`finanz-p20-suite-...\suite.db` innerhalb einer `TemporaryDirectory()`. Das ist
nötig, weil ältere Tests `app.db.DB_PATH` beim Import festhalten: Wiederholungen
mit derselben Ausgangsdatei ließen sonst alte Kategorien zurück. Die betroffene
Kategorietestdatei wurde mit der isolierten Ausführung zweimal erfolgreich geprüft.

Der Windows-Sandbox-Token kann auf mit Python-3.12-`mkdir(0700)` angelegte
Verzeichnisse nicht zugreifen. Der separate Teststarter verwendet ausschließlich
für temporäre Verzeichnisse vererbte Rechte (`mkdir(0777)` unter Windows).
Produktcode und Dateirechte der Auth-Dateien werden dadurch nicht geändert.
Ein bestehender POSIX-Dateimodustest ist unter Windows regulär übersprungen.

Beim Diagnoseversuch entstand das nicht zugängliche Verzeichnis
`C:\Users\lblet\dev\wt-p20\tmpu94p4lix`. Die automatische Ausführungsprüfung
lehnte das Zurücksetzen seiner Rechte und anschließende Löschen mit
„blocked by policy“ ab. Das Verzeichnis bleibt deshalb bestehen; es gehört
nicht zu den Paketdateien. Es gab keinen hängenden Testlauf; Prozessinformationen
über Windows CIM waren in dieser Umgebung nicht zugänglich.

## Dateien

- `app/rechenbasis.py`: gemeinsamer Filter, Berechnungen, Zeitvergleich, Hinweise und Cursorformat.
- `app/routers/dashboard.py`: Übersicht, Matrix, Hinweisablage und Delegation der alten Filter.
- `app/routers/buchungen.py`: gemeinsame Suche, Cursorseiten und trefferbezogene Gesamtsummen.
- `app/routers/konten.py`: gemeinsames Base64-Cursorformat.
- `app/kennzahlen.py`: SQL-Aggregation für Kennzahlwerte und Datenmonate.
- `db/migrations/014_hinweis_aus.sql`: idempotente bereichsgebundene Hinweisablage.
- `db/schema.sql`: identische Hinweisstruktur für neue Datenbanken.
- `tests/test_p20_snapshots.py`: vor dem Umbau angelegter ASGI-Regressionsschutz.
- `tests/snapshots/p20_alt.json`: unveränderte aufgezeichnete JSON-Antworten.
- `tests/test_rechenbasis.py`: fachliche P20-Vertragstests und die acht Rechenwege.
- `tests/test_p20_migration.py`: exakter Schema-Vergleich und zweimaliger Nachzug 014.
- `tests/test_auslagen.py`: neue Listenhülle und zusätzliche Migrationsversion berücksichtigt.
- `tests/test_bereiche.py`: Bereichsassertion an die neue Listenhülle angepasst.
- `tests/test_bereiche_migration.py`: vollständige Nachzugserwartung und echte Alt-Fixture ergänzt.
- `tests/test_konten_bewegungen.py`: neue Listenhülle und Migrationsversion berücksichtigt.
- `tests/test_kredit.py`: vollständige Nachzugsliste um 014 ergänzt.
- `tests/test_migrate.py`: Versionen und Schema-Status auf 014 aktualisiert.
- `tests/test_migrationsprotokoll.py`: Nachzugsliste um 014 ergänzt.
- `tests/test_saldoanker.py`: Nachzugsliste um 014 ergänzt.
- `scripts/p20_seed.py`: reproduzierbarer Seed und ASGI-Laufzeitmessung mit exakt 5.000 Buchungen.
- `scripts/test_p20_runner.py`: vollständige unittest-Discovery mit Windows-Temp-Kompatibilität.
- `docs/neubau/berichte/P20-plan.md`: Umsetzungsschritte und grundlegende Entscheidungen.
- `docs/neubau/berichte/P20-laufzeit.json`: maschinenlesbare Laufzeitmessung.
- `docs/neubau/berichte/P20-tests.txt`: vollständige ungekürzte Ausgabe des abschließenden Gesamtlaufs.
- `docs/neubau/berichte/P20-runde1.md`: dieser Umsetzungs- und Prüfbericht.
