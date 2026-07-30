# Design: Passwort-Selbstverwaltung und Wiederherstellung

**Datum:** 30.07.2026
**Status:** vom Benutzer inhaltlich freigegeben
**Produktive Anwendung:** Hohenegg Finanzstudio

## Ziel

Der Benutzer kann beim ersten Login selbst ein Passwort festlegen, es später
innerhalb der Anwendung ändern und es mit einem einmaligen
Wiederherstellungscode zurücksetzen. Die Bedienung benötigt im Normalfall keine
Proxmox-Konsole und keine Unterstützung durch Codex.

## Passwortanforderungen

- mindestens 6 und höchstens 128 Zeichen
- Groß- und Kleinbuchstaben sind erlaubt und werden unterschieden
- Zahlen und Sonderzeichen sind erlaubt
- jede beliebige Mischung ist zulässig
- es besteht keine Pflicht, mehrere Zeichenarten zu kombinieren
- Beispiele gültiger Eingaben: `123456`, `Hohenegg`, `Hohenegg7!`
- Steuerzeichen sowie ausschließlich aus Leerzeichen bestehende Eingaben sind
  unzulässig

Das Frontend nennt die Eingabe „Passwort“, nicht „PIN“.

## Ersteinrichtung

1. Der Benutzer meldet sich einmal mit dem vorhandenen Startpasswort an.
2. Die Auth-Konfiguration kennzeichnet diese Anmeldung mit
   `must_change_password`.
3. Solange diese Kennzeichnung aktiv ist, darf die Sitzung nur die Seite zur
   Ersteinrichtung und die dafür erforderlichen API-Endpunkte verwenden.
4. Der Benutzer gibt das neue Passwort zweimal ein.
5. Der Server prüft Gleichheit und Passwortanforderungen.
6. Der Server speichert ausschließlich einen scrypt-Hash des neuen Passworts.
7. Der Server erzeugt einen zufälligen Wiederherstellungscode und speichert
   ausschließlich dessen scrypt-Hash.
8. Der Klartext-Wiederherstellungscode wird genau einmal angezeigt. Die Seite
   bietet „Als Datei speichern“ und „Drucken“ an.
9. Alle bisherigen Sitzungen werden widerrufen. Der Benutzer meldet sich mit
   dem neuen Passwort erneut an.

## Passwort ändern

Unter **Mehr → Passwort ändern** gibt der Benutzer ein:

- aktuelles Passwort
- neues Passwort
- Wiederholung des neuen Passworts

Bei Erfolg werden Passwort-Hash und Sitzungsgeheimnis atomar ersetzt. Alle
Sitzungen einschließlich der aktuellen werden widerrufen. Der bestehende
Wiederherstellungscode bleibt gültig.

## Passwort vergessen

Die Login-Seite enthält **„Passwort vergessen?“**. Der Ablauf ist nur von einer
der drei erlaubten Tailscale-Geräteadressen erreichbar.

Der Benutzer gibt ein:

- Wiederherstellungscode
- neues Passwort
- Wiederholung des neuen Passworts

Bei Erfolg:

1. wird das neue Passwort gehasht und gespeichert,
2. werden alle Sitzungen widerrufen,
3. wird der verwendete Wiederherstellungscode ungültig,
4. wird ein neuer Wiederherstellungscode erzeugt,
5. wird der neue Code genau einmal zum Speichern oder Drucken angezeigt.

Existiert noch kein Wiederherstellungscode oder wurde er verloren, bleibt die
Proxmox-Konsole die letzte Rückfallmöglichkeit.

## Wiederherstellungscode

- mindestens 128 Bit kryptografische Zufälligkeit
- gut lesbares gruppiertes Format ohne leicht verwechselbare Zeichen
- serverseitig niemals im Klartext gespeichert
- nur einmal verwendbar
- derselbe Rate-Limiter wie beim Login, mit fünf Fehlversuchen pro
  Geräteadresse innerhalb von 15 Minuten
- neue Ausgabe nach jeder erfolgreichen Wiederherstellung

## Speicherung und Dienstkonfiguration

Die veränderbare Auth-Konfiguration liegt produktiv unter:

`/var/lib/finanz/auth.json`

Dieser Pfad befindet sich im bereits für den Dienst schreibbaren,
zugriffsgeschützten Datenbereich. Die systemd-Unit setzt
`FINANZ_AUTH_FILE=/var/lib/finanz/auth.json`.

Die Datei enthält ausschließlich:

- Passwort-Hash
- Sitzungsgeheimnis
- Hash des Wiederherstellungscodes
- Kennzeichnung für erzwungenen Passwortwechsel
- Formatversion

Schreibvorgänge erfolgen atomar über eine temporäre Datei mit anschließendem
`os.replace`. Dateirechte bleiben `0600`, Eigentümer ist der Dienstbenutzer
`finanz`. Die SQLite-Finanzdatenbank wird dabei nicht verändert.

Beim Deployment wird die bestehende Auth-Konfiguration aus dem Release
checksum-verifiziert in den neuen Datenpfad migriert und einmalig mit
`must_change_password=true` markiert.

## Komponenten und Endpunkte

### Backend

- zentrale Validierungsfunktion für Passwörter
- Auth-Konfigurationsspeicher mit atomarem Lesen und Schreiben
- serverseitiger Zustand für `must_change_password`
- Erzeugung, Hashing und Rotation des Wiederherstellungscodes
- Widerruf aller aktiven Sitzungen
- Rate-Limit für Login und Wiederherstellung

### API

- `GET /api/auth/state` – liefert nur, ob ein Passwortwechsel erzwungen ist
- `POST /api/auth/initial-password` – setzt beim ersten Login das eigene Passwort
- `POST /api/auth/change-password` – ändert das Passwort nach Prüfung des alten
- `POST /api/auth/recover` – setzt es mit dem Wiederherstellungscode zurück

Antworten enthalten niemals Passwort, Passwort-Hash, Sitzungsgeheimnis oder
gespeicherten Wiederherstellungs-Hash.

### Frontend

- Login-Seite mit Link „Passwort vergessen?“
- Seite „Eigenes Passwort festlegen“
- Seite „Passwort ändern“
- Seite „Passwort wiederherstellen“
- einmalige Ansicht des Wiederherstellungscodes mit Download- und Druckfunktion
- Eintrag „Passwort ändern“ im Menü **Mehr**

## Zugriffskontrolle

- Tailscale Serve und HTTPS bleiben unverändert.
- Nur die drei festgelegten Tailscale-Geräteadressen sind zugelassen.
- Der direkte Backend-Port bleibt ausschließlich an `127.0.0.1` gebunden.
- Eine Sitzung mit erzwungenem Passwortwechsel erhält keinen Zugriff auf
  Finanz-APIs oder die normale Studio-Oberfläche.
- Login-, Änderungs- und Wiederherstellungsantworten verraten nicht, welcher
  Teil einer Eingabe falsch war.

## Fehlerbehandlung

- falsches aktuelles Passwort oder falscher Wiederherstellungscode: HTTP 401
- ungültiges neues Passwort oder nicht übereinstimmende Wiederholung: HTTP 422
- zu viele Versuche: HTTP 429
- nicht freigegebenes Gerät: HTTP 403
- fehlende oder beschädigte Auth-Konfiguration: Dienst verweigert Anmeldung
  geschlossen mit HTTP 503
- Schreibfehler: bisherige gültige Konfiguration bleibt durch atomaren
  Dateiaustausch erhalten

## Tests

Die Umsetzung erfolgt testgetrieben. Abgedeckt werden mindestens:

- Akzeptanz von genau 6 Zeichen
- Zahlen, Groß-/Kleinbuchstaben, Sonderzeichen und gemischte Eingaben
- Ablehnung von weniger als 6, mehr als 128 und Steuerzeichen
- erzwungene Ersteinrichtung nach Login mit Startpasswort
- Sperre der Finanz-API bis zum Abschluss der Ersteinrichtung
- einmalige Ausgabe und Hash-Speicherung des Wiederherstellungscodes
- Passwortänderung nur mit korrektem aktuellem Passwort
- Wiederherstellung mit Code, Rotation des Codes und Ablehnung der Wiederverwendung
- Widerruf bestehender Sitzungen nach Änderung und Wiederherstellung
- Rate-Limit und Drei-Geräte-Begrenzung
- atomare Speicherung und Erhalt der bisherigen Datei bei simuliertem Fehler
- bestehende Unit-, Gruppen-, Drill-down- und Exporttests
- End-to-End-Prüfung im Produktivcontainer und nach vollständigem Neustart

## Rollback und Datensicherheit

Vor der Live-Schaltung werden eine konsistente Datenbanksicherung, eine Kopie
der bisherigen Auth-Datei und eine getrennte Release-Kopie erstellt. Die
systemd-Umschaltung erhält ein automatisches Rollback auf den aktuell
produktiven Commit `9c45fc2`. Buchungen und Belege werden von der Änderung nicht
bearbeitet.
