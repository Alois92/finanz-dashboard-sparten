# P62: Umstellung auf den Neubau mit Rückweg

Meilenstein M6. Modell: `gpt-6-astra`, Aufwand medium. Branch `pkt/p62-umstellung` von `neubau` (letztes Paket, nach allen anderen M1–M6-Paketen und nach P61).

## 1. Ziel

Diese Karte beschreibt kein Feature, sondern einen kontrollierten, wiederholbaren Ablauf: den Branch `neubau` einmal produktiv auf CT 101 zu setzen, mit Sicherung davor, festgelegter Reihenfolge, Prüfungen danach und einem konkreten, sofort ausführbaren Rückweg, falls etwas nicht stimmt. Sie liefert außerdem ein kleines, rein lesendes Prüfskript, das die wichtigste Prüfung (Zahlenvergleich alt/neu) nach der Umstellung automatisiert, statt sie von Hand nachzurechnen.

## 2. Kontext

Lies `docs/BETRIEB-UND-ARCHITEKTUR.md` vollständig, insbesondere Abschnitt 2 (wo CT 101 läuft, welche Dienste es gibt), Abschnitt 3 (Zugriffsweg, Tailscale), Abschnitt 6 (Sicherung, Wiederherstellung), Abschnitt 7 (bisheriger Update-Weg: `git pull` vs. versionierter Bundle-Weg), Abschnitt 8 (Merkregeln) und Abschnitt 9 (offene Punkte). Dann `docs/neubau/ARCHITEKTUR.md` Abschnitt 14 (Betrieb: Nachzug beim Start, `GET /api/betrieb/status`), `docs/neubau/pakete/P61-migrationsprobe.md` (das Skript, das hier für die Prüfung nach der Umstellung wiederverwendet wird), `docs/neubau/pakete/P02-sicherung-belege.md` (Sicherungsformat, `pruefe_sicherung`), `outputs/security-finanz-app/NOTFALL-WIEDERHERSTELLUNG.md` (Notfallpfad, falls der Rückweg selbst nicht reicht).

**Betriebsrahmen, der für diese Karte unbedingt gilt:**
- Es gibt keinen SSH-Server im Container. Zugang läuft ausschließlich über die Proxmox-Web-UI-Konsole (`https://192.168.1.254:8006`, Node-Shell von `pve`, darin `pct exec 101 -- ...`). **Der Nutzer meldet sich selbst an**; ein Agent tippt frühestens danach in die bereits offene Konsole.
- Passwörter und Wiederherstellungscodes werden **niemals** von einem Agenten erzeugt, gesetzt, angezeigt oder ins Transkript geschrieben. Wo ein Passwort nötig ist (z. B. Ersteinrichtung nach der Umstellung, falls die Auth-Datei sich ändert), führt der Nutzer das selbst aus.
- Produktionsänderungen laufen nur nach ausdrücklicher Freigabe des Nutzers, Schritt für Schritt, nicht automatisiert im Hintergrund.

## 3. Schnittstellen

Neues Skript `scripts/umstellung_pruefung.py` (nur Standardbibliothek, liest ausschließlich, ändert nichts):

```python
def pruefe_status(basis_url: str, session_cookie: str) -> dict
    # ruft GET /api/betrieb/status auf (angemeldet), gibt schema/sicherung/schreibgeschuetzt zurueck

def pruefe_zahlenvergleich(sicherung_vorher: Path, db_nachher: Path) -> dict
    # nutzt scripts.migrationsprobe.summen_je_sparte_jahr / summen_neu / vergleiche (P61)
    # gegen die vor der Umstellung gezogene Sicherungskopie und die Datenbank nach dem Nachzug

def zusammenfassung(status: dict, zahlenvergleich: dict) -> str
    # Klartext-Bericht fuer den Nutzer: "Umstellung ok" oder die konkrete Abweichung/das konkrete Problem
```

Kommandozeile: `python -m scripts.umstellung_pruefung --status-url <...> --sicherung-vorher <pfad> --db-nachher <pfad>`. Das Skript verändert nie eine Datenbank, es liest nur.

**Ablauf der Umstellung** (dies ist der eigentliche Inhalt der Karte, nicht nur Code):

1. **Sicherung vor dem Wechsel.** Auf CT 101, während der `studio`-Branch noch läuft: `GET /api/betrieb/status` prüfen (Sicherung aktuell, `db_ok`, `belege_fehlend=0`); danach eine zusätzliche, außerplanmäßige Sicherung auslösen (bestehender Mechanismus aus `app/backup.py`, z. B. über einen Neustart des Dienstes oder einen eigenen Aufruf) und den entstandenen Satz (`finanz-JJJJ-MM-TT.db`, `belege-JJJJ-MM-TT/`, `manifest-JJJJ-MM-TT.json`) an einen Ort außerhalb von `/var/lib/finanz` kopieren (z. B. auf das NAS oder lokal auf `NB-LOIS`), bevor irgendetwas verändert wird. Diese Kopie ist die Grundlage für den Zahlenvergleich und für den Rückweg.
2. **Migrationsprobe wiederholen.** `scripts/migrationsprobe.py` (P61) noch einmal gegen eine frische Kopie der gerade gezogenen Sicherung laufen lassen (lokal, nicht auf CT 101) und den Bericht lesen. Erst bei `vergleich.gleich == True` und einer erklärbaren, vom Nutzer akzeptierten Liste ungeklärter Transfers weitergehen.
3. **Freigabe einholen.** Dem Nutzer die Zusammenfassung aus Schritt 2 zeigen und ausdrücklich fragen, ob umgestellt werden soll. Kein automatischer Übergang zu Schritt 4.
4. **Reihenfolge auf CT 101** (Nutzer öffnet die Proxmox-Web-UI-Konsole und meldet sich an; danach tippt der Agent):
   1. `pct exec 101 -- bash -lc "systemctl show finanz.service -p WorkingDirectory --value"` — aktuellen Release-Pfad feststellen und notieren (Grundlage für den Rückweg).
   2. Neues, versioniertes Release ausliefern (bundle-/skriptbasierter Weg aus Abschnitt 7 der Betriebsdoku: `/opt/finanz-app-next-<commit>`), **ohne** den laufenden Dienst zu stoppen.
   3. Dienst `finanz.service` auf das neue Release umstellen (`WorkingDirectory` per Drop-in oder wie im bestehenden Weg vorgesehen) und neu starten. Der Schema-Nachzug läuft dabei automatisch beim Start (siehe `app/migrate.py`, `app/main.py`), inklusive einer eigenen Sicherung unmittelbar davor (siehe P00). Das ist der Moment, in dem die echten Produktionsdaten zum ersten Mal durch die neuen Migrationen laufen.
   4. Log des Starts lesen (`journalctl -u finanz.service` über dieselbe `pct exec`-Konsole) und auf Fehler beim Nachzug prüfen, bevor weitergemacht wird.
5. **Nachzug auf den echten Daten.** Läuft wie in Schritt 4.3 beschrieben automatisch und einmalig beim ersten Start des neuen Release; er ist derselbe Code-Pfad, der in P61 gegen die Kopie geprüft wurde, hier zum ersten Mal gegen die echte Datenbank in `/var/lib/finanz/finanz.db`.
6. **Prüfungen danach**, in dieser Reihenfolge, jede muss bestehen, bevor die nächste beginnt:
   1. `GET /api/betrieb/status` (angemeldet) → Schema aktuell, `schreibgeschuetzt=false`.
   2. `scripts/umstellung_pruefung.py` mit der Sicherung aus Schritt 1 gegen die jetzt laufende Datenbank (dazu eine frische Sicherungskopie der jetzt laufenden Datenbank ziehen, niemals die Live-Datei direkt lesen) → Zahlenvergleich alt/neu je Sparte und Jahr ohne Abweichung.
   3. **Login**: Nutzer meldet sich über `https://finanz.tailb1b087.ts.net` mit dem bestehenden App-Passwort an der neuen Oberfläche an (Agent tippt nicht, der Nutzer prüft das selbst und bestätigt).
   4. **Bankimport**: eine bekannte, bereits verarbeitete CSV noch einmal probeweise hochladen (oder eine kleine, harmlose Testdatei mit wenigen Zeilen) und prüfen, dass Doppelzählung erkannt bzw. verhindert wird.
   5. **Belege**: für eine Stichprobe von Buchungen mit Beleg prüfen, dass das Bild/PDF weiterhin abrufbar ist (Pfade haben sich durch die Umstellung nicht geändert, nur die Anwendung).
   6. Jede fehlgeschlagene Prüfung stoppt hier; weiter zu Abschnitt „Rückweg".
7. **Abschluss.** `docs/BETRIEB-UND-ARCHITEKTUR.md` aktualisieren: neuer aktiver Branch/Commit, Datum der Umstellung, Ergebnis der Prüfungen; alten Stand (`studio`) als abgelöst kennzeichnen, aber nicht löschen.

**Rückweg** (sofort ausführbar, keine Rückfrage bei offensichtlichem Fehlschlag in Schritt 6):
1. Dienst `finanz.service` stoppen.
2. `WorkingDirectory` zurück auf den in Schritt 4.1 notierten alten Release-Pfad stellen, Dienst neu starten — die Anwendung läuft wieder auf dem alten Stand (`studio`), unverändertem Code.
3. Falls die Datenbank durch den automatischen Nachzug bereits verändert wurde und das der Grund für den Rückweg ist: Dienst anhalten, die in Schritt 1 gezogene Sicherung (`finanz-JJJJ-MM-TT.db` plus `belege-JJJJ-MM-TT/`) exakt nach der Anleitung aus `docs/BETRIEB-UND-ARCHITEKTUR.md` Abschnitt 6 („Wiederherstellung eines app-internen Sicherungssatzes") zurückspielen, Manifest-Prüfsummen kontrollieren, danach den Dienst mit dem alten Release wieder starten.
4. `GET /api/betrieb/status` erneut prüfen; danach dieselben Prüfungen aus Schritt 6 (Login, ein harmloser Blick auf eine bekannte Buchung) gegen den alten Stand wiederholen.
5. Nutzer informieren, was fehlgeschlagen ist und welcher Schritt aus Abschnitt 6 den Rückweg ausgelöst hat; nichts an der neuen Version wird stillschweigend weiter versucht.

## 4. Nicht-Ziele

Kein neues Feature, keine Schemaänderung. Keine automatische Ausführung ohne Nutzer-Freigabe zwischen Schritt 3 und 4. Kein Setzen oder Anzeigen von Passwörtern oder Wiederherstellungscodes durch den Agenten. Kein Entfernen des `studio`-Branches oder alter Releases in diesem Paket.

## 5. Schritte

1. `scripts/umstellung_pruefung.py` bauen (reine Lesefunktionen, siehe Abschnitt 3), auf Basis von P61 wiederverwenden, nicht duplizieren.
2. Ablauf und Rückweg (Abschnitt 3, Punkte 1–7 und „Rückweg") als Abschnitt „Umstellung auf den Neubau" an `docs/BETRIEB-UND-ARCHITEKTUR.md` anhängen (Verweis aus Abschnitt 10 ergänzen), damit künftige Sitzungen den Stand kennen, auch bevor die Umstellung stattgefunden hat.
3. Tests für das Prüfskript.
4. Bericht; die eigentliche Ausführung des Ablaufs (Schritt 4 ff. in Abschnitt 3) erfolgt erst nach ausdrücklicher Freigabe des Nutzers in einer eigenen Sitzung, nicht als Teil der Umsetzung dieser Karte.

## 6. Tests

Neue Datei `tests/test_umstellung_pruefung.py`:
- `pruefe_zahlenvergleich` mit zwei synthetischen Wegwerf-Datenbanken (eine als „Sicherung vorher", eine als „Stand nachher" mit identischem fachlichem Inhalt): kein Unterschied.
- Künstlich eine Buchung nur in der „nachher"-Datenbank verändert: Abweichung wird gemeldet, mit Sparte, Jahr, Differenz.
- `zusammenfassung` erzeugt bei `gleich=True` einen eindeutig positiven Text, bei `gleich=False` eine Liste der Abweichungen (kein „ok" bei Problemen).
- `pruefe_status` gegen eine lokale Testinstanz (`TestClient` wie in den bestehenden API-Tests) mit `schreibgeschuetzt=True` → im Ergebnis klar erkennbar, keine falsche Positivmeldung.
- Skript ändert in keinem Testfall eine der beiden übergebenen Datenbanken (Prüfsumme vorher/nachher identisch).

## 7. Fertig heißt

- [ ] Prüfskript-Tests grün, Ausgabe im Bericht.
- [ ] Abschnitt „Umstellung auf den Neubau" in `docs/BETRIEB-UND-ARCHITEKTUR.md` vollständig, mit Ablauf und Rückweg wie in Abschnitt 3 dieser Karte.
- [ ] Ausdrücklich vermerkt, dass die eigentliche Umstellung auf CT 101 **nicht** Teil dieser Karte ist, sondern eine eigene, vom Nutzer freigegebene Ausführung des dokumentierten Ablaufs.
- [ ] Keine Geheimnisse, keine Passwörter oder Wiederherstellungscodes im Code, in Tests oder in der Doku.
- [ ] Bericht geschrieben.

## 8. Modell und Aufwand

`gpt-6-astra`, Aufwand medium: kein architektonisch neues Problem, aber hohe Sorgfaltsanforderung (Produktionsablauf, Rückweg, Sicherheitsrand), deshalb nicht auf `luna` delegiert.

## 9. Bericht zurück

Geänderte und neue Dateien mit je einem Satz. Vollständige Testausgabe des Prüfskripts. Der vollständige Text des neuen Doku-Abschnitts (oder Verweis darauf). Ausdrücklicher Hinweis, dass keine Produktionsänderung stattgefunden hat. Offene Punkte mit Grund. Keine Commits, kein Push.
