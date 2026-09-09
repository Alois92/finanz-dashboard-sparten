# Architektur Neubau, Fassung 1

Stand: 9. September 2026. Gilt für Branch `neubau`. Vorlage für Design und Bedienung ist der Klick-Prototyp (privates Artifact, Kopie beim Nutzer). Entscheidungen des Nutzers aus den Interviews vom 8. und 9. September sind eingearbeitet.

## 1. Ziele und Leitplanken

- Eine Person, ein Container, SQLite, FastAPI, statisches JavaScript ohne Build-Schritt, lokale Modelle. Der Stack bleibt.
- Die App wird als Ganzes neu gebaut und in einem Schritt produktiv gesetzt. Bis dahin läuft der Branch `studio` unverändert in Produktion.
- Langfristig skalierbar: Konten aller Arten (Bank, Karte, Kassa, später Depot und Wallet), Geldbewegungen getrennt von Kostenbuchungen, Bereiche als Mandanten, Import-Adapter mit gemeinsamem Ziel. Broker und Kryptowährungen sind spätere Adapter und Kontoarten, kein Umbau.
- Beträge in Cent als Ganzzahl plus Währung. Kennungen statt Namen als Schlüssel. Kein SQL, das nur SQLite kann, wenn es eine Standardform gibt.
- Jede Schemaänderung liefert beides: den Nachzug für bestehende Datenbanken und die aktualisierte `db/schema.sql` für neue. Beide müssen denselben Stand ergeben.
- Keine stillen Auffangbuchungen, keine erfundenen Anfangsstände, keine automatische Umdeutung alter Daten. Unbekanntes wird angezeigt, nicht mit Null ersetzt.

## 2. Bereiche (Mandanten)

Der Verein ist ein eigener Bereich in derselben Datenbank, nie in Gesamtzahlen, Kontenlisten, Suche, Regeln, Belegen oder Export des Hauptbereichs.

```
bereich(id, name, kuerzel, typ 'haupt'|'verein', aktiv, sortierung)
```

`bereich_id` kommt an: `sparte`, `bankkonto`, `beleg`, `regel`, `globale_kategoriegruppe`, `auswertungsgruppe`, `export_profil`. Kategorien, Buchungen und Zeilen erben den Bereich über die Sparte. Nachzug: Bereich 1 „Haupt", Bereich 2 „Verein"; Sparte mit `typ='verein'` bekommt Bereich 2, alles andere Bereich 1; Konten, Belege, Regeln und Gruppen folgen ihrer Sparte, ohne Sparte Bereich 1.

Jeder Endpoint bekommt `bereich_id` (Standard 1) und löst ihn über eine gemeinsame Dependency `bereich_dep` auf. Referenzierte Kennungen werden gegen den Bereich geprüft: ein Beleg aus Bereich 2 darf nicht an eine Buchung aus Bereich 1. Später ergänzt `benutzer_bereich(benutzer, bereich_id)` die Berechtigung; heute sieht der eine Nutzer beide Bereiche und wechselt per Umschalter.

## 3. Konten und Geldbewegungen

Bestehende Tabelle `bankkonto` wird pragmatisch zum allgemeinen Konto erweitert, damit keine Fremdschlüssel wandern. In der Oberfläche heißt es „Konto".

```
bankkonto  +  art 'bank'|'karte'|'kassa'|'depot'|'wallet' (Standard 'bank')
           +  waehrung TEXT NOT NULL DEFAULT 'EUR'
           +  kartenendnummer TEXT
           +  bereich_id INTEGER NOT NULL REFERENCES bereich(id)
           +  sortierung INTEGER NOT NULL DEFAULT 0
```

Je Sparte genau eine Kassa (`art='kassa'`, `sparte_id` Pflicht), angelegt vom Nachzug für jede aktive Sparte. Kassenkonten sind vom CSV-Import ausgeschlossen.

```
bewegung(id, konto_id NOT NULL → bankkonto, datum, valuta, betrag_signed_cent NOT NULL,
         waehrung NOT NULL DEFAULT 'EUR',
         art 'zahlung'|'transfer'|'gebuehr'|'zins'|'trade' NOT NULL DEFAULT 'zahlung',
         transfer_id → transfer, bankumsatz_id UNIQUE → bankumsatz,
         text, gegenpartei, quelle 'manuell'|'import'|'ausgleich'|'kredit'|'nachzug' NOT NULL,
         erstellt_am)
transfer(id, art 'bankomat'|'umbuchung'|'ausgleich'|'kartenabrechnung'|'sonstig' NOT NULL,
         von_konto_id → bankkonto, nach_konto_id → bankkonto, datum, betrag_cent, notiz, erstellt_am)
buchung_bewegung(buchung_id → buchung, bewegung_id → bewegung, anteil_signed_cent, PRIMARY KEY (buchung_id, bewegung_id))
```

Regeln:
- Ein importierter Bankumsatz erzeugt genau eine Bewegung (`bankumsatz_id` eindeutig). Eine manuell erfasste Bankzahlung erzeugt eine vorläufige Bewegung mit `quelle='manuell'`; beim späteren Abgleich mit dem Import wird sie durch die importierte ersetzt, nicht addiert.
- Eine Barbuchung erzeugt automatisch eine Bewegung auf der Kassa der zahlenden Sparte. Bei einer Auslage ist das die Kassa des Zahlers, nicht der Ziel-Sparte.
- Ein Transfer besteht aus zwei Bewegungen mit entgegengesetztem Vorzeichen. Bankomat-Abhebung = Transfer Bank → Kassa derselben Sparte; das ist erlaubt.
- Kontostände rechnen ausschließlich mit Bewegungen ab dem letzten Anker. Einnahmen und Ausgaben rechnen ausschließlich mit Buchungszeilen. Beides ist verknüpft, aber nie dasselbe.
- Depot und Wallet: Bewegungen mit `art='trade'` und später eigene Tabellen `position`/`kurs`. Nicht Teil des Neubaus, nur Platz dafür.

```
kontostand_anker(id, konto_id, stichtag, saldo_cent, quelle 'auszug'|'manuell'|'import', beleg_id, notiz, erstellt_am)
kassazaehlung(id, konto_id, datum, gerechnet_cent, gezaehlt_cent, differenz_cent, status 'offen'|'geklaert', notiz, buchung_id)
```

Ein Anker ist ein Tagesendstand. Ein neuer Auszug vergleicht seinen Stand mit der Rechnung und legt die Differenz offen. Eine Kassadifferenz ist zunächst offen; „als Kassadifferenz buchen" erzeugt ausdrücklich eine Buchung in der Kategorie „Kassadifferenz" der Sparte.

## 4. Kostenbuchungen

`buchung` und `buchungszeile` bleiben. Ergänzungen:

```
buchung        + version INTEGER NOT NULL DEFAULT 1
               + client_request_id TEXT UNIQUE
               + original_id → buchung           (Erstattung oder Storno bezieht sich hierauf)
               + storniert_am TEXT
buchungszeile  + neutral INTEGER NOT NULL DEFAULT 0   (1 = zählt nicht als Einnahme/Ausgabe, z. B. Tilgung)
buchung_aenderung(id, buchung_id, zeitpunkt, feld, alt, neu, grund)
```

- `PUT /api/buchungen/{id}` prüft `version` (409 bei Konflikt), ändert Zeilen anhand ihrer `id` in place, legt neue Zeilen an, löscht fehlende. Zeilen-IDs bleiben stabil.
- Erstattung: neue Buchung mit `original_id`, Richtung Einnahme in derselben Kategorie. Die Kategorie darf dann `richtung='beides'`. Netto-Kosten einer Kategorie = Ausgaben minus verknüpfte Erstattungen.
- Storno: `storniert_am` setzen, Buchung bleibt sichtbar, zählt nicht mehr.
- Die View `v_einnahmen_ausgaben` schließt `neutral=1`, Umbuchungen und stornierte Buchungen aus.
- Geldaktionen (Buchung anlegen, Ausgleich, Foto übernehmen) tragen `client_request_id`. Gleicher Schlüssel und gleiche Daten liefern dasselbe Ergebnis, gleicher Schlüssel und andere Daten liefern 409.

## 5. Auslagen und Ausgleich

Privat bezahlt für eine andere Sparte. Die Buchung liegt bei der Sparte, der die Kosten gehören.

```
auslage(id, buchung_id UNIQUE → buchung, zahler_sparte_id → sparte, zahler_konto_id → bankkonto, betrag_cent, erstellt_am)
ausgleich(id, transfer_id → transfer, datum, von_sparte_id, nach_sparte_id, betrag_cent,
          zahlungsart 'bar'|'bank', client_request_id TEXT UNIQUE, aufgehoben_am, notiz)
ausgleich_zuordnung(ausgleich_id, auslage_id, betrag_cent, PRIMARY KEY (ausgleich_id, auslage_id))
```

- Offen je Auslage = `betrag_cent` minus Summe der Zuordnungen nicht aufgehobener Ausgleiche.
- `POST /api/ausgleiche` erhält Zahler-Sparte, Ziel-Sparte, Auslagen-IDs, Datum, Betrag, Zahlungsart, Quell- und Zielkonto, `client_request_id`. Verteilung FIFO nach Datum und ID innerhalb der gewählten Auslagen. Betrag größer als Summe der offenen Beträge wird abgelehnt. Bei Barzahlung und unzureichender Kassa: Warnung in der Antwort, kein Abbruch.
- `DELETE /api/ausgleiche/{id}` setzt `aufgehoben_am` und storniert den Transfer. Historie bleibt.
- Änderung einer Buchung mit Auslage: Betrag darf nicht unter die zugeordnete Summe fallen; sonst 409 mit Liste der betroffenen Ausgleiche.

## 6. Kredit

```
kredit(id, sparte_id, konto_id, name, monatsrate_cent, zinssatz REAL, beginn, kategorie_zins_id → kategorie, aktiv)
kredit_jahr(kredit_id, jahr, zins_cent, restschuld_cent, status 'geschaetzt'|'bestaetigt', beleg_id, PRIMARY KEY (kredit_id, jahr))
```

Jede Rate ist eine Buchung mit zwei Zeilen: Zins (Kategorie Zinsen, Ausgabe) und Tilgung (`neutral=1`). Ohne bestätigtes Jahr wird der Zins nach dem Vorjahr geschätzt. `PUT /api/kredite/{id}/jahre/{jahr}` mit Jahreszins und Restschuld verteilt den Zins centgenau auf die vorhandenen Raten des Jahres (Division mit Rest), erfindet keine fehlenden Raten und meldet Abweichungen.

## 7. Kategorien, Regeln, Kennzahlen

- `PATCH /api/kategorien/{id}`: `name`, `aktiv`, `richtung`, `sortierung`. Stillgelegte Kategorien bleiben in allen Auswertungen und Listen, nur nicht in der Auswahl für neue Buchungen.
- Stichwörter sind Regeln. `regel` bekommt `quelle 'gelernt'|'stichwort'|'manuell'`, `auto_verbuchen INTEGER`, `eingabe_sparte_id`, `gelernt_aus_buchung_id`, `bereich_id`. Nur `auto_verbuchen=1` darf Bankumsätze automatisch verbuchen; Stichwörter sind Vorschläge. `POST /api/regeln`, erweitertes `PATCH`, `POST /api/regeln/vorschau`. Der Resolver in `app/regeln.py` erhält Text, Betrag, Konto und die gewählte Sparte; die Sparte ist bei manueller Erfassung verbindlich.
- Eigene Kennzahlen:

```
kennzahl(id, sparte_id, name, sortierung)
kennzahl_term(id, kennzahl_id, kategorie_id, messgroesse 'einnahmen'|'ausgaben'|'netto', vorzeichen INTEGER)
```

## 8. Auswertung: ein Filtervertrag

`app/auswertungen.py` bündelt alle Rechenwege. Ein Filter besteht aus: `bereich_id`, `sparte_id` oder `auswertungsgruppe_id`, `globalgruppe_id`, `jahr` oder `von`/`bis`, `kategorie_id`, `richtung`, `zahlungsart`, `stichtag`.

- `GET /api/uebersicht`: Ist bis Stichtag, Vorjahr gleicher Zeitraum, Vorjahresrest ab Stichtag, Jahreserwartung (Ist plus Vorjahresrest), Sparten-Kacheln, Monatsreihen, Hinweise, Datenstand je Sparte.
- `GET /api/jahresmatrix`: je Kategorie und Jahr Einnahmen, Ausgaben, Saldo getrennt, plus Erwartung fürs laufende Jahr, mit Kategorie-IDs und Aktiv-Kennzeichen.
- `GET /api/buchungen`: derselbe Filter plus `q`, `limit` (Standard 100) und Cursor aus Datum und ID; Gesamtsummen über alle Treffer.
- Drilldowns verwenden exakt denselben Filter wie die Zahl, die angeklickt wurde.
- Stichtag: Serverdatum in Europe/Vienna, 29. Februar wird auf den 28. abgebildet. Kein festes Jahr im Code.
- Hinweise: Kostenanstieg (hochgerechnet), fehlende regelmäßige Einnahme erst fünf Tage nach dem üblichen Tag, offene Auslagen, größte Einzelbuchung, offene Bankumsätze, Anteil der größten Kategorie. Ausgeblendete Hinweise werden serverseitig je Schlüssel gespeichert (`hinweis_aus(schluessel, bis_wert_aendert, erstellt_am)`).

## 9. Export

```
export_profil(id, bereich_id, sparte_id, jahr, name, erstellt_am, aktualisiert_am)
export_profil_ausschluss(profil_id, kategorie_id, buchung_id)
```

`POST /api/export/vorschau` liefert ausgewählte Zeilen, Summen, fehlende Belege und eine Revision. `POST /api/export/paket` prüft die Revision und erzeugt ein ZIP: Excel-Liste, Belegfotos benannt `JJJJ-MM-TT_Betrag_EUR_B<buchung>_Beleg<id>.<ext>`, Inhaltsliste mit IDs, Auswahlumfang und Zeitpunkt. Suche grenzt nur die Prüfliste ein; Teil-Export nur mit ausdrücklichem Schalter. „Alle Sparten" bedeutet alle Sparten des Bereichs. `steuer_relevant` bleibt ein fachliches Feld und wird nicht für die Auswahl verwendet.

## 10. Schema-Nachzug

- `db/migrations/NNN_name.sql` oder `NNN_name.py` (mit `up(con)`), fortlaufend nummeriert.
- `schema_version(version INTEGER PRIMARY KEY, name, angewendet_am)`.
- `app/migrate.py`: `status(con)`, `pending(con)`, `apply(con, backup_dir)`. Jeder Schritt in einer Transaktion. Vor dem ersten anstehenden Schritt eine datierte Sicherung über die vorhandene Backup-Funktion. Scheitert ein Schritt: Rollback, Abbruch, App startet ohne Schreibrechte und meldet es in der Oberfläche.
- Neue Datenbank: `schema.sql` einspielen und alle Migrationen als angewendet markieren. Bestehende ohne `schema_version`: Version 0 als Basis eintragen, danach anstehende Schritte.
- Aufruf beim Start in `app/main.py` vor dem ersten Request und vor Hintergrundaufgaben; zusätzlich `python -m app.migrate status|apply`.
- Datenbereinigungen und fachliche Umdeutungen gehören nicht in automatische Migrationen; sie laufen als vorbereitete Skripte mit Vorschau und Freigabe.

## 11. Frontend

Neues Verzeichnis `static-neu/`, während der Entwicklung unter `/neu` gemountet, bei der Umstellung unter `/`. Kein Build. ES-Module: `app.js` (Zustand, Router), `api.js`, `charts.js`, `format.js`, `pages/uebersicht.js`, `pages/sparte.js`, `pages/erfassen.js`, `pages/buchungen.js`, `pages/konten.js`, `pages/kategorien.js`, `pages/belege.js`, `pages/bankimport.js`, `pages/export.js`. Design-Tokens, Layout, Texte und Abläufe kommen aus dem Prototyp; Schriften liegen lokal in `static-neu/fonts/`. Handy startet auf Erfassen, PC auf Übersicht. Bereichsumschalter in der Sidebar und im Mobil-Menü.

## 12. Tests

`python -m unittest discover -s tests` mit `FINANZ_DB` auf Wegwerf-Datenbank; Integrationstests aus `scripts/` werden nach `tests/` überführt. Pflichtszenarien: privat bezahlte Hofausgabe → Teilausgleich → Rücknahme; Foto → Buchung → CSV-Import ohne Doppelzählung; Kreditrate → Jahreszins bestätigt; Verein in jedem Datenpfad ausgeschlossen; Split → Kategorie stillgelegt und umbenannt → Kennzahl und Export unverändert; Neustart mit alter Datenbank → Nachzug → Summen je Sparte und Jahr unverändert.

## 13. Migration der Bestandsdaten (Meilenstein M6)

Reihenfolge: Sicherung, Nachzug auf einer Kopie, Summenvergleich je Sparte und Jahr vorher/nachher, zweite Probe, dann Produktion. Zuordnung: `bankkonto` → Konto mit `art='bank'`; je Sparte Kassa anlegen; bestehende Umbuchungen (`transfer_gruppe_id`) → Transfer mit zwei Bewegungen, Konten nur bei eindeutiger Quelle, sonst als „ungeklärt" markiert; Buchungen mit `zahlungsart='bar'` → Kassa-Bewegungen; Anfangsstände bleiben unbekannt, bis der Nutzer Anker setzt. Keine Umdeutung von Kategorien wie „Hohenegg" oder alten Kreditraten.

## 14. Betrieb

Deployment bleibt: `git pull` im Container, Neustart; der Nachzug läuft beim Start mit Sicherung. Sicherung umfasst künftig Datenbank und Belegverzeichnis mit Manifest. `GET /api/betrieb/status` (angemeldet) zeigt Schema-Version, letzte Sicherung, Belege gesichert, Zweitziel erreichbar.
