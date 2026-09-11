# P62 Runde 1 — Umstellung auf den Neubau mit Rückweg

Datum: 11. September 2026. Zweig `pkt/p62-umstellung` (von `neubau`, Stand `1e54adc`),
Worktree `C:\Users\lblet\dev\wt-p62`. Umsetzung: Claude Fable 5.1.

## Keine Produktionsänderung

**An CT 101 wurde nichts verändert.** Es wurde kein Release ausgeliefert, kein Dienst
neu gestartet, keine Datenbank angefasst und keine Proxmox-Konsole geöffnet. Dieses
Paket liefert ausschließlich Dokumentation, ein rein lesendes Prüfskript, Tests und
einen kleinen, standardmäßig wirkungslosen Konfigurationsschalter in `app/main.py`.
Die eigentliche Umstellung ist eine **eigene, vom Nutzer freigegebene Sitzung**, die
den jetzt dokumentierten Ablauf Schritt für Schritt abarbeitet.

## Dateien

| Datei | Was |
|---|---|
| `scripts/umstellung_pruefung.py` | **neu.** Rein lesendes Prüfskript: `pruefe_status`, `pruefe_zahlenvergleich`, `zusammenfassung`, Kommandozeile; nutzt `summen_je_sparte_jahr`, `summen_neu`, `vergleiche` und `_anzahl` aus `scripts/migrationsprobe.py` (P61), ohne sie zu duplizieren. |
| `tests/test_umstellung_pruefung.py` | **neu.** 17 Tests: Zahlenvergleich gleich/abweichend, Unveränderlichkeit beider Quellen, Quellenschutz, Status-Bewertung (auch gegen die echte ASGI-Anwendung mit `schreibgeschuetzt=true`), Zusammenfassungstexte und die Mount-/Login-Prüfung. |
| `docs/BETRIEB-UND-ARCHITEKTUR.md` | **geändert.** Neuer Abschnitt 11 „Umstellung auf den Neubau" (11.1–11.8 inklusive Rückweg); Abschnitt 10 verweist darauf. |
| `app/main.py` | **geändert.** `FINANZ_FRONTEND` entscheidet, welches Frontend unter `/` liegt; die Anmeldeseiten des Studios sind unabhängig davon unter `/` eingehängt. Siehe unten. |
| `docs/neubau/berichte/P62-tests.txt` | **neu.** Vollständige Testausgabe. |

## Änderung an `app/main.py` (Befund 2 der Abnahme P30)

Der Befund: Die Anmeldung unter `/neu` führt auf `/login.html` des Studios, und nach
erfolgreichem Login landet der Nutzer wieder auf `/`, also im alten Studio. Vor der
Umstellung muss `static-neu` den Root-Mount übernehmen.

Ein reiner Mount-Tausch reicht nicht: `static-neu` hat keine `login.html`, und die
Anmeldepfade sind in `app/auth.py` fest verdrahtet (`OEFFENTLICHE_PFADE`,
`INITIAL_SETUP_PATHS`, die Umleitungen auf `/login.html` und `/password-setup.html`)
sowie in `static-neu/api.js` und `static-neu/app.js`. Umgesetzt wurde deshalb:

1. `frontend_verzeichnis(wert)` — reine Funktion; `"neu"` ergibt `static-neu`, jeder
   andere Wert (auch leer oder unbekannt) bleibt beim Studio.
2. `ROOT_DIR = frontend_verzeichnis(os.environ.get("FINANZ_FRONTEND"))` für den
   Root-Mount. **Ohne gesetzte Variable ändert sich nichts** — Standard bleibt Studio.
3. Die neun Studio-Anmeldeseiten (`login.html`, `login.js`, `password-setup.*`,
   `password-change.*`, `password-recover.*`, `password-common.css`) werden als
   eigene `FileResponse`-Routen **vor** dem Root-Mount registriert und kommen damit
   immer aus `static-studio`, egal welches Frontend unter `/` liegt.

`/studio/` und `/neu/` bleiben unverändert erreichbar. Die Umstellung setzt später
nur ein systemd-Drop-In (`Environment=FINANZ_FRONTEND=neu`); der Rückweg entfernt es
wieder, ohne Codeänderung. Keine Änderung an `db/`, `app/migrate.py` oder an
Frontend-Dateien.

### Browserprüfung (drei Testinstanzen, Wegwerf-DB `%TEMP%\p62-app.db`, `FINANZ_INSTANZ=test`)

| Instanz | `/` | `/neu/` | `/studio/` | `/login.html` | `/api/health` |
|---|---|---|---|---|---|
| A: ohne `FINANZ_FRONTEND`, Bypass an (Port 8040) | 200, Studio (27884 B) | 200, neu (2420 B) | 200, Studio | 200 | 200 |
| B: `FINANZ_FRONTEND=neu`, Bypass an (Port 8041) | 200, **neu** (2420 B) | 200, neu | 200, Studio | 200 | 200 |
| C: `FINANZ_FRONTEND=neu`, **ohne** Bypass (Port 8042) | 303 → `/login.html` | 303 → `/login.html` | 303 → `/login.html` | 200 | 200 |

Im Browser geprüft: Instanz B zeigt unter `/` die Kopfzeile „Hohenegg · Finanzstudio ·
neu" (also `static-neu`), `/studio/` weiterhin das Studio-Dashboard mit Verlauf,
Sparten-Vergleich und Top-Listen; Instanz C zeigt unter `/` die vollständig gestylte
Anmeldeseite, `login.js` und `password-common.css` laden mit 200 aus `static-studio`.
Keine Konsolenfehler, keine 404. Die Instanzen wurden danach gestoppt und die
Wegwerf-Dateien gelöscht. `FINANZ_TEST_AUTH_BYPASS` wurde ausschließlich in den
Testinstanzen A und B verwendet, nie in der Testsuite.

## Prüfskript

```
python -m scripts.umstellung_pruefung --status-url <basis-url>
    --sicherung-vorher <pfad> --db-nachher <pfad>
```

- `pruefe_status(basis_url, session_cookie, oeffner=None)` ruft `GET /api/betrieb/status`
  angemeldet ab und meldet: Schema nicht aktuell, anstehende Migrationen,
  `schreibgeschuetzt=true`, fehlende oder defekte Sicherung, fehlende Belege. Der
  Sitzungswert kommt aus `FINANZ_SESSION_COOKIE`, nicht von der Kommandozeile.
- `pruefe_zahlenvergleich(sicherung_vorher, db_nachher)` rechnet die alte Zählweise auf
  der Sicherung gegen `v_einnahmen_ausgaben` auf dem Stand nachher, beides über
  P61-Funktionen. Beide Dateien werden **nur** mit `mode=ro` geöffnet; SHA256 vor und
  nach dem Lauf steht im Ergebnis (`unveraendert`). Quellen mit offenem WAL/Journal,
  UNC-Pfade, `/var/lib/finanz/finanz.db` und ein als `FINANZ_DB` gesetzter Pfad werden
  abgewiesen; ein nicht nachgezogener „Stand nachher" ergibt einen klaren Fehler.
- `zusammenfassung(status, zahlenvergleich)` sagt nur „Umstellung ok", wenn beides ohne
  Befund ist; sonst nennt sie jede Abweichung mit Sparte, Jahr, Feld und Differenz in
  Cent und verweist auf den Rückweg. Exitcodes 0 / 1 / 2.

## Testausgabe

Vollständig in `docs/neubau/berichte/P62-tests.txt`.

```
== tests.test_umstellung_pruefung -v ==
... 17 Tests ...
Ran 17 tests in 3.9s
OK

== unittest discover -s tests (frische FINANZ_DB) ==
Ran 430 tests in 184.961s
OK (skipped=1)
```

430 = 413 vorher + 17 neue, 1 übersprungen, wie erwartet.

## Offene Punkte

1. **Die Umstellung selbst steht aus.** Abschnitt 11 der Betriebsdoku ist geschrieben,
   aber nicht ausgeführt. Produktiv läuft weiterhin `studio`.
2. **Der Zahlenvergleich ist nur gegen synthetische Datenbanken gelaufen**, nicht gegen
   eine echte Produktionskopie. Der Pfad ist derselbe wie in P61/A2neu, aber der
   Nachweis auf echten Daten entsteht erst in Schritt 11.6.2.
3. **`FINANZ_FRONTEND=neu` ist nur lokal geprüft**, nicht auf CT 101 und nicht über
   Tailscale. Der Login-Weg wurde mangels Passwort nur bis zur Anmeldeseite geprüft
   (Umleitung und Auslieferung); dass der Sprung nach `/` nach erfolgreichem Login im
   Neubau landet, folgt aus dem Root-Mount, ist aber nicht durchgeklickt. Das ist
   Schritt 11.6.3 und ausdrücklich Sache des Nutzers.
4. **Der Modellwechsel P43c ist dokumentiert, nicht gemessen.** Welches Modell aus
   `outputs/modelltest/` gewinnt, steht in der Doku als Platzhalter `<modell>`; die
   CPU-Laufzeit misst der Nutzer beim Wechsel.
5. **Der Weg zu einer frischen „nachher"-Kopie** (11.6.2) legt kurzzeitig
   `umstellung-nachher.db` im Sicherungsordner des Containers an. Der Befehl liest die
   Live-Datenbank schreibgeschützt über die SQLite-Backup-API; er ist so noch nie auf
   CT 101 gelaufen und sollte beim ersten Mal Schritt für Schritt mit dem Nutzer
   ausgeführt werden. Die Datei anschließend löschen.
6. **Vorbestehende Eigenheit der Testsuite, nicht von diesem Paket verursacht:** ein
   zweiter Lauf auf derselben `FINANZ_DB`-Datei lässt
   `test_auto_kategorien.test_namensabgleich_hat_vorrang_vor_regel` fehlschlagen
   (Kategorie-IDs verschieben sich durch Reste des Vorlaufs). Mit frisch gelöschter
   `%TEMP%\p62-test.db` ist die Suite grün. Beim Fahren der Suite die Datei vorher
   entfernen.

Keine Passwörter, keine Wiederherstellungscodes, keine echten Namen und keine neuen
Abhängigkeiten in Code, Tests oder Doku.
