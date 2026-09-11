# P40c – Vorschlagsliste Erfassen (QA2-03/P40b) & Buchungs-Herkunft Bankimport (P42b): Runde 1

Branch `pkt/p40c-vorschlaege`, Worktree `C:\Users\lblet\dev\wt-p40c`, Ausgangsstand `neubau` 76ae6ac.

## Was gebaut wurde

### Teil 1 – Schnellerfassung: bis zu drei Kategorietreffer mit Herkunft

**Backend**

- `app/regeln.py`: die Kandidaten-Sammelschleife aus `finde_regel` wurde in eine neue Hilfsfunktion `_regel_kandidaten(...)` ausgelagert (identische Trefferlogik, keine Verhaltensänderung). `finde_regel` nutzt sie unverändert für den einen besten Treffer.
  Neue Funktion `finde_regeln(con_oder_regeln, text, *, sparte_id=None, konto_id=None, bereich_id=1, betrag_cent=None, maximal=3)`: sortiert dieselben Kandidaten nach (Priorität aufsteigend, Bedingungslänge absteigend, id) und liefert je Zielkategorie höchstens einen Eintrag (Duplikate durch mehrere passende Regeln auf dieselbe Kategorie werden gefiltert). Konflikte, die `finde_regel` als `konflikt: True` zusammenfasst, tauchen hier bewusst als mehrere gleichwertige Treffer auf – für eine Auswahlliste ist das das gewünschte Verhalten.
- `app/routers/schnellerfassung.py` (`_parse_einzeltext`): liefert zusätzlich `"treffer": [{kategorie_id, kategorie_name, sparte_id, sparte_name, quelle: "name"|"regel", regel_name}]`, maximal 3, Reihenfolge Namensabgleich → Merkregeln.
  - Findet der Namensabgleich eine Kategorie, ist sie `treffer[0]` (`quelle: "name"`).
  - Die bestehenden Top-Level-Felder `kategorie_id`/`kategorie_name`/`sparte_id`/`sparte_name`/`quelle`/`regel_name` bleiben unverändert befüllt (= erster Treffer) – bestehende Tests/Aufrufer brauchen keine Anpassung.
  - Weitere Regeltreffer werden **immer** über `finde_regeln(...)` nachgeladen (auch wenn der Namensabgleich schon traf), bis `treffer` 3 Einträge hat oder keine weiteren Kandidaten mehr da sind. Schon verwendete Zielkategorien werden dabei ausgeschlossen (kein doppelter Treffer auf dieselbe Kategorie).

**Frontend** (`static-neu/pages/erfassen.js`)

- Neuer Zustand `M.treffer` (Array aus `/parse`) und `M.trefferIndex` (markierter Treffer, Vorgabe 0).
- `zeigeVorschlag(v)` übernimmt `v.treffer` und ruft `renderTrefferChips()`: bis zu drei anklickbare Chips „Sparte · Kategorie (Regel „…“)“ bzw. „(Name)“, der markierte Chip ist hervorgehoben (`.ef-chip.active`).
- Neue Funktion `uebernehmeTreffer()` überträgt den markierten Treffer in Sparte-/Kategorie-Select (respektiert weiterhin `M.manuellSparte`/`M.manuellKategorie`) – wird beim Parsen für den Vorgabetreffer automatisch aufgerufen (bisheriges Verhalten unverändert) sowie bei Chip-Klick und beim Verlassen des Textfelds per Tab.
- Tastatur im Textfeld (`textArea` keydown-Handler):
  - Enter (ohne Shift) speichert weiterhin sofort (QA2-01 unverändert, `form.requestSubmit()`).
  - ↑/↓ wechseln nur die Markierung zwischen den Chips (kein sofortiges Übernehmen), zyklisch.
  - Tab übernimmt den gerade markierten Treffer in die Selects, bevor der Fokus das Feld verlässt.
  - Klick auf einen Chip markiert ihn und übernimmt ihn sofort.
- `static-neu/pages/erfassen.css`: zwei neue, minimale Regeln `.ef-chip`/`.ef-chip.active` (Muster wie bestehendes `.ef-badge`).
- Der KI-Vorschlag (P70, `#ef-ki-sugg`) wurde nicht angefasst – erscheint weiterhin nur, wenn das Kategoriefeld nach dem regelbasierten Weg leer bleibt.

### Teil 2 – Bankimport: Buchungs-Herkunft für verbuchte Umsätze

**Backend** (`app/routers/import_bank.py`, `GET /api/bankumsaetze`)

- Jeder Umsatz bekommt jetzt ein Feld `"buchung": {id, typ, text, kategorie_name} | null`. Ermittelt über eine einzelne Zusatzabfrage (`buchung` JOIN `buchungszeile` JOIN `kategorie`, gefiltert auf `bankumsatz_id IN (...)` der verbuchten Umsätze dieser Seite) – kein N+1.
- `vorschlag`-Feld (nur für offene Umsätze, wie bisher) ist unverändert; für verbuchte/ignorierte Umsätze existiert weiterhin **kein** `vorschlag`-Schlüssel (bestehender Test `test_bankumsaetze_liste_hat_vorschlag_nur_fuer_offene` bestätigt das unverändert).

**Frontend** (`static-neu/pages/bankimport.js`)

- `zuordnungZelle(u, state)`: verbuchte Zeilen zeigen jetzt „verbucht als Ausgabe · Kategorie · Text“ (Typ-Label über neue Konstante `TYP_LABEL`), sofern `u.buchung` vorhanden ist; ohne `buchung` bleibt der bisherige Fallback-Text „siehe Buchungsliste“ (sollte praktisch nie auftreten, ist aber ein sicheres Netz).

## Tests

Neue Datei `tests/test_p40c_vorschlaege.py` (11 Tests), auf derselben echten ASGI-/Schema-Testinfrastruktur wie `tests/test_bereiche.py`:

- `TrefferListeTest` (5): bis zu drei Treffer Name→Regel, reiner Regelweg mit Prioritäts-Reihenfolge, Kappung auf 3 bei vier Kandidaten, Abwärtskompatibilität der Top-Level-Felder (= erster Treffer), leere Liste ohne Treffer.
- `FindeRegelnTest` (3): direkter Test von `app.regeln.finde_regeln` – höchstens ein Treffer je Zielkategorie, leere Liste ohne Treffer, `maximal` begrenzt das Ergebnis.
- `BankumsatzBuchungFeldTest` (1): `buchung: null` für offene Umsätze, gefüllt (`id`/`typ`/`text`/`kategorie_name`, inkl. überschriebenem Text) nach dem Verbuchen; `vorschlag` bleibt für verbuchte Umsätze abwesend.
- `P40cJsSyntaxTest` (2): `node --check` für `erfassen.js` und `bankimport.js`.

Ergebnis: **11/11 grün** (Einzellauf), ebenso beim Gesamtlauf enthalten.

## Gesamtsuiten-Ergebnis

`FINANZ_DB=%TEMP%\p40c-suite.db` (vorher gelöscht), `python -m unittest discover -s tests` im Worktree:

```
Ran 572 tests in 712.221s
OK (skipped=1)
```

Rohausgabe: `docs/neubau/berichte/P40c-tests.txt`. Der eine übersprungene Test ist unabhängig von P40c (bestehendes Verhalten, siehe frühere Berichte). Keine Regression in den bestehenden Paketen (P40/P40b, P42, P70/P71, QA-Fixes etc.) – 572 Tests statt zuvor 561, Differenz = die 11 neuen P40c-Tests.

`node --check` für beide geänderten JS-Dateien einzeln gegengeprüft (`erfassen.js`, `bankimport.js`) – beide grün.

## Live-Prüfung

Keine eigene Wegwerf-Instanz auf Port 8083 gestartet – die geforderten Verhaltensweisen (Treffer-Liste inkl. Herkunft und Reihenfolge, Abwärtskompatibilität der Top-Level-Felder, `buchung`-Feld für offene/verbuchte Umsätze) sind bereits über echte HTTP-Anfragen gegen die echte ASGI-App mit echtem Schema in `tests/test_p40c_vorschlaege.py` abgedeckt (gleiches Muster wie `tests/test_bereiche.py`, `tests/test_p42_bankimport.py`). Kein Browser verfügbar (laut Auftrag belegt) – die Chip-Bedienung (Pfeiltasten/Tab/Klick) in `erfassen.js` ist deshalb nur durch Code-Review und `node --check`, nicht durch einen Klicktest abgedeckt.

## Abweichungen von der Karte (mit Begründung)

1. **Weitere Regeltreffer werden auch geholt, wenn der Namensabgleich schon eine Kategorie fand** (nicht nur als Fallback). Die Karte verlangt „bis zu drei Treffer mit Herkunft“ – mit nur einem Namenstreffer und keinem Nachladen der Regeln wäre die Liste in den allermeisten Fällen einelementig und die Pfeiltasten-Navigation liefe ins Leere. Die Top-Level-Felder (das, was gespeichert wird) bleiben trotzdem exakt der Namenstreffer wie zuvor – nur die Auswahlliste wird reichhaltiger.
2. **`finde_regeln` zeigt Konflikt-Kandidaten (gleiche Priorität/Länge, unterschiedliches Ziel) als separate Treffer**, statt sie wie `finde_regel` zu einem `konflikt: True`-Objekt zusammenzufassen. Für eine Ein-Antwort-Funktion ist ein Konflikt ein Problem; für eine Auswahlliste ist er genau der Fall, in dem die Auswahl durch den Nutzer sinnvoll ist. Keine Änderung an `finde_regel` selbst.
3. **Kein Live-Smoke-Test über Port 8083.** Laut Auftrag ist der Browser belegt; die HTTP-Ebene (worauf es hier ankommt: Response-Shape und Reihenfolge) ist bereits durch echte ASGI-Requests mit echtem Schema abgedeckt. Die rein clientseitige Tastatur-/Klick-Interaktion in `erfassen.js` bleibt dadurch ungetestet über einen echten Browser – siehe „Offen“.

## Offene Punkte

- **Kein Klicktest der Chip-/Tastaturbedienung** in `erfassen.js` (Browser war belegt). Empfehlung: kurzer manueller Test – Text mit mehreren Treffern eintippen, mit ↑/↓ zwischen Chips wechseln, mit Tab übernehmen, mit Enter weiterhin sofort speichern (QA2-01 darf nicht brechen).
- `ef-chip`-Styling ist bewusst minimal (passend zu bestehenden `.ef-badge`/`.ef-sugg`-Mustern) – falls die spätere UI-Abnahme mehr Kontrast/Spacing will, ist das ein reiner CSS-Nachzug ohne Logikänderung.
- Keine Migration nötig (wie gefordert) – bestätigt, keine Schemaänderung in diesem Paket.

## Commit

Ein Commit im Worktree auf `pkt/p40c-vorschlaege`, kein Push, kein Merge (Hash siehe Rückmeldung nach `git commit`).
