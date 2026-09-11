# QA-Fix A: Erfassen, Übersicht, Sparte, Kategorien

Worktree `C:\Users\lblet\dev\wt-qa-a`, Branch `fix/qa-erfassen-uebersicht`, Basis neubau 67a4011.
Behebt die Befunde aus `docs/neubau/berichte/QA-1-geruest-uebersicht-sparte-kategorien.md` und
`QA-2-erfassen-buchungen-storno.md` (beide Berichte waren im Hauptklon nur untracked vorhanden
und wurden für diese Arbeit in den Worktree übernommen/committet).

Kein Push, kein Merge. Jeder Befund ein eigener Commit (außer QA1-03/QA1-04/QA1-05, die dieselbe
Datei `kategorien.js` und denselben PATCH-Endpoint betreffen und sinnvoll gebündelt wurden).

## Behoben

**QA2-02 (kritisch) — `parseBetrag()` verfälschte „12.50“ zu 1250**
Ursache: Punkte wurden immer als Tausendertrennzeichen entfernt, bevor das Komma zum Dezimalpunkt
wurde. Fix: `static-neu/format.js` unterscheidet jetzt anhand Position (bei Komma+Punkt) bzw.
Anzahl/Nachkommastellen (bei nur Punkt) zwischen Dezimal- und Tausendertrennzeichen.
Test: `tests/js/parse_betrag.test.mjs` (Node) + `tests/test_qa2_02_parse_betrag.py` (Wrapper).
Commit `08f6a85`.

**QA2-04 (hoch) — `client_request_id` wurde bei jedem Speichern-Versuch neu erzeugt**
Ursache: `crypto.randomUUID()` direkt im submit-Handler von `erfassen.js`, dadurch erkannte der
Server einen Retry nach Netzwerkfehler nicht als Wiederholung (Doppelbuchungsrisiko).
Fix: `M.requestId` wird einmal beim Formularaufbau erzeugt, bei Fehlschlag wiederverwendet, nach
Erfolg/Reset neu erzeugt. `bankimport.js`/`buchungen.js` (Erstattung) geprüft: verwenden kein
`client_request_id`-Feld, daher dort kein Änderungsbedarf.
Test: `tests/test_qa2_04_client_request_id.py`. Commit `da40741`.

**QA1-02 (kritisch) — Drilldown-Saldo immer € 0,00**
Ursache: `GET /api/buchungen` lieferte im `summen`-Objekt kein `saldo_cent` (nur
`einnahmen_cent`/`ausgaben_cent`/`anzahl`), Frontend fiel auf `|| 0` zurück.
Fix: `app/routers/buchungen.py` (`_buchungsseite`) ergänzt `saldo_cent` nach demselben Muster wie
`rechenbasis.py`. Der jetzt überflüssige `|| 0`-Fallback wurde aus `uebersicht.js`/`sparte.js`
entfernt.
Test: `tests/test_qa1_02_saldo_cent.py`. Commit `03a2a81`.

**QA1-03 (mittel) — Duplikat-Kategorienamen ohne Warnung akzeptiert**
Fix: `app/routers/stammdaten.py` (`PATCH`/`POST /api/kategorien`) lehnt jetzt einen Namen ab, der
in derselben Sparte und demselben Parent bereits von einer anderen **aktiven** Kategorie verwendet
wird (case-insensitiv, getrimmt) — 409 mit Klartextmeldung, die `kategorien.js` unverändert als
Toast anzeigt (`error.detail` wurde schon vorher ausgewertet).
Test: `tests/test_qa1_03_kategorie_duplikat.py`. Commit `5c98287`.

**QA1-04 (niedrig) — leerer Name verpuffte ohne Rückmeldung**
Fix: `kategorien.js` zeigt jetzt einen Toast „Name darf nicht leer sein.“ statt beim leeren Feld
stillschweigend abzubrechen (Backend gab schon vorher 400, nur ungenutzt vom Frontend). Commit
`5c98287`.

**QA1-05 (niedrig, unsicher) — vereinzelter `TypeError … replaceWith` in `kategorien.js`**
Fix: `startRename()` prüft jetzt defensiv `if (!span) return;`, bevor auf die `.kname`-Zelle
zugegriffen wird (Absicherung gegen die im Bericht vermutete Race zwischen Blur-Speichern und
erneutem Klick auf „umbenennen“). Commit `5c98287`.

**QA1-01 (mittel) — Sparten-Wechsel ohne ID im Hash**
Ursache: `sparte.js` normalisierte jeden `#/sparte/<id>`-Hash sofort auf das ID-lose `#/sparte`
zurück; Kopf-Dropdown/Sidebar/Kacheln setzten nie eine ID in die URL.
Fix: `sparte.js` (`syncSparteAusHash`, `waehleSparte`, `render`), `uebersicht.js` (`goSparte`) und
`app.js` (`setFilter`, nur auf der Sparte-Seite) schreiben/lesen jetzt konsequent
`#/sparte/<id>`. Der Gruppen-Hash `#/sparte/gruppe-<id>` (P32b) bleibt unverändert vorrangig
(siehe `docs/neubau/abnahme/P60b-P31b-P32b.md`).
Test: `tests/test_qa1_01_sparte_hash.py`. Commit `8107e77`.
**Einschränkung:** kein Browser verfügbar (siehe Auftrag) — die Tests prüfen den Quelltext
(node --check + gezielte Struktur-Assertions), nicht das tatsächliche Hash-/Verlaufsverhalten im
Browser. Empfehlung: vor Abnahme einmal mit echtem Browser durchklicken (Kachel → andere Kachel →
Zurück-Taste → Deep-Link kopieren/neu laden).

**QA2-01 (mittel) — Enter im Erfassen-Textfeld speicherte nicht**
Fix: `erfassen.js` hat jetzt einen `keydown`-Handler auf dem Textfeld: Enter ruft
`form.requestSubmit()` (nutzt die vorhandene Validierung/Toasts), Shift+Enter bleibt ein normaler
Zeilenumbruch.
Test: `tests/test_qa2_01_enter_speichert.py`. Commit `2a6f9a1`.

**QA2-06 (niedrig) — Zahlungsart-Filter ohne „Sonstiges“**
Fix: `static-neu/index.html` (`#filter-zahlungsart`) um `<option value="sonstiges">` ergänzt.
Test: `tests/test_qa2_06_zahlungsart_sonstiges.py`. Commit `3195c29`.

**QA2-07 (niedrig) — Kategorie-Filter zeigt nicht unterscheidbare Dubletten**
Fix: `drawKategorieFilter()` in `app.js` hängt bei „Alle Sparten“ und Namensdubletten das
Sparten-Kürzel an die Option an (z. B. „Auto (VHM)“); mit aktivem Sparten-Filter oder bei
eindeutigen Namen bleibt die Beschriftung unverändert.
Test: `tests/test_qa2_07_kategorie_filter_kuerzel.py`. Commit `8618169`.

**QA2-05 (niedrig) — keine Obergrenze für Buchungsbeträge**
Fix: `ZeileIn.betrag_cent` in `app/schemas.py` bekommt `le=BETRAG_CENT_MAX` (100 Mio. € in Cent).
Test: `tests/test_qa2_05_betrag_obergrenze.py`. Commit `cd92b33`.
**Nicht mitgezogen (bewusst, außerhalb des Befunds):** `UmbuchungIn`/`ErstattenZeileIn`
(`buchungen.py`) sowie `betrag_cent` in `auslagen.py`/`konten.py`/`kredite.py`/
`beleg_auswertung.py` haben dieselbe fehlende Obergrenze. Als separate Aufgabe eingeplant
(`task_7bc1cec5` im Sitzungs-Backlog).

**QA1-06 (niedrig) — fehlendes Favicon**
Fix: `<link rel="icon" href="data:,">` in `static-neu/index.html`.
Test: `tests/test_qa1_06_favicon.py`. Commit `e3c1b3b`.

## Nicht behoben / offen

- Keine — alle 12 im Auftrag genannten Befunde wurden bearbeitet.
- QA1-01 (siehe oben) konnte mangels Browser nur per Quelltextprüfung verifiziert werden, nicht
  end-to-end im Browser.
- QA2-05 wurde nur für `ZeileIn.betrag_cent` behoben; die anderen `betrag_cent`-Felder sind als
  Folgeaufgabe vorgemerkt, siehe oben.
- QA2-03 (Vorschlagszeile mit bis zu drei Treffern/Pfeiltasten, Regel-Herkunft) war **nicht** Teil
  des Auftrags für diese Runde und wurde nicht angefasst.

## Tests

Betroffene JS-Dateien alle mit `node --check` geprüft (grün). Gesamtsuite im Worktree:

```
FINANZ_DB=%TEMP%\qa-a-suite.db  (vorher gelöscht)
<venv-python> -m unittest discover -s tests
Ran 528 tests in 235.487s
OK (skipped=1)
```

Volle Ausgabe: `docs/neubau/berichte/QA-fix-A-tests.txt`. Der eine übersprungene Test sowie die im
Log sichtbaren Tracebacks (absichtlich erzeugte Fehlerpfade: Bild-Unidentified-Error,
NAS-aus-Simulation, Backup-Konflikt bei parallel laufenden Testinstanzen) gehören zu bestehenden,
unveränderten Tests und sind kein Befund dieser Runde.

## Commits (fix/qa-erfassen-uebersicht, neu seit 67a4011)

```
08f6a85 QA2-02: parseBetrag unterscheidet Dezimal- von Tausendertrennzeichen
da40741 QA2-04: client_request_id im Erfassen-Formular bleibt fuer Retries stabil
03a2a81 QA1-02: GET /api/buchungen liefert saldo_cent im summen-Objekt
5c98287 QA1-03/QA1-04/QA1-05: Kategorie-Umbenennen absichert (Duplikate, leerer Name, Race)
8107e77 QA1-01: Sparten-Wechsel bildet die ID jetzt im Hash ab (#/sparte/<id>)
2a6f9a1 QA2-01: Enter im Erfassen-Textfeld speichert direkt
3195c29 QA2-06: Buchungsliste-Filter Zahlungsart um Sonstiges ergaenzt
8618169 QA2-07: Kategorie-Filter kennzeichnet gleichnamige Kategorien mit Sparten-Kuerzel
cd92b33 QA2-05: Obergrenze fuer Buchungsbetraege (ZeileIn.betrag_cent)
e3c1b3b QA1-06: Favicon-Link verhindert 404 auf /favicon.ico
```

Kein Push, kein Merge.
