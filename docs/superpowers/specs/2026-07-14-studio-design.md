# Design-Spezifikation: „Studio" — dritte Dashboard-Variante

Datum: 2026-07-14 · Status: vom Benutzer freigegeben · Branch: `studio`

## Kontext und Ziel

Das Finanz-Dashboard hat zwei Oberflächen: die alte unter `/` (static/) und das dunkle
„Cockpit" unter `/cockpit` (static-cockpit/, Branch `cockpit-redesign`). Der Benutzer
wünscht eine **dritte, parallele Variante** mit komplett neuem, modernem Design:
Desktop-stark, aber **voll am Handy bedienbar inklusive Buchungserfassung** (späterer
Zugriff via Tailscale geplant). Hell und Dunkel **umschaltbar**. Alle vier Auswertungs-
schwerpunkte auf der Startseite: Verlauf, Sparten-Vergleich, Kategorien-Ranking,
Trend-Signale.

## Entscheidung

- Neues Verzeichnis `static-studio/`, gemountet unter `/studio` (dritter
  StaticFiles-Mount in `app/main.py`). Alt und Cockpit bleiben unangetastet.
- **Kein neuer Backend-Endpoint.** Signale und Vorjahresvergleiche werden im Browser
  aus den vorhandenen APIs berechnet: `/api/dashboard`, `/api/verlauf`,
  `/api/jahresvergleich` (inkl. `per_kategorie`), `/api/sparten`, `/api/kategorien`,
  `/api/buchungen`, `/api/vorschlag`, `/api/belege`, `/api/bankimport`.
- Graphen selbstgebaut als Inline-SVG (wie Cockpit, keine Fremd-Library, offlinefähig).
- Schriften lokal (`static-studio/fonts/`), keine externen Requests.

## Gestaltung

- **Charakter:** ruhig, hochwertig, Banking-App-artig. Karten mit feinen Rändern/Schatten,
  großzügiger Weißraum.
- **Themes:** CSS-Variablen; Standard folgt `prefers-color-scheme`, Umschalter im
  Kopfbereich, Wahl in `localStorage`. Hell: fast weiß, Anthrazit-Text. Dunkel: tiefes
  Blau-Anthrazit (kein reines Schwarz), helle Karten-Abstufung.
- **Akzent:** Smaragdgrün für Einnahmen/positiv, warmes Rot für Ausgaben/negativ.
  Sparten behalten je eine feste Kennfarbe (Palette wie Cockpit, nach Sortierung).
- **Typografie:** UI-Schrift humanistisch (lokal gebundelt), Zahlen tabellarisch
  (font-variant-numeric bzw. Mono-Ziffern) für saubere Spalten.

## Layout

- **Desktop (≥ 900 px):** schmale Seitenleiste links mit Navigation
  (Übersicht, Auswertungen, Buchungen, Erfassen, Kategorien, Belege, Bankimport)
  + Theme-Umschalter. Oben im Inhalt: Zeitraum-Schnellwahl
  (Dieses Jahr / Letztes Jahr / 12 Monate / Alles) und Sparten-Filter als Pills.
- **Mobil (< 900 px):** Seitenleiste weg; stattdessen fixe Bottom-Navigation mit den
  wichtigsten Zielen (Übersicht, Auswertungen, **Erfassen** mittig hervorgehoben,
  Buchungen, Mehr). „Mehr" öffnet die restlichen Seiten. Touch-Ziele ≥ 44 px,
  Erfassen-Formular als Vollbild-Ansicht.

## Startseite „Übersicht" (von oben nach unten)

1. **Signal-Karten** (automatisch berechnet, max. 3): stärkster Kostenanstieg
   (Kategorie, Vergleich Vorperiode), größte Einnahmequelle, Hochrechnung Jahresende
   (lineare Projektion aus Monatsdurchschnitt). Bei zu wenig Daten: Karte ausblenden.
2. **KPI-Karten:** Einnahmen / Ausgaben / Saldo; Sparkline als eigener Streifen
   **unter** der Zahl (Regel aus Cockpit-Feedback: nie überlappen).
3. **Verlaufs-Graph groß:** Balken Einnahmen/Ausgaben + Saldo-Linie; Umschalter
   Monats-/Jahresansicht.
4. **Sparten-Vergleich:** je Sparte eine Zeile mit Einnahmen- und Ausgaben-Balken
   (gemeinsame Skala) + Saldo-Zahl.
5. **Kategorien-Ranking:** zwei Spalten (Top-Ausgaben, Top-Einnahmen), je mit
   Veränderung zum Vorjahr als ▲/▼ und Prozent; ohne Vorjahresdaten ohne Pfeil.

## Weitere Seiten

Funktional identisch zum Cockpit (gleiche API-Aufrufe), im Studio-Stil:
Auswertungen (Jahresvergleich gesamt/Sparte/Kategorie), Buchungen (Liste + Filter),
Erfassen (Formular + Schnellerfassung mit `/api/vorschlag`), Kategorien, Belege,
Bankimport. Umbuchungen bleiben in Auswertungen ausgeblendet (wie bisher).

## Fehlerverhalten

- API-Fehler: dezente Fehlerkarte mit Meldung statt leerer Fläche, Rest der Seite
  bleibt nutzbar.
- Leere DB: freundlicher Leerzustand mit Hinweis auf „Erfassen".

## Tests / Verifikation

- Wegwerf-DB über `FINANZ_DB` (niemals gegen die echte NAS-DB testen).
- Playwright: Desktop- und Mobil-Viewport (375 px) durchklicken, Screenshots;
  prüfen: Theme-Umschalter, Bottom-Nav am Handy, Erfassen am Handy, Signale,
  Ranking-Pfeile, keine Überlappungen.
- Echte DB vor/nach Testlauf unverändert (Buchungen zählen).

## Nicht-Ziele

- Kein Umbau von `/` oder `/cockpit`, keine Schema-Änderungen, kein Login,
  kein Server-Rendering, keine Fremd-Chart-Library.
