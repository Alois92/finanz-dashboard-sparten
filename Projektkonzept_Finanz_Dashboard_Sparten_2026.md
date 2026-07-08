# Projektkonzept: Lokales Finanz-Dashboard mit Sparten, Belegen und Auswertungen

Privat, Vermietung, Zimmervermietung, Bauernhof, Verein, Privat Alois, Privat Frau

Stand: Juli 2026

Dieses Dokument ersetzt nicht die urspruengliche Konzeption, sondern ist eine neue, umgearbeitete Zielversion. Der Fokus liegt nicht auf einem klassischen Buchhaltungsprogramm, sondern auf einem lokalen Informations-, Beleg- und Auswertungssystem.

Wichtige Leitidee:

> Die Daten bleiben je Sparte sauber getrennt. In den Auswertungen koennen sie frei zusammengeklickt und grafisch dargestellt werden.

---

## 1. Ziel des Projekts

Das System soll helfen, Einnahmen, Ausgaben, Bankbewegungen und Belege uebersichtlich zu erfassen, wiederzufinden und grafisch auszuwerten.

Es soll kein vollwertiges Buchhaltungsprogramm mit Doppik, Bilanzierung oder Steuerlogik ersetzen. Stattdessen soll es ein praktisches lokales Werkzeug sein fuer:

- persoenliche Finanzuebersicht
- getrennte Spartenverwaltung
- Bank-Eingangs- und Ausgangsuebersichten
- Belegablage und Belegzuordnung
- flexible grafische Auswertungen
- exportierbare Aufstellungen fuer Vermietung, Verein oder Steuerberater
- spaetere Erweiterung mit OCR, lokaler KI und automatischen Vorschlaegen

Der wichtigste Nutzen ist nicht, dass jede Buchung steuerlich perfekt automatisiert wird, sondern dass jederzeit sichtbar ist:

- Woher kamen Einnahmen?
- Wohin gingen Ausgaben?
- Welche Sparte verursacht welche Kosten?
- Welche Kategorien steigen oder fallen?
- Welche Belege fehlen?
- Welche Daten koennen fuer Steuerberater, Verein oder eigene Planung exportiert werden?

---

## 2. Grundprinzip: Sparten getrennt, Auswertung flexibel

Das System besteht aus mehreren getrennten Sparten. Jede Sparte funktioniert wie ein eigener Arbeitsbereich oder Reiter.

Geplante Sparten:

- Privatvermietung
- Zimmervermietung Hof
- Bauernhof
- Verein
- Alois privat
- Frau privat

Jede Sparte hat eigene:

- Bankkonten oder Bankimporte
- Einnahmen und Ausgaben
- Kategorien
- Unterkategorien
- Belege
- Regeln und Vorschlaege
- Auswertungen
- Exporte

Trotzdem soll es moeglich sein, Sparten in den Dashboards frei zusammenzufassen.

Beispiele:

- Vermietung gesamt = Privatvermietung + Zimmervermietung Hof
- Privat gesamt = Alois privat + Frau privat
- Hof gesamt = Bauernhof + Zimmervermietung Hof
- Alles ohne Verein = alle Sparten ausser Verein
- Gesamtuebersicht = alle Sparten
- Steuerrelevante Bereiche = Privatvermietung + Zimmervermietung Hof + Bauernhof
- Verein separat = nur Verein

Wichtig: Diese Zusammenfuehrung findet nur in der Auswertung statt. Die Originaldaten bleiben immer ihrer Sparte zugeordnet.

---

## 3. Keine klassische Buchhaltung, sondern Finanzinformationssystem

Das System soll bewusst einfacher und alltagstauglicher sein als ein klassisches Buchhaltungsprogramm.

Es braucht:

- Einnahmen
- Ausgaben
- Kategorien
- Belege
- Bankimporte
- Filter
- Diagramme
- Exporte

Es braucht im Start nicht zwingend:

- doppelte Buchhaltung
- Kontenrahmen
- Bilanz
- Soll/Haben-Logik
- automatische Steuererklaerung
- komplexe Periodenabgrenzung
- verpflichtende steuerliche Vollstaendigkeit fuer Privatbereiche

Fuer Vermietung, Verein und Bauernhof sollen die Daten aber sauber genug sein, dass daraus gute Aufstellungen und Exportpakete entstehen koennen.

---

## 4. Benutzeroberflaeche: Reiter, Filter, Diagramme

Die Oberflaeche soll klickbar und filterbar sein. Der Benutzer soll keine Abfragen schreiben muessen.

### 4.1 Hauptnavigation

Oben oder seitlich gibt es Reiter:

- Dashboard
- Buchungen
- Belege
- Bankimporte
- Kategorien
- Auswertungen
- Exporte
- Einstellungen

Zusaetzlich gibt es eine Sparten-Auswahl:

- Alle Sparten
- Privatvermietung
- Zimmervermietung Hof
- Bauernhof
- Verein
- Alois privat
- Frau privat
- eigene Auswertungsgruppen

### 4.2 Filterleiste

Jedes Dashboard und jede Liste hat eine Filterleiste.

Filter:

- Zeitraum: Monat, Quartal, Jahr, frei
- Sparte: eine, mehrere oder alle
- Auswertungsgruppe: z. B. Vermietung gesamt, Privat gesamt
- Richtung: Einnahmen, Ausgaben, beide
- Hauptkategorie
- Unterkategorie
- Detailkategorie
- Tag
- Bankkonto
- Zahlungsart
- Belegstatus
- Person
- Betrag von/bis
- Suchtext

Alle Filter sollen per Klick, Dropdown, Checkbox, Suchfeld oder Mehrfachauswahl funktionieren.

### 4.3 Diagramme

Gewuenschte Diagramme:

- Einnahmen und Ausgaben pro Monat
- Einnahmen und Ausgaben pro Sparte
- Kategorienvergleich
- Top-Ausgaben
- Top-Einnahmen
- Entwicklung einer Kategorie ueber die Zeit
- Jahresvergleich
- Ausgaben je Person
- Vermietungsergebnis
- Bauernhof-Kostenstruktur
- Vereins-Einnahmen/Ausgaben
- Belege fehlen nach Sparte oder Kategorie
- Kreis-/Donutdiagramm fuer Kategorien
- Balkendiagramm fuer Monatswerte
- Liniengrafik fuer Entwicklung
- Tabelle unter jeder Grafik mit den passenden Einzelbuchungen

Wichtig: Wenn man auf eine Grafik klickt, soll die passende Detailansicht erscheinen. Beispiel: Klick auf "Versicherungen" zeigt alle Buchungen, die in der Auswertung enthalten sind.

---

## 5. Kategorienmodell

Das Kategorienmodell muss flexibel sein. Kategorien duerfen nicht fest im Code eingebaut sein.

Jede Sparte kann eigene Kategorien haben. Kategorien koennen spaeter selbst hinzugefuegt, umbenannt, deaktiviert oder weiter unterteilt werden.

### 5.1 Grundstruktur je Buchung

Jede Buchung hat mindestens:

- Sparte
- Datum
- Richtung: Einnahme oder Ausgabe
- Betrag
- Hauptkategorie
- optional Unterkategorie
- optional Detailkategorie
- optional Tags
- optional Beleg
- optional Bankumsatz
- Notiz

Beispiel Bauernhof:

- Sparte: Bauernhof
- Richtung: Ausgabe
- Hauptkategorie: Tiere
- Unterkategorie: Tierarzt
- Detailkategorie: Medikamente
- Tag: Rinder

Beispiel Privat:

- Sparte: Alois privat
- Richtung: Ausgabe
- Hauptkategorie: Auto
- Unterkategorie: Versicherung
- Detailkategorie: Haftpflicht

### 5.2 Kategorieebenen

Empfohlene Ebenen:

1. Sparte
2. Richtung
3. Hauptkategorie
4. Unterkategorie
5. Detailkategorie
6. Tags

Die ersten drei Ebenen sind fuer gute Auswertungen wichtig. Detailkategorien und Tags koennen nach Bedarf wachsen.

### 5.3 Globale Auswertungsgruppen

Manche Auswertungen sollen Kategorien aus verschiedenen Sparten zusammenfassen.

Beispiel "Versicherungen gesamt":

- Alois privat: Auto - Versicherung
- Frau privat: Krankenversicherung
- Bauernhof: Betriebsversicherung
- Privatvermietung: Gebaeudeversicherung
- Zimmervermietung Hof: Haftpflicht oder Gebaeudeanteil

Dafuer braucht es globale Auswertungsgruppen. Eine Kategorie kann einer oder mehreren globalen Gruppen zugeordnet werden.

Beispiele fuer globale Gruppen:

- Versicherungen
- Auto und Mobilitaet
- Gebaeude
- Instandhaltung
- Tiere
- Lebensmittel und Leben
- Energie
- Steuern und Abgaben
- Vermietung
- Hofbetrieb
- Verein
- Gesundheit
- Freizeit

Damit kann man z. B. grafisch darstellen:

- Versicherungen gesamt ueber alle Sparten
- Versicherungen nur privat
- Versicherungen nur betrieblich
- Gebaeudekosten Vermietung + Hof
- Auto-Ausgaben Alois privat
- Tierarztkosten im Bauernhof

---

## 6. Beispielkategorien je Sparte

Die folgenden Kategorien sind Startvorschlaege. Sie sollen spaeter in der Oberflaeche bearbeitbar sein.

### 6.1 Bauernhof

Einnahmen:

- Verkauf Tiere
- Verkauf Produkte
- Foerderungen
- Dienstleistungen
- Sonstige Einnahmen

Ausgaben:

- Futtermittel
- Tierarzt
- Medikamente
- Tiereinkauf
- Maschinen
- Diesel und Treibstoff
- Reparaturen Maschinen
- Gebaeude
- Instandhaltung
- Strom und Energie
- Wasser
- Versicherung
- Beitraege und Abgaben
- Werkzeuge und Material
- Pacht
- Sonstiges

Optionale Tags:

- Rinder
- Wald
- Wiese
- Maschinen
- Stall
- Foerderung

### 6.2 Zimmervermietung Hof

Einnahmen:

- Zimmermiete
- Reinigungspauschale
- Nebenkosten
- Sonstige Einnahmen

Ausgaben:

- Reinigung
- Waesche
- Reparaturen
- Instandhaltung
- Plattformgebuehren
- Ausstattung
- Moebel
- Strom
- Wasser
- Heizung
- Versicherung
- Werbung
- Sonstiges

Optionale Tags:

- Gast
- Zimmer
- Plattform
- Saison

### 6.3 Privatvermietung

Einnahmen:

- Miete
- Betriebskosten-Akonto
- Nachzahlung Betriebskosten
- Sonstige Einnahmen

Ausgaben:

- Betriebskosten
- Reparaturen
- Instandhaltung
- Darlehenszinsen
- Versicherung
- Gebuehren und Abgaben
- Steuerberatung
- Verwaltung
- Rueckzahlungen
- Sonstiges

Optionale Tags:

- Wohnung
- Gebaeude
- Mieter
- Jahresabrechnung

### 6.4 Verein

Einnahmen:

- Mitgliedsbeitraege
- Spenden
- Veranstaltungseinnahmen
- Foerderungen
- Verkauf
- Sonstige Einnahmen

Ausgaben:

- Veranstaltungskosten
- Miete
- Material
- Bewirtung
- Versicherung
- Bankspesen
- Verwaltung
- Anschaffungen
- Fahrtkosten
- Sonstiges

Optionale Tags:

- Veranstaltung
- Mitglied
- Vorstand
- Kassa
- Bank

### 6.5 Alois privat

Einnahmen:

- Gehalt
- Rueckerstattung
- Privatverkauf
- Sonstige Einnahmen

Ausgaben:

- Leben
- Wohnen
- Auto
- Treibstoff
- Versicherung
- Gesundheit
- Freizeit
- Kleidung
- Technik
- Abos
- Bank und Gebuehren
- Steuern und Abgaben
- Geschenke
- Sonstiges

Optionale Tags:

- Fixkosten
- variabel
- wichtig
- einmalig
- wiederkehrend

### 6.6 Frau privat

Einnahmen:

- Gehalt
- Rueckerstattung
- Privatverkauf
- Sonstige Einnahmen

Ausgaben:

- Leben
- Wohnen
- Auto
- Treibstoff
- Versicherung
- Gesundheit
- Freizeit
- Kleidung
- Technik
- Abos
- Bank und Gebuehren
- Steuern und Abgaben
- Geschenke
- Sonstiges

Optionale Tags:

- Fixkosten
- variabel
- wichtig
- einmalig
- wiederkehrend

---

## 7. Buchungen und Bankimport

### 7.1 Buchungstypen

Es gibt drei praktische Arten, wie eine Buchung entsteht:

1. Bankbuchung aus CSV-Import
2. Manuelle Buchung
3. Bar-/Kassabuchung

Fachlich hat jede Buchung einen von drei **Typen**:

- **Einnahme**
- **Ausgabe**
- **Umbuchung** (Transfer zwischen eigenen Konten)

Umbuchungen sind wichtig, damit Eigenuebertraege (z. B. Privatkonto -> Sparkonto oder Entnahme Hof -> Privat) die Auswertungen nicht verfaelschen. Sie werden standardmaessig aus Einnahmen-/Ausgaben-Diagrammen herausgerechnet und koennen ueber `transfer_gruppe_id` als zusammengehoeriges Paar (Abgang + Zugang) verknuepft werden.

### 7.1a Splitbuchungen

Ein Bankumsatz oder eine Bargeldrechnung kann auf mehrere Kategorien aufgeteilt werden (z. B. Baumarktrechnung = Hof + Privat). Deshalb besteht eine Buchung aus:

- einem **Kopf** (`buchung`) mit Sparte, Datum, Typ, Belegstatus usw.
- einer oder mehreren **Zeilen** (`buchungszeile`) mit je Kategorie und Betrag

Regel: Die Summe der Buchungszeilen muss dem Kopfbetrag entsprechen, und bei verknuepftem Bankumsatz auch dessen Betrag. Eine einfache Buchung ohne Split hat genau eine Zeile.

Jede Buchung kann spaeter mit einem oder mehreren Belegen verknuepft werden.

### 7.2 Bankimport

Bankdaten sollen per CSV importiert werden. Optional kann spaeter camt.053 ergaenzt werden.

Beim Import erkennt das System:

- Datum
- Betrag (wird als `betrag_cent` gespeichert)
- Kontostand nach der Buchung, falls in der CSV vorhanden (`saldo_nachher_cent`)
- Buchungstext
- Auftraggeber oder Empfaenger
- IBAN, falls vorhanden
- Konto
- Importquelle

Der Import soll Dubletten erkennen. Mehrfachimport derselben CSV darf keine doppelten Buchungen erzeugen. Dazu bekommt jeder Umsatz einen `import_hash` (je Konto eindeutig), und jeder Importlauf wird als `import_batch` protokolliert.

**Kontostand-Abgleich:** Wenn der Saldo nach der Buchung mitgeliefert wird, kann das System pruefen, ob der errechnete Verlauf zum echten Kontostand passt. Abweichungen weisen auf fehlende oder doppelte Umsaetze hin - der beste Weg, um Luecken automatisch zu finden.

### 7.3 Zuordnung zur Sparte

Wenn ein Bankkonto eindeutig einer Sparte gehoert, werden importierte Bewegungen automatisch dieser Sparte zugeordnet.

Wenn ein Konto gemischt genutzt wird, muss die Buchung manuell einer Sparte zugeordnet werden.

Beispiele:

- Vereinskonto -> automatisch Verein
- Vermietungskonto -> automatisch Privatvermietung
- Privatkonto Alois -> Alois privat
- gemischtes Hof-/Privatkonto -> manuelle Auswahl oder Regelvorschlag

### 7.4 Regeln und Vorschlaege

Das System soll Vorschlaege machen, aber nicht ungeprueft fest buchen.

Regelbeispiele:

- "Miete" im Text -> Privatvermietung, Einnahme, Miete
- bekannter Tierarzt -> Bauernhof, Ausgabe, Tierarzt
- Versicherung XY -> globale Gruppe Versicherungen, passende Sparte nach Konto
- Supermarkt -> privat, Ausgabe, Leben
- Vereinsmitglied Name -> Verein, Einnahme, Mitgliedsbeitrag

Vorschlaege koennen bestaetigt oder korrigiert werden. Aus Korrekturen koennen neue Regeln entstehen.

---

## 8. Belege

Belege sind Nachweise zu Buchungen. Sie sollen nicht den Alltag verlangsamen, aber spaeter leicht auffindbar sein.

### 8.1 Belegstatus

Jede Buchung kann einen Belegstatus haben:

- kein Beleg notwendig
- Beleg fehlt
- Beleg vorhanden
- Eigenbeleg
- Beleg unklar

### 8.2 Belegablage

Belege koennen kommen aus:

- Scan
- Smartphone-Foto
- PDF
- E-Mail-Anhang, manuell gespeichert
- Paperless-ngx

Empfohlene Ablage:

```text
daten/
  belege/
    bauernhof/
    zimmervermietung-hof/
    privatvermietung/
    verein/
    alois-privat/
    frau-privat/
```

Jeder Beleg wird mit seiner Sparte verbunden. Ein Beleg kann optional mehreren Buchungen zugeordnet werden, z. B. bei Splitbuchungen.

### 8.3 Belege und Export

Fuer Vermietung, Zimmervermietung, Bauernhof und Verein soll ein Exportpaket moeglich sein:

- Uebersicht als PDF
- Buchungsliste als CSV/XLSX
- Belegliste
- Belegdateien
- optional ZIP-Paket

Privatbereiche brauchen diesen Export meist nicht, koennen ihn aber bekommen.

---

## 9. Dashboards und Auswertungen

### 9.1 Startdashboard

Das Startdashboard zeigt:

- Einnahmen aktueller Monat
- Ausgaben aktueller Monat
- Saldo
- Einnahmen/Ausgaben nach Sparte
- Top 10 Ausgabenkategorien
- offene Buchungen ohne Kategorie
- Buchungen mit fehlendem Beleg
- Vergleich zum Vormonat

### 9.2 Sparten-Dashboard

Jede Sparte hat ein eigenes Dashboard:

- Einnahmen/Ausgaben im Zeitraum
- Entwicklung pro Monat
- Kategorienverteilung
- groesste Einzelbuchungen
- fehlende Belege
- offene Zuordnungen
- gespeicherte Auswertungen fuer diese Sparte

### 9.3 Gruppen-Dashboard

Auswertungsgruppen koennen frei definiert werden.

Beispiele:

- Vermietung gesamt
- Privat gesamt
- Hof gesamt
- Alles ohne Verein
- Gesamtuebersicht
- Versicherungen gesamt

Jede Gruppe kann im Dashboard ausgewaehlt werden.

### 9.4 Detailansicht

Jede Grafik muss auf Einzelbuchungen zurueckfuehren.

Beispiel:

Klick auf Balken "Versicherungen 2026" oeffnet:

- alle enthaltenen Buchungen
- Summe
- Spartenanteile
- Kategorien
- Belegstatus
- Exportmoeglichkeit

---

## 10. Selbst pflegbare Stammdaten

Der Benutzer soll folgende Dinge selbst pflegen koennen:

- Sparten
- Kategorien
- Unterkategorien
- Detailkategorien
- Tags
- globale Auswertungsgruppen
- Bankkonten
- Personen
- Kontakte
- Regeln
- Exportvorlagen

Kategorien sollen deaktiviert statt geloescht werden, sobald Buchungen daran haengen. So bleiben alte Auswertungen stabil.

---

## 11. Datenmodell

Das Datenmodell soll flexibel genug sein, um spaeter zu wachsen.

### 11.0 Grundregeln des Datenmodells

Vor den einzelnen Tabellen gelten einige verbindliche Grundregeln, die spaeter nur teuer nachruestbar waeren:

- **Geldbetraege immer als Ganzzahl in Cent** (`..._cent INTEGER`). Niemals Float. Aus 12345 wird bei der Anzeige 123,45 EUR.
- **Waehrung** ist im MVP immer EUR und wird nicht gespeichert. Fremdwaehrung kann spaeter bewusst ergaenzt werden.
- **Ein Bankumsatz kann in mehrere Buchungszeilen aufgeteilt werden** (Split). Deshalb Trennung in Originalbewegung (`bankumsatz`), fachlichen Kopf (`buchung`) und Zeilen (`buchungszeile`).
- **Umbuchungen/Transfers** zwischen eigenen Konten sind ein eigener Typ (`typ = umbuchung`) und werden standardmaessig aus Einnahmen-/Ausgaben-Auswertungen herausgerechnet.
- **Status wird nie generisch `status` genannt**, sondern eindeutig: `buchungsstatus`, `belegstatus`, `importstatus`.
- **Kategorien werden deaktiviert statt geloescht**, sobald Buchungen daran haengen.
- Der **Verein ist eine geschuetzte Sparte** (`geschuetzt = 1`) und spaeter als eigene Datei abtrennbar.

### 11.1 Zentrale Tabellen

**sparte**

- id
- name
- kuerzel
- typ: privat, vermietung, hof, verein, sonstiges
- geschuetzt (0/1, fuer Verein = 1)
- aktiv
- farbe
- sortierung

**auswertungsgruppe** (buendelt *Sparten*, z. B. "Vermietung gesamt")

- id
- name
- beschreibung
- farbe
- aktiv

**auswertungsgruppe_sparte**

- auswertungsgruppe_id
- sparte_id

**globale_kategoriegruppe** (buendelt *Kategorien* spartenuebergreifend, z. B. "Versicherungen")

- id
- name
- beschreibung
- farbe
- aktiv

**kategorie**

- id
- sparte_id
- parent_id (Selbstbezug: Haupt-/Unter-/Detailkategorie)
- name
- richtung: einnahme, ausgabe, beides
- aktiv
- sortierung

**kategorie_globalgruppe** (n:m - eine Kategorie kann in mehreren globalen Gruppen sein)

- kategorie_id
- globalgruppe_id

**kontakt** (Lieferanten, Mieter, Mitglieder, Gegenparteien)

- id
- name
- typ: lieferant, mieter, mitglied, sonstiges
- iban optional
- notiz
- aktiv

**person** (fuer den Filter "Person", z. B. wer die Ausgabe getaetigt hat)

- id
- name
- aktiv

**bankkonto**

- id
- sparte_id optional (leer = gemischt genutzt)
- inhaber
- name
- iban optional
- bank
- aktiv

**import_batch** (ein CSV-Importlauf, fuer Dublettenpruefung und Nachvollziehbarkeit)

- id
- bankkonto_id
- dateiname
- importiert_am
- anzahl_zeilen
- anzahl_neu
- anzahl_dubletten
- quelle

**bankumsatz** (Originalbewegung aus der Bank, wird nie fachlich veraendert)

- id
- bankkonto_id
- import_batch_id
- datum
- valuta
- betrag_cent
- saldo_nachher_cent optional (fuer Kontostand-Abgleich)
- text
- gegenpartei
- iban_gegenpartei
- import_hash (fuer Dublettenerkennung, eindeutig je Konto)
- importstatus: offen, verbucht, ignoriert

**buchung** (fachlicher Kopf; Betrag = Summe der Buchungszeilen)

- id
- sparte_id
- datum
- typ: einnahme, ausgabe, umbuchung
- betrag_cent (Summe der Zeilen, zur Kontrolle gespeichert)
- kontakt_id optional
- person_id optional
- bankkonto_id optional
- bankumsatz_id optional
- zahlungsart: bar, bank, karte, sonstiges
- transfer_gruppe_id optional (verknuepft die zwei Seiten einer Umbuchung)
- belegstatus: kein_beleg_noetig, beleg_fehlt, beleg_vorhanden, eigenbeleg, beleg_unklar
- buchungsstatus: offen, zugeordnet, bestaetigt
- text
- notiz
- erstellt_am
- geaendert_am

**buchungszeile** (eine Kategorie-/Split-Zeile einer Buchung)

- id
- buchung_id
- kategorie_id
- betrag_cent
- notiz
- Steuer-Felder (leer im MVP, spaeter fuer Export nutzbar): brutto_cent, netto_cent, ust_cent, ust_satz, steuer_relevant (0/1), steuer_notiz

Kontrolle: `SUM(buchungszeile.betrag_cent) = buchung.betrag_cent`, und bei verknuepftem Bankumsatz zusaetzlich `= bankumsatz.betrag_cent`.

**beleg**

- id
- sparte_id
- kontakt_id optional (erkannter Lieferant)
- dateiname
- pfad
- sha256_hash
- belegdatum
- betrag_erkannt_cent optional
- notiz

**buchung_beleg** (n:m - ein Beleg kann mehreren Buchungen dienen, eine Buchung mehrere Belege haben)

- buchung_id
- beleg_id

**tag**

- id
- name
- farbe

**buchung_tag**

- buchung_id
- tag_id

**regel** (ab Phase 2; macht nur Vorschlaege, bucht nicht fest)

- id
- name
- aktiv
- prioritaet
- bedingung_text
- bedingung_betrag_von_cent optional
- bedingung_betrag_bis_cent optional
- bankkonto_id optional
- ziel_sparte_id optional
- ziel_kategorie_id optional
- ziel_typ optional
- ziel_tag_id optional

### 11.2 Warum eine zentrale Datenbank sinnvoll ist

Fuer dieses Projekt ist eine zentrale Datenbank mit strikter Sparten-ID sinnvoller als viele getrennte Datenbanken.

Grund:

- Dashboards ueber mehrere Sparten sind einfacher
- globale Auswertungsgruppen sind einfacher
- Filter funktionieren schneller
- Kategorien koennen trotzdem je Sparte getrennt bleiben
- Exporte koennen sauber nach Sparte gefiltert werden

Die Trennung passiert durch Pflichtfeld `sparte_id`, Oberflaechenfilter und klare Exportlogik.

Fuer den Verein wird zusaetzlich eine Schutzlogik eingebaut. Er bleibt technisch in derselben Datenbank moeglich, wird aber als **geschuetzte Sparte** (`sparte.geschuetzt = 1`) besonders behandelt:

- Verein ist immer separat exportierbar
- Verein wird in Gesamtansichten sichtbar markiert
- keine automatische Vermischung mit Privatgruppen
- eigene Beleg- und Bankkonto-Zuordnung
- so gebaut, dass der Verein spaeter als **eigene SQLite-Datei/Instanz** abgetrennt werden kann

Falls der Verein an Nachfolger oder Pruefer uebergeben werden muss, ist eine eigene Datei langfristig sauberer. Fuer den MVP laeuft er im System mit, wird aber technisch trennbar gehalten.

---

## 12. Technische Architektur

### 12.1 Empfohlener Start

Empfohlen wird eine lokale Web-App mit:

- SQLite als Datenbank
- Python/FastAPI als Backend
- einfache moderne Weboberflaeche
- interaktive Diagramme
- CSV-Import
- Beleg-Dateispeicher
- optional Paperless-ngx fuer OCR und Dokumentenablage

Warum eigene Web-App:

Paperless-ngx ist gut fuer Belege, aber nicht fuer flexible Finanz-Dashboards. Home Assistant ist gut fuer schnelle Eingaben und Erinnerungen, aber nicht als Hauptsystem fuer Auswertungen. Deshalb sollte die eigentliche Logik in einer kleinen lokalen Web-App liegen.

### 12.2 Komponenten

- Web-App: zentrale Bedienoberflaeche
- SQLite-Datenbank: Buchungen, Kategorien, Filter, Regeln
- Belegordner: PDF, JPG, Scans
- Importordner: CSV-Dateien je Bank
- Exportordner: PDF, CSV, XLSX, ZIP
- optional Paperless-ngx: OCR, Volltextsuche, Dublettenpruefung
- optional Home Assistant: Erinnerungen und Schnellzugriff

### 12.3 Lokaler Betrieb

Das System laeuft lokal im Heimnetz.

Zugriff:

- PC
- Tablet
- Smartphone im WLAN
- unterwegs nur ueber WireGuard

Keine sensiblen Daten muessen in eine Cloud.

---

## 13. MVP Version 1.0

Die erste Version soll bewusst schlank sein, aber den Kern richtig treffen. Die urspruengliche v1 war noch zu gross - der erste echte Meilenstein wird enger geschnitten, damit schnell etwas Nutzbares steht.

### 13.1 Erster Meilenstein (Minimalkern)

- Sparten anlegen und anzeigen
- Kategorien und Unterkategorien je Sparte pflegen
- Buchungen manuell erfassen
- Betrag konsequent in Cent (`betrag_cent`)
- Typ je Buchung: Einnahme, Ausgabe, Umbuchung
- Split faehig (Kopf + Buchungszeilen), aber im ersten Schritt meist eine Zeile
- einfache Tabellenansicht mit Basisfiltern
- ein Dashboard (Gesamtuebersicht + Sparte)
- Export als CSV

### 13.2 Danach (nachgelagerte Ausbaustufen)

In dieser Reihenfolge:

1. Bank-CSV-Import mit Dublettenschutz und Kontostand-Abgleich
2. Belege hochladen und mit Buchungen verknuepfen
3. Auswertungsgruppen und globale Kategoriegruppen
4. interaktive Diagramme mit Drill-down (Klick fuehrt zu Einzelbuchungen)
5. Regelvorschlaege
6. PDF-/XLSX-Exportpakete

### 13.3 Erste Dashboards (sobald Diagramme kommen)

- Gesamtuebersicht
- Spartenuebersicht
- Einnahmen/Ausgaben pro Monat
- Kategorienauswertung
- Versicherungen gesamt
- Vermietung gesamt
- Privat gesamt
- Belege fehlen

### 13.4 Noch nicht im MVP

- automatische OCR-Auslesung
- lokaler LLM
- komplexes Matching mit Score
- Rollen/Rechte fuer mehrere Benutzer
- vollautomatischer Bankabruf
- Steuerlogik (die Steuer-Felder werden aber leer vorbereitet)
- Fremdwaehrung
- mobile App

Diese Punkte koennen spaeter ergaenzt werden.

---

## 14. Ausbauphasen

### Phase 1: Grundsystem

- Datenmodell
- lokale Web-App
- Sparten
- Kategorien
- manuelle Buchungen
- erste Diagramme

### Phase 2: Bankimport

- CSV-Import
- Dublettenschutz
- Bankkonto-Zuordnung
- erste Regeln fuer Kategorien

### Phase 3: Belege

- Belege hochladen
- Belege mit Buchungen verknuepfen
- Belegstatus
- fehlende Belege anzeigen

### Phase 4: Dashboards

- interaktive Filter
- gespeicherte Auswertungen
- globale Kategoriegruppen
- Detailansichten per Klick

### Phase 5: Export

- Vermietungsexport
- Vereinsexport
- Bauernhof-Auswertung
- Privatuebersicht
- PDF/CSV/XLSX/ZIP

### Phase 6: Automatisierung

- Regelvorschlaege
- wiederkehrende Buchungen
- Belegvorschlaege
- OCR mit Paperless
- optional lokales LLM fuer Feldvorschlaege

---

## 15. Beispiele fuer konkrete Auswertungen

Das System soll folgende Fragen per Klick beantworten koennen:

- Wie hoch waren alle Einnahmen im Jahr 2026?
- Wie hoch waren alle Ausgaben im Jahr 2026?
- Was ist das Ergebnis nur fuer Vermietung?
- Was ist das Ergebnis nur fuer den Bauernhof?
- Was geben Alois und Frau gemeinsam privat aus?
- Wie viel wurde insgesamt fuer Versicherungen bezahlt?
- Wie viel davon war privat?
- Wie viel davon war Vermietung?
- Wie viel davon war Bauernhof?
- Wie hoch waren Tierarztkosten im Bauernhof?
- Wie entwickeln sich Futtermittelausgaben ueber die Monate?
- Welche Belege fehlen fuer Vermietung?
- Welche Buchungen sind noch ohne Kategorie?
- Welche Ausgaben waren groesser als ein bestimmter Betrag?
- Welche Einnahmen kamen aus Zimmervermietung?
- Wie sieht der Verein im aktuellen Jahr aus?

---

## 16. Exportlogik

Exports sollen nicht nur rohe Tabellen sein, sondern brauchbare Pakete.

### 16.1 Vermietung

Export:

- Jahresuebersicht Einnahmen/Ausgaben
- Kategorienuebersicht
- Einzelbuchungen
- Belegliste
- Belege als Dateien

Ziel:

- Steuerberater kann damit weiterarbeiten
- eigene Kontrolle wird einfacher

### 16.2 Zimmervermietung Hof

Export:

- Einnahmen aus Zimmervermietung
- Plattformgebuehren
- Reinigung
- Instandhaltung
- Ausstattung
- Belege

### 16.3 Bauernhof

Export:

- Einnahmen/Ausgaben nach Kategorien
- Foerderungen
- Tierarzt
- Futtermittel
- Maschinen
- Gebaeude
- Belege

### 16.4 Verein

Export:

- Einnahmen/Ausgaben
- Kassen-/Bankuebersicht
- Veranstaltungsauswertung
- Belegliste
- Belege

Hinweis: Rechtliche und vereinsrechtliche Anforderungen muessen separat geprueft werden.

### 16.5 Privat

Export:

- Jahresuebersicht
- Kategorienauswertung
- optional Einzelbuchungen

Privat dient vor allem der eigenen Information.

---

## 17. Wichtige Bedienlogik

### 17.1 Buchung erfassen

Minimaler Ablauf:

1. Sparte waehlen
2. Datum eingeben
3. Einnahme oder Ausgabe waehlen
4. Betrag eingeben
5. Kategorie waehlen
6. optional Unterkategorie, Tag, Beleg
7. speichern

### 17.2 Bankbuchung bearbeiten

1. Bankimport oeffnen
2. offene Buchungen sehen
3. Vorschlag pruefen
4. Sparte und Kategorie bestaetigen
5. Belegstatus setzen
6. speichern

### 17.3 Kategorie hinzufuegen

1. Sparte waehlen
2. Haupt- oder Unterkategorie anlegen
3. Richtung festlegen
4. optional globale Auswertungsgruppe zuweisen
5. speichern

### 17.4 Auswertung erstellen

1. Zeitraum waehlen
2. Sparten oder Gruppe waehlen
3. Kategorien oder globale Gruppe waehlen
4. Diagramm ansehen
5. bei Bedarf Detailbuchungen oeffnen
6. optional als gespeicherte Ansicht sichern

---

## 18. Sicherheits- und Datenschutzkonzept

Das System enthaelt sensible Finanzdaten. Deshalb:

- lokaler Betrieb
- kein oeffentlicher Zugriff
- Zugriff nur LAN oder WireGuard
- regelmaessige Backups
- verschluesselte Backups
- keine automatische Cloud-Synchronisation der Belegordner
- Export nur bewusst und manuell
- starke Passwoerter
- optional getrenntes Netzwerk/VLAN

Backups:

- taeglich lokal/NAS
- monatlich offline
- Restore-Test mindestens einmal im Jahr

---

## 19. Warum diese Architektur passt

Diese Architektur passt besser als ein klassisches Buchhaltungssystem, weil der eigentliche Wunsch Auswertung und Uebersicht ist.

Sie bietet:

- klare Sparten
- freie Filter
- klickbare Diagramme
- eigene Kategorien
- globale Auswertungen
- Belegzuordnung
- Exportfaehigkeit
- lokale Datenhaltung
- Erweiterbarkeit

Sie vermeidet:

- unnoetige Buchhaltungs-Komplexitaet
- starre Kontenrahmen
- Cloud-Abhaengigkeit
- Vermischung von Verein, Privat und Betrieb
- Excel-Chaos mit vielen Kopien

---

## 20. Naechste konkrete Schritte

1. Sparten final bestaetigen
2. Startkategorien je Sparte grob festlegen
3. alte Excel als Muster importieren oder analysieren
4. Beispieldatei eines Bank-CSV je Konto bereitstellen
5. Datenmodell als SQLite-Schema bauen
6. erste lokale Web-App mit Dashboard bauen
7. manuelle Buchungserfassung umsetzen
8. CSV-Import umsetzen
9. Filter- und Diagrammsystem bauen
10. Belegverknuepfung ergaenzen
11. Vermietungs-Export als erstes Exportpaket bauen
12. danach Verein, Bauernhof und Privat erweitern

Empfohlener Pilot:

Zuerst eine Sparte produktiv testen, am besten Privatvermietung oder Zimmervermietung Hof. Danach Kategorien und Bedienung anpassen und erst dann alle Sparten aktiv nutzen.

---

## 21. Kurzfassung

Das Zielsystem ist ein lokales, klickbares Finanz-Dashboard mit Belegverwaltung.

Jede Buchung gehoert zu einer Sparte. Jede Sparte hat eigene Kategorien. Ueber Filter und Auswertungsgruppen koennen Sparten und Kategorien frei zusammengefuehrt werden.

Damit sind sowohl getrennte Detailansichten als auch Gesamtgrafiken moeglich:

- Bauernhof alleine
- Vermietung gesamt
- Alois privat
- Frau privat
- Privat gesamt
- Verein separat
- Versicherungen ueber alle Sparten
- Gesamtuebersicht

Das System bleibt alltagstauglich, lokal, auswertbar und spaeter exportfaehig.

