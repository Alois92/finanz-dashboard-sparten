# P20: Gemeinsame Rechenbasis, Übersicht, Jahresmatrix, Buchungsliste mit Cursor

Meilenstein M2. Modell: `gpt-6-astra`, Aufwand high. Branch `pkt/p20-auswertungen` von `neubau` (nach M1).

## 1. Ziel

Alle Auswertungen rechnen über einen gemeinsamen Filter und dieselben Funktionen, damit Übersicht, Matrix, Drilldown und Buchungsliste nie widersprüchliche Zahlen zeigen. Das laufende Jahr wird nach Saison hochgerechnet (Ist plus Vorjahresrest ab Stichtag), der Stichtag kommt vom Server.

## 2. Kontext

Lies `docs/neubau/ARCHITEKTUR.md` Abschnitt 8, dann `app/routers/dashboard.py` (bestehende `/api/dashboard`, `/api/jahresvergleich`, `/api/verlauf`, `_where`), `app/routers/buchungen.py` (`GET /api/buchungen`, `/api/buchungen/suche`), `app/routers/gruppen.py`, `app/bereiche.py`, `app/kennzahlen.py` (P15), `app/routers/auslagen.py` (P12), `app/konten.py` (P13), `db/schema.sql` (Views), `tests/test_buchungen_suche.py`, `scripts/test_drilldown_api.py`. Fachliche Vorgaben aus dem Prototyp: Hinweise (Kostenanstieg hochgerechnet, fehlende regelmäßige Einnahme erst fünf Tage nach dem üblichen Tag, offene Auslagen, größte Einzelbuchung, offene Bankumsätze, Anteil der größten Kategorie), Kacheln mit Ist „bisher", Kennzahlen mit Jahreserwartung.

## 3. Schnittstellen

Neues Modul `app/rechenbasis.py`:

```python
@dataclass
class Filter:
    bereich_id: int = 1
    sparte_id: int | None = None
    auswertungsgruppe_id: int | None = None
    globalgruppe_id: int | None = None
    jahr: int | None = None
    von: str | None = None
    bis: str | None = None
    kategorie_id: int | None = None
    richtung: str | None = None        # 'einnahme'|'ausgabe'
    zahlungsart: str | None = None     # 'bar'|'bank'|'karte'
    stichtag: str | None = None        # Standard: heute, siehe stichtag_heute()

def filter_dep(...) -> Filter                     # FastAPI-Dependency aus Query-Parametern, prüft Bereich und Sparten-/Gruppen-Zugehörigkeit
def sparten_ids(con, f: Filter) -> list[int]      # Sparte, Gruppe oder alle Sparten des Bereichs (ohne Verein im Hauptbereich)
def where_zeilen(con, f) -> tuple[str, list]      # WHERE auf v_einnahmen_ausgaben (Umbuchungen, neutral, storniert ausgeschlossen)
def summen(con, f) -> dict                        # {einnahmen_cent, ausgaben_cent, saldo_cent}
def monatsreihe(con, f) -> dict                   # {einnahmen: [12], ausgaben: [12]}
def je_kategorie(con, f) -> list[dict]            # [{kategorie_id, name, sparte_id, aktiv, einnahmen_cent, ausgaben_cent}]
def stichtag_heute() -> str   # ISO-Datum. Europe/Vienna über zoneinfo, ABER mit Rückfall auf die
                              # lokale Zeit, wenn die Zeitzonendaten fehlen (unter Windows ist das
                              # Paket tzdata nicht installiert und darf nicht ergänzt werden).
                              # Test: die Funktion liefert auch ohne Zeitzonendaten ein gültiges Datum.
def vorjahresrest(con, f, stichtag) -> dict       # Summen des Vorjahres mit datum > stichtag im Vorjahr (29.02. → 28.02.)
def erwartung(con, f, stichtag) -> dict           # Ist + Vorjahresrest, nur wenn f.jahr == Jahr des Stichtags
def hinweise(con, f, stichtag) -> list[dict]      # [{schluessel, art, text, drill: Filter-Parameter}]
```

Endpoints (`app/routers/dashboard.py`, bestehende bleiben und delegieren):

```
GET /api/uebersicht?<Filter>
 → {stichtag, jahr, ist: {einnahmen_cent, ausgaben_cent, saldo_cent}, vorjahr_gleicher_zeitraum: {...}, vorjahr_gesamt: {...},
    erwartung: {einnahmen_cent, ausgaben_cent, saldo_cent}|null,
    monate: {einnahmen: [12], ausgaben: [12], vorjahr_einnahmen: [12], vorjahr_ausgaben: [12]},
    sparten: [{sparte_id, name, kuerzel, farbe, einnahmen_cent, ausgaben_cent, saldo_cent}],
    top: {ausgaben: [{kategorie_id, name, sparte_id, betrag_cent, anteil}], einnahmen: [...]},
    hinweise: [...], auslagen_offen: [...aus P12], konten: [...aus P13 mit stand/datenstand], datenstand: {letzte_buchung, letzter_import}}
GET /api/jahresmatrix?<Filter>&jahre=2023,2024,2025,2026
 → {jahre: [...], stichtag, zeilen: [{kategorie_id, name, sparte_id, aktiv, richtung, werte: {"2025": {einnahmen_cent, ausgaben_cent}, ...}, erwartung_cent: {einnahmen, ausgaben}|null, monatsdurchschnitt_cent}], summen: {...je Jahr}}
GET /api/buchungen?<Filter>&q=&limit=100&cursor=
 → {buchungen: [...wie bisher plus auslage, neutral_cent, version] — **kein `storniert_am`**: die Tabelle `buchung` hat keine solche Spalte, Storno kommt erst mit P51, summen: {anzahl, einnahmen_cent, ausgaben_cent}, naechster_cursor}
   Cursor = base64 von "datum|id" der letzten Zeile; Summen über alle Treffer, nicht nur die Seite
GET /api/buchungen/suche  → delegiert an GET /api/buchungen mit q (bleibt aus Kompatibilität)
GET /api/hinweise/aus  und  POST /api/hinweise/aus {schluessel, bis_wert}   → ausgeblendete Hinweise (Tabelle hinweis_aus)
```

Migration `db/migrations/013_hinweis_aus.sql` (009 bis 012 sind belegt): `hinweis_aus(id INTEGER PRIMARY KEY, bereich_id INTEGER NOT NULL REFERENCES bereich(id), schluessel TEXT NOT NULL, bis_wert TEXT, erstellt_am TEXT NOT NULL DEFAULT (datetime('now')), UNIQUE(bereich_id, schluessel))` — **mit `bereich_id`**, sonst blendet ein Hinweis im Hauptbereich denselben Schlüssel im Vereinsbereich mit aus. Ein Hinweis erscheint wieder, wenn sein aktueller Wert (im Schlüssel kodiert, z. B. Prozent auf 5 gerundet oder Cent) von `bis_wert` abweicht.

Regeln:
- Verein-Sparten (Bereich 2) tauchen im Hauptbereich nirgends auf; im Bereich 2 sind sie die einzigen.
- Überlappende Gruppen: Sparten-IDs als Menge, keine Doppelzählung.
- Drilldown ist derselbe Endpoint `GET /api/buchungen` mit denselben Filterparametern plus `kategorie_id`/`monat`; die Zahl auf der Kachel und die Summe der Liste stimmen überein (Test).
- Hinweise: „fehlende regelmäßige Einnahme" nur, wenn die Kategorie im Vorjahr in mindestens 11 Monaten Einnahmen hatte, im aktuellen Monat keine, und der Stichtag ≥ üblicher Tag (Median der Vorjahrestage) + 5.
- Erwartung nur für das Stichtagsjahr; für abgeschlossene Jahre `null`. Kategorien ohne Vorjahr: Erwartung = Ist mit Kennzeichen `ohne_vorjahr`.

## 4. Nicht-Ziele

Kein Frontend. Keine Export-Änderung (M6). Keine Kennzahl-Definition (P15), nur deren Wert im Sparten-Kontext mitliefern, falls einfach.

## 5. Schritte

1. `app/rechenbasis.py` mit Filter und Funktionen; bestehende `_where`-Logik dorthin ziehen. **Nicht** `app/auswertungen.py` — der Name kollidiert mit dem bestehenden `app/auswertung.py` (Rechnungsfoto-Auswertung mit Ollama).
2. `/api/uebersicht`, `/api/jahresmatrix`, Cursor-Buchungsliste, Hinweise, Migration 013.
3. Bestehende Endpoints auf die neuen Funktionen umstellen (gleiche Antworten wie bisher, Regression durch bestehende Tests).
4. Tests, Gesamtlauf, Bericht.

## 6. Tests

Neue Datei `tests/test_rechenbasis.py` mit reproduzierbarem Seed (feste Buchungen in zwei Jahren, zwei Sparten, Verein-Sparte, Umbuchung, neutrale Zeile, gelöschte Buchung — **keine** stornierte, die gibt es erst ab P51):
- Summen der Übersicht = Summe der Kacheln = Summe der Buchungsliste (gleicher Filter).
- Umbuchung, neutrale Zeile und stornierte Buchung zählen nirgends.
- Verein erscheint nicht im Hauptbereich; mit `bereich_id=2` nur Verein.
- Erwartung: Vorjahr hat Buchung am 15.11.; Stichtag 08.09.: Erwartung = Ist + Vorjahresrest inklusive November; Stichtag 31.12.: Erwartung = Ist.
- 29.02. als Stichtag im Schaltjahr → Vorjahresrest ab 28.02.
- Jahresmatrix: Kategorie mit Einnahme 100 und Ausgabe 20 zeigt beides getrennt; stillgelegte Kategorie mit Historie erscheint mit `aktiv=0`.
- Buchungsliste: 250 Buchungen, `limit=100`: drei Seiten über Cursor, keine Lücke, keine Dublette; `summen.anzahl` = 250 auf jeder Seite.
- Drilldown: Kachel „Futtermittel 2026" = Summe der Liste mit `kategorie_id`.
- Hinweis „Miete fehlt": Vorjahr 12 Monate am 3., aktueller Monat ohne, Stichtag 08. → Hinweis; Stichtag 05. → kein Hinweis.
- Hinweis ausblenden mit `bis_wert`; bei geändertem Wert erscheint er wieder.
- Bestehende Tests grün.

## 7. Fertig heißt

- [ ] Alle Tests grün, vollständige Ausgabe im Bericht.
- [ ] Migration zweimal über den Runner; `schema.sql` und Nachzug gleich.
- [ ] Laufzeit `GET /api/uebersicht` mit 5.000 Buchungen unter 300 ms lokal (im Bericht messen).
- [ ] Keine Geheimnisse.
- [ ] Bericht geschrieben.

## 8. Bericht zurück

Geänderte und neue Dateien mit je einem Satz. Vollständige Testausgabe. Laufzeitmessung. Offene Punkte mit Grund. Keine Commits, kein Push.

---

## 10. Nachtrag aus der Kontrolle (Fable, 10. September 2026) — verbindlich

### 10.1 Rechenbasis: was zählt wo hinein

Diese Tabelle ist der Kern des Pakets. Jede Zeile bekommt einen eigenen Testfall im Seed.

| Vorgang | Einnahmen/Ausgaben | Kontostand | Bemerkung |
|---|---|---|---|
| Normale Einnahme oder Ausgabe | ja | über die Bewegung | |
| **Umbuchung** | **nein** | ja | Quelle der Wahrheit: `buchung.typ='umbuchung'` wird ausgeschlossen, nicht der Transfer |
| **Neutrale Zeile** (Kredittilgung) | **nein** | ja, voller Ratenbetrag | `buchungszeile.neutral = 1` |
| Kreditzins | ja, als Ausgabe | im Ratenbetrag enthalten | |
| **Auslage** | bei der Sparte der **Buchung**, nicht beim Zahler | beim Konto des Zahlers | |
| **Ausgleich** | **nirgends** | ja, Transfer zwischen zwei Konten | erzeugt keine Buchung |
| Kassadifferenz | ja | ja | |
| Gelöschte Buchung | nein | nein | Storno gibt es erst ab P51 |

### 10.2 Festlegungen, die vorher offen waren

- **Verein-Ausschluss ausschließlich über `sparte.bereich_id`.** Nicht über `sparte.typ='verein'`,
  nicht über `geschuetzt`. Diese beiden Felder sind ab jetzt rein informativ. (Schuld B2)
- **Quelle der Wahrheit** (Schuld B3): Einnahmen- und Ausgabensummen kommen aus den Buchungen
  (`v_einnahmen_ausgaben`), Kontostände aus den Bewegungen (`bewegung`). Niemals mischen.
- **Konten in der Übersicht:** Summe **je Währung**, nie über Währungen hinweg. `stand_cent` darf
  `null` sein, wenn kein Anker existiert — eine Kassa ohne Anker wird **nicht** als 0 ausgewiesen.
- **Ist und Erwartung:** Ist ist `datum <= stichtag`. Vordatierte Buchungen des laufenden Jahres
  zählen weder ins Ist noch zusätzlich in die Erwartung. `richtung` filtert `buchung.typ`, nicht
  `kategorie.richtung`.

### 10.3 Cursor

Ein Format für alle Listen: Base64 von `datum|id`, **mit `id` als Tiebreaker** bei gleichem Datum.
Ohne Tiebreaker entstehen Lücken, sobald mehrere Buchungen dasselbe Datum tragen — genau der Fall
im Test mit 250 Buchungen. Der bestehende Cursor in `app/routers/konten.py` (`datum_id`) wird auf
dasselbe Format umgestellt.

### 10.4 Regressionsschutz vor dem Umbau

**Zuerst** Snapshot-Tests der heutigen Antworten von `/api/dashboard`, `/api/jahresvergleich`,
`/api/verlauf` und `/api/buchungen/suche` anlegen (echte Testdaten, Antwort als erwartetes JSON
festhalten), **dann** die Logik nach `app/rechenbasis.py` ziehen. `scripts/test_drilldown_api.py`
ist ein Skript und zählt nicht als Test.

### 10.5 Nicht Teil dieses Pakets

Die Schulden A3 (zwei Runner-Semantiken) und A4 (Ad-hoc-Schema in `db.py`) waren früher hier
verortet. Sie werden separat behandelt und gehören **nicht** in P20. Dieses Paket ist ohnehin das
schwerste; es trägt keine Fremdaufgaben.

### 10.6 Laufzeit

Das Kriterium (Übersicht unter 300 ms) wird mit einem Seed von 5.000 Buchungen geprüft; das
Seed-Skript gehört zum Paket. Kennzahlen dürfen nicht je Term in Python iterieren, sondern müssen
in einer Abfrage rechnen — sonst reißt die Übersicht die Grenze.
