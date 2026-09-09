# P61: Migrationsprobe auf einer Kopie der Produktionsdatenbank

Meilenstein M6. Modell: `gpt-6-astra`, Aufwand medium. Branch `pkt/p61-migrationsprobe` von `neubau` (nach allen Migrationen aus M1–M5, insbesondere P11 mit der Bestandsdaten-Übernahme).

## 1. Ziel

Bevor auf CT 101 umgestellt wird, läuft der gesamte Schema-Nachzug (alle Migrationen, einschließlich der in P11 bereits eingebauten Übernahme der Bestandsdaten: Kassen je Sparte, Umbuchungspaare zu Transfers, Barbuchungen zu Kassa-Bewegungen) einmal vollständig gegen eine echte Kopie der Produktionsdatenbank. Die Summen je Sparte und Jahr vor und nach dem Nachzug werden verglichen; jede Abweichung wird gemeldet, keine wird stillschweigend hingenommen. Der Lauf wird ein zweites Mal auf einer frischen Kopie wiederholt und muss dasselbe Ergebnis liefern.

## 2. Kontext

Lies `docs/neubau/ARCHITEKTUR.md` Abschnitt 10 und 13, dann `app/migrate.py` (`status`, `pending`, `apply`, Sicherung vor dem ersten anstehenden Schritt), `app/backup.py` (`sichere_datenbank`, `pruefe_sicherung`), `docs/neubau/pakete/P11-konten-bewegungen.md` Abschnitt „Nachzug der Bestandsdaten" (genau das wird hier geprüft, nicht neu gebaut), `docs/neubau/pakete/P00-schema-nachzug.md`, `docs/BETRIEB-UND-ARCHITEKTUR.md` Abschnitt 6 (wo die Produktionsdatenbank liegt und wie die bestehende Sicherung funktioniert). **Diese Karte liest niemals die echte Produktionsdatenbank schreibend und arbeitet nie direkt auf `FINANZ_DB`** — jeder Lauf zieht zuerst eine Dateikopie und schreibt ausschließlich auf dieser Kopie.

## 3. Schnittstellen

Neues Skript `scripts/migrationsprobe.py`, nur Standardbibliothek und vorhandene Module (`app.migrate`, `sqlite3`):

```python
def summen_je_sparte_jahr(con) -> dict
    # {sparte_id: {jahr: {"einnahmen_cent": int, "ausgaben_cent": int}}}
    # rechnet direkt aus buchung/buchungszeile (typ != 'umbuchung', ohne Ruecksicht auf
    # Bewegungen/Transfer/neutral/storniert_am - das ist bewusst die ALTE, einfache Rechenweise,
    # gegen die verglichen wird)

def summen_neu(con) -> dict
    # dieselbe Form, aus v_einnahmen_ausgaben (nach dem Nachzug), inkl. Ausschluss von
    # neutral=1 und stornierten Zeilen, damit "gleich" wirklich "gleich in der Fachlichkeit" heisst

def vergleiche(alt: dict, neu: dict) -> dict
    # {"gleich": bool, "abweichungen": [{"sparte_id","jahr","feld","alt_cent","neu_cent","differenz_cent"}]}
    # jede Abweichung > 0 Cent wird aufgelistet, nichts wird gerundet oder verschluckt

def lauf(quelle_db: Path, arbeitsordner: Path) -> dict
    # 1. prueft, dass quelle_db existiert und lesbar ist
    # 2. kopiert quelle_db (shutil.copy2) nach arbeitsordner/kopie.db - danach wird NUR
    #    noch die Kopie angefasst
    # 3. summen_je_sparte_jahr(kopie) VOR dem Nachzug
    # 4. app.migrate.apply(kopie_connection, sicherung=...) mit Sicherung im arbeitsordner
    # 5. summen_neu(kopie) NACH dem Nachzug
    # 6. vergleiche(...); zusaetzlich: Anzahl "ungeklaerter" Transfers aus dem Migrationslog von P11
    #    (Notiz "Konten ungeklaert") und Anzahl Buchungen "Zahlung unbekannt" werden mitgemeldet,
    #    nicht nur die Summen
    # gibt {"summen_vorher", "summen_nachher", "vergleich", "migrationslog", "ungeklaerte_transfers",
    #       "zahlung_unbekannt"} zurueck und schreibt denselben Inhalt als JSON-Report nach
    #    arbeitsordner/bericht.json
```

Kommandozeile: `python -m scripts.migrationsprobe <pfad-zur-produktions-db-kopie-oder-original> --arbeitsordner <ordner>`; ohne `--arbeitsordner` wird ein `tempfile.TemporaryDirectory()` verwendet und am Ende ausgegeben, wohin der Bericht vor dem Aufräumen kopiert wurde (der Bericht selbst bleibt liegen, die Datenbank-Kopie wird gelöscht).

## 4. Nicht-Ziele

Keine neue Migration, keine Änderung an der in P11 gebauten Übernahmelogik. Keine Ausführung gegen die echte Produktionsdatenbank oder gegen `FINANZ_DB` (das ist P62). Kein Datenbereinigungs-Skript für Kategorien wie „Hohenegg" oder alte Kreditraten (ausdrücklich aus dem Scope, siehe ARCHITEKTUR Abschnitt 13).

## 5. Schritte

1. `summen_je_sparte_jahr`, `summen_neu`, `vergleiche` als reine Funktionen mit eigenen Tests.
2. `lauf` mit Kopiervorgang, Aufruf von `app.migrate.apply`, Bericht.
3. Kommandozeile.
4. Zweimal auf zwei frischen synthetischen Kopien laufen lassen (siehe Tests), Ergebnis vergleichen.
5. Tests, Gesamtlauf, Bericht.

## 6. Tests

Neue Datei `tests/test_migrationsprobe.py`, jede Prüfung mit `tempfile.TemporaryDirectory()`, nie im Arbeitsbaum:
- Fixture-Datenbank im Stand VOR den M1-Migrationen aufbauen (aus einer frühen Fassung von `db/schema.sql` oder gezielt per SQL: zwei Sparten, mehrere Jahre, Barbuchungen, ein Umbuchungspaar mit erkennbaren Konten, ein Umbuchungspaar ohne erkennbare Konten, eine stornierte Buchung falls das Testschema das schon kennt, sonst ohne) — Ziel ist ein realistischer Altbestand, keine echten Namen.
- `lauf()` auf einer Kopie dieser Fixture: `vergleich.gleich == True`, keine Abweichung je Sparte/Jahr; `ungeklaerte_transfers` nennt genau das eine unklare Paar.
- Quelle bleibt unverändert: Prüfsumme der ursprünglichen Fixture-Datei vor und nach `lauf()` identisch (nur die Kopie im Arbeitsordner hat sich geändert).
- Zweiter Lauf mit einer frischen Kopie derselben Fixture liefert denselben `vergleich` und dieselbe Anzahl ungeklärter Fälle (Reproduzierbarkeit).
- Künstlich eine Abweichung einbauen (z. B. eine Buchungszeile mit `neutral=1` nach dem Nachzug, die in der alten Rechenweise mitgezählt wurde): `vergleich.gleich == False`, die Abweichung erscheint mit Sparte, Jahr und Differenz in Cent.
- `lauf()` mit nicht existierender `quelle_db` → klarer Fehler, kein stiller Abbruch.
- Bericht `bericht.json` enthält alle Felder aus `lauf()`.

## 7. Fertig heißt

- [ ] Alle Tests grün, vollständige Ausgabe im Bericht.
- [ ] Zwei vollständige Läufe (siehe Schritt 4) mit identischem Ergebnis, beide Berichte im Bericht verlinkt oder eingefügt.
- [ ] Nachweis, dass die verwendete Quelle nach dem Lauf unverändert ist (Prüfsumme vorher/nachher im Bericht).
- [ ] Keine Geheimnisse, keine echten Namen, keine neuen Abhängigkeiten.
- [ ] Bericht geschrieben.

## 8. Modell und Aufwand

`gpt-6-astra`, Aufwand medium: die fachliche Vergleichsrechnung (alte vs. neue Zählweise, neutral/storniert/Transfer-Ausschlüsse) verlangt genaues Lesen der bestehenden Views, aber keine neue Architektur.

## 9. Bericht zurück

Geänderte und neue Dateien mit je einem Satz. Vollständige Testausgabe. Beide Migrationsproben-Berichte (Zusammenfassung). Offene Punkte mit Grund. Keine Commits, kein Push.
