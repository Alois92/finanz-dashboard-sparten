# P20: Gemeinsame Rechenbasis, Übersicht, Jahresmatrix, Buchungsliste mit Cursor

Meilenstein M2. Modell: `gpt-6-astra`, Aufwand high. Branch `pkt/p20-auswertungen` von `neubau` (nach M1).

## 1. Ziel

Alle Auswertungen rechnen über einen gemeinsamen Filter und dieselben Funktionen, damit Übersicht, Matrix, Drilldown und Buchungsliste nie widersprüchliche Zahlen zeigen. Das laufende Jahr wird nach Saison hochgerechnet (Ist plus Vorjahresrest ab Stichtag), der Stichtag kommt vom Server.

## 2. Kontext

Lies `docs/neubau/ARCHITEKTUR.md` Abschnitt 8, dann `app/routers/dashboard.py` (bestehende `/api/dashboard`, `/api/jahresvergleich`, `/api/verlauf`, `_where`), `app/routers/buchungen.py` (`GET /api/buchungen`, `/api/buchungen/suche`), `app/routers/gruppen.py`, `app/bereiche.py`, `app/kennzahlen.py` (P15), `app/routers/auslagen.py` (P12), `app/konten.py` (P13), `db/schema.sql` (Views), `tests/test_buchungen_suche.py`, `scripts/test_drilldown_api.py`. Fachliche Vorgaben aus dem Prototyp: Hinweise (Kostenanstieg hochgerechnet, fehlende regelmäßige Einnahme erst fünf Tage nach dem üblichen Tag, offene Auslagen, größte Einzelbuchung, offene Bankumsätze, Anteil der größten Kategorie), Kacheln mit Ist „bisher", Kennzahlen mit Jahreserwartung.

## 3. Schnittstellen

Neues Modul `app/auswertungen.py`:

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
    stichtag: str | None = None        # Standard: heute in Europe/Vienna

def filter_dep(...) -> Filter                     # FastAPI-Dependency aus Query-Parametern, prüft Bereich und Sparten-/Gruppen-Zugehörigkeit
def sparten_ids(con, f: Filter) -> list[int]      # Sparte, Gruppe oder alle Sparten des Bereichs (ohne Verein im Hauptbereich)
def where_zeilen(con, f) -> tuple[str, list]      # WHERE auf v_einnahmen_ausgaben (Umbuchungen, neutral, storniert ausgeschlossen)
def summen(con, f) -> dict                        # {einnahmen_cent, ausgaben_cent, saldo_cent}
def monatsreihe(con, f) -> dict                   # {einnahmen: [12], ausgaben: [12]}
def je_kategorie(con, f) -> list[dict]            # [{kategorie_id, name, sparte_id, aktiv, einnahmen_cent, ausgaben_cent}]
def stichtag_heute() -> str                       # Europe/Vienna, ISO
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
 → {buchungen: [...wie bisher plus auslage, neutral_cent, version, storniert_am], summen: {anzahl, einnahmen_cent, ausgaben_cent}, naechster_cursor}
   Cursor = base64 von "datum|id" der letzten Zeile; Summen über alle Treffer, nicht nur die Seite
GET /api/buchungen/suche  → delegiert an GET /api/buchungen mit q (bleibt aus Kompatibilität)
GET /api/hinweise/aus  und  POST /api/hinweise/aus {schluessel, bis_wert}   → ausgeblendete Hinweise (Tabelle hinweis_aus)
```

Migration `db/migrations/009_hinweis_aus.sql`: `hinweis_aus(schluessel TEXT PRIMARY KEY, bis_wert TEXT, erstellt_am)`. Ein Hinweis erscheint wieder, wenn sein aktueller Wert (im Schlüssel kodiert, z. B. Prozent auf 5 gerundet oder Cent) von `bis_wert` abweicht.

Regeln:
- Verein-Sparten (Bereich 2) tauchen im Hauptbereich nirgends auf; im Bereich 2 sind sie die einzigen.
- Überlappende Gruppen: Sparten-IDs als Menge, keine Doppelzählung.
- Drilldown ist derselbe Endpoint `GET /api/buchungen` mit denselben Filterparametern plus `kategorie_id`/`monat`; die Zahl auf der Kachel und die Summe der Liste stimmen überein (Test).
- Hinweise: „fehlende regelmäßige Einnahme" nur, wenn die Kategorie im Vorjahr in mindestens 11 Monaten Einnahmen hatte, im aktuellen Monat keine, und der Stichtag ≥ üblicher Tag (Median der Vorjahrestage) + 5.
- Erwartung nur für das Stichtagsjahr; für abgeschlossene Jahre `null`. Kategorien ohne Vorjahr: Erwartung = Ist mit Kennzeichen `ohne_vorjahr`.

## 4. Nicht-Ziele

Kein Frontend. Keine Export-Änderung (M6). Keine Kennzahl-Definition (P15), nur deren Wert im Sparten-Kontext mitliefern, falls einfach.

## 5. Schritte

1. `app/auswertungen.py` mit Filter und Funktionen; bestehende `_where`-Logik dorthin ziehen.
2. `/api/uebersicht`, `/api/jahresmatrix`, Cursor-Buchungsliste, Hinweise, Migration 009.
3. Bestehende Endpoints auf die neuen Funktionen umstellen (gleiche Antworten wie bisher, Regression durch bestehende Tests).
4. Tests, Gesamtlauf, Bericht.

## 6. Tests

Neue Datei `tests/test_auswertungen.py` mit reproduzierbarem Seed (feste Buchungen in zwei Jahren, zwei Sparten, Verein-Sparte, Umbuchung, neutrale Zeile, stornierte Buchung):
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
