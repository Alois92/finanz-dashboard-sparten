# Betrieb & Architektur — Hohenegg Finanzstudio

**Zweck:** Einstiegsdokument, damit jede neue Sitzung / jeder neue Agent sofort
weiß, **wo** das Finanz-Dashboard läuft, **wie** man zugreift, **wie sicher** es
ist und **welche lokalen Modelle** es nutzt — und ohne Rückfragen weiterarbeiten
kann.

**Stand:** 2026-09-08. Zusammengeführt aus Projektnotizen (`outputs/…`,
`docs/SICHERHEIT.md`, `NOTFALL-WIEDERHERSTELLUNG.md`) und dem Assistenten-Gedächtnis.
**Enthält bewusst keine** Passwörter, Wiederherstellungscodes, privaten Schlüssel
oder Hash-Werte.

> Mehrere Detailwerte stammen aus datierten Momentaufnahmen und können auf der
> produktiven Instanz inzwischen abweichen. Alles unter „⚠️ Live verifizieren"
> vor dem Handeln am Produktivsystem prüfen.

---

## 1. Kurzüberblick

| Frage | Antwort |
|---|---|
| Was | FastAPI-Webapp „Hohenegg Finanzstudio" (SQLite, statisches JS-Frontend `static-studio/`) |
| Wo produktiv | Debian-12-LXC **CT 101** (`finanz`) auf **Proxmox** (`pve`, 192.168.1.254) am **Lenovo ThinkCentre M910q** |
| Zugriff produktiv | nur über **Tailscale**: `https://finanz.tailb1b087.ts.net` + App-Passwort |
| Zugriff lokal/Dev | `http://127.0.0.1:8000` (uvicorn lokal starten) |
| Code | `github.com/Alois92/finanz-dashboard-sparten`, Branch **`studio`** |
| Lokales KI-Modell | **Ollama** in CT 101, Vision-Modell **qwen2.5vl:3b** (Rechnungsfoto-Auswertung) |
| Daten produktiv | `/var/lib/finanz/finanz.db` **im Container** (nicht mehr live vom NAS) |

---

## 2. Wo es läuft

### Produktion (der echte Betrieb)

- **Hardware:** Lenovo ThinkCentre M910q (i5-7500T, 4 Kerne, kein AVX512; 16 GB RAM; ~265 GB SSD).
- **Proxmox-Host:** Hostname `pve`, LAN-IP `192.168.1.254`, Proxmox VE 8.3.5. Web-UI: `https://192.168.1.254:8006` (Login `root@pam`).
- **Home Assistant** läuft **getrennt** in **VM 100** (`haos14.2`) auf demselben Host — nicht anfassen.
- **Finanz-App:** unprivilegierter LXC **CT 101**, Hostname `finanz`, Debian 12.
  - Autostart aktiv, `/dev/net/tun` durchgereicht, `nesting=1`.
  - LAN-IP (DHCP an `vmbr0`): zuletzt `192.168.1.129`.
  - Zeitzone `Europe/Vienna`, Locale `de_AT.UTF-8`.
  - Ressourcen: ⚠️ Live verifizieren — Übergabe 19.07. nannte 2 Kerne/1 GB, danach für Ollama auf **3 Kerne / 8 GB RAM** erhöht.
- **Dienste im Container (systemd):**
  - `finanz.service` — uvicorn, lauscht **nur** auf `127.0.0.1:8000`, stark gehärtet (`NoNewPrivileges`, `ProtectSystem=strict`, leere Capabilities, Schreibzugriff nur auf `/var/lib/finanz`, `UMask=0077`). Dienstbenutzer `finanz` ohne Login-Shell.
  - `finanz-serve.service` — stellt nach `tailscaled` den privaten HTTPS-Zugang wieder her (Tailscale Serve).
  - `ollama` — lokaler KI-Server auf `127.0.0.1:11434` (siehe Abschnitt 5).
- **Code/venv im CT:** Basis `/opt/finanz-app` (venv `/opt/finanz-app/.venv`, Python 3.11.2). Aktives Release wird versioniert ausgeliefert, z. B. `/opt/finanz-app-next-<commit>` — der wahre Pfad steht in `systemctl show finanz.service -p WorkingDirectory --value`.

### Lokal / Entwicklung (dieser PC, `NB-LOIS`)

- Repo-Arbeitskopie: `Z:\…\Finanz Dashboard Lois\finanz-dashboard-sparten` (Z: ist das NAS `\\192.168.1.119\Daten`).
- Start: `.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000` → `http://127.0.0.1:8000`.
- DB-Speicherort-Logik: `FINANZ_DB` (ENV) → `instance/db_location.txt` → sonst temporäre Wegwerf-DB. Lokal zeigt die Config auf die NAS-DB.

---

## 3. Zugriff

- **Produktive Adresse (einzig richtige):** `https://finanz.tailb1b087.ts.net`
- **Voraussetzung:** Tailscale auf dem Gerät installiert, eingeschaltet und mit dem Tailnet-Konto `l.bletzacher@hotmail.com` verbunden. Die URL allein genügt nicht.
- **Danach:** App-Passwort eingeben (siehe Sicherheit).
- **Freigegebene Geräte:** `nb-lois`, `s24-ultra-von-lois`, `s24-ultra-von-theresia`.
- **Tailnet-Knoten:** Server `finanz` = `100.106.212.24`; `homeassistant` = `100.72.201.96`. Tailnet-Suffix `tailb1b087.ts.net`. Key-Ablauf war `15.01.2027`.
- **Bewusst gesperrt:** direkter LAN-Zugriff auf `:8000`, öffentliches Internet (kein Router-Portforward, **kein** Tailscale Funnel), SSH im Container (deaktiviert/maskiert).
- **Weitere Person hinzufügen:** separat in Tailscale einladen — **niemals** eigene Microsoft-/Tailnet-Zugangsdaten weitergeben.

---

## 4. Wie sicher es ist

Schutzschichten (von außen nach innen):

1. **Tailscale** — nur freigegebene Geräte erreichen den Server; keine öffentliche Exposition.
2. **HTTPS** via Tailscale Serve (`tailnet only`).
3. **App-Passwort** — scrypt-Hashes in `/var/lib/finanz/auth.json` (`600:finanz:finanz`), niemals Klartext. Sitzung max. **12 h**, Logout widerruft sofort, Fehlversuche werden rate-limitiert (5 Fehlversuche → 15 min Sperre je IP, im Speicher; ein Dienst-Neustart hebt sie auf). **Die Auth-Datei wird nur beim Prozessstart gelesen:** nach jeder Änderung über `scripts/set_auth_password.py` (Startpasswort, Recovery-Code) ist `systemctl restart finanz` nötig, sonst meldet der Login weiter „Anmeldung ist noch nicht eingerichtet“ (QA4-08, 11.09.2026).
4. **Selbstverwaltung** (Stand 2026-08-01, produktiver Commit `0c8ec836`): Ersteinrichtung mit erzwungenem Passwortwechsel, Passwort ändern, Passwort per **Wiederherstellungscode** zurücksetzen (Code wird genau einmal angezeigt).
5. **systemd-Härtung** des Dienstes (siehe Abschnitt 2).

**Geheimnis-Handhabung:** Passwort und Recovery-Code liegen benutzer-/PC-gebunden per **Windows DPAPI** auf `NB-LOIS` (`Passwort-anzeigen.cmd`, `Wiederherstellungscode-anzeigen.cmd`, `DPAPI-Zugang-aktualisieren.ps1`). Sie stehen **nie** in Chat, Git, Shell-Historie oder Logs. **Claude darf Passwörter/Codes nicht selbst erzeugen oder ausgeben** — der Nutzer führt solche Kommandos selbst aus.

**Notfall (weder Passwort noch Code verfügbar):** `outputs/security-finanz-app/NOTFALL-WIEDERHERSTELLUNG.md` — root-only Auth-Backup, Dienst mit Restart-Trap stoppen, unter Benutzer `finanz` temporäres Startpasswort setzen, Ersteinrichtung erzwingen.

---

## 5. Lokale Modelle (Rechnungsfoto-Auswertung)

Bewusste Nutzer-Entscheidung: **keine Cloud-KI** für Rechnungsfotos.

- **Ollama** läuft lokal in CT 101 (systemd, `127.0.0.1:11434`).
- **Aktives Modell:** `qwen2.5vl:3b` (Vision). `qwen2.5vl:7b` (6 GB) war zu schwer für die CPU und ist ggf. noch installiert, aber ungenutzt (Löschkandidat: `ollama rm qwen2.5vl:7b`).
- **Ablauf:** Foto hochladen → asynchroner Hintergrund-Task (`app/auswertung.py`) verkleinert das Bild auf 1280 px und ruft `POST {FINANZ_OLLAMA_URL}/api/chat`; Ergebnis erscheint unter „Ausgewertete Rechnungen" und kann als Buchung übernommen werden. Dauer je Bon mehrere Minuten (CPU-only, gewollt asynchron).
- **Konfiguration (systemd-Drop-Ins unter `/etc/systemd/system/finanz.service.d/`):** `FINANZ_OLLAMA_MODEL=qwen2.5vl:3b`, `FINANZ_OLLAMA_TIMEOUT=2400`; Default-URL `http://127.0.0.1:11434`.
- **Auto-Kategorien:** `app/regeln.py` lernt aus jeder gespeicherten Buchung eine Merkregel (Umbuchungen ausgenommen); der Parser nutzt diese Regeln.

---

## 6. Datenbank & Backups

- **Produktiv:** `/var/lib/finanz/finanz.db` **im Container** (Eigentümer `finanz`, Modus `600`, WAL aktiv). Diese Datei wurde am 16./19.07. checksum-verifiziert vom NAS in den CT kopiert — der Produktivbetrieb läuft **nicht** live von der NAS-Datei.
- **NAS-Datei** `\\192.168.1.119\Daten\Finanzdaten\finanz.db` ist die **Dev-/Rückfallkopie** (Stand ~16.07.), nicht die produktive Quelle. Nicht verwechseln.
- **App-internes Backup** (`app/backup.py`): Tageskopie nach `<DB-Ordner>/backup/`, 30 Stück, SQLite-Backup-API, beim Start + alle 6 h. Zweitziel via `FINANZ_BACKUP_ZIEL2` möglich (UNC-Pfad, im CT als Drop-In).
- **Sicherung vor Schema-Nachzug:** App-Start und `python -m app.migrate apply` erstellen bei anstehenden Migrationen immer eine eigene, frische Datenbankkopie im selben Backup-Ordner: `finanz-JJJJ-MM-TT-HHMM-vor-nachzug-v<zielversion>.db`. Die Zielversion ist die höchste anstehende Migration. Bei gleichem Namen wird `-2`, `-3`, … vor `.db` ergänzt; bestehende Kopien werden nie wiederverwendet oder überschrieben. Die SQLite-Backup-API übernimmt den aktuellen Stand, anschließend wird die Integrität geprüft. Diese Dateien sind von der Tagesrotation ausgenommen; nach erfolgreicher Nachzugssicherung bleiben separat die zehn zuletzt geschriebenen Nachzugssicherungen erhalten. Scheitert die Sicherung einer dauerhaften Datenbank, bricht der Nachzug mit `MigrationsFehler` ab und die App startet schreibgeschützt. Bei Wegwerf-Datenbanken sowie ohne anstehende Migrationen wird keine Nachzugssicherung angelegt. Der eigene Modus sichert nur die Datenbank; Belege, Tagesmanifest und Zweitziel gehören weiterhin zur Tageskopie.
- **Proxmox-Backup:** manueller `vzdump` von CT 101 auf lokale Platte existiert; **automatisches NAS-Backup fehlt noch** (siehe Abschnitt 9).

### Wiederherstellung eines app-internen Sicherungssatzes

1. Dienst anhalten und die zugehörige `finanz-JJJJ-MM-TT.db` als `finanz.db` an den konfigurierten DB-Speicherort zurückkopieren.
2. Den Inhalt von `belege-JJJJ-MM-TT/` nach `belege/` an denselben Speicherort zurückkopieren; die Unterordnerstruktur bleibt dabei unverändert.
3. Das Manifest `manifest-JJJJ-MM-TT.json` prüfen und insbesondere DB- sowie Beleg-Prüfsummen mit den zurückkopierten Dateien vergleichen.
4. Dienst wieder starten und anschließend `GET /api/betrieb/status` als angemeldeter Benutzer prüfen.

Für einen Rückweg nach einem Schema-Nachzug den Dienst anhalten und die passende
`finanz-JJJJ-MM-TT-HHMM-vor-nachzug-v<zielversion>.db` (gegebenenfalls mit
laufendem Zusatz) als Datenbank zurückspielen; dazu die zum gesicherten Schema
passende App-Version einsetzen. Diese Kopie enthält den Datenbankstand direkt
vor dem Nachzug und hat kein eigenes Belegmanifest. Die letzten zehn solcher
Kopien bleiben auch dann erhalten, wenn ältere Tageskopien entfernt werden.

---

## 7. Code, Tests & produktives Update

- **Repo:** `github.com/Alois92/finanz-dashboard-sparten` (privat). **Aktive Linie: Branch `studio`** (`main` ist nur das frühe MVP). Frontend liegt in `static-studio/` (erreichbar unter `/` und `/studio`).
- **Wichtig:** Die echte DB nutzt eigene Sparten-Kürzel **HM, FK, HOF, ZINA, AL, TH** — nicht die Seed-Namen (PV/ZVH/VER/FR).
- **Tests** (Wegwerf-DBs, verändern keine echten Daten):
  ```powershell
  .\.venv\Scripts\python.exe -m unittest discover -s tests -v
  ```
- **Produktives Update auf CT 101** (kein SSH-Server im Container!):
  1. Nutzer öffnet Proxmox-Web-UI `https://192.168.1.254:8006` (`root@pam`) — im Browser/Playwright; **der Nutzer loggt sich ein**, Claude tippt danach.
  2. In der **Node-Shell von `pve`** (nicht der Container-Konsole) via `pct exec 101`:
     ```sh
     pct exec 101 -- bash -lc "systemctl show finanz.service -p WorkingDirectory --value"   # aktives Release
     ```
  3. ⚠️ **Update-Weg vor dem Handeln klären:** Für einfache, nicht-auth-relevante Änderungen wurde früher `cd /opt/finanz-app && git pull && systemctl restart finanz` genutzt. Für sicherheitsrelevante Releases gilt der **bundle-/skriptbasierte Weg** (versionierte `/opt/finanz-app-next-<commit>`, `upgrade-password-self-service.sh` + `verify-…`), der die Auth-Datei bytegenau bewahrt und bei Fehlern zurückrollt. Welcher Weg aktuell gilt: am Release-Pfad erkennen und im Zweifel den skriptbasierten wählen.
  4. Terminal-Ausgabe im xterm.js-iframe auslesen: `window.term.buffer.active`.

---

## 8. Merkregeln für neue Agenten/Sitzungen

- **Niemals fremde/fiktive Daten in die echte DB.** Testdaten nur in Wegwerf-DB via `FINANZ_DB=<temp>` (und danach löschen). Transparent zeigen, woher Zahlen stammen.
- **Kein Passwort/Recovery-Code selbst erzeugen oder ins Transkript schreiben** — der Nutzer führt Auth-Kommandos selbst aus.
- **Produktion nur mit ausdrücklicher Freigabe ändern** (Deployments, Migrationen, Datenlöschung, Force-Push, Zugangsentfernung).
- Zugang zu CT 101 nur über die **Proxmox-Web-UI-Konsole** (der Nutzer meldet sich an); es gibt **keinen** SSH-Server im Container.
- Vor Aussagen über Code/Zustand: **gegen den aktuellen Stand verifizieren** — vieles hier sind datierte Momentaufnahmen.

---

## 9. Offene Punkte & „⚠️ Live verifizieren"

Offene Aufgaben (Stand der Notizen):

1. **NAS-Backup** von CT 101 (+ VM 100) fehlt noch — SMB-Storage in Proxmox scheiterte an `NT_STATUS_ACCESS_DENIED` (NAS = Synology DS220j; SMB-Version/Benutzerrechte prüfen). Danach: geplanter `vzdump` wöchentlich + **echter Restore-Test**.
2. **Zweites Backup-Ziel** `FINANZ_BACKUP_ZIEL2` auf CT 101 als Drop-In aktivieren (setzt eingehängtes, beschreibbares NAS voraus).
3. **Wiederherstellungscode nachtragen** (Audit 2026-09-06 fand `recovery_hash: null` auf der Instanz): `scripts/set_auth_password.py --nur-recovery-code`, dann Dienst neu starten — **Nutzer führt das selbst aus**.
4. **Temporären Admin-Zugang entfernen:** Benutzer `finanzdeploy` + SSH-Key + NOPASSWD-sudo auf `pve` (nur nach ausdrücklicher Freigabe; irreversibel).

Zu verifizierende Widersprüche zwischen den Ständen:

- **Deployter Commit auf CT 101:** dokumentiert `0c8ec836` (2026-08-01). `origin/studio` steht inzwischen weiter (Audit-Fixes 2026-09-06, zuletzt HEAD `ef82c4e`). Ob CT 101 aktuell ist → prüfen.
- **CT-101-Ressourcen:** 2 Kerne/1 GB (07-19) vs. 3 Kerne/8 GB (nach Ollama-Ausbau).
- **Hardware-Blatt** im IT-Ordner nennt den ThinkCentre „Ubuntu + Home Assistant"; tatsächlich läuft dort **Proxmox** mit HA-VM + Finanz-CT. Das Inventar-Blatt ist veraltet.

---

## 10. Verweise

- **Abschnitt 11 (unten) - „Umstellung auf den Neubau“: vollständiger Ablauf mit
  Sicherung, Migrationsprobe, Freigabe, Reihenfolge auf CT 101, Prüfungen danach
  und Rückweg. Noch nicht ausgeführt; Produktion läuft weiter auf `studio`.**
- `scripts/umstellung_pruefung.py` — rein lesendes Prüfskript für Schritt 11.6
  (Betriebsstatus und Zahlenvergleich alt/neu je Sparte und Jahr).
- `docs/neubau/abnahme/A2neu-migrationsprobe.md` — Ergebnis der Migrationsprobe
  auf der echten Produktionskopie samt der Befunde, die nach der Umstellung zu
  erledigen sind.
- `docs/SICHERHEIT.md` — Zugriff/Auth im Detail, Ersteinrichtung des Passworts.
- `outputs/security-finanz-app/NOTFALL-WIEDERHERSTELLUNG.md` — Notfallpfad.
- `outputs/security-finanz-app/abschluss-2026-08-01-passwort-selbstverwaltung.md` — Endzustand Passwort-Selbstverwaltung, Backups, DPAPI.
- `outputs/2026-07-19-gesamtfortschritt-und-uebergabe.md` — ausführliche Erst-Übergabe (Architektur, Tailscale, Migration).
- `Projektkonzept_Finanz_Dashboard_Sparten_2026.md` — fachliches Konzept.
- Assistenten-Gedächtnis: `finanz-dashboard-mobil-deployment`, `foto-auswertung-lokal`, `backup-nas-offen`, `audit-offene-schritte`, `studio-variante`.

---

## 11. Umstellung auf den Neubau

**Stand 2026-09-11: noch nicht ausgeführt.** Produktiv läuft weiterhin Branch
`studio`. Dieser Abschnitt beschreibt den Ablauf, damit er in einer eigenen,
vom Nutzer ausdrücklich freigegebenen Sitzung Schritt für Schritt abgearbeitet
werden kann. Das Schreiben dieses Abschnitts (Paket P62) hat **nichts** an der
Produktion verändert.

Grundregeln aus Abschnitt 8 gelten unverändert: kein SSH im Container (Zugang
nur über die Proxmox-Web-UI-Konsole, **der Nutzer meldet sich selbst an**), kein
Passwort und kein Wiederherstellungscode durch einen Agenten, jeder
Produktionsschritt einzeln und nur nach Freigabe.

### 11.1 Schritt 1 — Sicherung vor dem Wechsel

Noch auf dem alten Stand (`studio`):

1. `GET /api/betrieb/status` als angemeldeter Nutzer aufrufen und prüfen:
   Sicherung von heute vorhanden, `db_ok=true`, `belege_fehlend=0`.
2. Den heutigen Sicherungssatz aus `/var/lib/finanz/backup/` **aus dem Container
   heraus** kopieren — `finanz-JJJJ-MM-TT.db`, `belege-JJJJ-MM-TT/`,
   `manifest-JJJJ-MM-TT.json` — und außerhalb von `/var/lib/finanz` ablegen
   (NAS oder lokal auf `NB-LOIS`), zum Beispiel über die Node-Shell:

   ```sh
   pct exec 101 -- bash -lc "ls -t /var/lib/finanz/backup/finanz-????-??-??.db | head -1"
   pct pull 101 /var/lib/finanz/backup/finanz-<DATUM>.db /tmp/finanz-vor-umstellung.db
   ```

   Diese Kopie ist die Grundlage für den Rückweg (Abschnitt 11.8).
3. **Wichtig:** `app/backup.py` legt pro Tag genau eine Tageskopie an und
   überschreibt eine vorhandene nicht. Die Kopie aus Schritt 2 kann also einige
   Stunden alt sein. Den Stand unmittelbar vor dem Nachzug liefert die
   automatische Sicherung aus Schritt 11.4.3
   (`finanz-JJJJ-MM-TT-HHMM-vor-nachzug-v<zielversion>.db`); sie ist die
   maßgebliche „Sicherung vorher" für den Zahlenvergleich in 11.6.

### 11.2 Schritt 2 — Migrationsprobe wiederholen

`scripts/migrationsprobe.py` (P61) **lokal**, nie auf CT 101, gegen eine frische
Kopie der gerade gezogenen Sicherung:

```powershell
.venv\Scripts\python.exe -m scripts.migrationsprobe <lokale Kopie> --arbeitsordner %TEMP%\probe-prod
```

Weitergehen nur bei `vergleich.gleich == True`, leerem `foreign_key_check`,
`integrity_check == ok` und einer Liste ungeklärter Transfers, die der Nutzer
gesehen und akzeptiert hat. Das Ergebnis der bisher gefahrenen Probe steht in
`docs/neubau/abnahme/A2neu-migrationsprobe.md`; die dort genannten zwei Befunde
(still entfernte Zuordnung `auswertungsgruppe_sparte`, vier Buchungen „Zahlung
unbekannt") sind nach der Umstellung vom Nutzer in der App zu erledigen.

### 11.3 Schritt 3 — Freigabe einholen

Die Zusammenfassung aus Schritt 2 dem Nutzer zeigen und ausdrücklich fragen, ob
umgestellt werden soll. **Kein automatischer Übergang zu Schritt 4.**

### 11.4 Schritt 4 — Reihenfolge auf CT 101

Der Nutzer öffnet `https://192.168.1.254:8006`, meldet sich an und öffnet die
**Node-Shell von `pve`**. Erst danach tippt der Agent.

1. Aktives Release feststellen und **notieren** (Grundlage des Rückwegs):

   ```sh
   pct exec 101 -- bash -lc "systemctl show finanz.service -p WorkingDirectory --value"
   ```

2. Neues, versioniertes Release `/opt/finanz-app-next-<commit>` ausliefern
   (bundle-/skriptbasierter Weg aus Abschnitt 7), Abhängigkeiten im venv
   installieren — **ohne** den laufenden Dienst zu stoppen:

   ```sh
   pct exec 101 -- bash -lc "cd /opt/finanz-app-next-<commit> && .venv/bin/pip install -r requirements.txt"
   ```
3. Dienst auf das neue Release umstellen (`WorkingDirectory` per Drop-in bzw.
   wie im bestehenden Weg vorgesehen) und neu starten. Beim Start läuft der
   Schema-Nachzug automatisch und legt unmittelbar davor die eigene Sicherung
   `finanz-JJJJ-MM-TT-HHMM-vor-nachzug-v<zielversion>.db` an (siehe Abschnitt 6).
   Das ist der Moment, in dem die echten Produktionsdaten zum ersten Mal durch
   die neuen Migrationen laufen.
4. Start-Log lesen und auf Fehler beim Nachzug prüfen, **bevor** weitergemacht wird:

   ```sh
   pct exec 101 -- bash -lc "systemctl status finanz --no-pager | head -12; journalctl -u finanz -n 40 --no-pager"
   ```

5. **Oberfläche auf den Neubau umschalten.** Solange `FINANZ_FRONTEND` nicht
   gesetzt ist, liefert `/` weiterhin `static-studio`; die Anmeldung führt nach
   erfolgreichem Login auf `/` und damit ins alte Studio (Befund 2 der Abnahme
   P30). Erst dieser Schritt macht den Neubau zur Startseite:

   ```sh
   pct exec 101 -- bash -lc "mkdir -p /etc/systemd/system/finanz.service.d && printf '[Service]\nEnvironment=FINANZ_FRONTEND=neu\n' > /etc/systemd/system/finanz.service.d/frontend.conf && systemctl daemon-reload && systemctl restart finanz"
   ```

   Danach liegt `static-neu` unter `/`, das alte Studio bleibt unter `/studio/`
   erreichbar und der Neubau zusätzlich unter `/neu/`. Die Anmelde- und
   Passwortseiten (`/login.html`, `/password-setup.html`, `/password-change.html`,
   `/password-recover.html` samt JS/CSS) kommen weiterhin aus `static-studio` und
   sind unter `/` fest eingehängt — sie funktionieren unabhängig davon, welches
   Frontend den Root-Mount hat.
6. **Modellwechsel der Foto-Auswertung** (Schuld P43c). Erst **nach** Schritt 5
   und nur, wenn die Prüfungen aus 11.6 bestanden sind — der Modellwechsel ist
   fachlich unabhängig von der Umstellung und darf deren Fehlersuche nicht
   stören. Das Gewinnermodell aus `outputs/modelltest/` zuerst laden, dann per
   Drop-in aktivieren:

   ```sh
   pct exec 101 -- bash -lc "ollama pull qwen3.5:4b && ollama list"
   pct exec 101 -- bash -lc "printf '[Service]\nEnvironment=FINANZ_OLLAMA_MODEL=qwen3.5:4b\n' > /etc/systemd/system/finanz.service.d/ollama-modell.conf && systemctl daemon-reload && systemctl restart finanz"
   ```

   `FINANZ_OLLAMA_TIMEOUT=2400` bleibt unverändert; `think: false` steckt bereits
   im Code (`app/auswertung.py`). Danach **ein** Testfoto hochladen und die
   Laufzeit auf der CPU messen. Das alte Modell `qwen2.5vl:3b` bleibt installiert,
   bis das neue über mehrere Bons bestanden hat.

### 11.5 Schritt 5 — Nachzug auf den echten Daten

Läuft automatisch und einmalig in Schritt 11.4.3. Es ist derselbe Code-Pfad, der
in P61/A2neu gegen eine Kopie geprüft wurde — hier zum ersten Mal gegen
`/var/lib/finanz/finanz.db`. Scheitert er, startet die App schreibgeschützt und
meldet das unter `/api/betrieb/status`; dann sofort weiter mit dem Rückweg.

### 11.6 Schritt 6 — Prüfungen danach

In dieser Reihenfolge; jede muss bestehen, bevor die nächste beginnt. Jede
fehlgeschlagene Prüfung beendet die Umstellung und führt zu Abschnitt 11.8.

1. **Betriebsstatus.** `GET /api/betrieb/status` (angemeldet): Schema aktuell,
   `anstehend` leer, `schreibgeschuetzt=false`, Sicherung in Ordnung.
2. **Zahlenvergleich alt/neu** mit `scripts/umstellung_pruefung.py`. Dazu die
   automatische Sicherung von vor dem Nachzug und eine **frische, abgeschlossene**
   Kopie des jetzigen Stands lokal bereitlegen — die laufende Datei
   `/var/lib/finanz/finanz.db` wird nie direkt gelesen (WAL):

   ```sh
   pct exec 101 -- bash -lc "ls -t /var/lib/finanz/backup/finanz-*-vor-nachzug-*.db | head -1"
   pct exec 101 -- runuser -u finanz -- /opt/finanz-app/.venv/bin/python -c "import sqlite3; q=sqlite3.connect('file:/var/lib/finanz/finanz.db?mode=ro',uri=True); z=sqlite3.connect('/var/lib/finanz/backup/umstellung-nachher.db'); q.backup(z); z.close(); q.close()"
   pct pull 101 /var/lib/finanz/backup/finanz-<...>-vor-nachzug-v<N>.db /tmp/vorher.db
   pct pull 101 /var/lib/finanz/backup/umstellung-nachher.db /tmp/nachher.db
   ```

   Beide Dateien lokal auf `NB-LOIS` legen (UNC-Pfade sind gesperrt) und prüfen:

   ```powershell
   $env:FINANZ_SESSION_COOKIE = "<Sitzungswert aus dem Browser>"
   .venv\Scripts\python.exe -m scripts.umstellung_pruefung --status-url https://finanz.tailb1b087.ts.net --sicherung-vorher <lokal>\vorher.db --db-nachher <lokal>\nachher.db
   ```

   Das Skript liest ausschließlich (`mode=ro`), vergleicht die SHA256-Prüfsummen
   beider Dateien vor und nach dem Lauf und meldet jede Abweichung je Sparte,
   Jahr und Feld in Cent. Exitcode 0 = in Ordnung, 1 = Abweichung oder Problem,
   2 = Lauf fehlgeschlagen. Ohne `--status-url` läuft nur der Zahlenvergleich;
   das Ergebnis gilt dann ausdrücklich als unvollständig. Der Sitzungswert steht
   bewusst nur in der Umgebungsvariablen, nicht auf der Kommandozeile. Die Datei
   `umstellung-nachher.db` nach der Prüfung im Container wieder löschen.
3. **Login.** Der Nutzer meldet sich selbst über `https://finanz.tailb1b087.ts.net`
   mit dem bestehenden App-Passwort an und bestätigt, dass er nach dem Login auf
   der neuen Oberfläche landet. Der Agent tippt hier nicht.
4. **Bankimport.** Eine bekannte, bereits verarbeitete CSV noch einmal probeweise
   hochladen (oder eine kleine, harmlose Testdatei) und prüfen, dass die
   Doppelerkennung greift und nichts doppelt gezählt wird.
5. **Belege.** Für eine Stichprobe von Buchungen mit Beleg prüfen, dass Bild oder
   PDF weiterhin abrufbar ist. Die Belegpfade ändern sich durch die Umstellung
   nicht, nur die Anwendung.
6. **Nacharbeit aus A2neu** (kein Abbruchgrund, aber dem Nutzer zu zeigen): die
   von Migration 003 entfernte Gruppenzuordnung und die vier Buchungen „Zahlung
   unbekannt" im Betriebs-/Migrationsprotokoll.

### 11.7 Schritt 7 — Abschluss

Diesen Abschnitt aktualisieren: Datum der Umstellung, neuer aktiver Branch und
Commit, Ergebnis der Prüfungen aus 11.6. Abschnitt 1 und 7 auf den neuen Branch
umstellen und den bisherigen Stand `studio` als abgelöst kennzeichnen — der
Branch und die alten Releases werden **nicht** gelöscht.

### 11.8 Rückweg

Sofort ausführbar; bei einem offensichtlichen Fehlschlag in 11.6 ohne Rückfrage.

1. Dienst stoppen: `pct exec 101 -- bash -lc "systemctl stop finanz"`.
2. Frontend-Drop-in entfernen, damit `/` wieder das Studio liefert:
   `rm -f /etc/systemd/system/finanz.service.d/frontend.conf` (analog
   `ollama-modell.conf`, falls Schritt 11.4.6 schon lief — das alte Modell
   `qwen2.5vl:3b` ist dann wieder aktiv), anschließend `systemctl daemon-reload`.
3. `WorkingDirectory` zurück auf den in 11.4.1 notierten alten Release-Pfad
   stellen und den Dienst starten. Die Anwendung läuft wieder auf dem alten,
   unveränderten Stand (`studio`).
4. Nur falls der automatische Nachzug die Datenbank bereits verändert hat **und**
   genau das der Grund für den Rückweg ist: Dienst anhalten und die Sicherung
   `finanz-JJJJ-MM-TT-HHMM-vor-nachzug-v<zielversion>.db` nach Abschnitt 6
   („Wiederherstellung eines app-internen Sicherungssatzes") zurückspielen,
   Manifest- und Prüfsummen kontrollieren, danach mit dem alten Release starten.
   Reicht diese Kopie nicht, gilt der vollständige Sicherungssatz aus 11.1.
5. `GET /api/betrieb/status` erneut prüfen, danach Login und ein Blick auf eine
   bekannte Buchung gegen den alten Stand.
6. Dem Nutzer sagen, welche Prüfung aus 11.6 den Rückweg ausgelöst hat und was
   genau fehlgeschlagen ist. An der neuen Version wird nichts stillschweigend
   weiter versucht.

Reicht der Rückweg nicht, weil die Anmeldung selbst betroffen ist, gilt
`outputs/security-finanz-app/NOTFALL-WIEDERHERSTELLUNG.md` — die dort nötigen
Passwortschritte führt ausschließlich der Nutzer aus.
