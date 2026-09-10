# P31 Runde 1 – Seite Übersicht (Startseite)

## Geänderte und neue Dateien

- `static-neu/pages/uebersicht.js` (geändert, war Platzhalter): echte Startseite. Lädt `GET /api/uebersicht` und baut KPI-Zeile, Sparten-Kacheln, Hinweise mit Ausblenden, Konten/Kassen, offene Auslagen, Jahresverlauf und größte Kategorien; Drilldowns über eine lokale `drillBuchungen()`-Funktion, die `GET /api/buchungen` lädt und `ui.js#drill()` zum Anzeigen nutzt.
- `static-neu/pages/uebersicht.css` (neu): Klassen, die `style.css` noch nicht kennt (Kacheln, Hinweiszeilen, Kontenliste, Balkenlisten, Legende, Filterhinweis), wird von `uebersicht.js` beim ersten `render` per `<link>` nachgeladen.
- `static-neu/charts.js` (erweitert, keine bestehenden Exporte geändert): neue Funktion `sparklineCompare(current, previous, color)` zeichnet eine Sparkline mit gestrichelter Vorjahreslinie für die drei KPI-Kacheln.
- `tests/test_p31_uebersicht.py` (neu): sechs Tests, siehe unten.
- `docs/neubau/berichte/P31-tests.txt` (neu): vollständige Ausgabe der Gesamtsuite.

## Verwendete Endpunkte mit wörtlichem Antwort-JSON

Aufgezeichnet mit dem FastAPI-Testclient-Muster aus `tests/test_bereiche.py` (`FINANZ_TEST_AUTH_BYPASS=1`, `FINANZ_DB` auf eine Wegwerf-Datei unter `%TEMP%`), Testdaten: Bereich 1 mit zwei Hauptsparten (Buchungen 2025/2026, eine Einnahme, zwei Ausgaben in verschiedenen Sparten) und einem Bankkonto mit Anker; Bereich 2 (Verein) ohne Buchungen.

### `GET /api/uebersicht?bereich_id=1&jahr=2026&stichtag=2026-09-10`

```json
{
  "stichtag": "2026-09-10", "jahr": 2026,
  "ist": {"einnahmen_cent": 20000, "ausgaben_cent": 10500, "saldo_cent": 9500},
  "vorjahr_gleicher_zeitraum": {"einnahmen_cent": 0, "ausgaben_cent": 5000, "saldo_cent": -5000},
  "vorjahr_gesamt": {"einnahmen_cent": 0, "ausgaben_cent": 5000, "saldo_cent": -5000},
  "erwartung": {"einnahmen_cent": 20000, "ausgaben_cent": 10500, "saldo_cent": 9500},
  "monate": {
    "einnahmen": [0,20000,0,0,0,0,0,0,0,0,0,0],
    "ausgaben": [0,0,9000,1500,0,0,0,0,0,0,0,0],
    "vorjahr_einnahmen": [0,0,0,0,0,0,0,0,0,0,0,0],
    "vorjahr_ausgaben": [0,0,5000,0,0,0,0,0,0,0,0,0]
  },
  "sparten": [
    {"sparte_id": 1, "name": "Privatvermietung", "kuerzel": "PV", "farbe": "#6AA9FF", "einnahmen_cent": 20000, "ausgaben_cent": 9000, "saldo_cent": 11000},
    {"sparte_id": 2, "name": "Zimmervermietung Hof", "kuerzel": "ZVH", "farbe": "#2DD4BF", "einnahmen_cent": 0, "ausgaben_cent": 1500, "saldo_cent": -1500},
    {"sparte_id": 3, "name": "Bauernhof", "kuerzel": "HOF", "farbe": "#C084FC", "einnahmen_cent": 0, "ausgaben_cent": 0, "saldo_cent": 0},
    {"sparte_id": 5, "name": "Alois privat", "kuerzel": "AL", "farbe": "#FB923C", "einnahmen_cent": 0, "ausgaben_cent": 0, "saldo_cent": 0},
    {"sparte_id": 6, "name": "Frau privat", "kuerzel": "FR", "farbe": "#818CF8", "einnahmen_cent": 0, "ausgaben_cent": 0, "saldo_cent": 0}
  ],
  "top": {
    "ausgaben": [
      {"kategorie_id": 1, "name": "Futtermittel", "sparte_id": 1, "betrag_cent": 9000, "anteil": 0.857},
      {"kategorie_id": 3, "name": "Buerobedarf", "sparte_id": 2, "betrag_cent": 1500, "anteil": 0.143}
    ],
    "einnahmen": [{"kategorie_id": 2, "name": "Verkauf", "sparte_id": 1, "betrag_cent": 20000, "anteil": 1.0}]
  },
  "hinweise": [
    {"schluessel": "kostenanstieg::110", "art": "kostenanstieg", "wert": "110",
     "text": "Ausgaben hochgerechnet 110% über dem Vorjahr.",
     "drill": {"bereich_id": 1, "jahr": 2026, "stichtag": "2026-09-10"}},
    {"schluessel": "groesste_buchung::20000", "art": "groesste_buchung", "wert": "20000",
     "text": "Größte Buchung: 20000 Cent.",
     "drill": {"bereich_id": 1, "jahr": 2026, "stichtag": "2026-09-10", "kategorie_id": 2}},
    {"schluessel": "kategorie_anteil:1:86", "art": "kategorie_anteil", "wert": "86",
     "text": "Futtermittel: 86% der Ausgaben.",
     "drill": {"bereich_id": 1, "jahr": 2026, "stichtag": "2026-09-10", "kategorie_id": 1, "richtung": "ausgabe"}}
  ],
  "auslagen_offen": [],
  "konten": [
    {"id": 1, "name": "Testkonto", "sparte_id": 1, "waehrung": "EUR", "konto_id": 1, "stichtag": "2026-09-10",
     "stand_cent": 100000, "saldo_cent": 0,
     "anker": {"stichtag": "2026-08-01", "saldo_cent": 100000, "quelle": "auszug"},
     "bewegungen_seit_anker": 0, "letzter_import": null, "import_alter_tage": null,
     "datenstand": "aktuell", "hinweis": ""}
  ],
  "konten_je_waehrung": {"EUR": {"stand_cent": 100000, "unbekannte_konten": 0}},
  "datenstand": {"letzte_buchung": "2026-04-01", "letzter_import": null}
}
```

### `GET /api/uebersicht?bereich_id=2&jahr=2026&stichtag=2026-09-10` (Verein, ohne Buchungen)

```json
{
  "stichtag": "2026-09-10", "jahr": 2026,
  "ist": {"einnahmen_cent": 0, "ausgaben_cent": 0, "saldo_cent": 0},
  "vorjahr_gleicher_zeitraum": {"einnahmen_cent": 0, "ausgaben_cent": 0, "saldo_cent": 0},
  "vorjahr_gesamt": {"einnahmen_cent": 0, "ausgaben_cent": 0, "saldo_cent": 0},
  "erwartung": {"einnahmen_cent": 0, "ausgaben_cent": 0, "saldo_cent": 0},
  "monate": {"einnahmen": [0,0,0,0,0,0,0,0,0,0,0,0], "ausgaben": [0,0,0,0,0,0,0,0,0,0,0,0],
             "vorjahr_einnahmen": [0,0,0,0,0,0,0,0,0,0,0,0], "vorjahr_ausgaben": [0,0,0,0,0,0,0,0,0,0,0,0]},
  "sparten": [{"sparte_id": 4, "name": "Verein", "kuerzel": "VER", "farbe": "#F472B6",
               "einnahmen_cent": 0, "ausgaben_cent": 0, "saldo_cent": 0}],
  "top": {"ausgaben": [], "einnahmen": []}, "hinweise": [], "auslagen_offen": [],
  "konten": [], "konten_je_waehrung": {},
  "datenstand": {"letzte_buchung": null, "letzter_import": null}
}
```

Bestätigt den Bereichsvertrag: Bereich 1 enthält nie die Vereins-Sparte (id 4), Bereich 2 enthält ausschließlich sie.

### `GET /api/jahresmatrix?bereich_id=1&jahre=2025,2026&stichtag=2026-09-10` (Auszug)

```json
{"jahre": [2025, 2026], "stichtag": "2026-09-10",
 "zeilen": [
   {"kategorie_id": 1, "name": "Futtermittel", "sparte_id": 1, "aktiv": 1, "richtung": "ausgabe",
    "werte": {"2025": {"einnahmen_cent": 0, "ausgaben_cent": 5000}, "2026": {"einnahmen_cent": 0, "ausgaben_cent": 9000}},
    "erwartung_cent": {"einnahmen": 0, "ausgaben": 9000}, "ohne_vorjahr": false,
    "monatsdurchschnitt_cent": {"2025": {"einnahmen_cent": 0, "ausgaben_cent": 416}, "2026": {"einnahmen_cent": 0, "ausgaben_cent": 1000}}}
 ],
 "summen": {"2025": {"einnahmen_cent": 0, "ausgaben_cent": 5000, "saldo_cent": -5000},
            "2026": {"einnahmen_cent": 20000, "ausgaben_cent": 10500, "saldo_cent": 9500}}}
```

Diesen Endpunkt nutzt `uebersicht.js` nicht direkt (er gehört zur Sparten-Seite P3x), wurde aber wie im Nachtrag verlangt aufgezeichnet.

### `GET /api/hinweise/aus?bereich_id=1` (vor Ausblenden)

```json
[]
```

### `POST /api/hinweise/aus?bereich_id=1` mit `{"schluessel":"kostenanstieg::110","bis_wert":"110"}`

```json
{"id": 1, "bereich_id": 1, "schluessel": "kostenanstieg::110", "bis_wert": "110", "erstellt_am": "2026-09-10 19:29:03"}
```

Danach liefert `GET /api/hinweise/aus?bereich_id=1` genau diesen Eintrag, und `GET /api/uebersicht` führt `kostenanstieg::110` nicht mehr in `hinweise`.

### `GET /api/jahre?bereich_id=1`

```json
{"jahre": [2026, 2025]}
```

## Wichtige Entscheidungen

1. **Sparten-Kacheln respektieren den aktiven Sparten-Filter.** Der Prototyp rechnet die Kacheln clientseitig ohne Filter (`ignoreFilter`-Trick); das echte `GET /api/uebersicht` kennt das nicht — setzt man `sparte_id`, liefert `sparten[]` nur noch diese eine Sparte (siehe `rb._sparten_sql`). Die Karte selbst klärt das im Klammertext von Abschnitt 3 ("ohne sparte_id/gruppe = alle Sparten des Bereichs"). Ich habe mich für den wörtlichen API-Vertrag entschieden: `sparte_id` wird wie jeder andere Filter mitgeschickt, die Kacheln zeigen dann entsprechend nur die gefilterte(n) Sparte(n). Das weicht vom Demo-Verhalten des Prototyps ab, folgt aber der tatsächlichen, dokumentierten Serverlogik.
2. **KPI-Vergleich immer gegen `vorjahr_gesamt`**, für laufendes und abgeschlossenes Jahr gleichermaßen (Karte, Abschnitt 3, wörtlich so beschrieben — `vorjahr_gleicher_zeitraum` wird geliefert, aber laut Karte nicht für den Prozentvergleich verwendet).
3. **Monatsfilter für den Verlaufs-Drilldown** nutzt das reale `Filter.monat`-Format `JJJJ-MM` (Regex in `rechenbasis.py`), nicht die einstellige Monatszahl aus der Prototyp-Pseudologik.
4. **Auslagen-Drilldown ohne zusätzlichen API-Aufruf**: `auslagen_offen[].auslagen[]` enthält bereits Einzelposten (`datum`, `text`, `kategorie`, `offen_cent`), die direkt im Dialog angezeigt werden; der in der Karte vorgesehene Rückfall auf `go("sparte", zahler_sparte_id)` greift nur, falls eine Gruppe ausnahmsweise keine Einzelposten mitliefert.
5. **`h.text` wird ungeprüft als HTML eingebettet** (kein `esc()`), wie von der Karte verlangt ("das text-Feld selbst gilt als bereits sicher"). Die aufgezeichneten Texte enthalten aktuell kein Markup, nur normalen Text.

## Wunsch an das Gerüst

P30 hat einige Bausteine nur teilweise verdrahtet, die P31 gebraucht hätte. Alles lokal in `uebersicht.js` nachgezogen (keine Änderung an `app.js`/`api.js`/`ui.js`):

1. **Kein `state.filter`-Objekt.** Die Karte setzt es voraus ("Parameter aus `state.filter`"), tatsächlich hält `app.js` nur `state.sparteId` und `state.year` als eigene Felder; `#filter-richtung`, `#filter-zahlungsart`, `#filter-kategorie` existieren im Markup, werden aber nirgends ausgelesen oder gebunden. Lokaler Ersatz: `uebersicht.js` liest diese drei Felder bei jedem Request direkt per `document.querySelector` aus.
2. **`#year-select` hat in `app.js` keinen `onchange`-Handler.** Jahreswechsel hätte ohne Weiteres gar keine Wirkung gehabt. Lokal gebunden (einmalig, per `dataset`-Flag).
3. **`#sparte-select`-Wechsel löst in `app.js` kein Neu-Rendern der aktiven Seite aus** (nur `drawSidebar()`). Gleiches gilt implizit für die drei Filterfelder. Lokaler Ersatz: `uebersicht.js` hängt einen zusätzlichen `change`-Listener an, der `window.dispatchEvent(new Event('hashchange'))` auslöst — das triggert exakt denselben vollen Render-Zyklus wie echte Navigation (Sidebar, Kopfzeile, Seite bleiben konsistent), ohne `app.js` zu verändern.
4. **`#filter-kategorie` hat keine Optionen** (nur „alle“) — `app.js` füllt sie nie mit echten Kategorien. Für P31 nicht kritisch behoben, das Feld bleibt praktisch ungenutzt; würde eine spätere Karte (`app.js`-Zuständigkeit oder eigene Kategorie-Ladefunktion) brauchen.
5. **`ui.js#drill(title, content)` ist ein generischer Dialog-Öffner**, keine filterbewusste Drilldown-Funktion wie in der P31-Karte beschrieben (`drill(h.drill)`). Lokaler Ersatz: `drillBuchungen(filterParams, title)` in `uebersicht.js` holt `GET /api/buchungen` und übergibt das fertige HTML an `ui.js#drill()`.
6. **`charts.js#sparkline` zeichnet nur eine Linie**, die Karte verlangt aber Ist- und Vorjahreslinie in der KPI-Sparkline. Da P31 laut Nachtrag als einziges Paket `charts.js` erweitern darf, wurde `sparklineCompare(current, previous, color)` ergänzt (bestehende Exporte unverändert).

## Testausgabe

Isolierter Lauf (`-m unittest discover -s tests -p test_p31_uebersicht.py`, `FINANZ_DB` auf Wegwerf-Datei):

```
Ran 6 tests in 6.382s
OK
```

Enthält: Auslieferung von `/neu/pages/uebersicht.js` (200, referenziert `api.js`), `node --check` für `uebersicht.js` und `charts.js` (grün, `node` ist in dieser Umgebung vorhanden), Bereichsgrenze Haupt/Verein, Feldvertrag von `/api/uebersicht` (alle von der Seite gelesenen Felder vorhanden), Hinweis ausblenden/erneut laden.

Gesamtsuite (`-m unittest discover -s tests`, Wegwerf-DB vorher gelöscht), vollständige Ausgabe in [`P31-tests.txt`](P31-tests.txt):

```
Ran 304 tests in 503.376s
OK (skipped=1)
```

Keine Fehlschläge. Die im Log sichtbaren `PIL.UnidentifiedImageError`-Tracebacks stammen aus bestehenden, nicht mit P31 verwandten Beleg-Auswertungstests (absichtlich provozierte Fehlerpfade, kein Testfehlschlag).

## App manuell geprüft

`uvicorn app.main:app` auf Port 8131, `FINANZ_TEST_AUTH_BYPASS=1`, `FINANZ_INSTANZ=test`, Wegwerf-DB. Per `curl`:

- `GET /neu/` → 200 (HTML)
- `GET /neu/pages/uebersicht.js` → 200
- `GET /neu/pages/uebersicht.css` → 200
- `GET /neu/charts.js` → 200 (bestätigt: Erweiterung lädt weiterhin fehlerfrei)
- `GET /api/uebersicht?bereich_id=1` → 200, echtes JSON

Server danach beendet (Prozess über den Port ermittelt und gestoppt).

## Was im Browser NICHT geprüft werden konnte

Kein echter Browser verfügbar (nur FastAPI-Testclient und `curl`). Nicht geprüft:

- Visuelle Darstellung der Kacheln, KPI-Karten, Sparklines, Balkendiagramm.
- Tatsächliches Klickverhalten (Kachel → Sparte, Hinweis-„×“, Monatsbalken, Top-Balken, Auslagen-Zeile) — die Handler sind verdrahtet und durch Code-Lesen nachvollzogen, aber nicht interaktiv im DOM getestet.
- Bereichswechsel in der Sidebar mit Neuladen der Übersicht.
- Mobile Ansicht (< 760 px) — CSS-Regeln in `uebersicht.css` orientieren sich an den Breakpoints aus `style.css` (`.g2-1` bricht dort ebenfalls auf eine Spalte um), aber ungeprüft im echten Viewport.
- Konsolenfehler im echten Browser.

## Offene Punkte

- Die unter „Wunsch an das Gerüst“ genannten Lücken (kein `state.filter`, `#year-select` ohne Handler, `#sparte-select`-Wechsel ohne Re-Render, leeres Kategorie-Dropdown) wurden ausschließlich lokal in `uebersicht.js` kompensiert, nicht in `app.js` behoben — wie vom Nachtrag vorgeschrieben.
- Entscheidung 1 (Sparten-Kacheln respektieren `sparte_id`-Filter, abweichend vom Prototyp-Demo-Verhalten) ist eine bewusste Auslegung eines Widerspruchs zwischen Kartentext und Prototyp; falls das nicht gewünscht ist, müsste `uebersicht.js` die Sparten-Kacheln über einen zweiten, ungefilterten `GET /api/uebersicht`-Aufruf laden.
- Kein Playwright/Browsertest möglich (siehe oben) — rein serverseitig und über `curl` verifiziert.
