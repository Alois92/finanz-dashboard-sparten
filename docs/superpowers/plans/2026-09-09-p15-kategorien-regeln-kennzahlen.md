# P15 Kategorien, Regeln und Kennzahlen Implementation Plan

> Umsetzung im bestehenden Worktree ohne Commit; die Nutzer-Auftragskarte und ihre bestätigte Architekturentscheidung sind die freigegebene Spezifikation.

**Goal:** Kategorien, Regeln mit Herkunft und bereichsgeprüfte eigene Kennzahlen vollständig gemäß P15 bereitstellen.

**Architecture:** Bestehende Kategorien- und Regelrouter werden gezielt erweitert. Die Regelauflösung bleibt in `app/regeln.py`; Kennzahlen erhalten mit `app/kennzahlen.py` und `app/routers/kennzahlen.py` einen eigenen Daten-/HTTP-Schnitt. Migration 008 erweitert `regel` und legt die Kennzahlentabellen an; `schema.sql` bildet denselben Endstand ab.

**Tech Stack:** Python, FastAPI, Pydantic, SQLite, unittest, bestehender Migrationsrunner.

## Global Constraints

- Bereichsdependency an fachlichen Endpunkten, keine Änderung an Auth/Health/Schema/Betrieb.
- Keine Konto-, Bewegungs- oder Transferstrukturen.
- Migration idempotent; Runner allgemein lassen.
- Keine neuen Abhängigkeiten; Tests mit `tempfile.TemporaryDirectory()` außerhalb des Arbeitsbaums.
- Referenzen mit den Helfern aus `app/bereiche.py` prüfen.

### Tasks

1. Migration/schema: Test für zweimaligen Nachzug, Migration 008 und Schema-Endstand.
2. Kategorien: Test für inklusive Liste und PATCH; minimaler Router-Patch.
3. Regelmodell/-auflösung: Herkunft, Bereich/Sparte-Kontext, Konflikte, stillgelegte Ziele; erst Tests, dann Implementierung.
4. Regel-API/Import/Lernen: CRUD/Preview und Herkunftsregeln; bestehende Importpfade minimal ändern.
5. Kennzahlen: Rechenmodul und CRUD-/GET-Router mit Bereichs- und ID-Prüfungen, Tests.
6. Gesamtsuite, Bestandsdatenbank aus Schema/Seed, doppelter Nachzug, Bericht.
