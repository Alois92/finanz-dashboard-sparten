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

Der Dienst muss produktiv auf die geschützte Auth-Datei zeigen:

```ini
FINANZ_AUTH_FILE=/var/lib/finanz/auth.json
```

Danach im Projektverzeichnis ausführen:

```powershell
.\.venv\Scripts\python.exe scripts\set_auth_password.py
```

Für die lokale Entwicklung speichert das Skript ausschließlich
einen mit scrypt abgeleiteten Passwortwert sowie ein zufälliges Sitzungsgeheimnis
in `instance/auth.json`. Diese Datei ist durch `.gitignore` vom Repository
ausgeschlossen und darf nicht per E-Mail, Messenger oder Git weitergegeben
werden.

Produktiv ein Startpasswort mit **6 bis 128 Zeichen** zweimal verdeckt eingeben.
Das Skript setzt `must_change_password` und speichert in
`/var/lib/finanz/auth.json` nur scrypt-Hashes und ein zufälliges
Sitzungsgeheimnis, niemals das Passwort im Klartext. Die Datei gehört dem
Dienstbenutzer `finanz`, muss Dateimodus `0600` haben und darf nicht per E-Mail,
Messenger oder Git weitergegeben werden. Beim ersten Login muss ein eigenes
Passwort gesetzt werden.

Danach den Anwendungsdienst neu starten. Beim Öffnen der produktiven Adresse
muss anschließend die Login-Seite erscheinen.
Nach der Passwortwahl zeigt die Anwendung den **Wiederherstellungscode** genau
einmal an. Den Code sofort kopieren oder drucken und sicher offline verwahren;
er lässt sich später nicht aus der Auth-Datei zurücklesen.


## Freigegebene Geräte

Vorerst dürfen nur diese drei persönlichen Geräte auf die Finanz-App zugreifen:

- PC `nb-lois`
- Handy `s24-ultra-von-lois`
- Handy `s24-ultra-von-theresia`

Die Tailscale-Zugriffsregel muss HTTPS-Zugriff auf den Knoten `finanz` nur von
diesen Geräten erlauben. Zusätzlich prüft die Anwendung die von Tailscale Serve
übergebene Geräteadresse selbst. Standardmäßig sind die IPv4- und IPv6-Adressen
genau dieser drei Geräte sowie die lokale Serveradresse freigegeben. Ein anderes
Tailnet-Gerät erhält bereits vor der Passwortabfrage HTTP 403.

Falls ein Gerät in Tailscale neu angelegt wird und dadurch eine neue Adresse
erhält, muss `FINANZ_ALLOWED_CLIENT_IPS` am Dienst aktualisiert werden. Vor einer
Änderung der zentralen Tailscale-Regeln muss die vorhandene Konfiguration
gesichert und geprüft werden, damit insbesondere Home Assistant nicht
unbeabsichtigt gesperrt wird.

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

Auf der Login-Seite **Passwort vergessen** wählen, den Wiederherstellungscode
und das neue Passwort eingeben. Nach erfolgreicher Wiederherstellung wird der
alte Code ungültig und ein neuer Wiederherstellungscode einmalig angezeigt.

Alternativ kann ein Administrator die Ersteinrichtung neu starten:
Falls das Passwort vergessen wurde, auf dem Produktivserver das
Passwortskript erneut ausführen und den Dienst neu starten. Vor Änderungen an
Tailscale immer zuerst die bestehende Zugriffsregel exportieren bzw. kopieren.
Die Finanzdatenbank wird von der Passwort-Einrichtung nicht verändert.
