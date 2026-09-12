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

Auf dem Produktivserver aus dem aktiven Release-Verzeichnis ausführen:

```sh
cd /opt/finanz-app-next-<COMMIT>
sudo -u finanz env FINANZ_AUTH_FILE=/var/lib/finanz/auth.json \
  /opt/finanz-app/.venv/bin/python scripts/set_auth_password.py
```

Nur für die lokale Windows-Entwicklung im Projektverzeichnis ausführen:

```powershell
.\.venv\Scripts\python.exe scripts\set_auth_password.py
```

Für die lokale Entwicklung speichert das Skript ausschließlich
mit scrypt abgeleitete Hashes von Passwort und Wiederherstellungscode sowie
ein zufälliges Sitzungsgeheimnis in `instance/auth.json`. Diese Datei ist
durch `.gitignore` vom Repository ausgeschlossen und darf nicht per E-Mail,
Messenger oder Git weitergegeben werden.

Produktiv ein Startpasswort mit **6 bis 128 Zeichen** zweimal verdeckt eingeben.
Das Skript setzt `must_change_password`, erzeugt zusätzlich einen zufälligen
Wiederherstellungscode und speichert in `/var/lib/finanz/auth.json` nur
scrypt-Hashes von Passwort und Code sowie ein zufälliges Sitzungsgeheimnis,
niemals Passwort oder Code im Klartext. Die Datei gehört dem Dienstbenutzer
`finanz`, muss Dateimodus `0600` haben und darf nicht per E-Mail, Messenger
oder Git weitergegeben werden. Beim ersten Login muss ein eigenes Passwort
gesetzt werden.

Danach den Anwendungsdienst neu starten. Beim Öffnen der produktiven Adresse
muss anschließend die Login-Seite erscheinen.
Nach dem Setzen des Passworts zeigt das Skript den **Wiederherstellungscode**
genau einmal auf der Konsole an (ebenso zeigt die Anwendung ihn nach der
Web-Ersteinrichtung genau einmal an). Den Code sofort kopieren oder drucken
und sicher offline verwahren — getrennt von der Auth-Datei und getrennt vom
Passwort selbst, z. B. in einem Passwort-Manager oder ausgedruckt in einem
Safe. Er lässt sich später nicht aus der Auth-Datei zurücklesen.


## Freigegebene Geräte

Vorerst dürfen nur diese drei persönlichen Geräte auf die Finanz-App zugreifen:

- PC `nb-lois`
- Handy `s24-ultra-von-lois`
- Handy `s24-ultra-von-theresia`

Die Tailscale-Zugriffsregel muss HTTPS-Zugriff auf den Knoten `finanz` nur von
diesen Geräten erlauben. Zusätzlich prüft die Anwendung selbst die
Geräteadresse - **nicht** durch eigene Auswertung von Tailscale-/Proxy-Headern,
sondern über `request.client`, das uvicorn aus dem `X-Forwarded-For`-Header
befüllt, wenn es mit `--proxy-headers --forwarded-allow-ips=127.0.0.1`
gestartet wird (uvicorn ≥ 0.34 setzt `proxy_headers=True` standardmäßig; das
explizite Flag in `ExecStart` bleibt trotzdem Pflicht, siehe
`docs/BETRIEB-UND-ARCHITEKTUR.md` Abschnitt 11). Läuft der Dienst ohne
Proxy-Header-Auswertung oder mit `FORWARDED_ALLOW_IPS=*`, ist der Gerätefilter
wirkungslos bzw. per Header spoofbar. Standardmäßig sind die IPv4- und
IPv6-Adressen genau dieser drei Geräte sowie die lokale Serveradresse
freigegeben. Ein anderes Tailnet-Gerät erhält bereits vor der Passwortabfrage
HTTP 403 - vorausgesetzt, die Middleware-Reihenfolge stimmt: Gerätefilter und
Anmeldung laufen vor jeder anderen Anwendungslogik (auch vor dem
Schreibschutz nach einem fehlgeschlagenen Datenbank-Nachzug, siehe
Sicherheitsaudit run-1 Befund F6 in `docs/neubau/SCHULDEN.md`).

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

Diese Funktion setzt voraus, dass in `auth.json` überhaupt ein
Wiederherstellungscode hinterlegt ist. `scripts/set_auth_password.py` erzeugt
seit der Einführung des `--nur-recovery-code`-Flags bei jedem normalen
Passwort-Setzen automatisch einen neuen Code. Fehlt er dennoch (z. B. weil die
Datei mit einer älteren Skriptversion angelegt wurde), auf dem Produktivserver
ausführen:

```sh
cd /opt/finanz-app-next-<COMMIT>
sudo -u finanz env FINANZ_AUTH_FILE=/var/lib/finanz/auth.json \
  /opt/finanz-app/.venv/bin/python scripts/set_auth_password.py --nur-recovery-code
```

Auf einem Windows-Rechner (Betrieb direkt aus dem Projektordner, `auth.json`
liegt dann unter `instance\auth.json`) lautet derselbe Aufruf in PowerShell:

```powershell
.\.venv\Scripts\python.exe scripts\set_auth_password.py --nur-recovery-code
```

Das Passwort und das Sitzungsgeheimnis bleiben dabei unverändert, nur der
Wiederherstellungscode wird neu erzeugt und einmalig auf der Konsole angezeigt.
Diesen Code sofort sicher notieren — er lässt sich danach nicht mehr aus
`auth.json` zurücklesen. Ein eventuell zuvor vorhandener alter Code wird durch
den neuen ungültig.

Alternativ kann ein Administrator die Ersteinrichtung neu starten:
Falls das Passwort vergessen wurde, auf dem Produktivserver das
Passwortskript ohne `--nur-recovery-code` erneut ausführen (setzt ein neues
Passwort **und** einen neuen Wiederherstellungscode) und den Dienst neu
starten. Vor Änderungen an Tailscale immer zuerst die bestehende
Zugriffsregel exportieren bzw. kopieren. Die Finanzdatenbank wird von der
Passwort-Einrichtung nicht verändert.

Sind weder das Passwort noch der Wiederherstellungscode bekannt, gibt es
keinen Weg über die Anwendung selbst zurück in die Anmeldung: Nur der direkte
Serverzugriff (SSH bzw. lokaler Zugriff auf den Produktivserver) erlaubt es,
`scripts/set_auth_password.py` erneut auszuführen und damit ein neues
Passwort und einen neuen Code zu setzen.
