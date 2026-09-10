# P12 – Auslagen und Ausgleich, Runde 1

Arbeitsverzeichnis: `C:\Users\lblet\dev\wt-p12`, Branch `pkt/p12-auslagen-ausgleich`.
Grundlage: Paket P12 vollständig, Architektur Abschnitte 4 und 5, P10-Bereichshelfer und P11-Konten-/Bewegungslogik.
Keine Commits und kein Push; keine Änderungen in anderen Worktrees.

## Umsetzung

Privat bezahlte Ausgaben bleiben als Kosten bei der Ziel-Sparte; ihre Barbewegung liegt auf der Kassa der Zahlersparte.
Ausgleiche verteilen den Betrag FIFO, erzeugen einen Transfer und zwei Bewegungen und verändern keine Einnahmen oder Ausgaben.
Rücknahme erhält die Zuordnungshistorie und storniert beide Transferbewegungen.
Schreibtransaktionen mit `BEGIN IMMEDIATE` schützen offene Beträge, Versionsprüfung und Wiederholungsschlüssel auch bei konkurrierenden Requests.
Der allgemeine Migrationsrunner `app/migrate.py` bleibt unverändert.

## Geänderte und neue Dateien

| Datei | Änderung |
| --- | --- |
| `db/migrations/005_auslagen_ausgleich.sql` | Ergänzt Version und Request-ID sowie die vorgegebenen Auslagen-/Ausgleichstabellen und technische Wiederholungsdaten idempotent über den allgemeinen Runner. |
| `db/schema.sql` | Enthält denselben P12-Strukturstand für neue Datenbanken. |
| `app/auslagen.py` | Bündelt Bereichsprüfungen, offene Beträge, Auslagensynchronisierung und Zuordnungssperren. |
| `app/wiederholung.py` | Speichert SHA-256 des kanonischen Request-JSON und die ursprüngliche Antwort dauerhaft und prüft deren Bereich. |
| `app/routers/auslagen.py` | Implementiert Auslagenliste, Ausgleich mit FIFO und Kassa-Warnung, Aufhebung und Ausgleichsliste. |
| `app/routers/buchungen.py` | Ergänzt private Zahler, wiederholbare Anlage, verpflichtende PUT-Version, stabile Zeilen-IDs und den Schutz zugeordneter Auslagen. |
| `app/bewegungen.py` | Bucht Barzahlungen mit Auslage auf die Zahlersparte. |
| `app/routers/konten.py` | Verhindert das isolierte Stornieren eines Ausgleichstransfers am allgemeinen Transfer-Endpunkt. |
| `app/schemas.py` | Ergänzt P12-Eingabefelder, optionale Zeilen-IDs und die Prüfung gültiger ISO-Buchungsdaten. |
| `app/main.py` | Registriert ausschließlich den neuen fachlichen Router unter `/api`. |
| `tests/test_auslagen.py` | Prüft den kompletten Ablauf, Bank-/Bereichsgrenzen, FIFO, Wiederholungen, Konflikte, Rücknahme, Rollback, parallele Requests und Schema-Nachzug. |
| `tests/fixtures/schema_p11.sql` | Bewahrt das echte P11-Schema aus `HEAD:db/schema.sql` als unveränderte historische Testgrundlage. |
| `tests/test_konten_bewegungen.py` | Passt vorhandene P11-Tests an verpflichtende PUT-Versionen und den zusätzlichen Nachzug 005 an. |
| `tests/test_bereiche_migration.py` | Entfernt beim Aufbau historischer Fixtures auch P12-Objekte und erwartet die zusätzliche Migration 005. |
| `tests/test_migrate.py` | Erwartet Version 5 bei vollständigem Nachzug und Neuanlage. |
| `docs/neubau/berichte/P12-runde1.md` | Dokumentiert Umsetzung, Annahmen, Review, Testausgabe und Nachzugsbelege. |

## Endpunkte und Bereichsprüfung

Alle neuen Endpunkte verwenden `BereichDep`, also die zentrale `bereich_dep` mit Standardbereich 1; die bestehende Auth-Middleware bleibt unverändert.

| Endpunkt | Bereichsprüfung |
| --- | --- |
| `GET /api/auslagen?bereich_id=&stichtag=&sparte_id=&zahler_sparte_id=` | Filtersparten über `pruefe_sparte`; SQL begrenzt Buchungen auf den Bereich; Auslagen prüfen Buchung, Zahlersparte und optionales Zahlerkonto, Kategorien über `pruefe_kategorie`. |
| `POST /api/ausgleiche` | Beide Sparten über `pruefe_sparte`, explizite/aufgelöste Konten über `pruefe_konto`, jede Auslage über ihre Buchung und Zahlersparte; zusätzlich fachliche Zuordnung und Kontoinhaberschaft. |
| `DELETE /api/ausgleiche/{ausgleich_id}` | Beide Sparten, Transferkonten und alle zugeordneten Auslagen werden vor der Aufhebung geprüft. |
| `GET /api/ausgleiche?bereich_id=&sparte_id=&jahr=` | Spartefilter über `pruefe_sparte`, SQL-Bereichsfilter sowie Prüfung beider Sparten, Transfers und zugeordneten Auslagen. |
| Erweitert: `POST /api/buchungen` | Bestehende Buchungsreferenzprüfungen plus private Zahlersparte und Zahlungskonto; gespeicherte Wiederholungen prüfen den dauerhaft gespeicherten Bereich vor Ausgabe der Originalantwort. |
| Erweitert: `PUT /api/buchungen/{buchung_id}` | Bestehende und neue Referenzen über P10-Helfer; fremde Zeilen werden über ihre Buchung geprüft; Versionsvergleich und s?mtliche Referenz-/Zuordnungspr?fungen innerhalb derselben Schreibtransaktion. |
| Erweitert: `GET /api/buchungen` und Suche | Bestehende Bereichsfilter bleiben erhalten; Antworten ergänzen Version und Auslagenstatus. |

Keine Bereichsdependency wurde an `/api/auth/*`, `/api/health`, `/api/schema` oder `/api/betrieb/status` angebracht.

## Begründete Annahmen

1. Die spezifizierten Fachtabellen enthalten weder Request-Hash noch Originalantwort. Deshalb ergänzt `request_wiederholung` diese technischen Daten, getrennt von unveränderten fachlichen Spalten und Fremdschlüsseln. Der Schlüssel gilt je Aktionsart global; ein anderer Bereich erhält 409 ohne gespeicherte Antwort. Kanonisierung nutzt validierte JSON-Daten einschließlich Defaults, sortierte Objektschlüssel und kompakte Separatoren; Listenreihenfolge bleibt Bestandteil der Nutzdaten.
2. Eine Wiederholung liefert die ursprüngliche Antwort auch nach Bearbeitung, Kategorien-Stilllegung oder Rücknahme. Sie legt nichts neu an und reaktiviert keinen aufgehobenen Ausgleich. PUT verwendet Versionsschutz; `client_request_id` bezeichnet die ursprüngliche Anlage.
3. Die Auslagenliste enthält nur zum Stichtag offene Auslagen mit Buchungsdatum bis einschließlich Stichtag. Split-Kategorien erscheinen als nach Kategorie-ID geordnete, kommaseparierte Namen. Vollständig bezahlte Auslagen bleiben in Buchungslisten mit `ausgeglichen: true` sichtbar.
4. Entfernen oder Wechseln des Zahlers sowie Verschieben der Kosten-Sparte und Löschen der Buchung sind bei vorhandenen Zuordnungen gesperrt, auch nach Aufhebung; sonst würde die geforderte Historie durch `ON DELETE CASCADE` verloren gehen. Eine Betragsänderung wird nur an aktiven Zuordnungen gemessen. Datumsänderungen dürfen aktive Zuordnungen nicht nachträglich überholen; ein unverändertes Datum bleibt bei zulässig rückdatierten Sammelausgleichen bearbeitbar.
5. Bankausgleiche verwenden zwei Bankkonten der jeweils angegebenen Sparte in gleicher Währung; Barausgleiche Kassenkonten. Ein angegebenes Zahlungskonto einer privat bezahlten Buchung muss der Zahlersparte gehören. Ohne bekanntes Bankkonto bleibt die P11-Kennzeichnung der unbekannten Zahlung bestehen.
6. Die Kassa-Warnung verwendet die nicht stornierten Bewegungen bis zum Zahlungsdatum. Ein unbekannter Anfangsstand wird nicht erfunden; Saldoanker bleiben P13 vorbehalten. Der Tagesstandard folgt wie im vorhandenen Backend dem lokalen Serverdatum, in dieser Umgebung Europe/Vienna.
7. Die Architekturvorgabe stabiler Zeilen-IDs wird beim PUT umgesetzt: übermittelte IDs werden aktualisiert, neue Zeilen angelegt und fehlende entfernt. Zusätzliche Steuerinformationen vorhandener Zeilen bleiben erhalten.
8. Für eine echte P11→P12-Probe wird `db/schema.sql` aus dem Git-Ausgangsstand verwendet, nicht das bereits um P12 erweiterte Schema. Die lokale Bestandsdatenbank und Sicherung enthalten ausschließlich synthetische Daten aus Schema/Seed und zusätzlichen Testbuchungen; Namen wurden darin neutralisiert.
9. Der vorgegebene Python-Interpreter erzeugt innerhalb dieser Windows-Sandbox bei `TemporaryDirectory()` Verzeichnisse mit unzugänglicher ACL (`WinError 5`). Ausschließlich im Testprozess ersetzt ein Wrapper den Modus 0700 bei `os.mkdir` durch vererbte Windows-Berechtigungen; `TemporaryDirectory()` und dessen Bereinigung bleiben aktiv. Produktcode, Auth und Validierung werden dadurch nicht verändert; alle Testdaten liegen außerhalb des Arbeitsbaums unter Temp.

## Verifikation und Review

Abschluss: **185 Tests in 342,641 Sekunden, keine Fehler, keine fehlgeschlagenen Tests, ein vorhandener POSIX-Plattform-Skip** (`OK (skipped=1)`, Exitcode 0). Alle 13 P12-Tests bestanden. `git diff --check` ist sauber; alle 16 geänderten/neuen Dateien sind oben erfasst.

Neue Tests wurden zunächst rot ausgeführt und anschließend grün. Ein separates, ausschließlich lesendes Code-Review fand zwei reproduzierte Randfälle (Replay nach Referenzänderung und Textkorrektur bei rückdatiertem Sammelausgleich); beide wurden mit Regressionstests korrigiert. Zusätzlich wird geprüft, dass ein fremder Zahler beim PUT auch bei aktiven Zuordnungen mit 404 abgewiesen wird.

Die gesamte Testsuite verwendet den vorgegebenen Interpreter und den Worktree als Arbeitsverzeichnis. Es werden keine Abhängigkeiten installiert und keine Tests ausgefiltert. Der vorhandene POSIX-Dateirechte-Test wird unter Windows durch seine bestehende Plattformbedingung übersprungen.

Ein früher vollständiger Lauf bestand bereits mit 185 Tests. Bei einem nachfolgenden Lauf beendete sich einmal der Uvicorn-Testprozess im Setup von `test_passwortaenderung_lehnt_fehlerhafte_eingaben_ab` ohne stdout/stderr. Der unveränderte Test bestand einzeln erneut (1 Test, 14,644 Sekunden); anschließend wurde die gesamte Suite ohne überlappende eigene Testläufe wiederholt. Auth-Code und Prüfungen wurden dafür nicht verändert. Ein zusätzlicher fachlicher Teillauf mit wiederverwendeter Wegwerf-DB traf außerdem auf einen alten Test-Kategorienamen; die vollständigen Läufe verwenden jeweils eine neue Datenbank.

### Testaufruf

Für jeden vollständigen Lauf wurde ein neuer, vorher nicht vorhandener Datenbankpfad verwendet. Die folgende Ausgabe enthält auch die erwarteten Fehlerlogs der negativen Backup- und Bildverarbeitungstests; deren Teststatus ist jeweils `ok`.

```powershell
$env:FINANZ_DB = Join-Path $env:TEMP 'p12-abschluss-tests.db'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTHONIOENCODING = 'utf-8'
@'
import os
import unittest

original_mkdir = os.mkdir

def inherited_acl_mkdir(path, mode=0o777, **kwargs):
    return original_mkdir(path, 0o777 if mode == 0o700 else mode, **kwargs)

os.mkdir = inherited_acl_mkdir
result = unittest.TextTestRunner(verbosity=2).run(
    unittest.defaultTestLoader.discover('tests')
)
raise SystemExit(not result.wasSuccessful())
'@ | & C:/Users/lblet/dev/finanz-dashboard-sparten/.venv/Scripts/python.exe -
```

### Vollständige Testausgabe

```text
test_nachzug_zweimal_und_schema_identisch (test_auslagen.AuslagenMigrationTest.test_nachzug_zweimal_und_schema_identisch) ... ok
test_auslage_teilausgleich_ruecknahme_und_kosten (test_auslagen.AuslagenTest.test_auslage_teilausgleich_ruecknahme_und_kosten) ... ok
test_bereichsgrenzen_und_bankausgleich (test_auslagen.AuslagenTest.test_bereichsgrenzen_und_bankausgleich) ... ok
test_fehlgeschlagener_ausgleich_rollt_kassenanlage_zurueck (test_auslagen.AuslagenTest.test_fehlgeschlagener_ausgleich_rollt_kassenanlage_zurueck) ... ok
test_historie_replay_nach_aenderung_und_aufhebung (test_auslagen.AuslagenTest.test_historie_replay_nach_aenderung_und_aufhebung) ... ok
test_idempotenz_buchung_und_ausgleich (test_auslagen.AuslagenTest.test_idempotenz_buchung_und_ausgleich) ... ok
test_kassawarnung_zehn_euro_und_volle_tilgung (test_auslagen.AuslagenTest.test_kassawarnung_zehn_euro_und_volle_tilgung) ... ok
test_parallele_requests_serialisieren_offen_version_und_request_id (test_auslagen.AuslagenTest.test_parallele_requests_serialisieren_offen_version_und_request_id) ... ok
test_replay_nach_kategoriestilllegung_und_unbenutzter_auslage (test_auslagen.AuslagenTest.test_replay_nach_kategoriestilllegung_und_unbenutzter_auslage) ... ok
test_textkorrektur_bei_zulaessigem_rueckdatiertem_ausgleich (test_auslagen.AuslagenTest.test_textkorrektur_bei_zulaessigem_rueckdatiertem_ausgleich) ... ok
test_validierung_fifo_stichtag_und_warnung (test_auslagen.AuslagenTest.test_validierung_fifo_stichtag_und_warnung) ... ok
test_version_und_zuordnungssperre (test_auslagen.AuslagenTest.test_version_und_zuordnungssperre) ... ok
test_zeilen_ids_bleiben_stabil_und_fremde_werden_abgewiesen (test_auslagen.AuslagenTest.test_zeilen_ids_bleiben_stabil_und_fremde_werden_abgewiesen) ... ok
test_api_ist_ohne_anmeldung_gesperrt (test_auth.AuthIntegrationTest.test_api_ist_ohne_anmeldung_gesperrt) ... ok
test_browser_wird_auf_vorhandene_loginseite_umgeleitet (test_auth.AuthIntegrationTest.test_browser_wird_auf_vorhandene_loginseite_umgeleitet) ... ok
test_falsches_passwort_wird_abgewiesen (test_auth.AuthIntegrationTest.test_falsches_passwort_wird_abgewiesen) ... ok
test_freigegebenes_tailscale_geraet_erreicht_den_login (test_auth.AuthIntegrationTest.test_freigegebenes_tailscale_geraet_erreicht_den_login) ... ok
test_login_setzt_sicheres_cookie_und_oeffnet_api (test_auth.AuthIntegrationTest.test_login_setzt_sicheres_cookie_und_oeffnet_api) ... ok
test_logout_loescht_cookie (test_auth.AuthIntegrationTest.test_logout_loescht_cookie) ... ok
test_manipuliertes_cookie_wird_abgewiesen (test_auth.AuthIntegrationTest.test_manipuliertes_cookie_wird_abgewiesen) ... ok
test_nicht_freigegebenes_tailscale_geraet_wird_abgewiesen (test_auth.AuthIntegrationTest.test_nicht_freigegebenes_tailscale_geraet_wird_abgewiesen) ... ok
test_unbekannter_host_header_wird_abgewiesen (test_auth.AuthIntegrationTest.test_unbekannter_host_header_wird_abgewiesen) ... ok
test_abgelaufene_api_session_fuehrt_zur_loginseite (test_auth_expiry_frontend.AuthExpiryFrontendTest.test_abgelaufene_api_session_fuehrt_zur_loginseite) ... ok
test_studio_bietet_logout_ueber_post_an (test_auth_frontend.AuthFrontendTest.test_studio_bietet_logout_ueber_post_an) ... ok
test_ersteinrichtung_gibt_code_einmal_aus (test_auth_lifecycle.AuthLifecycleIntegrationTest.test_ersteinrichtung_gibt_code_einmal_aus) ... ok
test_ersteinrichtung_kann_nicht_wiederholt_werden (test_auth_lifecycle.AuthLifecycleIntegrationTest.test_ersteinrichtung_kann_nicht_wiederholt_werden) ... ok
test_ersteinrichtung_lehnt_json_array_ab (test_auth_lifecycle.AuthLifecycleIntegrationTest.test_ersteinrichtung_lehnt_json_array_ab) ... ok
test_ersteinrichtung_lehnt_malformedes_json_ab (test_auth_lifecycle.AuthLifecycleIntegrationTest.test_ersteinrichtung_lehnt_malformedes_json_ab) ... ok
test_ersteinrichtung_lehnt_ungueltige_eingaben_ab (test_auth_lifecycle.AuthLifecycleIntegrationTest.test_ersteinrichtung_lehnt_ungueltige_eingaben_ab) ... ok
test_ersteinrichtung_lehnt_ungueltiges_utf8_ab (test_auth_lifecycle.AuthLifecycleIntegrationTest.test_ersteinrichtung_lehnt_ungueltiges_utf8_ab) ... ok
test_login_lehnt_ungueltiges_utf8_neutral_ab (test_auth_lifecycle.AuthLifecycleIntegrationTest.test_login_lehnt_ungueltiges_utf8_neutral_ab) ... ok
test_passwortaenderung_lehnt_fehlerhafte_eingaben_ab (test_auth_lifecycle.AuthLifecycleIntegrationTest.test_passwortaenderung_lehnt_fehlerhafte_eingaben_ab) ... ok
test_passwortaenderung_lehnt_json_array_ab (test_auth_lifecycle.AuthLifecycleIntegrationTest.test_passwortaenderung_lehnt_json_array_ab) ... ok
test_passwortaenderung_lehnt_malformedes_json_ab (test_auth_lifecycle.AuthLifecycleIntegrationTest.test_passwortaenderung_lehnt_malformedes_json_ab) ... ok
test_passwortaenderung_lehnt_ungueltiges_utf8_ab (test_auth_lifecycle.AuthLifecycleIntegrationTest.test_passwortaenderung_lehnt_ungueltiges_utf8_ab) ... ok
test_passwortaenderung_widerruft_alte_sitzung (test_auth_lifecycle.AuthLifecycleIntegrationTest.test_passwortaenderung_widerruft_alte_sitzung) ... ok
test_recovery_lehnt_fehlerhafte_eingaben_ab (test_auth_lifecycle.AuthLifecycleIntegrationTest.test_recovery_lehnt_fehlerhafte_eingaben_ab) ... ok
test_recovery_lehnt_json_array_neutral_ab (test_auth_lifecycle.AuthLifecycleIntegrationTest.test_recovery_lehnt_json_array_neutral_ab) ... ok
test_recovery_lehnt_malformedes_json_neutral_ab (test_auth_lifecycle.AuthLifecycleIntegrationTest.test_recovery_lehnt_malformedes_json_neutral_ab) ... ok
test_recovery_lehnt_ungueltiges_utf8_neutral_ab (test_auth_lifecycle.AuthLifecycleIntegrationTest.test_recovery_lehnt_ungueltiges_utf8_neutral_ab) ... ok
test_recovery_rotiert_code_und_lehnt_wiederverwendung_ab (test_auth_lifecycle.AuthLifecycleIntegrationTest.test_recovery_rotiert_code_und_lehnt_wiederverwendung_ab) ... ok
test_recovery_sperrt_nach_fuenf_ungueltigen_payloads (test_auth_lifecycle.AuthLifecycleIntegrationTest.test_recovery_sperrt_nach_fuenf_ungueltigen_payloads) ... ok
test_setup_assets_sind_waehrend_ersteinrichtung_erreichbar (test_auth_lifecycle.AuthLifecycleIntegrationTest.test_setup_assets_sind_waehrend_ersteinrichtung_erreichbar) ... ok
test_startpasswort_erlaubt_nur_ersteinrichtung (test_auth_lifecycle.AuthLifecycleIntegrationTest.test_startpasswort_erlaubt_nur_ersteinrichtung) ... ok
test_wiederherstellungsseite_und_assets_sind_oeffentlich (test_auth_lifecycle.AuthLifecycleIntegrationTest.test_wiederherstellungsseite_und_assets_sind_oeffentlich) ... ok
test_store_schreibt_atomar_und_laesst_keine_temporaere_datei (test_auth_store.AuthConfigStoreTest.test_store_schreibt_atomar_und_laesst_keine_temporaere_datei) ... ok
test_store_setzt_dateimodus_0600 (test_auth_store.AuthConfigStoreTest.test_store_setzt_dateimodus_0600) ... skipped 'POSIX-Dateirechte'
test_wiederherstellungscode_hat_mindestens_128_bit (test_auth_store.AuthConfigStoreTest.test_wiederherstellungscode_hat_mindestens_128_bit) ... ok
test_genau_sechs_zeichen_und_alle_zeichenarten_sind_erlaubt (test_auth_store.PasswordValidationTest.test_genau_sechs_zeichen_und_alle_zeichenarten_sind_erlaubt) ... ok
test_hashing_verwendet_die_flexible_passwortvalidierung (test_auth_store.PasswordValidationTest.test_hashing_verwendet_die_flexible_passwortvalidierung) ... ok
test_ungueltige_passwoerter_werden_abgewiesen (test_auth_store.PasswordValidationTest.test_ungueltige_passwoerter_werden_abgewiesen) ... ok
test_manipulierte_session_wird_abgewiesen (test_auth_unit.AuthUnitTest.test_manipulierte_session_wird_abgewiesen) ... ok
test_passwort_hash_enthaelt_keinen_klartext (test_auth_unit.AuthUnitTest.test_passwort_hash_enthaelt_keinen_klartext) ... ok
test_rate_limit_sperrt_nach_fuenf_fehlern (test_auth_unit.AuthUnitTest.test_rate_limit_sperrt_nach_fuenf_fehlern) ... ok
test_session_gilt_hoechstens_zwoelf_stunden (test_auth_unit.AuthUnitTest.test_session_gilt_hoechstens_zwoelf_stunden) ... ok
test_buchung_speichern_legt_regel_an (test_auto_kategorien.AutoKategorienTest.test_buchung_speichern_legt_regel_an) ... ok
test_ein_einzelnes_gemeinsames_wort_reicht_nicht_fuer_einen_treffer (test_auto_kategorien.AutoKategorienTest.test_ein_einzelnes_gemeinsames_wort_reicht_nicht_fuer_einen_treffer) ... ok
test_kurze_eingabe_trifft_lange_gelernte_regel_ueber_wort_tokens (test_auto_kategorien.AutoKategorienTest.test_kurze_eingabe_trifft_lange_gelernte_regel_ueber_wort_tokens) ... ok
test_namensabgleich_hat_vorrang_vor_regel (test_auto_kategorien.AutoKategorienTest.test_namensabgleich_hat_vorrang_vor_regel) ... ok
test_parse_ordnet_per_regel_zu_ohne_kategorienamen (test_auto_kategorien.AutoKategorienTest.test_parse_ordnet_per_regel_zu_ohne_kategorienamen) ... ok
test_umbuchung_lernt_nicht (test_auto_kategorien.AutoKategorienTest.test_umbuchung_lernt_nicht) ... ok
test_belege_manifest_und_pruefsummen_werden_gesichert (test_backup.BackupTest.test_belege_manifest_und_pruefsummen_werden_gesichert) ... ok
test_belegsicherung_ohne_db_kopie_schreibt_db_null (test_backup.BackupTest.test_belegsicherung_ohne_db_kopie_schreibt_db_null) ... ok
test_beschaedigte_tagesdatei_wird_durch_gueltige_sicherung_ersetzt (test_backup.BackupTest.test_beschaedigte_tagesdatei_wird_durch_gueltige_sicherung_ersetzt) ... ok
test_betriebsstatus_enthaelt_nur_oeffentliche_sicherungsfelder (test_backup.BackupTest.test_betriebsstatus_enthaelt_nur_oeffentliche_sicherungsfelder) ... ok
test_fehlender_beleg_steht_im_manifest_und_db_sicherung_bleibt_erfolgreich (test_backup.BackupTest.test_fehlender_beleg_steht_im_manifest_und_db_sicherung_bleibt_erfolgreich) ... ok
test_fehlgeschlagene_sicherung_hinterlaesst_keine_tagesdatei (test_backup.BackupTest.test_fehlgeschlagene_sicherung_hinterlaesst_keine_tagesdatei) ... DB-Sicherung fehlgeschlagen (Betrieb laeuft weiter)
Traceback (most recent call last):
  File "C:\Users\lblet\dev\wt-p12\app\backup.py", line 262, in sichere_datenbank
    quelle.backup(kopie)
  File "C:\Users\lblet\dev\wt-p12\tests\test_backup.py", line 231, in backup
    raise sqlite3.OperationalError("simulierter Abbruch")
sqlite3.OperationalError: simulierter Abbruch
ok
test_geloeschte_belegkopie_wird_beim_zweiten_lauf_erneuert (test_backup.BackupTest.test_geloeschte_belegkopie_wird_beim_zweiten_lauf_erneuert) ... ok
test_identische_originalnamen_in_verschiedenen_sparten_bleiben_getrennt (test_backup.BackupTest.test_identische_originalnamen_in_verschiedenen_sparten_bleiben_getrennt) ... ok
test_ohne_zweitziel_bleibt_alles_wie_bisher (test_backup.BackupTest.test_ohne_zweitziel_bleibt_alles_wie_bisher) ... ok
test_pruefe_sicherung_erkennt_manipulierte_belegkopie (test_backup.BackupTest.test_pruefe_sicherung_erkennt_manipulierte_belegkopie) ... ok
test_rotation_entfernt_db_belegordner_und_manifest_gemeinsam (test_backup.BackupTest.test_rotation_entfernt_db_belegordner_und_manifest_gemeinsam) ... ok
test_unerreichbares_zweitziel_laesst_erstkopie_gueltig (test_backup.BackupTest.test_unerreichbares_zweitziel_laesst_erstkopie_gueltig) ... DB-Sicherung auf Zweitziel fehlgeschlagen, Erstkopie bleibt gueltig (\\kein-host-xyz-existiert\share\backup)
Traceback (most recent call last):
  File "C:\Users\lblet\AppData\Local\Programs\Python\Python312\Lib\pathlib.py", line 1311, in mkdir
    os.mkdir(self, mode)
  File "<stdin>", line 4, in inherited_acl_mkdir
PermissionError: [WinError 5] Zugriff verweigert: '\\\\kein-host-xyz-existiert\\share\\backup'

During handling of the above exception, another exception occurred:

Traceback (most recent call last):
  File "C:\Users\lblet\dev\wt-p12\app\backup.py", line 292, in _sichere_auf_zweitziel
    BACKUP_ZIEL2.mkdir(parents=True, exist_ok=True)
  File "C:\Users\lblet\AppData\Local\Programs\Python\Python312\Lib\pathlib.py", line 1320, in mkdir
    if not exist_ok or not self.is_dir():
                           ^^^^^^^^^^^^^
  File "C:\Users\lblet\AppData\Local\Programs\Python\Python312\Lib\pathlib.py", line 875, in is_dir
    return S_ISDIR(self.stat().st_mode)
                   ^^^^^^^^^^^
  File "C:\Users\lblet\AppData\Local\Programs\Python\Python312\Lib\pathlib.py", line 840, in stat
    return os.stat(self, follow_symlinks=follow_symlinks)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
PermissionError: [WinError 5] Zugriff verweigert: '\\\\kein-host-xyz-existiert\\share\\backup'
ok
test_zweiter_lauf_am_selben_tag_ist_idempotent (test_backup.BackupTest.test_zweiter_lauf_am_selben_tag_ist_idempotent) ... ok
test_zweitziel_erhaelt_eine_gueltige_zweitkopie (test_backup.BackupTest.test_zweitziel_erhaelt_eine_gueltige_zweitkopie) ... ok
test_absurde_abweichung_nur_pruefhinweis (test_beleg_auswertung.BelegAuswertungTest.test_absurde_abweichung_nur_pruefhinweis) ... Bild-Verkleinerung fehlgeschlagen - sende Original
Traceback (most recent call last):
  File "C:\Users\lblet\dev\wt-p12\app\auswertung.py", line 108, in _lade_bild_base64
    bild = Image.open(io.BytesIO(roh))
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "C:\Users\lblet\dev\finanz-dashboard-sparten\.venv\Lib\site-packages\PIL\Image.py", line 3532, in open
    raise UnidentifiedImageError(msg)
PIL.UnidentifiedImageError: cannot identify image file <_io.BytesIO object at 0x000001F95CB25FD0>
ok
test_auftrag_anlegen_und_dedupe (test_beleg_auswertung.BelegAuswertungTest.test_auftrag_anlegen_und_dedupe) ... ok
test_brutto_mit_mwst_je_position (test_beleg_auswertung.BelegAuswertungTest.test_brutto_mit_mwst_je_position) ... Bild-Verkleinerung fehlgeschlagen - sende Original
Traceback (most recent call last):
  File "C:\Users\lblet\dev\wt-p12\app\auswertung.py", line 108, in _lade_bild_base64
    bild = Image.open(io.BytesIO(roh))
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "C:\Users\lblet\dev\finanz-dashboard-sparten\.venv\Lib\site-packages\PIL\Image.py", line 3532, in open
    raise UnidentifiedImageError(msg)
PIL.UnidentifiedImageError: cannot identify image file <_io.BytesIO object at 0x000001F95D01CEA0>
ok
test_brutto_proportional_ohne_mwst (test_beleg_auswertung.BelegAuswertungTest.test_brutto_proportional_ohne_mwst) ... Bild-Verkleinerung fehlgeschlagen - sende Original
Traceback (most recent call last):
  File "C:\Users\lblet\dev\wt-p12\app\auswertung.py", line 108, in _lade_bild_base64
    bild = Image.open(io.BytesIO(roh))
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "C:\Users\lblet\dev\finanz-dashboard-sparten\.venv\Lib\site-packages\PIL\Image.py", line 3532, in open
    raise UnidentifiedImageError(msg)
PIL.UnidentifiedImageError: cannot identify image file <_io.BytesIO object at 0x000001F95D01D0D0>
ok
test_ollama_nicht_erreichbar_bleibt_offen (test_beleg_auswertung.BelegAuswertungTest.test_ollama_nicht_erreichbar_bleibt_offen) ... Bild-Verkleinerung fehlgeschlagen - sende Original
Traceback (most recent call last):
  File "C:\Users\lblet\dev\wt-p12\app\auswertung.py", line 108, in _lade_bild_base64
    bild = Image.open(io.BytesIO(roh))
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "C:\Users\lblet\dev\finanz-dashboard-sparten\.venv\Lib\site-packages\PIL\Image.py", line 3532, in open
    raise UnidentifiedImageError(msg)
PIL.UnidentifiedImageError: cannot identify image file <_io.BytesIO object at 0x000001F95D01D2B0>
ok
test_rabatt_wird_mitskaliert (test_beleg_auswertung.BelegAuswertungTest.test_rabatt_wird_mitskaliert) ... Bild-Verkleinerung fehlgeschlagen - sende Original
Traceback (most recent call last):
  File "C:\Users\lblet\dev\wt-p12\app\auswertung.py", line 108, in _lade_bild_base64
    bild = Image.open(io.BytesIO(roh))
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "C:\Users\lblet\dev\finanz-dashboard-sparten\.venv\Lib\site-packages\PIL\Image.py", line 3532, in open
    raise UnidentifiedImageError(msg)
PIL.UnidentifiedImageError: cannot identify image file <_io.BytesIO object at 0x000001F95D01D940>
ok
test_status_endpoint_erlaubt_nur_verworfen_oder_verbucht (test_beleg_auswertung.BelegAuswertungTest.test_status_endpoint_erlaubt_nur_verworfen_oder_verbucht) ... ok
test_stimmige_bruttosumme_unveraendert (test_beleg_auswertung.BelegAuswertungTest.test_stimmige_bruttosumme_unveraendert) ... Bild-Verkleinerung fehlgeschlagen - sende Original
Traceback (most recent call last):
  File "C:\Users\lblet\dev\wt-p12\app\auswertung.py", line 108, in _lade_bild_base64
    bild = Image.open(io.BytesIO(roh))
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "C:\Users\lblet\dev\finanz-dashboard-sparten\.venv\Lib\site-packages\PIL\Image.py", line 3532, in open
    raise UnidentifiedImageError(msg)
PIL.UnidentifiedImageError: cannot identify image file <_io.BytesIO object at 0x000001F95D01DB70>
ok
test_verarbeitung_gemockt_setzt_fertig_und_mapped_kategorie (test_beleg_auswertung.BelegAuswertungTest.test_verarbeitung_gemockt_setzt_fertig_und_mapped_kategorie) ... Bild-Verkleinerung fehlgeschlagen - sende Original
Traceback (most recent call last):
  File "C:\Users\lblet\dev\wt-p12\app\auswertung.py", line 108, in _lade_bild_base64
    bild = Image.open(io.BytesIO(roh))
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "C:\Users\lblet\dev\finanz-dashboard-sparten\.venv\Lib\site-packages\PIL\Image.py", line 3532, in open
    raise UnidentifiedImageError(msg)
PIL.UnidentifiedImageError: cannot identify image file <_io.BytesIO object at 0x000001F95D01DD50>
ok
test_belege_und_verknuepfungen (test_bereiche.BereicheTest.test_belege_und_verknuepfungen) ... ok
test_buchungen_suche_und_schreiben (test_bereiche.BereicheTest.test_buchungen_suche_und_schreiben) ... ok
test_dashboard_jahre_und_verlauf (test_bereiche.BereicheTest.test_dashboard_jahre_und_verlauf) ... ok
test_export_xlsx_und_bericht (test_bereiche.BereicheTest.test_export_xlsx_und_bericht) ... ok
test_fachliche_endpoints_haben_zentrale_dependency (test_bereiche.BereicheTest.test_fachliche_endpoints_haben_zentrale_dependency) ... ok
test_fehlendes_bereichsschema_bleibt_kontrolliert_gesperrt (test_bereiche.BereicheTest.test_fehlendes_bereichsschema_bleibt_kontrolliert_gesperrt) ... ok
test_fotoauftraege_grenzen (test_bereiche.BereicheTest.test_fotoauftraege_grenzen) ... ok
test_fotoverarbeitung_uebergibt_belegbereich (test_bereiche.BereicheTest.test_fotoverarbeitung_uebergibt_belegbereich) ... ok
test_gruppen_sind_bereichsgebunden (test_bereiche.BereicheTest.test_gruppen_sind_bereichsgebunden) ... ok
test_kategorien_grenzen (test_bereiche.BereicheTest.test_kategorien_grenzen) ... ok
test_login_ignoriert_unbekannten_bereich_fachlicher_endpoint_nicht (test_bereiche.BereicheTest.test_login_ignoriert_unbekannten_bereich_fachlicher_endpoint_nicht) ... ok
test_regeln_und_namensabgleich_der_schnellerfassung (test_bereiche.BereicheTest.test_regeln_und_namensabgleich_der_schnellerfassung) ... ok
test_stammdaten_und_bereichsaufloesung (test_bereiche.BereicheTest.test_stammdaten_und_bereichsaufloesung) ... ok
test_upload_dubletten_nur_im_bereich (test_bereiche.BereicheTest.test_upload_dubletten_nur_im_bereich) ... ok
test_account_creation_and_import_reject_foreign_references (test_bereiche_import.BereicheImportTest.test_account_creation_and_import_reject_foreign_references) ... ok
test_batch_checks_all_ids_before_first_commit (test_bereiche_import.BereicheImportTest.test_batch_checks_all_ids_before_first_commit) ... ok
test_domain_two_rule_and_batch_mutations (test_bereiche_import.BereicheImportTest.test_domain_two_rule_and_batch_mutations) ... ok
test_foreign_and_inconsistent_rules_are_not_proposed (test_bereiche_import.BereicheImportTest.test_foreign_and_inconsistent_rules_are_not_proposed) ... ok
test_foreign_mutations_are_404_and_do_not_write (test_bereiche_import.BereicheImportTest.test_foreign_mutations_are_404_and_do_not_write) ... ok
test_lists_and_foreign_filters (test_bereiche_import.BereicheImportTest.test_lists_and_foreign_filters) ... ok
test_rule_learning_stays_in_domain (test_bereiche_import.BereicheImportTest.test_rule_learning_stays_in_domain) ... ok
test_current_schema_accepts_migration_and_seed_has_separate_domains (test_bereiche_migration.BereicheMigrationTest.test_current_schema_accepts_migration_and_seed_has_separate_domains) ... ok
test_migration_assigns_domains_and_removes_only_foreign_memberships (test_bereiche_migration.BereicheMigrationTest.test_migration_assigns_domains_and_removes_only_foreign_memberships) ... ok
test_schema_and_migration_have_identical_structure (test_bereiche_migration.BereicheMigrationTest.test_schema_and_migration_have_identical_structure) ... ok
test_sql_runner_logs_skipped_existing_column (test_bereiche_migration.BereicheMigrationTest.test_sql_runner_logs_skipped_existing_column) ... ok
test_sql_runner_preserves_trigger_and_string_semicolons (test_bereiche_migration.BereicheMigrationTest.test_sql_runner_preserves_trigger_and_string_semicolons) ... ok
test_sql_runner_rolls_back_fk_failure_and_restores_enforcement (test_bereiche_migration.BereicheMigrationTest.test_sql_runner_rolls_back_fk_failure_and_restores_enforcement) ... ok
test_liefert_hoechstens_200_neueste_buchungen (test_buchungen_suche.BuchungenSucheApiTest.test_liefert_hoechstens_200_neueste_buchungen) ... ok
test_sucht_case_insensitiv_in_text_notiz_und_kontakt (test_buchungen_suche.BuchungenSucheApiTest.test_sucht_case_insensitiv_in_text_notiz_und_kontakt) ... ok
test_alter_fingerabdruck_verhindert_neuen_umsatz (test_import_bank.ImportBankApiTest.test_alter_fingerabdruck_verhindert_neuen_umsatz) ... ok
test_dublettenschutz_bei_wiederholtem_import (test_import_bank.ImportBankApiTest.test_dublettenschutz_bei_wiederholtem_import) ... ok
test_erfolgreicher_import_mehrerer_umsaetze (test_import_bank.ImportBankApiTest.test_erfolgreicher_import_mehrerer_umsaetze) ... ok
test_george_fixture_importiert_alle_zeilen_und_erkennt_spalten (test_import_bank.ImportBankApiTest.test_george_fixture_importiert_alle_zeilen_und_erkennt_spalten) ... ok
test_george_identische_zeilen_bleiben_zwei_und_reimport_ist_dubletten (test_import_bank.ImportBankApiTest.test_george_identische_zeilen_bleiben_zwei_und_reimport_ist_dubletten) ... ok
test_kaputte_csv_liefert_4xx_statt_500 (test_import_bank.ImportBankApiTest.test_kaputte_csv_liefert_4xx_statt_500) ... ok
test_semikolon_beispiel_prueft_und_speichert_saldo (test_import_bank.ImportBankApiTest.test_semikolon_beispiel_prueft_und_speichert_saldo) ... ok
test_verbuchen_erzeugt_buchung_und_lernt_regel (test_import_bank.ImportBankApiTest.test_verbuchen_erzeugt_buchung_und_lernt_regel) ... ok
test_erkennung_und_utf16 (test_import_bank.ParserTest.test_erkennung_und_utf16) ... ok
test_parse_betrag_cent (test_import_bank.ParserTest.test_parse_betrag_cent) ... ok
test_parse_datum (test_import_bank.ParserTest.test_parse_datum) ... ok
test_datei_ohne_kassabuch_layout_erzeugt_andere_warnung (test_import_excel.ImportExcelApiTest.test_datei_ohne_kassabuch_layout_erzeugt_andere_warnung)
Kein Blatt hat eine erkennbare Kopfzeile -> eigener Hinweistext. ... ok
test_dubletten_bei_wiederholtem_einspielen (test_import_excel.ImportExcelApiTest.test_dubletten_bei_wiederholtem_einspielen) ... ok
test_einspielen_legt_buchungen_an (test_import_excel.ImportExcelApiTest.test_einspielen_legt_buchungen_an) ... ok
test_leere_vorlage_erzeugt_warnung (test_import_excel.ImportExcelApiTest.test_leere_vorlage_erzeugt_warnung)
Aufgabe 1: eine Datei ohne jede Betragszeile darf nicht stillschweigend ... ok
test_pruefen_aendert_datenbank_nicht (test_import_excel.ImportExcelApiTest.test_pruefen_aendert_datenbank_nicht) ... ok
test_unbekannte_kategorien_werden_gemeldet (test_import_excel.ImportExcelApiTest.test_unbekannte_kategorien_werden_gemeldet) ... ok
test_bankomat_storno_und_cursor (test_konten_bewegungen.KontenApiTest.test_bankomat_storno_und_cursor) ... ok
test_bar_anlegen_aendern_loeschen (test_konten_bewegungen.KontenApiTest.test_bar_anlegen_aendern_loeschen) ... ok
test_csv_und_kassa_importverbot (test_konten_bewegungen.KontenApiTest.test_csv_und_kassa_importverbot) ... ok
test_geteilten_import_loeschen_und_transferimport_erhalten (test_konten_bewegungen.KontenApiTest.test_geteilten_import_loeschen_und_transferimport_erhalten) ... ok
test_import_verknuepfung_und_vorlaeufige_bewegung (test_konten_bewegungen.KontenApiTest.test_import_verknuepfung_und_vorlaeufige_bewegung) ... ok
test_kompatible_barumbuchung_und_storno (test_konten_bewegungen.KontenApiTest.test_kompatible_barumbuchung_und_storno) ... ok
test_konten_alias_validierung_und_bereich (test_konten_bewegungen.KontenApiTest.test_konten_alias_validierung_und_bereich) ... ok
test_notiz_kann_keinen_fremden_transfer_stornieren (test_konten_bewegungen.KontenApiTest.test_notiz_kann_keinen_fremden_transfer_stornieren) ... ok
test_put_prueft_erhaltenen_umsatz_und_oeffnet_abgeloesten (test_konten_bewegungen.KontenApiTest.test_put_prueft_erhaltenen_umsatz_und_oeffnet_abgeloesten) ... ok
test_unbekannte_zahlung_und_fremdes_konto (test_konten_bewegungen.KontenApiTest.test_unbekannte_zahlung_und_fremdes_konto) ... ok
test_bestandskopie_nachzug_und_schema_identisch (test_konten_bewegungen.KontenMigrationTest.test_bestandskopie_nachzug_und_schema_identisch) ... ok
test_alte_datenbank_erhaelt_basis_version_und_einmalige_sicherung (test_migrate.MigrationTest.test_alte_datenbank_erhaelt_basis_version_und_einmalige_sicherung) ... ok
test_fehlende_sicherung_ist_bei_wegwerf_datenbank_erlaubt (test_migrate.MigrationTest.test_fehlende_sicherung_ist_bei_wegwerf_datenbank_erlaubt) ... ok
test_fehlerhafte_migration_rollt_zurueck_und_sperrt_version (test_migrate.MigrationTest.test_fehlerhafte_migration_rollt_zurueck_und_sperrt_version) ... ok
test_fehlgeschlagene_pflichtsicherung_stoppt_nachzug (test_migrate.MigrationTest.test_fehlgeschlagene_pflichtsicherung_stoppt_nachzug) ... ok
test_migrationsfehler_startet_app_schreibgeschuetzt (test_migrate.MigrationTest.test_migrationsfehler_startet_app_schreibgeschuetzt) ... ok
test_neue_datenbank_ist_auf_version_5_ohne_anstehende_migrationen (test_migrate.MigrationTest.test_neue_datenbank_ist_auf_version_5_ohne_anstehende_migrationen) ... ok
test_neue_und_alte_datenbank_haben_gleiche_tabellenliste (test_migrate.MigrationTest.test_neue_und_alte_datenbank_haben_gleiche_tabellenliste) ... ok
test_schema_endpoint_liefert_erwartete_felder (test_migrate.MigrationTest.test_schema_endpoint_liefert_erwartete_felder) ... ok
test_schreibschutz_blockiert_auth_login_nicht (test_migrate.MigrationTest.test_schreibschutz_blockiert_auth_login_nicht) ... ok
test_schreibschutz_blockiert_post_aber_nicht_get (test_migrate.MigrationTest.test_schreibschutz_blockiert_post_aber_nicht_get) ... ok
test_aktuelles_passwort_ist_fuer_passwortmanager_gekennzeichnet (test_password_frontend.PasswordFrontendTest.test_aktuelles_passwort_ist_fuer_passwortmanager_gekennzeichnet) ... ok
test_desktop_navigation_verlinkt_passwortaenderung (test_password_frontend.PasswordFrontendTest.test_desktop_navigation_verlinkt_passwortaenderung) ... ok
test_erfolgsmeldung_ist_fokussierbar_und_fuehrt_zur_anmeldung (test_password_frontend.PasswordFrontendTest.test_erfolgsmeldung_ist_fokussierbar_und_fuehrt_zur_anmeldung) ... ok
test_kopiermeldung_bleibt_im_sichtbaren_recovery_panel (test_password_frontend.PasswordFrontendTest.test_kopiermeldung_bleibt_im_sichtbaren_recovery_panel) ... ok
test_login_verlinkt_passwort_vergessen (test_password_frontend.PasswordFrontendTest.test_login_verlinkt_passwort_vergessen) ... ok
test_mehr_menue_verlinkt_passwortaenderung (test_password_frontend.PasswordFrontendTest.test_mehr_menue_verlinkt_passwortaenderung) ... ok
test_netzwerkfehler_werden_verstaendlich_angezeigt (test_password_frontend.PasswordFrontendTest.test_netzwerkfehler_werden_verstaendlich_angezeigt) ... ok
test_passwortaenderung_sendet_altes_und_neues_passwort (test_password_frontend.PasswordFrontendTest.test_passwortaenderung_sendet_altes_und_neues_passwort) ... ok
test_passwortfelder_begrenzen_laenge_und_verwenden_neues_autocomplete (test_password_frontend.PasswordFrontendTest.test_passwortfelder_begrenzen_laenge_und_verwenden_neues_autocomplete) ... ok
test_recovery_code_kann_kopiert_werden (test_password_frontend.PasswordFrontendTest.test_recovery_code_kann_kopiert_werden) ... ok
test_recovery_code_wird_nur_in_einem_sicheren_bereich_angeboten (test_password_frontend.PasswordFrontendTest.test_recovery_code_wird_nur_in_einem_sicheren_bereich_angeboten) ... ok
test_setup_hat_zwei_passwortfelder_und_recovery_aktionen (test_password_frontend.PasswordFrontendTest.test_setup_hat_zwei_passwortfelder_und_recovery_aktionen) ... ok
test_setup_ruft_initial_password_mit_same_origin_credentials_auf (test_password_frontend.PasswordFrontendTest.test_setup_ruft_initial_password_mit_same_origin_credentials_auf) ... ok
test_weiter_zur_anmeldung_ist_vollwertige_aktion (test_password_frontend.PasswordFrontendTest.test_weiter_zur_anmeldung_ist_vollwertige_aktion) ... ok
test_wiederherstellung_setzt_neues_passwort_und_zeigt_fehler (test_password_frontend.PasswordFrontendTest.test_wiederherstellung_setzt_neues_passwort_und_zeigt_fehler) ... ok
test_windows_cleanup_ist_idempotent_und_beendet_den_gestarteten_baum (test_process_cleanup.ProcessCleanupTest.test_windows_cleanup_ist_idempotent_und_beendet_den_gestarteten_baum) ... ok
test_manuelles_verbuchen_lernt_regel_und_liefert_vollstaendigen_vorschlag (test_regeln.RegelvorschlagApiTest.test_manuelles_verbuchen_lernt_regel_und_liefert_vollstaendigen_vorschlag) ... ok
test_regelverwaltung_und_bulk_uebernahme (test_regeln.RegelvorschlagApiTest.test_regelverwaltung_und_bulk_uebernahme) ... ok
test_studio_bietet_bulk_uebernahme_und_regelverwaltung (test_regeln.RegelvorschlagApiTest.test_studio_bietet_bulk_uebernahme_und_regelverwaltung) ... ok
test_verbuchen_validiert_kategorierichtung_und_umbuchung (test_regeln.RegelvorschlagApiTest.test_verbuchen_validiert_kategorierichtung_und_umbuchung) ... ok
test_dezimalkomma_bleibt_beim_splitten_erhalten (test_schnellerfassung_mehrere.SammeltextErfassungTest.test_dezimalkomma_bleibt_beim_splitten_erhalten) ... ok
test_mehrere_positionen_durch_komma_getrennt (test_schnellerfassung_mehrere.SammeltextErfassungTest.test_mehrere_positionen_durch_komma_getrennt) ... ok
test_mehrzeiliger_text_wird_je_zeile_geparst (test_schnellerfassung_mehrere.SammeltextErfassungTest.test_mehrzeiliger_text_wird_je_zeile_geparst) ... ok
test_parse_verhaelt_sich_unveraendert (test_schnellerfassung_mehrere.SammeltextErfassungTest.test_parse_verhaelt_sich_unveraendert) ... ok
test_autostart_empfiehlt_keine_lan_freigabe (test_secure_launchers.SecureLauncherTest.test_autostart_empfiehlt_keine_lan_freigabe) ... ok
test_handy_launcher_oeffnet_nur_private_produktiv_url (test_secure_launchers.SecureLauncherTest.test_handy_launcher_oeffnet_nur_private_produktiv_url) ... ok
test_cli_akzeptiert_sechs_zeichen_und_schreibt_neues_format (test_set_auth_password.SetAuthPasswordTest.test_cli_akzeptiert_sechs_zeichen_und_schreibt_neues_format) ... ok
test_nur_recovery_code_laesst_passwort_unveraendert (test_set_auth_password.SetAuthPasswordTest.test_nur_recovery_code_laesst_passwort_unveraendert) ... ok
test_nur_recovery_code_ohne_bestehende_datei_scheitert_sauber (test_set_auth_password.SetAuthPasswordTest.test_nur_recovery_code_ohne_bestehende_datei_scheitert_sauber) ... Keine bestehende Auth-Datei unter C:\Users\lblet\AppData\Local\Temp\tmp6jvtub62\auth.json gefunden. Ohne bestehendes Passwort kann kein Recovery-Code erzeugt werden.
ok
test_suchfeld_nutzt_server_suche_mit_debounce_und_normale_leerliste (test_studio_suche.StudioSucheTest.test_suchfeld_nutzt_server_suche_mit_debounce_und_normale_leerliste) ... ok
test_betrag_0_oder_negativ_wird_abgelehnt (test_umbuchungen.UmbuchungenApiTest.test_betrag_0_oder_negativ_wird_abgelehnt) ... ok
test_gleiche_sparte_wird_abgelehnt (test_umbuchungen.UmbuchungenApiTest.test_gleiche_sparte_wird_abgelehnt) ... ok
test_umbuchung_erzeugt_zwei_gekoppelte_buchungen (test_umbuchungen.UmbuchungenApiTest.test_umbuchung_erzeugt_zwei_gekoppelte_buchungen) ... ok
test_umbuchung_ist_erfolgsneutral_im_dashboard (test_umbuchungen.UmbuchungenApiTest.test_umbuchung_ist_erfolgsneutral_im_dashboard) ... ok

----------------------------------------------------------------------
Ran 185 tests in 342.641s

OK (skipped=1)
```

### Doppelter Nachzug

Die Probe ruft `app.migrate.anwenden(con, sicherung, sicherung_pflicht=True)` zweimal auf; die Sicherung verwendet die SQLite-Backup-API. Der zweite Lauf erstellt keine weitere Sicherung und verändert auch keine Versionszeitpunkte. Zusätzlich prüft der automatisierte Migrationstest die erneute Anwendung bei bereits vorhandenen P12-Objekten ohne Versionsmarke.

```text
Datenbank: C:\Users\lblet\AppData\Local\Temp\p12-bestand.db
Basis: git show HEAD:db/schema.sql + db/seed.sql (P11), Versionen 1-4 markiert
Kuenstlicher Bestand: 4 Konten, 4 Buchungen, 4 Zeilen, 4 Bewegungen
Sicherung: C:\Users\lblet\AppData\Local\Temp\p12-bestand-vorher.db
Erster Runner-Lauf angewendet: [5]
Zweiter Runner-Lauf angewendet: []
SHA-256 SQL-Dump nach Lauf 1: 6cf29c16b2e36df97dc3ff04c977c2dc460f2d69dd7471fd81669ffc3203f5b3
SHA-256 SQL-Dump nach Lauf 2: 6cf29c16b2e36df97dc3ff04c977c2dc460f2d69dd7471fd81669ffc3203f5b3
Kosten vorher/nachher: [(1, '2025', 'einnahme', 20000), (1, '2026', 'ausgabe', 1234), (2, '2025', 'einnahme', 20000), (2, '2026', 'ausgabe', 1234)]
Kontosalden vorher/nachher: [(2, 18766), (4, 18766)]
Schema-Neuanlage / Nachzug: table_info, foreign_key_list, index_list identisch
Keine automatische Auslage: 0
PRAGMA integrity_check: ok; foreign_key_check: []
Status: {'aktuell': 5, 'anstehend': [], 'basis': False}
```

## Offene Punkte

Keine offenen P12-Implementierungspunkte. Einzige Plattformgrenze der Prüfung: Der bereits vorhandene Test auf POSIX-Dateimodus 0600 ist mit dem vorgeschriebenen Windows-Interpreter nicht ausführbar und wird durch seine bestehende Plattformbedingung übersprungen. Auth und Validierung wurden nicht abgeschwächt. Frontend, Saldoanker, Import-/Regeländerungen und Umdeutung von Altdaten bleiben entsprechend den Nicht-Zielen unberührt.
