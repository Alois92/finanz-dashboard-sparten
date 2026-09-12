# Sicherheitsaudit run-1 — Behebung (12. September 2026)

Grundlage: `docs/neubau/berichte/SECURITY-AUDIT-run1.md` /
`SECURITY-AUDIT-run1-findings.json` (Ziel `neubau` d5df927). Bearbeitet im
Worktree `C:\Users\lblet\dev\wt-sec`, Branch `fix/security-audit-run1`. Je
Befund: Regressionstest zuerst rot, dann Fix, dann grün, eigener Commit.

| Nr. | Commit |
|---|---|
| F4 | `25cf700` |
| F1 | `e027cdc` |
| F2 | `0bbf01b` |
| F3 | `6e990ca` |
| F5 | `5899835` |
| F7 | `826b2a8` |
| F6 | `70cbaf6` |
| F8 | `c91ccec` |

Reihenfolge folgt der Empfehlung des Audits (F4/F1 zuerst, dann F2/F3, dann
F5/F6/F7, F8 zuletzt).

## F4 — Backup-Rotation löschte den Belege-Store (HOCH)

- **Test vorher rot:** `tests/test_backup.py::test_bereinigung_loescht_nur_unreferenzierte_store_dateien`
  (32 Tageskopien, Beleg A ändert sich nach der ältesten Kopie, Beleg B bleibt
  unverändert). Ohne Fix wurde beim ersten automatischen `_rotiere`-Aufruf
  (ausgelöst durch `_sichere_belege`, sobald mehr als 30 Tageskopien existieren)
  bereits der gesamte Store geleert — Testinstrumentierung (`wraps=_bereinige_store`)
  bestätigt, dass die Funktion lief.
- **Fix:** `_bereinige_store` sammelt Referenzen jetzt als aufgelöste Store-Pfade
  (`_store_pfad(...).resolve()`) und vergleicht `pfad.resolve()` dagegen, statt
  `(sha256, Originalname)` gegen `(sha256, Endung)` zu vergleichen (die nie
  gleich sein konnten).
- **Test nachher grün:** referenzierte Dateien (aktueller Hash von A, Hash von B)
  bleiben erhalten, der verwaiste alte Hash von A wird gelöscht;
  `pruefe_sicherung(<behaltener Tag>)["belege_fehlend"] == 0`. Restliche
  20 Tests in `test_backup.py` weiterhin grün.
- Abweichung: keine.

## F1 — Gespeicherte XSS über Kategorienamen (HOCH)

- **Test vorher rot:**
  - `tests/test_auth.py::test_content_security_policy_wird_gesetzt` (kein
    CSP-Header vorhanden).
  - `tests/test_f1_kategorie_name.py` (POST/PATCH `/api/kategorien` mit
    `<img src=x onerror=...>` bzw. 81 Zeichen liefen mit 201/200 durch).
  - `tests/test_import_excel.py::test_boesartiger_spaltenkopf_erzeugt_warnung_und_keine_kategorie`
    (Spaltenkopf mit Payload wurde unverändert zur Kategorie).
- **Fix:**
  - `static-neu/pages/uebersicht.js`: `${esc(h.text)}` statt `${h.text}` im
    einzigen ungeschützten Sink der Datei.
  - `app/auth.py::_secure_headers`: `Content-Security-Policy: default-src 'self';
    script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:;
    font-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'`.
  - Geprüft, ob beide Frontends Inline-Skripte/externe Quellen nutzen
    (`grep -rn "<script"`/`"on[a-z]*="` über `static-neu/index.html`,
    `static-studio/*.html`): je ein Inline-Theme-Skript im Kopf, sonst keine
    Inline-Handler und keine externen Skript-/Font-Quellen (Fonts liegen
    self-hosted unter `static-neu/fonts/`, `static-studio` nutzt `@font-face`
    ohne externe URL). Beide Theme-Skripte nach `theme-init.js` ausgelagert
    statt Hash/Nonce zu verwalten. Inline-`style="..."`-Attribute (in mehreren
    `.js`-Dateien per `innerHTML` gesetzt) bleiben über `style-src 'unsafe-inline'`
    erlaubt.
  - `app/schemas.py::kategorie_name_gueltig` (max. 80 Zeichen, kein `<`/`>`,
    keine Steuerzeichen), verwendet in `stammdaten.py` (POST/PATCH → 422) und
    `import_excel.py` (Spaltenkopf → `warne()`, keine Kategorie).
- **Test nachher grün:** CSP-Header vorhanden, XSS-Payload/Überlänge → 422,
  Spaltenkopf-Payload → Warnung statt Kategorie (auch beim `einspielen`-Modus
  keine Zeile in `kategorie`). `node --check` für `uebersicht.js`,
  `theme-init.js` (beide Frontends) ohne Fehler.
- Abweichung: keine.

## F2 — Wettlauf bei Rückerstattungen (HOCH)

- **Test vorher rot:** `tests/test_f2_erstattung_race.py` gegen echte
  Server-Instanz (eigener uvicorn-Prozess, echte Anmeldung), 8 parallele
  `POST /api/buchungen/{id}/erstatten` über `ThreadPoolExecutor` — vorher 3 von
  8 mit 201 (statt 1), `netto_cent` negativ.
- **Fix:** Rest-Prüfung zusätzlich im `nach_anlage`-Hook wiederholt, der
  innerhalb der `BEGIN-IMMEDIATE`-Transaktion von `erstelle_buchung` läuft;
  eine `HTTPException` dort rollt die neue Erstattung vollständig zurück.
  Kein zweites `BEGIN IMMEDIATE`.
- **Test nachher grün:** genau eine 201, Rest 422, `netto_cent == 0`.
  `tests/test_p51_storno.py` (12 Tests) weiterhin grün.
- Abweichung: keine.

## F3 — Wettlauf bei „Beleg-Auswertung übernehmen“ (HOCH)

- **Test vorher rot:** `tests/test_f3_uebernahme_race.py`, 8 parallele
  `POST /api/beleg-auswertungen/{id}/uebernehmen` mit je eigener
  `client_request_id` gegen eine echte Server-Instanz — vorher 7 von 8 mit 201
  (statt 1), mehrere Buchungen aus einem Beleg.
- **Fix:** Statuswechsel als bedingtes `UPDATE ... WHERE status='fertig'`
  innerhalb der Transaktion von `erstelle_buchung`; `rowcount != 1` → 409.
- **Test nachher grün:** genau eine 201/Buchung, Rest 409, Status `verbucht`.
  `tests/test_beleg_auswertung.py` (11 Tests) und `tests/test_p43_foto.py`
  (6 Tests) weiterhin grün.
- Abweichung: keine.

## F5 — Pfadausbruch beim Beleg-Upload (MITTEL, nur Windows)

- **Test vorher rot:** `tests/test_f5_upload_pfadausbruch.py` — Dateiname
  `../../../../evil.png` landete zwei Ebenen über dem Belegordner; Dateiname
  mit `/` bzw. 250 Zeichen führte zu `FileNotFoundError` (500).
- **Fix:** `original = pathlib.Path(...).name` (Basisname), Steuerzeichen
  entfernt, auf 120 Zeichen gekürzt (Endung bleibt erhalten); vor dem
  Schreiben `ziel.resolve().relative_to(basis)` geprüft (`ValueError` → 400);
  `OSError` beim Schreiben → 400 statt 500.
- **Test nachher grün:** Traversal-Dateiname bleibt im Belegordner,
  Schrägstrich/Überlänge → 201. `tests/test_bereiche.py` (14 Tests) und
  `tests/test_p71_pdf.py` (7 Tests) weiterhin grün.
- Abweichung: keine.

## F7 — Kein Größenlimit für Uploads/Importe (NIEDRIG)

- **Test vorher rot:** `tests/test_f7_upload_limit.py` (Limit im Test per
  Monkeypatch auf 10 Bytes gesetzt) — Beleg-Upload lief mit 201 durch,
  CSV-/Excel-Import scheiterten mit anderen Fehlern (400/500), statt die
  Datei gar nicht erst vollständig einzulesen.
- **Fix:** neues Modul `app/uploads.py` mit `MAX_UPLOAD_BYTES` (25 MB) und
  `lies_upload(datei, maximal=None)`, das `maximal+1` Bytes liest und bei
  Überschreitung 413 wirft; verwendet in `belege.py:106`, `import_bank.py:235`
  (jetzt `lies_upload`), `import_excel.py:289`. Das Limit wird bei jedem
  Aufruf frisch aus dem Modul gelesen (nicht als Default-Parameter gebunden),
  damit es per Monkeypatch testbar bleibt.
- **Test nachher grün:** alle drei Endpunkte liefern 413 bei Überschreitung.
  `tests/test_import_excel.py` (7 Tests) und `tests/test_p42_bankimport.py`
  (8 Tests) weiterhin grün.
- Abweichung: keine.

## F6 — Schreibschutz-Middleware vor Gerätefilter/Anmeldung (NIEDRIG)

- **Test vorher rot:** `tests/test_f6_middleware_reihenfolge.py` —
  `app.build_middleware_stack()` zeigte `AuthMiddleware` erst NACH
  `BaseHTTPMiddleware` (Schreibschutz), also außen; ein nicht freigegebenes
  Gerät bzw. eine fehlende Session bekamen im schreibgeschützten Zustand 503
  mit vollem Migrationsfehlertext statt 403/401.
- **Fix:** `schreibschutz_middleware` wird jetzt über
  `app.add_middleware(BaseHTTPMiddleware, dispatch=schreibschutz_middleware)`
  **vor** `AuthMiddleware`/`TrustedHostMiddleware` registriert (Starlette baut
  den Stack umgekehrt: zuerst registriert = innen, näher am Router). 503-Text
  generisch ("Datenbank derzeit schreibgeschuetzt"); Details bleiben über den
  angemeldeten `/api/schema`-Endpunkt abrufbar.
- **Test nachher grün:** Stack-Reihenfolge TrustedHost → Auth → Schreibschutz
  → Router; nicht freigegebenes Gerät → 403, keine Session → 401, beides ohne
  Migrationsfehler im Body.
- **Bestehende Tests angepasst** (prüften vorher den Detailtext bzw. setzten
  die alte Reihenfolge voraus):
  - `tests/test_migrate.py::test_schreibschutz_blockiert_post_aber_nicht_get`:
    prüft jetzt den generischen Text und zusätzlich `GET /api/schema` auf den
    Detailwert.
  - `tests/test_p72_betrieb.py::BetriebSicherungSchreibschutzTest`: der
    bestehende Test lief bisher bewusst unauthentifiziert (Moduldocstring:
    „schreibschutz_middleware greift vor der Auth-Prüfung“) — das ist exakt
    der behobene Fehler. Test bekommt jetzt eine (Bypass-)Session, um die
    Middleware zu erreichen, prüft den generischen Text; neuer Test
    `test_nicht_freigegebenes_geraet_bekommt_403_nicht_503` belegt, dass ein
    nicht freigegebenes Gerät 403 bekommt statt die Middleware zu erreichen.
  Beide Anpassungen sind im selben Commit wie der Fix enthalten.
  - Nachtrag (bei der Gesamtsuite gefunden): `tests/test_bereiche.py::
    test_fehlendes_bereichsschema_bleibt_kontrolliert_gesperrt` ist über
    `import test_bereiche as bereiche_tests; class X(bereiche_tests.BereicheTest)`
    in neun weiteren Testdateien wiederverwendet und prüfte für **beide**
    Anfragen (`GET /api/sparten`, `POST /api/buchungen`) den Text `"Nachzug"`.
    Das GET-503 kommt aber gar nicht von der schreibschutz_middleware, sondern
    von `BereichDep` selbst (fehlendes Bereichsschema) und behält seinen Text;
    nur das POST-503 kommt von der Middleware und hat jetzt den generischen
    Text. Test entsprechend aufgeteilt (separate Assertions je Methode) und
    zusätzlich `GET /api/schema` auf den Detailwert geprüft. Dieser Fund kam
    erst beim Lauf der Gesamtsuite zum Vorschein (Einzeltests der neuen Dateien
    prüften diesen geerbten Testfall nicht separat) und wurde in einem eigenen
    Nachtrags-Commit behoben (siehe Commit-Tabelle oben).
- Abweichung: die im Audit vorgeschlagene Fix-Snippet-Form
  (`app.add_middleware(BaseHTTPMiddleware, dispatch=schreibschutz_middleware)`)
  wurde übernommen; die Funktion selbst wurde von `@app.middleware("http")`
  (Dekorator) auf eine normale Funktion umgestellt und vor die
  `add_middleware`-Aufrufe verschoben, damit sie zur Registrierung existiert.

## F8 — Migrationsprotokoll ohne Bereichsfilter (NIEDRIG)

- **Test vorher rot:** `tests/test_migrationsprotokoll.py::test_eintraege_anderer_bereiche_sind_nicht_sichtbar`
  (je eine Buchung in Bereich 1 und 2, je ein `migrationsprotokoll`-Eintrag
  mit `buchung:<id>`) — `GET .../migrationsprotokoll?bereich_id=1` zeigte
  beide Einträge.
- **Fix:** `buchung:<id>`-Einträge werden über `buchung JOIN sparte` auf
  `bereich_id` gefiltert; `umbuchungsgruppe:<id>`-Einträge über
  `buchung.transfer_gruppe_id` (Spalte existiert bereits, siehe
  `db/migrations/004_konten_bewegungen.py`/`012_migrationsprotokoll.py`).
  Einträge ohne Buchungsbezug (anderes/unbekanntes `objektkennung`-Format)
  bleiben sichtbar.
- **Test nachher grün:** Bereich 1 sieht nur seinen Eintrag, Bereich 2 nur
  seinen; Einträge ohne Buchungsbezug bleiben in beiden Bereichen sichtbar.
  Bestehender Test `test_endpunkt_liefert_protokoll_mit_bereichsdependency`
  angepasst: die `umbuchungsgruppe:offen`-Fixture braucht jetzt eine passende
  Buchung im Haupt-Bereich, sonst würde sie korrekterweise herausgefiltert.
- Abweichung: Endpunkt wurde gefiltert statt entfernt (Alternative laut
  Audit), da kein Frontend ihn zwar nutzt, aber ein informativer,
  bereichssicherer Diagnose-Endpunkt weiterhin nützlich ist.

## Doku

- `docs/SICHERHEIT.md`: korrigiert, dass die App die Geräteadresse nicht
  selbst aus Tailscale-/Proxy-Headern liest, sondern über `request.client`,
  das uvicorn bei aktivierter Proxy-Header-Auswertung befüllt; Hinweis auf die
  jetzt korrekte Middleware-Reihenfolge (Gerätefilter/Anmeldung vor jeder
  Anwendungslogik, auch vor dem Schreibschutz).
- `docs/BETRIEB-UND-ARCHITEKTUR.md` Abschnitt 11: neuer Prüfschritt 4b —
  `ExecStart` auf `--proxy-headers --forwarded-allow-ips=127.0.0.1` prüfen,
  danach Test von einem nicht freigegebenen Tailnet-Gerät (erwartet 403) und
  mit gefälschtem `X-Forwarded-For`-Header von dort (weiterhin 403).
- `docs/neubau/SCHULDEN.md`: neuer Abschnitt „Sicherheitsaudit run-1 (12.09.)“
  mit der F1–F8-Tabelle (alle behoben) und den Härtungsnotizen als offene
  Kleinkram-Punkte (Mindestpasswortlänge, Recovery-Race, `/docs` abschalten,
  Warteschlangen-Cap, Sicherungs-Rate-Limit, `.gitignore`,
  `umstellung_pruefung.py` https-only, `FINANZ_TEST_AUTH_BYPASS`-Kopplung,
  IPv6-Vergleich, starlette-Update, ExecStart-Flags für die Umstellung).

## Offene Punkte (keine Befunde des Audits, aber notiert)

Siehe Härtungsnotizen-Tabelle in `docs/neubau/SCHULDEN.md`, Abschnitt
„Sicherheitsaudit run-1“. Keiner davon war Teil des Auftrags F1–F8; alle acht
Befunde sind behoben.

## Suite-Ergebnis

`tests/test_backup.py`, `tests/test_auth.py`, `tests/test_f1_kategorie_name.py`,
`tests/test_import_excel.py`, `tests/test_f2_erstattung_race.py`,
`tests/test_p51_storno.py`, `tests/test_f3_uebernahme_race.py`,
`tests/test_beleg_auswertung.py`, `tests/test_p43_foto.py`,
`tests/test_f5_upload_pfadausbruch.py`, `tests/test_bereiche.py`,
`tests/test_p71_pdf.py`, `tests/test_f7_upload_limit.py`,
`tests/test_p42_bankimport.py`, `tests/test_f6_middleware_reihenfolge.py`,
`tests/test_migrate.py`, `tests/test_p72_betrieb.py`,
`tests/test_migrationsprotokoll.py` wurden einzeln nach jedem Fix grün
verifiziert. Gesamtsuite-Ergebnis: siehe `docs/neubau/berichte/SECURITY-fix-tests.txt`.
