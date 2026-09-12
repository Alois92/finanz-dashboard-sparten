# Abnahme Sicherheitsaudit run-1 und Behebung F1–F8

Datum: 12. September 2026. Abnehmer: Fable (Kopf). Audit: 3 Aufklärungs-, 7 Jagd-, 5 Widerlegungs- und 7
Verifikationsagenten (Sonnet/Opus), Ergebnisse `berichte/SECURITY-AUDIT-run1.md`, `SECURITY-AUDIT-run1-findings.json`
(Schema geprüft) und im Workspace `outputs/security-audit-neubau/run-1/`. Behebung: Claude Sonnet, Zweig
`fix/security-audit-run1`, Commits `25cf700` … `3a67549`, Bericht `berichte/SECURITY-fix-run1.md`, Merge `dcd65a0`.

## Ergebnis: bestanden

## Befunde und Fixes

| Nr. | Schwere | Fix | Regressionstest |
|---|---|---|---|
| F1 XSS Kategoriename → Hinweise | hoch | `esc(h.text)` in `uebersicht.js`, CSP in `_secure_headers`, Kategorienamen ≤ 80 Zeichen ohne `<>`/Steuerzeichen (API 422, Excel-Import Warnung), Theme-Skript beider Frontends ausgelagert | `test_f1_kategorie_name.py`, `test_import_excel.py`, CSP in `test_auth.py` |
| F2 Wettlauf Erstattung | hoch | Rest-Prüfung im `nach_anlage`-Hook innerhalb der Transaktion | `test_f2_erstattung_race.py` (8 parallel → 1× 201) |
| F3 Wettlauf Übernahme | hoch | Status atomar reservieren (`UPDATE … WHERE status='fertig'`, rowcount) | `test_f3_uebernahme_race.py` |
| F4 Backup-Store-Bereinigung | hoch | Referenzen als aufgelöste Store-Pfade | `test_backup.py` mit >30 Kopien und befülltem Store |
| F5 Upload-Pfad | mittel | Basisname, Längenlimit, `relative_to`-Prüfung, `OSError` → 400 | Traversal-, Slash- und Langname-Tests |
| F6 Middleware-Reihenfolge | niedrig | Schreibschutz innen, generischer 503-Text | Stack-Reihenfolge und 403/401 statt 503 |
| F7 Upload-Größe | niedrig | `MAX_UPLOAD_BYTES` 25 MB, 413 | Limit per Monkeypatch |
| F8 Migrationsprotokoll | niedrig | Filter über `buchung → sparte → bereich_id` | zwei Bereiche |

## Eigene Prüfung

| Prüfung | Ergebnis |
|---|---|
| Diffs F1–F4 gelesen | wie in den verifizierten Fix-Vorschlägen; F2 ohne zweites `BEGIN IMMEDIATE` |
| Inline-Skripte/Handler in `static-neu` und `static-studio` | keine mehr (`grep`), Favicon-Daten-URI durch `img-src data:` gedeckt |
| Suite des Agenten | 657 Tests grün (`berichte/SECURITY-fix-tests.txt`); Gesamtsuite nach Merge siehe Schuldenliste |
| Browser (Instanz 8051 aus `neubau`) | CSP-Header gesetzt; Übersicht mit 2 Hinweisen und 3 Diagrammen, Betrieb, Erfassen und `/studio/` (4 SVG) laden ohne CSP-Fehler; Theme dunkel über `theme-init.js`; Konsole nur Font-Ladehinweise |

## Offen (Härtungsnotizen, in `SCHULDEN.md`)

Passwortmindestlänge, Recovery-Race, `/docs` abschalten, Warteschlangen-Cap, Sicherungs-Rate-Limit, `.gitignore`,
`umstellung_pruefung.py` nur https, `FINANZ_TEST_AUTH_BYPASS` an `FINANZ_INSTANZ` koppeln, IPv6-Vergleich, starlette-Update.
**Bei der Umstellung:** `ExecStart` mit `--proxy-headers --forwarded-allow-ips=127.0.0.1` und 403-Test von einem
fremden Tailnet-Gerät (Betriebsdoku Abschnitt 11, Schritt 4b). Zweiter Audit-Lauf nach der Umstellung empfohlen.
