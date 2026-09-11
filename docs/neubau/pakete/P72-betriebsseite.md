# P72: Betriebsseite

Branch `pkt/p72-betriebsseite` von `neubau` (Stand `76ae6ac`). Nutzerwunsch vom 11.09.2026, QA-Befund QA4-06 (`docs/neubau/berichte/QA-4-belege-foto-export-betrieb-login.md`): der Betriebsstatus (`GET /api/betrieb/status`) war bisher nirgendwo in der Oberfläche sichtbar.

## Ziel

Eine Betriebsseite (`#/betrieb`) im neuen Frontend (`static-neu/`), die für angemeldete Nutzer bündelt: Datenbankschema/Nachzug, Sicherungsstatus (mit Knopf zum manuellen Anstoßen), Erreichbarkeit der lokalen Foto-Auswertung (Ollama), Status des KI-Vorschlags, sowie Frontend/Instanz.

## Schnittstellen

Backend (`app/routers/betrieb.py`):
- `GET /api/betrieb/uebersicht` – bündelt Schema/Sicherung (wiederverwendet aus `app/main.py::betrieb_status()`, jetzt als `betrieb.baue_sicherung_und_schema_status()` ausgelagert), Ollama-Erreichbarkeit (wiederverwendet `beleg_auswertung.auswertung_status()`), `ki_vorschlag_aktiv`, `frontend`, `instanz`, `auswertungswarteschlange` (offen/laeuft/fehler aus `beleg_auswertung`). Keine Pfade, Secrets, Cookies.
- `POST /api/betrieb/sicherung` – stößt `backup.sichere_datenbank()` synchron in einem Thread an (derselbe Weg wie im Lifespan). 409 bei bereits laufender Sicherung (`backup.sicherungs_lock.locked()`-Check). 503 kommt automatisch von der bestehenden `schreibschutz_middleware`, kein eigener Pfad im Router.

Frontend (`static-neu/`):
- `pages/betrieb.js` + `pages/betrieb.css`, Route `betrieb` in `app.js` registriert (Sidebar, letzter Eintrag). Bottom-Nav bleibt unverändert (siehe Bericht, Abweichung).

## Tests

`tests/test_p72_betrieb.py`: Übersicht ohne Geheimnisse, Ollama gemockt (erreichbar/nicht erreichbar), Sicherung liefert Ergebnis, 409 bei gehaltenem Lock, 503 über die echte Middleware (ASGI-Aufruf, Muster `tests/test_bereiche.py`), `node --check` für `betrieb.js`/`app.js`. `tests/test_bereiche.py` erweitert um die neue Ausnahme `/api/betrieb/sicherung` in `test_fachliche_endpoints_haben_zentrale_dependency`.

Siehe `docs/neubau/berichte/P72-runde1.md` für Ergebnis, Abweichungen und offene Punkte.
