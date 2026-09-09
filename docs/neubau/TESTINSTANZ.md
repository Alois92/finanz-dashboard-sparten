# Test-Instanz auf Proxmox: CT 102 „finanz-test"

Ziel: Der Nutzer prüft jeden Meilenstein des Neubaus an einer eigenen Instanz mit einer Kopie seiner echten Daten, erreichbar über Tailscale auch am Handy. Die Produktion in CT 101 bleibt unberührt. Der Klon dient gleichzeitig als Probe für den Schema-Nachzug auf Bestandsdaten.

Voraussetzung: Nutzer ist in der Proxmox-Web-UI (`pve`, 192.168.1.254) angemeldet und öffnet die **Node-Shell von `pve`** (nicht die Container-Konsole). Claude gibt die Befehle vor, der Nutzer sieht jede Ausgabe. Es gibt keinen SSH-Server in den Containern.

## 1. Klon anlegen (einmalig)

Ein vollständiger Klon nimmt Code, venv, systemd-Einheiten, Ollama und die Datenbank mit. Für einen konsistenten Klon muss CT 101 kurz stehen (wenige Minuten, am besten abends):

```bash
pct stop 101
pct clone 101 102 --full --hostname finanz-test
pct start 101
pct set 102 --memory 4096 --cores 2      # Test braucht weniger als Produktion; Ollama bleibt optional
pct start 102
```

Alternative ohne Stillstand: `vzdump 101 --mode snapshot --storage local` und danach `pct restore 102 <Archiv> --hostname finanz-test` (Speicherplatz auf `local` vorher prüfen).

## 2. Tailscale neu anmelden (der Klon hat noch den Schlüssel von CT 101)

```bash
pct exec 102 -- bash -lc "tailscale logout; tailscale up --hostname finanz-test"
```

Die Ausgabe zeigt einen Anmelde-Link; der Nutzer öffnet ihn im Browser und bestätigt. Danach:

```bash
pct exec 102 -- bash -lc "tailscale status | head -3"
pct exec 102 -- bash -lc "systemctl restart finanz-serve.service && tailscale serve status"
```

Die Test-Instanz ist dann unter `https://finanz-test.<tailnet>.ts.net` erreichbar, nur im Tailnet.

## 3. Code auf den Neubau-Stand bringen

Aktives Release-Verzeichnis feststellen, dann Branch `neubau` auschecken:

```bash
pct exec 102 -- bash -lc "systemctl show finanz.service -p WorkingDirectory --value"
pct exec 102 -- bash -lc "cd \$(systemctl show finanz.service -p WorkingDirectory --value) && git fetch origin && git checkout neubau && git pull --ff-only && .venv/bin/pip install -q -r requirements.txt"
pct exec 102 -- bash -lc "systemctl restart finanz && sleep 3 && systemctl status finanz --no-pager | head -12 && journalctl -u finanz -n 30 --no-pager"
```

Beim Start läuft der Schema-Nachzug (P00) mit Sicherung; das Journal zeigt „DB-Sicherung vor Schema-Nachzug" und die angewendeten Versionen. Scheitert er, startet die App schreibgeschützt und meldet es im Journal und unter `/api/schema` (nach Login).

## 4. Als Test-Instanz kennzeichnen

Drop-In, damit die Oberfläche einen „TEST"-Hinweis zeigt und keine Sicherung aufs Zweitziel schreibt:

```bash
pct exec 102 -- bash -lc "mkdir -p /etc/systemd/system/finanz.service.d && printf '[Service]\nEnvironment=FINANZ_INSTANZ=test\nEnvironment=FINANZ_BACKUP_ZIEL2=\n' > /etc/systemd/system/finanz.service.d/test.conf && systemctl daemon-reload && systemctl restart finanz"
```

Die Umgebungsvariable `FINANZ_INSTANZ=test` wird vom neuen Frontend (M3) als Banner angezeigt; bis dahin ist sie wirkungslos, aber schon gesetzt.

## 5. Daten neu aus der Produktion holen (vor jedem Meilenstein-Test)

Auf der Node-Shell, ohne die Produktion zu stoppen (SQLite-Backup-Datei der App verwenden, nicht die Live-Datei):

```bash
pct exec 101 -- bash -lc "ls -t /var/lib/finanz/backup/finanz-*.db | head -1"
pct pull 101 /var/lib/finanz/backup/finanz-<DATUM>.db /tmp/finanz-prod-kopie.db
pct exec 102 -- bash -lc "systemctl stop finanz"
pct push 102 /tmp/finanz-prod-kopie.db /var/lib/finanz/finanz.db --user finanz --group finanz --perms 600
pct exec 102 -- bash -lc "systemctl start finanz && sleep 3 && journalctl -u finanz -n 20 --no-pager"
rm /tmp/finanz-prod-kopie.db
```

Der Neustart zieht die frische Kopie auf den Neubau-Stand nach. Damit ist jeder Meilenstein-Test zugleich eine Migrationsprobe mit echten Daten. Die Auth-Datei `/var/lib/finanz/auth.json` bleibt die des Klons (gleiches Passwort wie Produktion zum Klonzeitpunkt).

## 6. Prüfen

```bash
pct exec 102 -- bash -lc "curl -s http://127.0.0.1:8000/health"
pct exec 102 -- bash -lc "cd \$(systemctl show finanz.service -p WorkingDirectory --value) && FINANZ_DB=/var/lib/finanz/finanz.db .venv/bin/python -m app.migrate status"
```

Im Browser: Login, Übersicht, Bankimport mit der echten George-CSV (P01), später die neuen Seiten.

## 7. Zurücksetzen oder entfernen

Neu klonen: `pct stop 102 && pct destroy 102`, dann Abschnitt 1. Die Produktion wird durch nichts hier verändert.

## Offen

- Ollama läuft im Klon mit; wenn Speicher knapp ist, `systemctl disable --now ollama` in CT 102 (Fotoauswertung dann nur in Produktion testen).
- Tailscale-Name `finanz-test` muss im Tailnet frei sein.
