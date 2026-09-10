# P60 – Runde 1: Export-Oberfläche für das Steuerpaket

Branch `pkt/p60-export-oberflaeche`, Worktree `wt-p60`. Umsetzung nach dem
gemeinsamen Nachtrag vom 10. September 2026
(`docs/neubau/pakete/NACHTRAG-frontend-2026-09-10.md`), dessen Konfliktregeln
Vorrang vor der Paketkarte `docs/neubau/pakete/P60-export-oberflaeche.md` haben.
Erlaubte Änderungen laut Auftrag: ausschließlich `static-neu/pages/export.js`
sowie neue Dateien `static-neu/pages/export*.css` und
`static-neu/pages/export-*.js`. Kein Commit, kein Push.

## 1. Geänderte/neue Dateien

| Datei | Beschreibung |
|---|---|
| `static-neu/pages/export.js` | Ersetzt den P30-Platzhalter durch die vollständige Export-Seite: Profil laden/anlegen, Ausschluss-Dialog (Kategorien/Buchungen), Vorschau, Steuerpaket-ZIP mit 409/422-Behandlung, Rohexporte als echte Links. |
| `static-neu/pages/export.css` | Neu angelegt (per Nachtrag erlaubt); Layout für Aktionsleisten, Suchschalter, Kategorie-Chips, Ausschluss-Dialog und Mobil-Anpassungen (`@media(max-width:760px)`). |
| `tests/test_p60_export.py` | Neu angelegt: Seitenauslieferung, die von `export.js` gelesenen Felder der Profil-/Vorschau-/Paket-/Buchungen-Endpunkte, Content-Type des ZIP, 409/422-Verträge, Bereich-2-Abgrenzung, `node --check`. |

Die Route `#/export` war bereits in `app.js` als Platzhalter-Eintrag vorhanden
(`export:['Export','export']`) und musste laut Nachtrag nicht angefasst
werden.

## 2. Verwendete Endpunkte mit wörtlichem Antwort-JSON

Aufgezeichnet mit dem FastAPI-Testclient (Wegwerf-DB, `FINANZ_TEST_AUTH_BYPASS=1`),
Sparte mit einer Testkategorie und einer Testbuchung (Ausgabe, 42,00 €).

### `GET /api/export/profil?bereich_id=1&sparte_id=1&jahr=2026`
Status 200, `application/json`:
```json
{
  "id": 1,
  "bereich_id": 1,
  "sparte_id": 1,
  "jahr": 2026,
  "name": "Steuer",
  "erstellt_am": "2026-09-10 19:37:38",
  "aktualisiert_am": "2026-09-10 19:37:38",
  "kategorie_ids": [],
  "buchung_ids": [],
  "ausschluesse": [],
  "revision": "9f0c42b90417db878b8f46be7857e1b58b94329aa3698ba9a44d4dcac36a22bc"
}
```

### `PUT /api/export/profil/{id}?bereich_id=1`
Body `{"kategorie_ids": [], "buchung_ids": []}` → Status 200, gleiche Form wie
oben (Felder `kategorie_ids`/`buchung_ids`/`revision` aktualisiert).

### `POST /api/export/profil/{id}/uebernehmen-vom-vorjahr?bereich_id=1`
Status 200, liefert das (ggf. unveränderte) Profil in derselben Form; ohne
Vorjahresprofil bleiben die Kategorie-Ausschlüsse einfach leer, es gibt keinen
Fehler.

### `POST /api/export/vorschau?bereich_id=1`
Body `{"profil_id": 1}` → Status 200, `application/json`:
```json
{
  "revision": "9f0c42b90417db878b8f46be7857e1b58b94329aa3698ba9a44d4dcac36a22bc",
  "zeilen": [
    {
      "buchung_id": 1,
      "datum": "2026-03-05",
      "text": "P60 Testbeleg",
      "kategorie": "P60-Test-Kategorie",
      "betrag_cent": 4200,
      "anteil_cent": 4200,
      "belege": []
    }
  ],
  "summen": {"anzahl": 1, "einnahmen_cent": 0, "ausgaben_cent": 4200},
  "ausgeschlossen": {"kategorien": 0, "buchungen": 0},
  "belege_fehlend": []
}
```

### `GET /api/export/xlsx?bereich_id=1&profil_id=1`
Status 200, `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`
(Binärdaten, nicht abgedruckt).

### `POST /api/export/paket?bereich_id=1`
Body `{"profil_id": 1, "revision": "<aktuelle revision>"}` → Status 200,
`application/zip` (Binärdaten, nicht abgedruckt; enthält laut Test
`INHALT.txt` und die `.xlsx`-Arbeitsmappe). Bei veralteter `revision` Status
409 mit `{"detail": "Revision des Export-Profils oder der Buchungen stimmt
nicht mehr"}`; bei fehlenden Belegen Status 422 mit `{"detail": "Belege
fehlen"}`, mit `trotz_fehlender_belege: true` danach wieder 200.

### `GET /export/bericht?bereich_id=1&profil_id=1&jahr=2026`
Status 200, `text/html`. **Achtung (siehe Abschnitt 5):** `jahr` ist laut
Routensignatur ein Pflichtparameter, auch wenn `profil_id` gesetzt ist und
`jahr` dann inhaltlich ignoriert wird. Ohne `jahr` antwortet die Route mit 422.
`export.js` hängt deshalb immer beide Parameter an den Link.

### `GET /api/buchungen?bereich_id=1&jahr=2026&sparte_id=1&limit=1000`
Nur lesend verwendet, um im Ausschluss-Dialog auch bereits ausgeschlossene
Buchungen wieder anzeigen zu können (die Vorschau liefert nur die aktuell
nicht ausgeschlossenen Zeilen). Status 200, `application/json`:
```json
{
  "buchungen": [
    {
      "id": 1, "sparte_id": 1, "sparte_name": "Privatvermietung",
      "datum": "2026-03-05", "typ": "ausgabe", "version": 1,
      "betrag_cent": 4200, "zahlungsart": "bank",
      "belegstatus": "beleg_fehlt", "buchungsstatus": "offen",
      "text": "P60 Testbeleg", "notiz": null, "transfer_gruppe_id": null,
      "kontakt_id": null, "kontakt_name": null,
      "zeilen": [
        {"buchung_id": 1, "id": 1, "kategorie_id": 1,
         "kategorie_name": "P60-Test-Kategorie", "betrag_cent": 4200,
         "notiz": null, "neutral": 0}
      ],
      "neutral_cent": 0, "belege": [], "zahlungsstatus": "Zahlung unbekannt",
      "bezahlt_von_sparte_id": null
    }
  ],
  "summen": {"einnahmen_cent": 0, "ausgaben_cent": 4200, "anzahl": 1},
  "naechster_cursor": null
}
```

## 3. Entwurfsentscheidungen

- **Zeitraum/Sparte aus dem zentralen Zustand:** Die Seite verwendet
  `state.sparteId` und den Wert von `#year-select` direkt, statt eigene
  Auswahlfelder zu bauen. Da `app.js` weder den Sidebar-Sparte-Buttons noch
  `#year-select` ein Rerender der aktuellen Seite mitgibt (nur
  `drawSidebar()`/lokale Zustandsänderung), hängt `export.js` zusätzliche
  `change`/`click`-Listener an diese vorhandenen Elemente, die die eigene
  `render()`-Funktion erneut aufrufen. Siehe „Wunsch an das Gerüst“.
- **Profilpflege als Dialog:** „Ausschlüsse bearbeiten“ öffnet den
  gemeinsamen `drill()`-Dialog aus `ui.js` mit Kategorie-Chips (ganze
  Kategorie ausschließen) und einer Buchungsliste mit Einzel-Checkbox;
  Änderungen werden erst mit „Speichern“ in einem `PUT` gebündelt, nicht bei
  jedem Klick.
- **Vollständige Buchungsliste über `GET /api/buchungen`:** Die
  Export-Vorschau liefert nur die aktuell *nicht* ausgeschlossenen Zeilen –
  ein bereits ausgeschlossener Posten lässt sich darüber nicht wieder
  einschließen. Da P60 laut Nachtrag nur an `export.js`/`export*.css`
  arbeiten darf und `app/routers/export.py` nicht erweitern soll, lädt der
  Dialog stattdessen (rein lesend) `GET /api/buchungen` für den gewählten
  Zeitraum/Sparte und zeigt daraus alle Buchungen, unabhängig vom aktuellen
  Ausschlussstand.
- **Steuerpaket bewusst kein reiner `<a href>`-Link:** Die Rohexporte (Excel,
  Jahresbericht) sind echte `<a href>`-Links auf die bestehenden GET-Endpunkte
  mit `bereich_id`- und `profil_id`-Parameter, wie gefordert. Der
  ZIP-Endpunkt `POST /api/export/paket` verlangt dagegen laut P16/P60-Karte
  einen JSON-Body mit `revision` und liefert 409 (veraltete Revision) bzw. 422
  (fehlende Belege) – das ist mit einem einfachen Link nicht abbildbar. Der
  Button ruft deshalb `fetch()` mit `credentials: 'same-origin'` und löst den
  Download über einen kurzlebigen `Blob`-Link aus (kein `api.js`, da dieses
  nur JSON verarbeitet). Diese Abweichung von „keine Blob-Downloads“ ist durch
  den serverseitigen Vertrag erzwungen und wird hier dokumentiert.
- **Bereich 2 (Verein):** Kein eigener Code nötig – `api.js` hängt
  `bereich_id` aus `state.bereichId`/`localStorage` an jeden Aufruf, und jeder
  Export-Endpunkt filtert serverseitig über `Bereich`/`bereiche.py` auf genau
  diesen Bereich. Die Seite bietet keine Möglichkeit, den Bereich der
  exportierten Daten unabhängig vom globalen Bereichsumschalter zu setzen;
  ein Test (`test_verein_bereich_sieht_nur_eigene_buchungen_im_export`)
  bestätigt, dass ein Bereich-2-Profil aus Bereich 1 nicht erreichbar ist.
- **„Vom Vorjahr übernehmen“ immer sichtbar:** Um festzustellen, ob ein
  Vorjahresprofil existiert, müsste vorab `GET /api/export/profil` fürs
  Vorjahr aufgerufen werden – das legt laut Router bei Bedarf automatisch ein
  neues (leeres) Profil an. Um diesen unerwünschten Nebeneffekt zu vermeiden,
  ist der Button immer sichtbar (mit erklärendem Hinweistext); ruft man ihn
  ohne Vorjahresprofil auf, bleibt die Kategorienliste einfach leer.

## 4. Testausgabe (Kurzfassung)

Eigener, isolierter Nachweis (`tests/test_p60_export.py`, Wegwerf-DB):
**15 Tests, 0 Fehler, 0 Failures** (`OK`). Enthält auch `node --check` auf
`static-neu/pages/export.js`.

Gesamtsuite (`python -m unittest discover -s tests`, neue Wegwerf-DB):
**313 Tests, 6 Failures, 1 Skip** (`FAILED (failures=6, skipped=1)`, Laufzeit
ca. 507 s auf einer gemeinsam genutzten Maschine mit mehreren parallelen
Paket-Worktrees). Alle sechs Failures liegen in `test_auth.py` und
`test_auth_lifecycle.py` (Integrationstests, die einen echten HTTP-Server auf
einem Socket starten und dann prüfen, dass ungültige/fehlende Anmeldung
tatsächlich mit 401/403 abgewiesen wird – in dieser Sandbox greift diese
serverseitige Durchsetzung offenbar nicht, laut Nachtrag ein bekanntes
Sandbox-Verhalten: „Startet die Auth-Suite in der Sandbox nicht, das im
Bericht sagen und die eigene Testdatei isoliert grün zeigen.“). Keine der
sechs Failures betrifft Export/P60. Der isolierte Nachweis
(`test_p60_export.py`) läuft unabhängig davon grün: **15 Tests, 0 Fehler**.
Vollständige Ausgabe beider Läufe in `docs/neubau/berichte/P60-tests.txt`.

## 5. Wunsch an das Gerüst

1. `GET /export/bericht` verlangt `jahr` als Pflichtparameter, auch wenn
   `profil_id` gesetzt ist (dann wird `jahr` im Code gar nicht gelesen). Ein
   sauberer Fix wäre, `jahr` optional zu machen, wenn `profil_id` vorhanden
   ist. Bis dahin hängt `export.js` beide Parameter an den Link.
2. `app.js` verdrahtet `#year-select` gar nicht und den Sidebar-Sparte-
   Buttons sowie `#sparte-select` nur `drawSidebar()`, ohne die aktuelle
   Seite neu zu rendern. Jede Seite, die auf Zeitraum/Sparte reagieren muss,
   braucht deshalb eigene, redundante Listener auf dieselben globalen
   Elemente. Ein globaler Hook (z. B. ein `sparte`/`jahr`-Change-Event, auf
   das `render()` selbst lauscht) würde das für alle Pakete vereinfachen.
3. Es gibt keinen Endpunkt, der für ein Profil *alle* Buchungen des
   Zeitraums liefert (inklusive bereits ausgeschlossener). `export.js`
   behilft sich mit dem allgemeinen `GET /api/buchungen`, das aber andere
   Felder/Struktur als `POST /api/export/vorschau` hat (z. B. `zeilen[].neutral`
   statt `belege_fehlend`) und keine Belegprüfung mitliefert. Ein optionaler
   Parameter an `/api/export/vorschau` (z. B. `alle: true`), der auch
   ausgeschlossene Zeilen mit einem `ausgeschlossen`-Flag zurückgibt, wäre
   für diese Art Oberfläche deutlich passender.

## 6. Im Browser nicht geprüft

Es stand kein echter Browser (Playwright/Chrome) in dieser Umgebung zur
Verfügung. Geprüft wurde:
- `GET /neu/` und `GET /neu/pages/export.js` sowie `/neu/pages/export.css`
  live gegen `uvicorn` (Port 8160, Wegwerf-DB, `FINANZ_TEST_AUTH_BYPASS=1`):
  alle Statuscode 200.
- Alle sechs P16-Endpunkte über den FastAPI-Testclient mit echten Test-Daten
  (siehe Abschnitt 2), inklusive 409-/422-Fehlerpfad und ZIP-Inhalt.
- `node --check` auf `static-neu/pages/export.js` fehlerfrei.

Nicht geprüft werden konnten (und bleiben offen):
- Das tatsächliche Verhalten des Ausschluss-Dialogs im Browser (Kategorie
  anklicken deaktiviert Zeilen-Checkboxen, Fokus-Erhalt beim Tippen in der
  Dialog-Suche, `inert`/Fokusfalle von `ui.js`).
- Der 409-Hinweis-Toast und die automatische Vorschau-Aktualisierung bei
  veralteter Revision, ausgelöst durch echtes Klicken statt direkten
  API-Aufruf.
- Der 422-Bestätigungsdialog „trotzdem exportieren“ und der tatsächliche
  Blob-Download im Browser (Dateiname aus `Content-Disposition`).
- Die responsive/mobile Darstellung unter 760 px (Layout wurde nur anhand
  vorhandener CSS-Variablen/Klassenmuster aus `style.css` und dem Prototyp
  gebaut, nicht gerendert).

## 7. Offene Punkte

- Browserprüfung (siehe Abschnitt 6) steht aus; der Kopf müsste sie
  nachholen, sofern Playwright in dieser Umgebung nicht verfügbar ist.
- `GET /export/bericht`-Pflichtparameter `jahr` (siehe „Wunsch an das
  Gerüst“, Punkt 1) ist ein bestehender Rand-Bug in `export.py`, den P60
  laut Auftrag nicht selbst beheben darf.
- „Vom Vorjahr übernehmen“ ist immer sichtbar statt bedingt (siehe
  Abschnitt 3) – bewusste Entscheidung, um keinen leeren Profil-Datensatz
  fürs Vorjahr allein zur Sichtbarkeitsprüfung anzulegen.
- Die Buchungsliste im Ausschluss-Dialog ist auf 1000 Zeilen pro
  Sparte/Jahr begrenzt (Limit von `GET /api/buchungen`); bei mehr Buchungen
  zeigt die Seite einen Hinweis, lädt aber keine weiteren Seiten nach.
