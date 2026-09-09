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
3. **App-Passwort** — scrypt-Hashes in `/var/lib/finanz/auth.json` (`600:finanz:finanz`), niemals Klartext. Sitzung max. **12 h**, Logout widerruft sofort, Fehlversuche werden rate-limitiert.
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
- **Proxmox-Backup:** manueller `vzdump` von CT 101 auf lokale Platte existiert; **automatisches NAS-Backup fehlt noch** (siehe Abschnitt 9).

### Wiederherstellung eines app-internen Sicherungssatzes

1. Dienst anhalten und die zugehörige `finanz-JJJJ-MM-TT.db` als `finanz.db` an den konfigurierten DB-Speicherort zurückkopieren.
2. Den Inhalt von `belege-JJJJ-MM-TT/` nach `belege/` an denselben Speicherort zurückkopieren; die Unterordnerstruktur bleibt dabei unverändert.
3. Das Manifest `manifest-JJJJ-MM-TT.json` prüfen und insbesondere DB- sowie Beleg-Prüfsummen mit den zurückkopierten Dateien vergleichen.
4. Dienst wieder starten und anschließend `GET /api/betrieb/status` als angemeldeter Benutzer prüfen.

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

- `docs/SICHERHEIT.md` — Zugriff/Auth im Detail, Ersteinrichtung des Passworts.
- `outputs/security-finanz-app/NOTFALL-WIEDERHERSTELLUNG.md` — Notfallpfad.
- `outputs/security-finanz-app/abschluss-2026-08-01-passwort-selbstverwaltung.md` — Endzustand Passwort-Selbstverwaltung, Backups, DPAPI.
- `outputs/2026-07-19-gesamtfortschritt-und-uebergabe.md` — ausführliche Erst-Übergabe (Architektur, Tailscale, Migration).
- `Projektkonzept_Finanz_Dashboard_Sparten_2026.md` — fachliches Konzept.
- Assistenten-Gedächtnis: `finanz-dashboard-mobil-deployment`, `foto-auswertung-lokal`, `backup-nas-offen`, `audit-offene-schritte`, `studio-variante`.
