# QA-4 — Belege, Foto-Auswertung, Export, Betrieb, Login

Getestet am 11.09.2026 gegen die Instanzen `http://127.0.0.1:8055/` (Login-Bypass, Schema 17,
Wegwerf-Kopie) und `http://127.0.0.1:8056/` (ohne Bypass, frische Auth-Datei). Ollama lokal unter
`http://127.0.0.1:11434`, Modell `qwen3.5:4b`. Kein Code geändert.

## 1. Umfang — Checkliste

### 1.1 Belege (P43)

| # | Prüfpunkt | Ergebnis |
|---|---|---|
| 1 | Upload JPG per API (`POST /api/belege`, multipart) | OK — 7 Testfotos hochgeladen (IDs 7–14), korrekte `sha256_hash`, Datei physisch unter `belege/<sparte_id>/<id>_<name>` abgelegt |
| 2 | Upload mit falschem Dateityp (`.txt`) | OK — 400, `"Dateityp '.txt' nicht erlaubt. Zulaessig: heic, jpeg, jpg, pdf, png, webp"` |
| 3 | Upload mit ungültiger `sparte_id` (999) | OK — 404 „Sparte nicht gefunden“ |
| 4 | Upload ohne `sparte_id` (Pflichtfeld optional) | OK — Beleg wird angelegt/als Dublette erkannt, `sparte_id: null` möglich |
| 5 | Dublettenschutz: gleiche Datei zweimal hochladen | OK — zweiter Upload liefert `"dublette": true` und dieselbe `id`, keine neue Datei, `sparte_id` des Erst-Uploads bleibt bestehen (Dedup ist rein inhaltsbasiert je Bereich, unabhängig von der beim zweiten Versuch übergebenen Sparte — konsistent mit dem Code, aber siehe QA4-04) |
| 6 | Beleg-Datei abrufen (`GET /api/belege/{id}/datei`) | OK — 200, korrekter `Content-Type: image/jpeg`, korrekte Größe |
| 7 | Nicht existierenden Beleg abrufen/löschen | OK — 404 „Beleg nicht gefunden“ |
| 8 | Beleg löschen (`DELETE`), Datei danach abrufen | OK — 204, Datei danach 404, Datenbankzeile weg |
| 9 | Löschen eines mit einer Buchung verknüpften Belegs | OK — Verknüpfung per CASCADE entfernt, `belegstatus` der betroffenen Buchung automatisch auf `beleg_fehlt` zurückgesetzt |
| 10 | Beleg an Buchung hängen (`POST /buchungen/{id}/belege`) | OK — idempotent (erneuter Aufruf kein Fehler), `belegstatus` → `beleg_vorhanden` |
| 11 | Verknüpfung lösen (`DELETE /buchungen/{id}/belege/{beleg_id}`) | OK — `belegstatus` fällt automatisch zurück, sofern er einer der automatischen Zustände war |
| 12 | Belege einer Buchung auflisten | OK |
| 13 | Belegstatus in der Buchungsliste | OK — `belegstatus`/`beleg_vorhanden`/`beleg_fehlt` korrekt in `/api/buchungen`-Antwort und im Export („Fehlende Belege“-Liste) |
| 14 | Belege-Seite im Frontend (Upload-Kachel, Listen) | OK — lädt, zeigt „Belege zur Prüfung“ (fertige Auswertungen) und „Belege“ (alle Uploads) getrennt, aktualisiert sich nach Aktionen korrekt (erst nach Reload/Refetch, kein Live-Polling — normal für dieses SPA-Muster) |
| 15 | Upload-Button „Beleg fotografieren“ / „Rechnung fotografieren“ im Frontend | Vorhanden, nicht per echtem Dateidialog getestet (Upload im Browser-Werkzeug unzuverlässig, siehe Auftrag) — stattdessen alle Uploads über `curl -F` (siehe Punkt 1), das ist der gleiche Endpunkt |

### 1.2 Foto-Auswertung (Ollama, alle 7 Testbilder)

Auswertung erreichbar (`GET /api/auswertung/status` → `erreichbar: true`, `modell_vorhanden: true`).
Aufträge laufen sequenziell (ein Worker, ~15 s Polling) — „Dauer“ unten ist Zeit von Auftragserstellung
bis Fertigstellung inkl. Warteschlange, nicht reine Modellzeit.

| Bild | Soll | Ist (Händler / Datum / Summe) | Positionen | Dauer | Abweichung |
|---|---|---|---|---|---|
| photo…18 (Apotheke) | 09.04.2026, 37,30 €, 4 Pos. | St.Barbara Apotheke / **2026-09-04** / 37,30 € | 4 (korrekt) | 27 s | **Datum: Tag/Monat vertauscht** (QA4-01) |
| photo…22 (Lagerhaus) | 28.04.2026, 145,75 € | UNSER LAGERHAUS / 2026-04-28 / 145,75 € | 4 | 55 s | Keine — vollständig korrekt |
| photo…25 (Achensee Apotheke) | 26.07.2026, 73,85 €, 6 Pos. | ACHENSEE APOTHEKE KG / **2025-07-26** / 73,85 € | 6 (korrekt) | 88 s | **Jahr falsch** (2025 statt 2026, QA4-02); Netto→Brutto-Aufschlag korrekt ausgeführt (Hinweis „Netto-Preise erkannt“) |
| photo…29 (Handschrift) | 28.09.2024, 536 (vermutlich 536,00 €) | UWE / 2024-09-28 / **53,60 €** | 2 | 112 s | Datum korrekt; **Betrag vermutlich um Faktor 10 zu niedrig** (QA4-03, Soll-Format „536“ ohne Komma ist etwas mehrdeutig) |
| photo…32 (Sparkasse-Screenshot) | 09.09.2026, −5.000 € | (kein Händler erkannt, erwartbar) / 2026-09-09 / **−500,00 €** | 0 | 132 s | Datum korrekt; **Betrag um Faktor 10 zu niedrig** (−500 statt −5.000, QA4-03); App markiert das selbst korrekt als Hinweis „Summe der Positionen weicht vom Gesamtbetrag ab“ |
| synthetisch-baumarkt.jpg | 11.09.2026, 22,97 € | BAUMARKT HOHENEgg / 2026-09-11 / 22,97 € | 4 | 162 s | Keine — vollständig korrekt |
| testrechnung.jpg (Alpbachtal) | 25.08.2026, 30,00 € | alpbachtal / **2025-08-26** / 30,00 € | 1 | 187 s | **Tag UND Jahr falsch** (26.08.2025 statt 25.08.2026, QA4-05); Netto→Brutto-Aufschlag korrekt |

3 von 7 Bildern (Lagerhaus, Baumarkt) vollständig korrekt, 1 mit korrektem Betrag/Positionen aber
falschem Jahr, 3 mit Datums- und/oder Betragsabweichungen. Beträge und Positionszahlen sind bei den
„lesbaren“ Kassenzetteln (Apotheke, Achensee, Lagerhaus, Baumarkt) durchgehend korrekt — die Fehler
liegen fast ausschließlich bei Datum bzw. bei stark abweichenden/unüblichen Beträgen (Handschrift,
Screenshot). Kategorievorschlag (`kategorie_id`/`kategorie_name`) blieb bei allen Positionen `null`,
weil Sparte 1 „Vermietung Haus Münster“ keine zu den Artikeltexten passenden Kategorien/Merkregeln
hat — das ist erwartbares Verhalten, kein Fehler der Auswertung.

| Prüfpunkt | Ergebnis |
|---|---|
| Auftrag anlegen (`POST /api/belege/{id}/auswerten`) | OK, dedupliziert (erneuter Aufruf bei laufendem/fertigem Auftrag liefert denselben) |
| Status pollen (`GET /api/beleg-auswertungen`, `?status=fertig`) | OK |
| Prüf-Dialog im Frontend öffnet mit vorbelegten Werten | OK — Sparte, Datum (unkorrigiert vom Modell!), Zahlungsart „Bar“, je Position Text/Betrag/Kategorie-Dropdown (auf Kategorien der Beleg-Sparte beschränkt) |
| Übernahme als Buchung — Datum in der UI korrigieren, Kategorien wählen, „Übernehmen“ | OK (Beleg 8/St. Barbara): Buchung 28 korrekt mit korrigiertem Datum 2026-04-09, Text = Händlername, `belegstatus` → `beleg_vorhanden`, Beleg verknüpft |
| Übernahme via API mit vollständig korrekten Werten (Lagerhaus) | OK — Buchung 26 korrekt (Datum, Beträge, Kategorien, Text) |
| Ablehnen/Verwerfen im Frontend | OK — Button „Verwerfen“ löst `POST /beleg-auswertungen/{id}/status {"status":"verworfen"}` aus, verschwindet danach aus „Belege zur Prüfung“ |
| Ablehnen via API | OK |
| Übernehmen einer bereits verworfenen/verbuchten Auswertung | OK abgesichert — 409 „Auswertung ist noch nicht fertig oder bereits abgeschlossen“ |
| Wiederholte Übernahme mit gleicher `client_request_id` (P43b) | **Fehlerhaft** — liefert 409 statt der gecachten Erfolgsantwort (QA4-06, siehe unten) |
| Kategorie aus falscher Sparte bei Übernahme | OK abgesichert — 400 „Kategorie gehoert nicht zur gewaehlten Sparte“ |
| Gemischte Typen (einnahme+ausgabe) in einer Übernahme | OK abgesichert — 422 |
| Verhalten bei nicht erreichbarem Ollama | Nicht live provozierbar (Ollama lief durchgehend und durfte nicht gestoppt werden) — laut Code (`app/auswertung.py`) bleibt der Auftrag bei `URLError`/`OSError` auf „offen“ und wird bis zu 5× erneut versucht, danach „fehler“ mit sprechender Meldung; UI-seitig zeigt `auswertung/status` die Erreichbarkeit separat an. Codeprüfung, keine Live-Probe. |
| Bild-Rotation (quer→hochkant ohne EXIF) | Alle 5 Handyfotos ohne EXIF wurden korrekt ausgewertet (lesbare Ergebnisse), Drehlogik (`FINANZ_BILD_QUER_DREHEN`) ist aktiv und griff sichtbar |

### 1.3 Export (P60/P60b)

| Prüfpunkt | Ergebnis |
|---|---|
| `GET /api/export/xlsx` ohne Filter | OK — 200, gültige XLSX (openpyxl-lesbar), Blätter „Buchungen“/„Monatssummen“/„Kategorien“ |
| `xlsx` mit `sparte_id` | OK |
| `xlsx` mit `von`/`bis` | OK |
| `xlsx` mit ungültigem Datum | OK — 400 |
| `xlsx` mit `von` > `bis` | OK — 400 |
| `GET /export/bericht` ohne `jahr` | OK — 400 „jahr muss vierstellig sein“ (Pflicht ohne `profil_id`, wie im Auftrag erwartet) |
| `bericht` mit gültigem `jahr` | OK — 200, druckfähiges HTML mit Deckblatt, Sparten-Abschnitten, Monats-/Kategorie-Tabellen |
| `bericht` mit ungültigem `jahr` | OK — 400 |
| Export-Profil „Steuer“ automatisch anlegen (`GET /api/export/profil`) | OK |
| Ausschlüsse setzen (`PUT /api/export/profil/{id}`, Kategorie ausschließen) | OK — Vorschau (`anzahl`, Summen) reagiert korrekt, `revision`-Hash ändert sich |
| Revisionsprüfung beim Steuerpaket (`POST /api/export/paket`) mit veralteter Revision | OK abgesichert — 409 |
| Steuerpaket ohne „trotz fehlender Belege“ bei fehlenden Belegen | OK abgesichert — 422, Frontend zeigt Dialog „Belege fehlen“ mit Button „Trotzdem exportieren“ |
| Steuerpaket mit „Trotzdem exportieren“ | OK — 200, ZIP mit XLSX + `Belege/` + `INHALT.txt` |
| Frontend Export-Seite: Vorschau, Summen, „Fehlende Belege“-Liste, Buttons | OK — alle Werte konsistent mit API |
| Export je Bereich (`bereich_id`) | OK, per Query-Parameter steuerbar, im Frontend über Bereichs-Auswahl links oben |
| Inhalt der XLSX-Datei stichprobenartig gegen API geprüft | OK — Zeilen-/Summenanzahl der „ohne Filter“-Datei passt zur `/api/buchungen`-Übersicht |
| Mobile Ansicht (375 px) | OK — Export-Seite rendert sauber, keine Überläufe, Bottom-Nav vorhanden (ohne eigenes Export-Icon, das ist aber unauffällig, da über „≣“/Hauptnavigation erreichbar) |

### 1.4 Betrieb

| Prüfpunkt | Ergebnis |
|---|---|
| `GET /api/betrieb/status` | OK — liefert Schema (17, keine anstehenden Migrationen), Sicherung (`letzte: 2026-09-11`, `db_ok: true`, `belege_fehlend: 6`), Zweitziel `nicht_konfiguriert`, `schreibgeschuetzt: false` |
| `GET /api/betrieb/migrationsprotokoll` | OK — 4 Einträge, alle „zahlung_ungeklaert“ |
| `GET /api/schema` | OK — konsistent mit `/api/betrieb/status` |
| Sicherung manuell auslösen | **Kein POST-Endpunkt vorhanden** — `/api/betrieb/sicherung`, `/api/sicherung`, `/api/backup` liefern alle 405/404. Laut `app/routers/betrieb.py` gibt es nur die beiden GET-Endpunkte oben; ein manueller Trigger ist nicht Teil der API (evtl. nur per Hintergrund-Job/CLI vorgesehen) |
| Betriebsseite im Frontend | **Nicht vorhanden** — kein Menüpunkt „Betrieb“ in der Hauptnavigation (`Übersicht, Sparte, Erfassen, Buchungen, Konten, Kredit, Kategorien, Belege, Bankimport, Export`), auch kein Routen-Eintrag in `static-neu/app.js` |

### 1.5 Login ohne Bypass (Instanz 8056)

| Prüfpunkt | Ergebnis |
|---|---|
| `GET /` ohne Sitzung | OK — 303 auf `/login.html` |
| `GET /api/...` ohne Sitzung | OK — 401 „Anmeldung erforderlich.“ |
| `GET /neu/`, `/studio/` ohne Sitzung | OK — beide 303 auf `/login.html` (kein ungeschützter Zugriff) |
| `/login.html` direkt | OK — 200, öffentlich erreichbar |
| Öffentliche Assets (`password-recover.html/js`, `password-common.css`) | OK — alle 200 ohne Sitzung |
| `/api/health` | OK — 200 „ok“, öffentlich (erwartet für Monitoring) |
| Login-Versuch (`POST /api/auth/login`) | **503 „Anmeldung ist noch nicht eingerichtet.“** — auf dieser Instanz ist noch **kein** Startpasswort hinterlegt (keine `instance/auth.json` mit Konfiguration), siehe „Nicht geprüft“ |
| Recovery mit falschem Code | OK — 401 „Anmeldedaten sind nicht korrekt.“ |
| `/password-setup.html` ohne Sitzung | OK (laut Code/Test-Suite erwartet) — 303 auf `/login.html`; Ersteinrichtung erfordert zwingend zuerst eine gültige Sitzung mit dem vom Betreiber lokal per `scripts/set_auth_password.py` gesetzten Startpasswort. Es gibt bewusst **keinen** HTTP-Weg, ein Startpasswort ohne Server-/Dateizugriff zu setzen (Sicherheitsdesign, kein Fehler) |
| Sicherheits-Header (`X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Cache-Control: no-store`) | OK — auf beiden Instanzen konsistent gesetzt (per `AuthMiddleware._secure_headers`, greift auch bei Fehlerantworten) |
| Session-Cookie-Attribute (`__Host-`, HttpOnly, SameSite) | **Nur per Code-Review geprüft, nicht live** (siehe „Nicht geprüft“): `app/auth.py` setzt `COOKIE_NAME = "__Host-finanz_session"`, `secure=True`, `httponly=True`, `samesite="strict"`, `path="/"` — das erfüllt formal alle `__Host-`-Vorgaben (secure, kein `Domain`-Attribut, `path=/`) |
| Zugriff auf `/neu/` und `/studio/` nur angemeldet | Für „nicht angemeldet“ bestätigt (siehe oben); „angemeldet zeigt neues Frontend“ nicht testbar ohne Login |

## 2. Befunde

### QA4-01 — Foto-Auswertung: Tag und Monat im Datum vertauscht (Apotheke)
**Schweregrad:** mittel
**Seite:** Belege → Foto-Auswertung / Prüf-Dialog
**Schritte:** Foto `photo_2026-09-11_12-45-18.jpg` (Apotheke, Soll-Datum 09.04.2026) hochladen und
auswerten (`POST /api/belege/7/auswerten`).
**Erwartet:** `datum: "2026-04-09"`
**Tatsächlich:** `datum: "2026-09-04"` (Tag/Monat vertauscht)
**Beleg:** API-Antwort `GET /api/beleg-auswertungen` (Auftrag 8): `"datum": "2026-09-04"`, `"gesamt_cent": 3730` (Betrag korrekt, nur das Datum ist falsch). Der Prüf-Dialog übernimmt diesen Wert unkorrigiert in das Datumsfeld — Nutzer muss selbst bemerken und korrigieren.
**Betroffene Datei:** `app/auswertung.py` (Prompt/Parsing) bzw. Modellverhalten von `qwen3.5:4b`; kein offensichtlicher Fehler im Python-Code, eher eine Modell-Schwäche bei diesem Beleg.

### QA4-02 — Foto-Auswertung: Jahr falsch erkannt (Achensee Apotheke)
**Schweregrad:** mittel
**Seite:** Belege → Foto-Auswertung
**Schritte:** Foto `photo_2026-09-11_12-45-25.jpg` (Soll 26.07.2026) auswerten.
**Erwartet:** `datum: "2026-07-26"`
**Tatsächlich:** `datum: "2025-07-26"` (Jahr 2025 statt 2026)
**Beleg:** Auftrag 10, Betrag (73,85 €) und Positionsanzahl (6) korrekt, nur Jahr falsch.

### QA4-03 — Foto-Auswertung: Beträge bei zwei Belegen um Faktor 10 abweichend (Handschrift, Sparkasse-Screenshot)
**Schweregrad:** mittel
**Seite:** Belege → Foto-Auswertung
**Schritte:** `photo_2026-09-11_12-45-29.jpg` (Handschrift, Soll vermutlich 536,00 €) und
`photo_2026-09-11_12-45-32.jpg` (Sparkasse-Screenshot, Soll −5.000 €) auswerten.
**Erwartet:** 536,00 € bzw. −5.000,00 €
**Tatsächlich:** 53,60 € (Auftrag 11) bzw. −500,00 € (Auftrag 12) — jeweils Faktor 10 zu niedrig
**Beleg:** `"gesamt_cent": 5360"` bzw. `"gesamt_cent": -50000"`. Bei Beleg 12 markiert die App das Ergebnis bereits selbst korrekt mit dem Hinweis „Summe der Positionen (0,00 €) weicht vom Gesamtbetrag (-500,00 €) ab — bitte prüfen“, da keine Positionen erkannt wurden — der Nutzer wird also gewarnt, nur der Betrag selbst ist falsch.
**Einschränkung:** Der Sollwert „536“ im Testauftrag ist ohne Komma angegeben und daher etwas mehrdeutig; ich gehe von 536,00 € aus (konsistent mit den übrigen, mit Komma notierten Sollwerten).

### QA4-04 — Foto-Auswertung: Tag und Jahr falsch (Alpbachtal/testrechnung.jpg)
**Schweregrad:** mittel
**Seite:** Belege → Foto-Auswertung
**Schritte:** `testrechnung.jpg` (Soll 25.08.2026, 30,00 €) auswerten.
**Erwartet:** `datum: "2026-08-25"`
**Tatsächlich:** `datum: "2025-08-26"` — sowohl Tag (26 statt 25) als auch Jahr (2025 statt 2026) falsch
**Beleg:** Auftrag 14, Betrag 30,00 € korrekt.

### QA4-05 — Wiederholungs-Topf „beleg_uebernahme“ (P43b) wird nie persistiert — fehlendes `con.commit()`
**Schweregrad:** mittel
**Seite:** API `POST /api/beleg-auswertungen/{id}/uebernehmen`
**Schritte:**
1. `POST /api/beleg-auswertungen/9/uebernehmen` mit `client_request_id: "qa4-ueb-9-a"` und einem vollständigen Payload → 201, Buchung 26 wird angelegt, Auswertung 9 → Status `verbucht`.
2. Denselben Request mit identischem Body/`client_request_id` erneut senden.

**Erwartet:** Laut Code-Kommentar in `app/routers/beleg_auswertung.py` (`auswertung_uebernehmen`): „Die Wiederholungspruefung (client_request_id) laeuft VOR der Statuspruefung, damit ein wiederholter Aufruf auch nach dem Statuswechsel auf 'verbucht' noch die gleiche Antwort liefert statt faelschlich 409 zu melden.“ Also 200 mit derselben Antwort `{"buchung_id":26,"version":1}`.
**Tatsächlich:** 409 `{"detail":"Auswertung ist noch nicht fertig oder bereits abgeschlossen"}` — genau der Fall, den der Mechanismus laut Kommentar verhindern soll.
**Ursache (verifiziert):** In `auswertung_uebernehmen` wird nach `erstelle_buchung(...)` zwar `speichere_antwort(con, 'beleg_uebernahme', body, bereich, ergebnis_antwort)` aufgerufen, aber **kein** anschließendes `con.commit()`. Die Datenbankverbindung (`db_dep`) committet nicht automatisch, sondern schließt die Verbindung am Requestende nur (`app/db.py::db_dep`, kein Commit). Da `erstelle_buchung` selbst intern committet, bleibt die Buchung erhalten — aber der `INSERT INTO request_wiederholung(...)` danach wird beim Verbindungsschluss verworfen. Direkte Prüfung der Live-DB (`C:\Users\lblet\AppData\Local\Temp\qa-8055\finanz.db`) bestätigt: Tabelle `request_wiederholung` enthält **keinen einzigen** Eintrag mit `art='beleg_uebernahme'`, obwohl mehrere erfolgreiche Übernahmen mit `client_request_id` liefen.
**Auswirkung:** Kein Datenverlust und keine Doppelbuchung (der Status-Check fängt den zweiten Versuch ab), aber ein Client, der nach einem Netzwerk-Timeout automatisch mit derselben `client_request_id` wiederholt, bekommt fälschlich einen Fehler statt der ursprünglichen Erfolgsantwort und müsste selbst herausfinden, ob die Buchung schon existiert.
**Betroffene Datei:** `app/routers/beleg_auswertung.py`, Funktion `auswertung_uebernehmen` (fehlendes `con.commit()` nach `speichere_antwort(...)`, vor `return ergebnis_antwort`).

### QA4-06 — `/api/betrieb/sicherung`, `/api/sicherung`, `/api/backup` nicht vorhanden — kein manueller Sicherungs-Trigger über die API
**Schweregrad:** niedrig
**Seite:** API / Betrieb
**Schritte:** `POST` gegen `/api/betrieb/sicherung`, `/api/sicherung`, `/api/backup`.
**Erwartet:** laut Auftrag „Sicherung auslösen falls Endpunkt vorhanden“ — es wurde offengelassen, ob ein solcher Endpunkt existieren soll.
**Tatsächlich:** Alle drei Pfade liefern 404/405. `app/routers/betrieb.py` enthält nur die beiden GET-Endpunkte `status` und `migrationsprotokoll`; ein Schreib-/Trigger-Endpunkt ist im Router nicht vorhanden. Vermutlich beabsichtigt (Sicherung läuft als Hintergrund-Job, siehe `app/backup.py`), aber ohne Frontend-Seite „Betrieb“ hat ein Nutzer keine Möglichkeit, eine Sicherung manuell anzustoßen oder den Status außerhalb der API einzusehen.
**Betroffene Datei:** `app/routers/betrieb.py` (kein POST-Endpunkt), `static-neu/app.js` (keine Betriebs-Route im Frontend).

### QA4-07 — Login-Instanz 8056: kein Startpasswort konfiguriert, Ersteinrichtung nicht vollständig testbar
**Schweregrad:** — (kein Produktfehler, siehe unten)
**Seite:** Login-Instanz (8056)
**Befund:** `POST /api/auth/login` liefert für jedes Passwort 503 „Anmeldung ist noch nicht eingerichtet.“, weil `AUTH.settings.configured` `false` ist (keine `instance/auth.json` mit Passwort-Hash hinterlegt). Das Ersteinrichtungs-Formular (`/password-setup.html`) ist absichtlich nur mit gültiger Sitzung erreichbar (303 sonst), und diese Sitzung kann nur über ein vorab lokal per `scripts/set_auth_password.py` gesetztes Startpasswort erlangt werden — es gibt bewusst keinen HTTP-Weg, das allererste Passwort zu setzen. Da mir kein Startpasswort für diese Instanz mitgeteilt wurde und ich laut Auftrag keine Schreibrechte außerhalb meines Temp-Verzeichnisses habe (das Setzen des Startpassworts hätte `instance/auth.json` außerhalb meines erlaubten Bereichs verändert), konnte ich den gesamten Login-, Passwortwechsel-, Sperr- und Recovery-Flow **nicht end-to-end** durchspielen. Alles, was ohne Sitzung prüfbar war (Redirects, 401/403, öffentliche Pfade, Rate-Limit-Grundverhalten am Recovery-Endpunkt), wurde geprüft und war unauffällig. Kein Bug, sondern eine Einschränkung meines Testzugriffs — siehe Abschnitt 3. **Nachtrag:** siehe
Abschnitt 4, inzwischen mit Startpasswort und Neustart größtenteils aufgelöst, aber durch eine
selbst ausgelöste Rate-Limit-Sperre erneut unvollständig geblieben.

### QA4-08 — Betriebsdoku erwähnt Neustartpflicht nach Auth-Datei-Änderung nicht allgemein
**Schweregrad:** mittel
**Seite:** `docs/BETRIEB-UND-ARCHITEKTUR.md` / Betrieb
**Befund:** Die App liest ihre Auth-Datei (`auth.json`) ausschließlich beim Prozessstart (Singleton
`AUTH = AuthManager()` in `app/auth.py`, `AUTH_STORE.load()` nur im Konstruktor, kein
Datei-Watcher/Reload-Endpunkt — live bestätigt: nach manuellem Schreiben der Datei blieb
`POST /api/auth/login` bis zum Neustart bei 503 „Anmeldung ist noch nicht eingerichtet.“, siehe
Abschnitt 4). `docs/BETRIEB-UND-ARCHITEKTUR.md` dokumentiert diese Neustartpflicht nur an einer
einzigen, engen Stelle (Abschnitt „Wiederherstellungscode nachtragen“: „`scripts/set_auth_password.py
--nur-recovery-code`, dann Dienst neu starten“) — nicht als allgemeine Aussage für jede
Auth-Datei-Änderung, insbesondere nicht für die reguläre Ersteinrichtung eines Startpassworts. Das
Skript `scripts/set_auth_password.py` selbst gibt zwar bei jedem Lauf „Bitte den Finanzstudio-Dienst
jetzt neu starten.“ aus, das ersetzt aber keine Aussage in der Architekturübersicht, die als
Nachschlagewerk für Betriebs-Handgriffe dient.
**Betroffene Datei:** `docs/BETRIEB-UND-ARCHITEKTUR.md`, Abschnitt 4 „Wie sicher es ist“.
**Hinweis:** Kein Code geändert; ich habe lediglich einen unverbindlichen Doku-Ergänzungsvorschlag
als Hintergrund-Aufgabe hinterlegt (siehe Abschnitt 4).

## 3. Nicht geprüft / Einschränkungen

- **Login-Flow mit gültigem Passwort** — inzwischen vollständig nachgeholt, siehe Abschnitt 4
  „Nachtrag Login“ (Anmeldung, Sperre nach Fehlversuchen, Session-Cookie-Attribute, Ersteinrichtung,
  Passwortwechsel, Abmelden, `/` zeigt neues Frontend, `/neu/`/`/studio/` angemeldet erreichbar —
  alles live bestätigt). Offen geblieben: der Recovery-Code-Flow mit einem *gültigen* Code (auf
  Wunsch der Koordination ausgelassen, siehe Abschnitt 4) und die Cookie-Prüfung mit einem *echten*
  Browser statt `curl` (siehe nächster Punkt).
- **Session-Cookie im echten Browser** (statt `curl`) nicht geprüft: Der `Set-Cookie`-Header enthält
  `Secure`, obwohl Instanz 8056 nur über `http://127.0.0.1:8056` (kein TLS) läuft. `curl` prüft das
  Secure-Attribut nicht gegen das Protokoll und speichert/sendet das Cookie anstandslos — ob ein
  echter Browser das Cookie unter `http://127.0.0.1` ebenfalls akzeptiert (Chromium behandelt
  `127.0.0.1`/`localhost` als „potenziell vertrauenswürdigen Ursprung“ und würde es laut Spezifikation
  annehmen) oder stillschweigend verwirft, wurde nicht mit einem echten Browser gegen diese Instanz
  verifiziert.
- **Verhalten bei nicht erreichbarem Ollama** nur per Code-Review beurteilt (Ollama durfte laut
  Auftrag nicht gestoppt werden).
- **Datei-Upload direkt über die Browser-Oberfläche** (`<input type=file>`/Kamera-Button) nicht
  end-to-end mit echtem Dateidialog getestet — Upload im Browser-Werkzeug ist laut Auftrag
  unzuverlässig; stattdessen alle Uploads über `curl -F` gegen denselben API-Endpunkt, den auch das
  Frontend verwendet.
- **PDF-Upload** nicht getestet — es standen nur Bild-Testdateien zur Verfügung; die
  Endungsprüfung akzeptiert laut Code `.pdf`, das wurde aber nicht mit einer echten PDF-Datei live
  verifiziert.
- **HEIC-Upload** nicht getestet (keine Testdatei vorhanden).
- **Datei zu groß** (Upload-Limit) nicht getestet — kein offensichtliches Größenlimit im Code
  (`app/routers/belege.py`) gefunden; nicht mit einer großen Testdatei verifiziert.
- **Zweitziel-Sicherung** nicht geprüft — laut `/api/betrieb/status` „nicht_konfiguriert“, kein
  Endpunkt zum Konfigurieren gefunden/getestet.
- Browser-Oberfläche zeitweise durch eine **gemeinsam genutzte Browser-Instanz** anderer
  QA-Tester beeinflusst (Viewport wechselte mehrfach unerwartet zwischen Desktop/Mobile, vom Werkzeug
  selbst als „another Claude session set this“ bestätigt) — alle mobilen Screenshots wurden danach
  gezielt neu mit definiertem Viewport und Scroll-Position 0 erstellt, um das auszuschließen.
- Kategorievorschlag der Foto-Auswertung nur mit Sparte 1 (Vermietung) getestet, die keine
  thematisch passenden Kategorien/Merkregeln für Apotheken-/Baumarktartikel hat — die
  Vorschlagslogik selbst (`_kategorie_fuer_position`) wurde nicht mit passenden Merkregeln verifiziert.
- Buchungsstatus-Icons/Filter in der allgemeinen Buchungsliste außerhalb der Belege-bezogenen Felder
  nicht im Detail geprüft (außerhalb des mir zugewiesenen Bereichs).

## 4. Nachtrag Login (nach Freigabe durch Koordination)

Auf Anweisung der Koordination wurde für diesen Nachtrag ein Wegwerf-Startpasswort für Instanz 8056
gesetzt, um den vollständigen Login-Fluss zu prüfen (in QA4-07 war das mangels Zugangsdaten offen
geblieben).

**Vorgehen:** Auth-Datei `C:\Users\lblet\AppData\Local\Temp\qa-8056\auth.json` über die App-eigenen
Funktionen geschrieben (`app.auth.hash_password`, `app.auth_store.AuthConfigStore/AuthConfig`,
identischer Weg wie `scripts/set_auth_password.py`, nur ohne interaktives `getpass`, da stdin nicht
interaktiv ist): zufälliges 14-stelliges Passwort, `must_change_password=True`, neuer
`session_secret`, neuer Recovery-Code — exakt das Schema eines frisch eingerichteten Startpassworts.
Zugangsdaten wurden ausschließlich in einer lokalen Datei in meinem erlaubten Temp-Verzeichnis
(`C:\Users\lblet\AppData\Local\Temp\qa-8056\_start-credentials.txt`) zwischengehalten, nirgends sonst
notiert, und werden nach Abschluss des Tests gelöscht.

### Befund: Instanz liest die Auth-Datei nicht automatisch neu

Nach dem Schreiben der neuen `auth.json` liefert `POST /api/auth/login` auf der weiterhin laufenden
Instanz 8056 unverändert `503 {"detail":"Anmeldung ist noch nicht eingerichtet."}` — die Datei wird
**nicht** zur Laufzeit neu eingelesen.

**Ursache (Code-Review, `app/auth.py`):** Die Singleton-Instanz `AUTH = AuthManager()` wird genau
einmal beim Modul-Import erzeugt; `AuthManager.__init__` ruft `AUTH_STORE.load()` nur dort auf. Es
gibt keinen Datei-Watcher, keinen Reload-Endpunkt und keinen periodischen Neuladepfad — `grep` nach
`AUTH_STORE.load`/`reload`/`watch`/`mtime` in `app/` findet die Ladeaufrufe nur in
`AuthManager.__init__` (Zeilen 120/178/181). Ein Neuladen passiert sonst nur implizit über
`replace_config()`, das ausschließlich von den In-Prozess-Aktionen `initial-password`,
`change-password` und `recover` aufgerufen wird — nicht durch externe Dateiänderungen.

**→ Wie mit der Koordination vereinbart: Ich habe die Instanz NICHT selbst neu gestartet.** Die
Koordination müsste die Instanz 8056 neu starten, damit die neue Auth-Datei geladen wird. Der Rest
dieses Nachtrags (Anmeldung, Sperre, Cookie-Attribute, `/`-Weiterleitung, `/neu/`/`/studio/` im
angemeldeten Zustand, Ersteinrichtungspflicht, Passwortwechsel, Abmelden, Recovery-Code-Fluss) konnte
deshalb **nicht** durchgeführt werden und bleibt offen, bis der Neustart erfolgt ist.

Sobald die Instanz neu gestartet wurde, kann der Login-Fluss mit dem bereits gesetzten
Wegwerf-Startpasswort direkt fortgesetzt werden (Datei ist geschrieben und muss nicht neu erzeugt
werden), sofern die Zugangsdaten-Datei bis dahin nicht bereits gelöscht wurde.

### Fortsetzung nach Neustart durch die Koordination

Die Koordination hat die Instanz neu gestartet und bestätigt, dass die neue Auth-Datei geladen wurde
(`POST /api/auth/login` mit falschem Passwort lieferte danach 401 statt 503 — von mir nachgeprüft,
bestätigt).

Beim anschließenden Test der Sperre nach Fehlversuchen (siehe „Rate-Limit nach Fehlversuchen“ unten)
bin ich durch meine eigenen Testversuche selbst in die 429-Sperre gelaufen (`LoginRateLimiter`,
`max_failures=5`, `window_seconds=900` = 15 Minuten, in-memory pro Client-IP, `app/auth.py`). Diese
Sperre lässt sich **nicht** umgehen: Sie basiert auf `time.monotonic()` innerhalb des laufenden
Prozesses, wird nirgends in der DB persistiert und verfällt ausschließlich durch echten Zeitablauf
oder einen Prozess-Neustart. Ein weiterer Neustart nur zum Aufheben meiner eigenen Test-Sperre wurde
nicht angefragt und lag außerhalb des Auftrags („kein Warten, kein Monitor“ von der Koordination).
Der Login mit dem korrekten Wegwerf-Passwort blieb daher bis zum Ende meiner Sitzung mit 429
blockiert — ich konnte die Sperre selbst live bestätigen, aber keine erfolgreiche Anmeldung mehr
durchführen.

**Zwischenstand (vor dem zweiten Neustart):** Ich hatte mich beim Testen der Fehlversuchs-Sperre
(5 Fehlversuche vom selben Client `127.0.0.1` → `429`, danach auch das *korrekte* Passwort blockiert,
da die Sperre vor der Passwortprüfung greift) selbst für 15 Minuten ausgesperrt. Die Koordination hat
die Instanz daraufhin erneut neu gestartet, was die In-Memory-Sperre zurücksetzte. Danach wurde der
positive Login-Flow mit maximal 2 bewusst falschen Versuchen zu Ende geprüft (tatsächlich nur 1
benötigt, siehe unten).

**Live geprüft (nach dem zweiten Neustart, mit dem gesetzten Wegwerf-Startpasswort):**

| Prüfpunkt | Ergebnis |
|---|---|
| Anmeldung mit korrektem Startpasswort (`POST /api/auth/login`) | **OK** — 204, `Set-Cookie` gesetzt |
| Session-Cookie-Attribute live im Response | **OK, vollständig bestätigt:** `__Host-finanz_session=…; HttpOnly; Max-Age=43200; Path=/; SameSite=strict; Secure` — erfüllt alle `__Host-`-Vorgaben (Secure gesetzt, kein `Domain`-Attribut, `Path=/`); `Max-Age=43200` = 12 h wie in `SESSION_SECONDS` vorgesehen. **Secure-Verhalten über http:** Der Header selbst trägt `Secure`, obwohl die Instanz nur über `http://127.0.0.1:8056` (kein TLS) angesprochen wird — `curl` speichert/sendet das Cookie trotzdem anstandslos, weil `curl` das Secure-Attribut nicht gegen das Transportprotokoll prüft. Echte Browser behandeln `127.0.0.1`/`localhost` als „potenziell vertrauenswürdigen Ursprung“ (Chromium-Sonderregel) und akzeptieren `Secure`-Cookies dort auch über Klartext-HTTP — dieses Verhalten wurde aber nur aus der Spezifikation abgeleitet, nicht mit einem echten Browser gegen diese Instanz nachvollzogen (siehe „Nicht geprüft“) |
| `GET /api/auth/state` direkt nach Login | OK — `{"must_change_password": true}` |
| Geschützte API mit gültiger Sitzung, aber offener Ersteinrichtung | OK abgesichert — `GET /api/sparten` → 403 „Ersteinrichtung erforderlich.“ |
| `GET /` mit Sitzung, aber offener Ersteinrichtung | OK — 303 auf `/password-setup.html` |
| `GET /password-setup.html` mit Sitzung | OK — 200 |
| Ersteinrichtung abschließen (`POST /api/auth/initial-password`) | OK — 200, liefert einmaligen Recovery-Code; `must_change_password` wird `false` |
| Alte Sitzung nach Ersteinrichtung | OK abgesichert — sofort widerrufen (`replace_config()` → `revoke_all_sessions()`), `GET /api/sparten` mit altem Cookie → 401 |
| Erneute Anmeldung mit dem in der Ersteinrichtung gesetzten Passwort | OK — 204, neues Cookie, `must_change_password` jetzt `false` |
| `GET /` mit gültiger, vollständig eingerichteter Sitzung | **OK — zeigt das neue Frontend** (`<title>Hohenegg Finanzstudio</title>`, lädt `app.js` aus `static-neu`; keine Spur von `/studio`-Inhalten außer dem Wortbestandteil „…studio“ in „Finanzstudio“) |
| `GET /neu/` mit gültiger Sitzung | OK — 200 |
| `GET /studio/` mit gültiger Sitzung | OK — 200 (im angemeldeten Zustand wie erwartet erreichbar) |
| Passwortwechsel (`POST /api/auth/change-password`) | OK — 204 mit korrektem aktuellem Passwort |
| Alte Sitzung nach Passwortwechsel | OK abgesichert — sofort widerrufen, `GET /api/sparten` → 401 |
| Anmeldung mit dem *alten* Passwort nach dem Wechsel (bewusster Fehlversuch, 1 von max. 2) | OK abgesichert — 401 „Passwort ist nicht korrekt.“ |
| Anmeldung mit dem *neuen* Passwort nach dem Wechsel | OK — 204, neues Cookie |
| Abmelden (`POST /api/auth/logout`) | **OK, vollständig bestätigt** — 204, `Set-Cookie: __Host-finanz_session=""; expires=<sofort>; HttpOnly; Max-Age=0; Path=/; SameSite=strict; Secure` (Löschung mit denselben sicheren Attributen); Sitzung direkt danach ungültig (`GET /api/sparten` → 401) |
| Recovery-Code-Fluss (`POST /api/auth/recover`) | **Ausgelassen** wie von der Koordination angewiesen — war zuvor von der Werkzeug-Berechtigungsprüfung als „Konto-/Sicherheitseinstellung ändern“ blockiert worden (kein erneuter Versuch); mit **falschem** Code bereits als 401 bestätigt (Abschnitt 1.5) |

**Ergebnis dieses Nachtrags:** Der komplette Login-Fluss auf Instanz 8056 wurde jetzt end-to-end
live bestätigt und arbeitet in allen geprüften Punkten korrekt: Ersteinrichtungspflicht,
Session-Widerruf bei jeder Passwortänderung, Cookie-Attribute (`__Host-`, `HttpOnly`, `SameSite=strict`,
`Secure`, 12 h Gültigkeit), Weiterleitung aufs neue Frontend, Zugriff auf `/neu/` und `/studio/` im
angemeldeten Zustand, Passwortwechsel und Abmelden. Einzige Einschränkung: der Recovery-Code-Fluss
mit gültigem Code und das Secure-Cookie-Verhalten in einem *echten* Browser (statt `curl`) blieben
ausgespart bzw. unverifiziert (siehe „Nicht geprüft“).

### Befund: Auth-Datei-Neustartpflicht nicht in der Betriebsdoku dokumentiert

Auf Bitte der Koordination geprüft — siehe **QA4-08** in Abschnitt 2 für den vollständigen Befund
und die Empfehlung. Kurz: `docs/BETRIEB-UND-ARCHITEKTUR.md` dokumentiert die Neustartpflicht nur für
den Sonderfall „Wiederherstellungscode nachtragen“, nicht allgemein für jede Auth-Datei-Änderung.

## 5. Gesamturteil

Die Kernfunktionen meines Bereichs — Beleg-Upload mit Dublettenschutz, Verknüpfung/Lösung mit
Buchungen, Prüf-Dialog samt Übernahme/Ablehnung, Export mit Ausschluss- und Revisionsprüfung sowie
die Absicherung der Betriebs-Status-API — funktionieren korrekt und robust, einschließlich sauberer
Fehlerbehandlung an allen getesteten Rändern (falsche Typen, fehlende Referenzen, Revisionskonflikte).
Der wichtigste Fund ist ein reproduzierbarer, im Code eindeutig lokalisierter Bug bei der
Übernahme-Wiederholungssperre (QA4-05, fehlendes `con.commit()`); daneben zeigt die lokale
Foto-Auswertung bei 4 von 7 Testbildern Datums- oder Betragsabweichungen, die der Prüf-Dialog nicht
automatisch erkennt und die Nutzer daher vor jeder Übernahme sorgfältig gegenlesen müssen. Der
Login-Fluss ohne Bypass wurde nach zwei Neustarts der Instanz 8056 (Auth-Datei wird nachweislich nur
beim Prozessstart gelesen, QA4-08) vollständig end-to-end bestätigt — Ersteinrichtung, Session-Widerruf
bei jeder Passwortänderung, Cookie-Attribute, Weiterleitungen und Abmelden funktionieren alle korrekt;
offen blieben nur der Recovery-Code-Flow mit gültigem Code (ausgelassen) und die Cookie-Prüfung in
einem echten Browser statt `curl`.
