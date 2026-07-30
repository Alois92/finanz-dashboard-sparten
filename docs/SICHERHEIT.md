# Sicherheit und Zugriff

## Richtige Adresse

Das produktive Hohenegg Finanzstudio wird ausschließlich über diese private
Tailscale-Adresse geöffnet:

`https://finanz.tailb1b087.ts.net`

Tailscale muss auf dem jeweiligen Gerät eingeschaltet und verbunden sein.
`start-handy.cmd` öffnet genau diese Adresse. Die lokale Adresse
`http://127.0.0.1:8000` ist nur für Entwicklung und Wartung am Server gedacht.

## Vorgesehene Zugriffsschichten

1. Tailscale beschränkt den Netzwerkzugriff auf die freigegebenen Geräte.
2. HTTPS verschlüsselt die Verbindung.
3. Die Anwendung verlangt zusätzlich ein eigenes Passwort.
4. Eine Anmeldung läuft nach 12 Stunden ab.
5. Abmelden widerruft die aktuelle Sitzung sofort.
6. Wiederholte falsche Anmeldungen werden zeitweise gebremst.

Tailscale Funnel darf für diese Anwendung nicht aktiviert werden.

## Ersteinrichtung des Passworts auf dem Produktivserver

Im Projektverzeichnis ausführen:

```powershell
.\.venv\Scripts\python.exe scripts\set_auth_password.py
```

Das gewünschte Passwort zweimal eingeben. Das Skript speichert ausschließlich
einen mit scrypt abgeleiteten Passwortwert sowie ein zufälliges Sitzungsgeheimnis
in `instance/auth.json`. Diese Datei ist durch `.gitignore` vom Repository
ausgeschlossen und darf nicht per E-Mail, Messenger oder Git weitergegeben
werden.

Danach den Anwendungsdienst neu starten. Beim Öffnen der produktiven Adresse
muss anschließend die Login-Seite erscheinen.

## Freigegebene Geräte

Vorerst dürfen nur diese drei persönlichen Geräte auf die Finanz-App zugreifen:

- PC `nb-lois`
- Handy `s24-ultra-von-lois`
- Handy `s24-ultra-von-theresia`

Die Tailscale-Zugriffsregel muss HTTPS-Zugriff auf den Knoten `finanz` nur von
diesen Geräten erlauben. Vor einer Änderung der zentralen Tailscale-Regeln muss
die vorhandene Konfiguration gesichert und geprüft werden, damit insbesondere
Home Assistant nicht unbeabsichtigt gesperrt wird.

## Kontrolle nach einer Bereitstellung

1. Auf einem freigegebenen Gerät Tailscale einschalten.
2. `https://finanz.tailb1b087.ts.net` öffnen.
3. Prüfen, dass ohne Anmeldung keine Übersicht und keine API-Daten sichtbar sind.
4. Mit dem eingerichteten Passwort anmelden.
5. Vorhandene Buchungen stichprobenartig prüfen.
6. Abmelden und prüfen, dass die Zurück-Taste keinen Zugriff mehr ermöglicht.
7. Tailscale auf dem Gerät ausschalten und prüfen, dass die Seite nicht erreichbar ist.
8. Zugriff von einem nicht freigegebenen Gerät muss abgewiesen werden.

## Wiederherstellung

Falls das Passwort vergessen wurde, auf dem Produktivserver das
Passwortskript erneut ausführen und den Dienst neu starten. Vor Änderungen an
Tailscale immer zuerst die bestehende Zugriffsregel exportieren bzw. kopieren.
Die Finanzdatenbank wird von der Passwort-Einrichtung nicht verändert.
