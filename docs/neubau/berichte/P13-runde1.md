# P13 – Runde 1

Stand: 2026-09-09. Worktree: `C:\\Users\\lblet\\dev\\wt-p13`, Branch: `pkt/p13-saldoanker-kassa`.

## Ergebnis

P13 ist umgesetzt. Kontostände verwenden datierte Tagesendanker, unbekannte Anfangsstände bleiben `stand_cent: null`, Kassadifferenzen bleiben bis zur ausdrücklichen Buchung offen, und alle neuen fachlichen Endpunkte prüfen den Bereich.

## Geänderte und neue Dateien

- `app/konten.py`: Neue reine Funktion `kontostand(con, konto_id, stichtag)` berechnet Ankerstand, Bewegungen, Importalter und fachliche Hinweise.
- `app/routers/konten.py`: Bestehende Kontenendpunkte um P13-Felder sowie Anker-, Zählungs-, Differenzbuchungs- und Zählungsliste-Endpunkte erweitert.
- `app/routers/import_bank.py`: CSV-Importe mit erkannter Saldospalte legen für die jüngste Importzeile einen idempotenten Importanker an.
- `db/migrations/006_saldoanker_kassa.sql`: Idempotente Tabellen und Indizes für `kontostand_anker` und `kassazaehlung`.
- `db/schema.sql`: Neues Schema für Anker und Kassazählungen einschließlich identischer Indizes.
- `tests/test_saldoanker.py`: P13-API-, Rechen-, Bereichs-, Import- und Idempotenztests mit temporären Datenbanken.
- `tests/test_konten_bewegungen.py`: P11-Bestandsnachzug auf den zusätzlichen Migrationsschritt 006 angepasst.
- `tests/test_bereiche_migration.py`: Migrationserwartungen auf Version 6 angepasst.
- `tests/test_import_bank.py`: Neue P13-FK-Daten vor Konto-Neuanlage im Test bereinigt.
- `tests/test_regeln.py`: Neue P13-FK-Daten vor Konto-Neuanlage im Test bereinigt.
- `tests/test_migrate.py`: Versions- und Schema-Endpoint-Erwartungen auf Version 6 angepasst.

## Neue Endpunkte und Bereichsprüfung

- `GET /api/konten/{id}/stand?stichtag=`: Konto wird mit `pruefe_konto` gegen `bereich_dep` geprüft.
- `POST /api/konten/{id}/anker`: Konto und optionaler Beleg werden mit `pruefe_konto`/ `pruefe_beleg` im Bereich geprüft.
- `GET /api/konten/{id}/anker`: Konto wird mit `pruefe_konto` geprüft.
- `DELETE /api/konten/{id}/anker/{anker_id}`: Konto wird mit `pruefe_konto` geprüft und die Anker-ID zusätzlich auf dasselbe Konto eingeschränkt.
- `POST /api/konten/{id}/zaehlung`: Konto wird mit `pruefe_konto` geprüft; nur `art='kassa'` ist zulässig.
- `POST /api/konten/{id}/zaehlung/{zaehlung_id}/buchen`: Konto und Kategorie werden mit `pruefe_konto`/ `pruefe_kategorie` geprüft; Zählung zusätzlich auf das Konto eingeschränkt.
- `GET /api/kassazaehlungen?bereich_id=&status=`: Bereich wird über `bereich_dep` aufgelöst, die Abfrage filtert über das Konto-`bereich_id`.
- `GET /api/konten?bereich_id=` und Alias `/api/bankkonten`: Bestehende Kontenprüfung bleibt aktiv; jedes Konto erhält P13-Standfelder.

Nicht verändert wurden `/api/auth/*`, `/api/health`, `/api/schema` und `/api/betrieb/status`.

## Nachzugsprobe

Bestandsdatenbank erzeugt aus `db/schema.sql` und `db/seed.sql` unter `C:\\Users\\lblet\\AppData\\Local\\Temp\\p13-bestand.db`:

```
ERSTER_NACHZUG [1, 2, 3, 4, 6]
ZWEITER_NACHZUG []
STATUS {'aktuell': 6, 'anstehend': [], 'basis': True}
```

Der zweite Lauf wendete keinen Schritt an. Die separate Migrationstestprüfung bestätigt zusätzlich den identischen Snapshot nach zwei Läufen.

## Vollständige Testausgabe

Befehl (mit dem vorhandenen Interpreterpfad):

```
C:\\Users\\lblet\\dev\\finanz-dashboard-sparten\\.venv\\Scripts\\python.exe -m unittest discover -s tests
```

Die Windows-Sandbox verhindert bei `TemporaryDirectory()` das Öffnen neu angelegter SQLite-Dateien nach dem standardmäßigen temporären ACL-Schritt. Für den Testprozess wurde deshalb ausschließlich `tempfile._os.mkdir` so aufgerufen, dass die geerbten Temp-ACLs erhalten bleiben; die Tests verwenden weiterhin `tempfile.TemporaryDirectory()` und schreiben nicht in den Worktree.

```
python.exe : test_api_ist_ohne_anmeldung_gesperrt (test_auth.AuthIntegrationTest.test_api_ist_ohne_anmeldung_gesperrt) 
... ok
In Zeile:2 Zeichen:1
+ & 'C:\Users\lblet\dev\finanz-dashboard-sparten\.venv\Scripts\python.e ...
+ ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    + CategoryInfo          : NotSpecified: (test_api_ist_oh...esperrt) ... ok:String) [], RemoteException
    + FullyQualifiedErrorId : NativeCommandError
 
test_browser_wird_auf_vorhandene_loginseite_umgeleitet 
(test_auth.AuthIntegrationTest.test_browser_wird_auf_vorhandene_loginseite_umgeleitet) ... ok
test_falsches_passwort_wird_abgewiesen (test_auth.AuthIntegrationTest.test_falsches_passwort_wird_abgewiesen) ... ok
test_freigegebenes_tailscale_geraet_erreicht_den_login 
(test_auth.AuthIntegrationTest.test_freigegebenes_tailscale_geraet_erreicht_den_login) ... ok
test_login_setzt_sicheres_cookie_und_oeffnet_api 
(test_auth.AuthIntegrationTest.test_login_setzt_sicheres_cookie_und_oeffnet_api) ... ok
test_logout_loescht_cookie (test_auth.AuthIntegrationTest.test_logout_loescht_cookie) ... ok
test_manipuliertes_cookie_wird_abgewiesen (test_auth.AuthIntegrationTest.test_manipuliertes_cookie_wird_abgewiesen) 
... ok
test_nicht_freigegebenes_tailscale_geraet_wird_abgewiesen 
(test_auth.AuthIntegrationTest.test_nicht_freigegebenes_tailscale_geraet_wird_abgewiesen) ... ok
test_unbekannter_host_header_wird_abgewiesen 
(test_auth.AuthIntegrationTest.test_unbekannter_host_header_wird_abgewiesen) ... ok
test_abgelaufene_api_session_fuehrt_zur_loginseite 
(test_auth_expiry_frontend.AuthExpiryFrontendTest.test_abgelaufene_api_session_fuehrt_zur_loginseite) ... ok
test_studio_bietet_logout_ueber_post_an (test_auth_frontend.AuthFrontendTest.test_studio_bietet_logout_ueber_post_an) 
... ok
test_ersteinrichtung_gibt_code_einmal_aus 
(test_auth_lifecycle.AuthLifecycleIntegrationTest.test_ersteinrichtung_gibt_code_einmal_aus) ... ok
test_ersteinrichtung_kann_nicht_wiederholt_werden 
(test_auth_lifecycle.AuthLifecycleIntegrationTest.test_ersteinrichtung_kann_nicht_wiederholt_werden) ... ok
test_ersteinrichtung_lehnt_json_array_ab 
(test_auth_lifecycle.AuthLifecycleIntegrationTest.test_ersteinrichtung_lehnt_json_array_ab) ... ok
test_ersteinrichtung_lehnt_malformedes_json_ab 
(test_auth_lifecycle.AuthLifecycleIntegrationTest.test_ersteinrichtung_lehnt_malformedes_json_ab) ... ok
test_ersteinrichtung_lehnt_ungueltige_eingaben_ab 
(test_auth_lifecycle.AuthLifecycleIntegrationTest.test_ersteinrichtung_lehnt_ungueltige_eingaben_ab) ... ok
test_ersteinrichtung_lehnt_ungueltiges_utf8_ab 
(test_auth_lifecycle.AuthLifecycleIntegrationTest.test_ersteinrichtung_lehnt_ungueltiges_utf8_ab) ... ok
test_login_lehnt_ungueltiges_utf8_neutral_ab 
(test_auth_lifecycle.AuthLifecycleIntegrationTest.test_login_lehnt_ungueltiges_utf8_neutral_ab) ... ok
test_passwortaenderung_lehnt_fehlerhafte_eingaben_ab 
(test_auth_lifecycle.AuthLifecycleIntegrationTest.test_passwortaenderung_lehnt_fehlerhafte_eingaben_ab) ... ok
test_passwortaenderung_lehnt_json_array_ab 
(test_auth_lifecycle.AuthLifecycleIntegrationTest.test_passwortaenderung_lehnt_json_array_ab) ... ok
test_passwortaenderung_lehnt_malformedes_json_ab 
(test_auth_lifecycle.AuthLifecycleIntegrationTest.test_passwortaenderung_lehnt_malformedes_json_ab) ... ok
test_passwortaenderung_lehnt_ungueltiges_utf8_ab 
(test_auth_lifecycle.AuthLifecycleIntegrationTest.test_passwortaenderung_lehnt_ungueltiges_utf8_ab) ... ok
test_passwortaenderung_widerruft_alte_sitzung 
(test_auth_lifecycle.AuthLifecycleIntegrationTest.test_passwortaenderung_widerruft_alte_sitzung) ... ok
test_recovery_lehnt_fehlerhafte_eingaben_ab 
(test_auth_lifecycle.AuthLifecycleIntegrationTest.test_recovery_lehnt_fehlerhafte_eingaben_ab) ... ok
test_recovery_lehnt_json_array_neutral_ab 
(test_auth_lifecycle.AuthLifecycleIntegrationTest.test_recovery_lehnt_json_array_neutral_ab) ... ok
test_recovery_lehnt_malformedes_json_neutral_ab 
(test_auth_lifecycle.AuthLifecycleIntegrationTest.test_recovery_lehnt_malformedes_json_neutral_ab) ... ok
test_recovery_lehnt_ungueltiges_utf8_neutral_ab 
(test_auth_lifecycle.AuthLifecycleIntegrationTest.test_recovery_lehnt_ungueltiges_utf8_neutral_ab) ... ok
test_recovery_rotiert_code_und_lehnt_wiederverwendung_ab 
(test_auth_lifecycle.AuthLifecycleIntegrationTest.test_recovery_rotiert_code_und_lehnt_wiederverwendung_ab) ... ok
test_recovery_sperrt_nach_fuenf_ungueltigen_payloads 
(test_auth_lifecycle.AuthLifecycleIntegrationTest.test_recovery_sperrt_nach_fuenf_ungueltigen_payloads) ... ok
test_setup_assets_sind_waehrend_ersteinrichtung_erreichbar 
(test_auth_lifecycle.AuthLifecycleIntegrationTest.test_setup_assets_sind_waehrend_ersteinrichtung_erreichbar) ... ok
test_startpasswort_erlaubt_nur_ersteinrichtung 
(test_auth_lifecycle.AuthLifecycleIntegrationTest.test_startpasswort_erlaubt_nur_ersteinrichtung) ... ok
test_wiederherstellungsseite_und_assets_sind_oeffentlich 
(test_auth_lifecycle.AuthLifecycleIntegrationTest.test_wiederherstellungsseite_und_assets_sind_oeffentlich) ... ok
test_store_schreibt_atomar_und_laesst_keine_temporaere_datei 
(test_auth_store.AuthConfigStoreTest.test_store_schreibt_atomar_und_laesst_keine_temporaere_datei) ... ok
test_store_setzt_dateimodus_0600 (test_auth_store.AuthConfigStoreTest.test_store_setzt_dateimodus_0600) ... skipped 
'POSIX-Dateirechte'
test_wiederherstellungscode_hat_mindestens_128_bit 
(test_auth_store.AuthConfigStoreTest.test_wiederherstellungscode_hat_mindestens_128_bit) ... ok
test_genau_sechs_zeichen_und_alle_zeichenarten_sind_erlaubt 
(test_auth_store.PasswordValidationTest.test_genau_sechs_zeichen_und_alle_zeichenarten_sind_erlaubt) ... ok
test_hashing_verwendet_die_flexible_passwortvalidierung 
(test_auth_store.PasswordValidationTest.test_hashing_verwendet_die_flexible_passwortvalidierung) ... ok
test_ungueltige_passwoerter_werden_abgewiesen 
(test_auth_store.PasswordValidationTest.test_ungueltige_passwoerter_werden_abgewiesen) ... ok
test_manipulierte_session_wird_abgewiesen (test_auth_unit.AuthUnitTest.test_manipulierte_session_wird_abgewiesen) ... 
ok
test_passwort_hash_enthaelt_keinen_klartext (test_auth_unit.AuthUnitTest.test_passwort_hash_enthaelt_keinen_klartext) 
... ok
test_rate_limit_sperrt_nach_fuenf_fehlern (test_auth_unit.AuthUnitTest.test_rate_limit_sperrt_nach_fuenf_fehlern) ... 
ok
test_session_gilt_hoechstens_zwoelf_stunden (test_auth_unit.AuthUnitTest.test_session_gilt_hoechstens_zwoelf_stunden) 
... ok
test_buchung_speichern_legt_regel_an (test_auto_kategorien.AutoKategorienTest.test_buchung_speichern_legt_regel_an) 
... ok
test_ein_einzelnes_gemeinsames_wort_reicht_nicht_fuer_einen_treffer 
(test_auto_kategorien.AutoKategorienTest.test_ein_einzelnes_gemeinsames_wort_reicht_nicht_fuer_einen_treffer) ... ok
test_kurze_eingabe_trifft_lange_gelernte_regel_ueber_wort_tokens 
(test_auto_kategorien.AutoKategorienTest.test_kurze_eingabe_trifft_lange_gelernte_regel_ueber_wort_tokens) ... ok
test_namensabgleich_hat_vorrang_vor_regel 
(test_auto_kategorien.AutoKategorienTest.test_namensabgleich_hat_vorrang_vor_regel) ... ok
test_parse_ordnet_per_regel_zu_ohne_kategorienamen 
(test_auto_kategorien.AutoKategorienTest.test_parse_ordnet_per_regel_zu_ohne_kategorienamen) ... ok
test_umbuchung_lernt_nicht (test_auto_kategorien.AutoKategorienTest.test_umbuchung_lernt_nicht) ... ok
test_belege_manifest_und_pruefsummen_werden_gesichert 
(test_backup.BackupTest.test_belege_manifest_und_pruefsummen_werden_gesichert) ... ok
test_belegsicherung_ohne_db_kopie_schreibt_db_null 
(test_backup.BackupTest.test_belegsicherung_ohne_db_kopie_schreibt_db_null) ... ok
test_beschaedigte_tagesdatei_wird_durch_gueltige_sicherung_ersetzt 
(test_backup.BackupTest.test_beschaedigte_tagesdatei_wird_durch_gueltige_sicherung_ersetzt) ... ok
test_betriebsstatus_enthaelt_nur_oeffentliche_sicherungsfelder 
(test_backup.BackupTest.test_betriebsstatus_enthaelt_nur_oeffentliche_sicherungsfelder) ... ok
test_fehlender_beleg_steht_im_manifest_und_db_sicherung_bleibt_erfolgreich 
(test_backup.BackupTest.test_fehlender_beleg_steht_im_manifest_und_db_sicherung_bleibt_erfolgreich) ... ok
test_fehlgeschlagene_sicherung_hinterlaesst_keine_tagesdatei 
(test_backup.BackupTest.test_fehlgeschlagene_sicherung_hinterlaesst_keine_tagesdatei) ... DB-Sicherung fehlgeschlagen 
(Betrieb laeuft weiter)
Traceback (most recent call last):
  File "C:\Users\lblet\dev\wt-p13\app\backup.py", line 262, in sichere_datenbank
    quelle.backup(kopie)
  File "C:\Users\lblet\dev\wt-p13\tests\test_backup.py", line 231, in backup
    raise sqlite3.OperationalError("simulierter Abbruch")
sqlite3.OperationalError: simulierter Abbruch
ok
test_geloeschte_belegkopie_wird_beim_zweiten_lauf_erneuert 
(test_backup.BackupTest.test_geloeschte_belegkopie_wird_beim_zweiten_lauf_erneuert) ... ok
test_identische_originalnamen_in_verschiedenen_sparten_bleiben_getrennt 
(test_backup.BackupTest.test_identische_originalnamen_in_verschiedenen_sparten_bleiben_getrennt) ... ok
test_ohne_zweitziel_bleibt_alles_wie_bisher (test_backup.BackupTest.test_ohne_zweitziel_bleibt_alles_wie_bisher) ... ok
test_pruefe_sicherung_erkennt_manipulierte_belegkopie 
(test_backup.BackupTest.test_pruefe_sicherung_erkennt_manipulierte_belegkopie) ... ok
test_rotation_entfernt_db_belegordner_und_manifest_gemeinsam 
(test_backup.BackupTest.test_rotation_entfernt_db_belegordner_und_manifest_gemeinsam) ... ok
test_unerreichbares_zweitziel_laesst_erstkopie_gueltig 
(test_backup.BackupTest.test_unerreichbares_zweitziel_laesst_erstkopie_gueltig) ... DB-Sicherung auf Zweitziel 
fehlgeschlagen, Erstkopie bleibt gueltig (\\kein-host-xyz-existiert\share\backup)
Traceback (most recent call last):
  File "C:\Users\lblet\AppData\Local\Programs\Python\Python312\Lib\pathlib.py", line 1311, in mkdir
    os.mkdir(self, mode)
  File "<string>", line 1, in <lambda>
PermissionError: [WinError 5] Zugriff verweigert: '\\\\kein-host-xyz-existiert\\share\\backup'

During handling of the above exception, another exception occurred:

Traceback (most recent call last):
  File "C:\Users\lblet\dev\wt-p13\app\backup.py", line 292, in _sichere_auf_zweitziel
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
test_zweiter_lauf_am_selben_tag_ist_idempotent (test_backup.BackupTest.test_zweiter_lauf_am_selben_tag_ist_idempotent) 
... ok
test_zweitziel_erhaelt_eine_gueltige_zweitkopie 
(test_backup.BackupTest.test_zweitziel_erhaelt_eine_gueltige_zweitkopie) ... ok
test_absurde_abweichung_nur_pruefhinweis 
(test_beleg_auswertung.BelegAuswertungTest.test_absurde_abweichung_nur_pruefhinweis) ... Bild-Verkleinerung 
fehlgeschlagen - sende Original
Traceback (most recent call last):
  File "C:\Users\lblet\dev\wt-p13\app\auswertung.py", line 108, in _lade_bild_base64
    bild = Image.open(io.BytesIO(roh))
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "C:\Users\lblet\dev\finanz-dashboard-sparten\.venv\Lib\site-packages\PIL\Image.py", line 3532, in open
    raise UnidentifiedImageError(msg)
PIL.UnidentifiedImageError: cannot identify image file <_io.BytesIO object at 0x000001C66E509030>
ok
test_auftrag_anlegen_und_dedupe (test_beleg_auswertung.BelegAuswertungTest.test_auftrag_anlegen_und_dedupe) ... ok
test_brutto_mit_mwst_je_position (test_beleg_auswertung.BelegAuswertungTest.test_brutto_mit_mwst_je_position) ... 
Bild-Verkleinerung fehlgeschlagen - sende Original
Traceback (most recent call last):
  File "C:\Users\lblet\dev\wt-p13\app\auswertung.py", line 108, in _lade_bild_base64
    bild = Image.open(io.BytesIO(roh))
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "C:\Users\lblet\dev\finanz-dashboard-sparten\.venv\Lib\site-packages\PIL\Image.py", line 3532, in open
    raise UnidentifiedImageError(msg)
PIL.UnidentifiedImageError: cannot identify image file <_io.BytesIO object at 0x000001C66E6BE750>
ok
test_brutto_proportional_ohne_mwst (test_beleg_auswertung.BelegAuswertungTest.test_brutto_proportional_ohne_mwst) ... 
Bild-Verkleinerung fehlgeschlagen - sende Original
Traceback (most recent call last):
  File "C:\Users\lblet\dev\wt-p13\app\auswertung.py", line 108, in _lade_bild_base64
    bild = Image.open(io.BytesIO(roh))
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "C:\Users\lblet\dev\finanz-dashboard-sparten\.venv\Lib\site-packages\PIL\Image.py", line 3532, in open
    raise UnidentifiedImageError(msg)
PIL.UnidentifiedImageError: cannot identify image file <_io.BytesIO object at 0x000001C66E6BE980>
ok
test_ollama_nicht_erreichbar_bleibt_offen 
(test_beleg_auswertung.BelegAuswertungTest.test_ollama_nicht_erreichbar_bleibt_offen) ... Bild-Verkleinerung 
fehlgeschlagen - sende Original
Traceback (most recent call last):
  File "C:\Users\lblet\dev\wt-p13\app\auswertung.py", line 108, in _lade_bild_base64
    bild = Image.open(io.BytesIO(roh))
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "C:\Users\lblet\dev\finanz-dashboard-sparten\.venv\Lib\site-packages\PIL\Image.py", line 3532, in open
    raise UnidentifiedImageError(msg)
PIL.UnidentifiedImageError: cannot identify image file <_io.BytesIO object at 0x000001C66E509120>
ok
test_rabatt_wird_mitskaliert (test_beleg_auswertung.BelegAuswertungTest.test_rabatt_wird_mitskaliert) ... 
Bild-Verkleinerung fehlgeschlagen - sende Original
Traceback (most recent call last):
  File "C:\Users\lblet\dev\wt-p13\app\auswertung.py", line 108, in _lade_bild_base64
    bild = Image.open(io.BytesIO(roh))
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "C:\Users\lblet\dev\finanz-dashboard-sparten\.venv\Lib\site-packages\PIL\Image.py", line 3532, in open
    raise UnidentifiedImageError(msg)
PIL.UnidentifiedImageError: cannot identify image file <_io.BytesIO object at 0x000001C66E6BEDE0>
ok
test_status_endpoint_erlaubt_nur_verworfen_oder_verbucht 
(test_beleg_auswertung.BelegAuswertungTest.test_status_endpoint_erlaubt_nur_verworfen_oder_verbucht) ... ok
test_stimmige_bruttosumme_unveraendert 
(test_beleg_auswertung.BelegAuswertungTest.test_stimmige_bruttosumme_unveraendert) ... Bild-Verkleinerung 
fehlgeschlagen - sende Original
Traceback (most recent call last):
  File "C:\Users\lblet\dev\wt-p13\app\auswertung.py", line 108, in _lade_bild_base64
    bild = Image.open(io.BytesIO(roh))
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "C:\Users\lblet\dev\finanz-dashboard-sparten\.venv\Lib\site-packages\PIL\Image.py", line 3532, in open
    raise UnidentifiedImageError(msg)
PIL.UnidentifiedImageError: cannot identify image file <_io.BytesIO object at 0x000001C66E6BF010>
ok
test_verarbeitung_gemockt_setzt_fertig_und_mapped_kategorie 
(test_beleg_auswertung.BelegAuswertungTest.test_verarbeitung_gemockt_setzt_fertig_und_mapped_kategorie) ... 
Bild-Verkleinerung fehlgeschlagen - sende Original
Traceback (most recent call last):
  File "C:\Users\lblet\dev\wt-p13\app\auswertung.py", line 108, in _lade_bild_base64
    bild = Image.open(io.BytesIO(roh))
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "C:\Users\lblet\dev\finanz-dashboard-sparten\.venv\Lib\site-packages\PIL\Image.py", line 3532, in open
    raise UnidentifiedImageError(msg)
PIL.UnidentifiedImageError: cannot identify image file <_io.BytesIO object at 0x000001C66E6BF1F0>
ok
test_belege_und_verknuepfungen (test_bereiche.BereicheTest.test_belege_und_verknuepfungen) ... ok
test_buchungen_suche_und_schreiben (test_bereiche.BereicheTest.test_buchungen_suche_und_schreiben) ... ok
test_dashboard_jahre_und_verlauf (test_bereiche.BereicheTest.test_dashboard_jahre_und_verlauf) ... ok
test_export_xlsx_und_bericht (test_bereiche.BereicheTest.test_export_xlsx_und_bericht) ... ok
test_fachliche_endpoints_haben_zentrale_dependency 
(test_bereiche.BereicheTest.test_fachliche_endpoints_haben_zentrale_dependency) ... ok
test_fehlendes_bereichsschema_bleibt_kontrolliert_gesperrt 
(test_bereiche.BereicheTest.test_fehlendes_bereichsschema_bleibt_kontrolliert_gesperrt) ... ok
test_fotoauftraege_grenzen (test_bereiche.BereicheTest.test_fotoauftraege_grenzen) ... ok
test_fotoverarbeitung_uebergibt_belegbereich (test_bereiche.BereicheTest.test_fotoverarbeitung_uebergibt_belegbereich) 
... ok
test_gruppen_sind_bereichsgebunden (test_bereiche.BereicheTest.test_gruppen_sind_bereichsgebunden) ... ok
test_kategorien_grenzen (test_bereiche.BereicheTest.test_kategorien_grenzen) ... ok
test_login_ignoriert_unbekannten_bereich_fachlicher_endpoint_nicht 
(test_bereiche.BereicheTest.test_login_ignoriert_unbekannten_bereich_fachlicher_endpoint_nicht) ... ok
test_regeln_und_namensabgleich_der_schnellerfassung 
(test_bereiche.BereicheTest.test_regeln_und_namensabgleich_der_schnellerfassung) ... ok
test_stammdaten_und_bereichsaufloesung (test_bereiche.BereicheTest.test_stammdaten_und_bereichsaufloesung) ... ok
test_upload_dubletten_nur_im_bereich (test_bereiche.BereicheTest.test_upload_dubletten_nur_im_bereich) ... ok
test_account_creation_and_import_reject_foreign_references 
(test_bereiche_import.BereicheImportTest.test_account_creation_and_import_reject_foreign_references) ... ok
test_batch_checks_all_ids_before_first_commit 
(test_bereiche_import.BereicheImportTest.test_batch_checks_all_ids_before_first_commit) ... ok
test_domain_two_rule_and_batch_mutations 
(test_bereiche_import.BereicheImportTest.test_domain_two_rule_and_batch_mutations) ... ok
test_foreign_and_inconsistent_rules_are_not_proposed 
(test_bereiche_import.BereicheImportTest.test_foreign_and_inconsistent_rules_are_not_proposed) ... ok
test_foreign_mutations_are_404_and_do_not_write 
(test_bereiche_import.BereicheImportTest.test_foreign_mutations_are_404_and_do_not_write) ... ok
test_lists_and_foreign_filters (test_bereiche_import.BereicheImportTest.test_lists_and_foreign_filters) ... ok
test_rule_learning_stays_in_domain (test_bereiche_import.BereicheImportTest.test_rule_learning_stays_in_domain) ... ok
test_current_schema_accepts_migration_and_seed_has_separate_domains 
(test_bereiche_migration.BereicheMigrationTest.test_current_schema_accepts_migration_and_seed_has_separate_domains) 
... ok
test_migration_assigns_domains_and_removes_only_foreign_memberships 
(test_bereiche_migration.BereicheMigrationTest.test_migration_assigns_domains_and_removes_only_foreign_memberships) 
... ok
test_schema_and_migration_have_identical_structure 
(test_bereiche_migration.BereicheMigrationTest.test_schema_and_migration_have_identical_structure) ... ok
test_sql_runner_logs_skipped_existing_column 
(test_bereiche_migration.BereicheMigrationTest.test_sql_runner_logs_skipped_existing_column) ... ok
test_sql_runner_preserves_trigger_and_string_semicolons 
(test_bereiche_migration.BereicheMigrationTest.test_sql_runner_preserves_trigger_and_string_semicolons) ... ok
test_sql_runner_rolls_back_fk_failure_and_restores_enforcement 
(test_bereiche_migration.BereicheMigrationTest.test_sql_runner_rolls_back_fk_failure_and_restores_enforcement) ... ok
test_liefert_hoechstens_200_neueste_buchungen 
(test_buchungen_suche.BuchungenSucheApiTest.test_liefert_hoechstens_200_neueste_buchungen) ... ok
test_sucht_case_insensitiv_in_text_notiz_und_kontakt 
(test_buchungen_suche.BuchungenSucheApiTest.test_sucht_case_insensitiv_in_text_notiz_und_kontakt) ... ok
test_alter_fingerabdruck_verhindert_neuen_umsatz 
(test_import_bank.ImportBankApiTest.test_alter_fingerabdruck_verhindert_neuen_umsatz) ... ok
test_dublettenschutz_bei_wiederholtem_import 
(test_import_bank.ImportBankApiTest.test_dublettenschutz_bei_wiederholtem_import) ... ok
test_erfolgreicher_import_mehrerer_umsaetze 
(test_import_bank.ImportBankApiTest.test_erfolgreicher_import_mehrerer_umsaetze) ... ok
test_george_fixture_importiert_alle_zeilen_und_erkennt_spalten 
(test_import_bank.ImportBankApiTest.test_george_fixture_importiert_alle_zeilen_und_erkennt_spalten) ... ok
test_george_identische_zeilen_bleiben_zwei_und_reimport_ist_dubletten 
(test_import_bank.ImportBankApiTest.test_george_identische_zeilen_bleiben_zwei_und_reimport_ist_dubletten) ... ok
test_kaputte_csv_liefert_4xx_statt_500 (test_import_bank.ImportBankApiTest.test_kaputte_csv_liefert_4xx_statt_500) ... 
ok
test_semikolon_beispiel_prueft_und_speichert_saldo 
(test_import_bank.ImportBankApiTest.test_semikolon_beispiel_prueft_und_speichert_saldo) ... ok
test_verbuchen_erzeugt_buchung_und_lernt_regel 
(test_import_bank.ImportBankApiTest.test_verbuchen_erzeugt_buchung_und_lernt_regel) ... ok
test_erkennung_und_utf16 (test_import_bank.ParserTest.test_erkennung_und_utf16) ... ok
test_parse_betrag_cent (test_import_bank.ParserTest.test_parse_betrag_cent) ... ok
test_parse_datum (test_import_bank.ParserTest.test_parse_datum) ... ok
test_datei_ohne_kassabuch_layout_erzeugt_andere_warnung 
(test_import_excel.ImportExcelApiTest.test_datei_ohne_kassabuch_layout_erzeugt_andere_warnung)
Kein Blatt hat eine erkennbare Kopfzeile -> eigener Hinweistext. ... ok
test_dubletten_bei_wiederholtem_einspielen 
(test_import_excel.ImportExcelApiTest.test_dubletten_bei_wiederholtem_einspielen) ... ok
test_einspielen_legt_buchungen_an (test_import_excel.ImportExcelApiTest.test_einspielen_legt_buchungen_an) ... ok
test_leere_vorlage_erzeugt_warnung (test_import_excel.ImportExcelApiTest.test_leere_vorlage_erzeugt_warnung)
Aufgabe 1: eine Datei ohne jede Betragszeile darf nicht stillschweigend ... ok
test_pruefen_aendert_datenbank_nicht (test_import_excel.ImportExcelApiTest.test_pruefen_aendert_datenbank_nicht) ... ok
test_unbekannte_kategorien_werden_gemeldet 
(test_import_excel.ImportExcelApiTest.test_unbekannte_kategorien_werden_gemeldet) ... ok
test_bankomat_storno_und_cursor (test_konten_bewegungen.KontenApiTest.test_bankomat_storno_und_cursor) ... ok
test_bar_anlegen_aendern_loeschen (test_konten_bewegungen.KontenApiTest.test_bar_anlegen_aendern_loeschen) ... ok
test_csv_und_kassa_importverbot (test_konten_bewegungen.KontenApiTest.test_csv_und_kassa_importverbot) ... ok
test_geteilten_import_loeschen_und_transferimport_erhalten 
(test_konten_bewegungen.KontenApiTest.test_geteilten_import_loeschen_und_transferimport_erhalten) ... ok
test_import_verknuepfung_und_vorlaeufige_bewegung 
(test_konten_bewegungen.KontenApiTest.test_import_verknuepfung_und_vorlaeufige_bewegung) ... ok
test_kompatible_barumbuchung_und_storno (test_konten_bewegungen.KontenApiTest.test_kompatible_barumbuchung_und_storno) 
... ok
test_konten_alias_validierung_und_bereich 
(test_konten_bewegungen.KontenApiTest.test_konten_alias_validierung_und_bereich) ... ok
test_notiz_kann_keinen_fremden_transfer_stornieren 
(test_konten_bewegungen.KontenApiTest.test_notiz_kann_keinen_fremden_transfer_stornieren) ... ok
test_put_prueft_erhaltenen_umsatz_und_oeffnet_abgeloesten 
(test_konten_bewegungen.KontenApiTest.test_put_prueft_erhaltenen_umsatz_und_oeffnet_abgeloesten) ... ok
test_unbekannte_zahlung_und_fremdes_konto 
(test_konten_bewegungen.KontenApiTest.test_unbekannte_zahlung_und_fremdes_konto) ... ok
test_bestandskopie_nachzug_und_schema_identisch 
(test_konten_bewegungen.KontenMigrationTest.test_bestandskopie_nachzug_und_schema_identisch) ... ok
test_alte_datenbank_erhaelt_basis_version_und_einmalige_sicherung 
(test_migrate.MigrationTest.test_alte_datenbank_erhaelt_basis_version_und_einmalige_sicherung) ... ok
test_fehlende_sicherung_ist_bei_wegwerf_datenbank_erlaubt 
(test_migrate.MigrationTest.test_fehlende_sicherung_ist_bei_wegwerf_datenbank_erlaubt) ... ok
test_fehlerhafte_migration_rollt_zurueck_und_sperrt_version 
(test_migrate.MigrationTest.test_fehlerhafte_migration_rollt_zurueck_und_sperrt_version) ... ok
test_fehlgeschlagene_pflichtsicherung_stoppt_nachzug 
(test_migrate.MigrationTest.test_fehlgeschlagene_pflichtsicherung_stoppt_nachzug) ... ok
test_migrationsfehler_startet_app_schreibgeschuetzt 
(test_migrate.MigrationTest.test_migrationsfehler_startet_app_schreibgeschuetzt) ... ok
test_neue_datenbank_ist_auf_version_4_ohne_anstehende_migrationen 
(test_migrate.MigrationTest.test_neue_datenbank_ist_auf_version_4_ohne_anstehende_migrationen) ... ok
test_neue_und_alte_datenbank_haben_gleiche_tabellenliste 
(test_migrate.MigrationTest.test_neue_und_alte_datenbank_haben_gleiche_tabellenliste) ... ok
test_schema_endpoint_liefert_erwartete_felder 
(test_migrate.MigrationTest.test_schema_endpoint_liefert_erwartete_felder) ... ok
test_schreibschutz_blockiert_auth_login_nicht 
(test_migrate.MigrationTest.test_schreibschutz_blockiert_auth_login_nicht) ... ok
test_schreibschutz_blockiert_post_aber_nicht_get 
(test_migrate.MigrationTest.test_schreibschutz_blockiert_post_aber_nicht_get) ... ok
test_aktuelles_passwort_ist_fuer_passwortmanager_gekennzeichnet 
(test_password_frontend.PasswordFrontendTest.test_aktuelles_passwort_ist_fuer_passwortmanager_gekennzeichnet) ... ok
test_desktop_navigation_verlinkt_passwortaenderung 
(test_password_frontend.PasswordFrontendTest.test_desktop_navigation_verlinkt_passwortaenderung) ... ok
test_erfolgsmeldung_ist_fokussierbar_und_fuehrt_zur_anmeldung 
(test_password_frontend.PasswordFrontendTest.test_erfolgsmeldung_ist_fokussierbar_und_fuehrt_zur_anmeldung) ... ok
test_kopiermeldung_bleibt_im_sichtbaren_recovery_panel 
(test_password_frontend.PasswordFrontendTest.test_kopiermeldung_bleibt_im_sichtbaren_recovery_panel) ... ok
test_login_verlinkt_passwort_vergessen 
(test_password_frontend.PasswordFrontendTest.test_login_verlinkt_passwort_vergessen) ... ok
test_mehr_menue_verlinkt_passwortaenderung 
(test_password_frontend.PasswordFrontendTest.test_mehr_menue_verlinkt_passwortaenderung) ... ok
test_netzwerkfehler_werden_verstaendlich_angezeigt 
(test_password_frontend.PasswordFrontendTest.test_netzwerkfehler_werden_verstaendlich_angezeigt) ... ok
test_passwortaenderung_sendet_altes_und_neues_passwort 
(test_password_frontend.PasswordFrontendTest.test_passwortaenderung_sendet_altes_und_neues_passwort) ... ok
test_passwortfelder_begrenzen_laenge_und_verwenden_neues_autocomplete 
(test_password_frontend.PasswordFrontendTest.test_passwortfelder_begrenzen_laenge_und_verwenden_neues_autocomplete) 
... ok
test_recovery_code_kann_kopiert_werden 
(test_password_frontend.PasswordFrontendTest.test_recovery_code_kann_kopiert_werden) ... ok
test_recovery_code_wird_nur_in_einem_sicheren_bereich_angeboten 
(test_password_frontend.PasswordFrontendTest.test_recovery_code_wird_nur_in_einem_sicheren_bereich_angeboten) ... ok
test_setup_hat_zwei_passwortfelder_und_recovery_aktionen 
(test_password_frontend.PasswordFrontendTest.test_setup_hat_zwei_passwortfelder_und_recovery_aktionen) ... ok
test_setup_ruft_initial_password_mit_same_origin_credentials_auf 
(test_password_frontend.PasswordFrontendTest.test_setup_ruft_initial_password_mit_same_origin_credentials_auf) ... ok
test_weiter_zur_anmeldung_ist_vollwertige_aktion 
(test_password_frontend.PasswordFrontendTest.test_weiter_zur_anmeldung_ist_vollwertige_aktion) ... ok
test_wiederherstellung_setzt_neues_passwort_und_zeigt_fehler 
(test_password_frontend.PasswordFrontendTest.test_wiederherstellung_setzt_neues_passwort_und_zeigt_fehler) ... ok
test_windows_cleanup_ist_idempotent_und_beendet_den_gestarteten_baum 
(test_process_cleanup.ProcessCleanupTest.test_windows_cleanup_ist_idempotent_und_beendet_den_gestarteten_baum) ... ok
test_manuelles_verbuchen_lernt_regel_und_liefert_vollstaendigen_vorschlag 
(test_regeln.RegelvorschlagApiTest.test_manuelles_verbuchen_lernt_regel_und_liefert_vollstaendigen_vorschlag) ... ok
test_regelverwaltung_und_bulk_uebernahme (test_regeln.RegelvorschlagApiTest.test_regelverwaltung_und_bulk_uebernahme) 
... ok
test_studio_bietet_bulk_uebernahme_und_regelverwaltung 
(test_regeln.RegelvorschlagApiTest.test_studio_bietet_bulk_uebernahme_und_regelverwaltung) ... ok
test_verbuchen_validiert_kategorierichtung_und_umbuchung 
(test_regeln.RegelvorschlagApiTest.test_verbuchen_validiert_kategorierichtung_und_umbuchung) ... ok
test_anker_und_bewegungen_rechnen (test_saldoanker.SaldoankerApiTest.test_anker_und_bewegungen_rechnen) ... ok
test_importalter_und_csv_importanker (test_saldoanker.SaldoankerApiTest.test_importalter_und_csv_importanker) ... ok
test_kassazaehlung_und_buchen (test_saldoanker.SaldoankerApiTest.test_kassazaehlung_und_buchen) ... ok
test_unbekannter_stand_ist_nicht_null (test_saldoanker.SaldoankerApiTest.test_unbekannter_stand_ist_nicht_null) ... ok
test_voranker_warnung_und_bereich (test_saldoanker.SaldoankerApiTest.test_voranker_warnung_und_bereich) ... ok
test_zaehlung_nur_kassa_und_liste (test_saldoanker.SaldoankerApiTest.test_zaehlung_nur_kassa_und_liste) ... ok
test_migration_006_idempotent (test_saldoanker.SaldoankerMigrationTest.test_migration_006_idempotent) ... ok
test_dezimalkomma_bleibt_beim_splitten_erhalten 
(test_schnellerfassung_mehrere.SammeltextErfassungTest.test_dezimalkomma_bleibt_beim_splitten_erhalten) ... ok
test_mehrere_positionen_durch_komma_getrennt 
(test_schnellerfassung_mehrere.SammeltextErfassungTest.test_mehrere_positionen_durch_komma_getrennt) ... ok
test_mehrzeiliger_text_wird_je_zeile_geparst 
(test_schnellerfassung_mehrere.SammeltextErfassungTest.test_mehrzeiliger_text_wird_je_zeile_geparst) ... ok
test_parse_verhaelt_sich_unveraendert 
(test_schnellerfassung_mehrere.SammeltextErfassungTest.test_parse_verhaelt_sich_unveraendert) ... ok
test_autostart_empfiehlt_keine_lan_freigabe 
(test_secure_launchers.SecureLauncherTest.test_autostart_empfiehlt_keine_lan_freigabe) ... ok
test_handy_launcher_oeffnet_nur_private_produktiv_url 
(test_secure_launchers.SecureLauncherTest.test_handy_launcher_oeffnet_nur_private_produktiv_url) ... ok
test_cli_akzeptiert_sechs_zeichen_und_schreibt_neues_format 
(test_set_auth_password.SetAuthPasswordTest.test_cli_akzeptiert_sechs_zeichen_und_schreibt_neues_format) ... ok
test_nur_recovery_code_laesst_passwort_unveraendert 
(test_set_auth_password.SetAuthPasswordTest.test_nur_recovery_code_laesst_passwort_unveraendert) ... ok
test_nur_recovery_code_ohne_bestehende_datei_scheitert_sauber 
(test_set_auth_password.SetAuthPasswordTest.test_nur_recovery_code_ohne_bestehende_datei_scheitert_sauber) ... Keine 
bestehende Auth-Datei unter C:\Users\lblet\AppData\Local\Temp\tmpo6v54ylf\auth.json gefunden. Ohne bestehendes 
Passwort kann kein Recovery-Code erzeugt werden.
ok
test_suchfeld_nutzt_server_suche_mit_debounce_und_normale_leerliste 
(test_studio_suche.StudioSucheTest.test_suchfeld_nutzt_server_suche_mit_debounce_und_normale_leerliste) ... ok
test_betrag_0_oder_negativ_wird_abgelehnt 
(test_umbuchungen.UmbuchungenApiTest.test_betrag_0_oder_negativ_wird_abgelehnt) ... ok
test_gleiche_sparte_wird_abgelehnt (test_umbuchungen.UmbuchungenApiTest.test_gleiche_sparte_wird_abgelehnt) ... ok
test_umbuchung_erzeugt_zwei_gekoppelte_buchungen 
(test_umbuchungen.UmbuchungenApiTest.test_umbuchung_erzeugt_zwei_gekoppelte_buchungen) ... ok
test_umbuchung_ist_erfolgsneutral_im_dashboard 
(test_umbuchungen.UmbuchungenApiTest.test_umbuchung_ist_erfolgsneutral_im_dashboard) ... ok

----------------------------------------------------------------------
Ran 179 tests in 339.665s

OK (skipped=1)
```

Ergebnis: 179 Tests, 0 Fehler, 1 übersprungener plattformabhängiger Test (`POSIX-Dateirechte`). Die im Rohprotokoll enthaltenen Tracebacks stammen aus absichtlich simulierten Backup-/Bildverarbeitungsfehlern und enden jeweils mit `ok`.

## Annahmen

- Der vom Auftrag genannte Interpreterpfad ohne `dev\\` existiert nicht; verwendet wurde der vorhandene äquivalente Pfad unter `C:\\Users\\lblet\\dev\\finanz-dashboard-sparten\\.venv\\Scripts\\python.exe`.
- Der optionale `stichtag` des Stand-Endpunkts verwendet bei Auslassung das lokale Serverdatum; Importalter wird relativ zum abgefragten Stichtag berechnet.
- Ein Anker enthält Bewegungen desselben Tages; gerechnet werden nur Bewegungen mit Datum nach dem Anker bis einschließlich Stichtag.
- Das bisherige Feld `saldo_cent` bleibt als Kompatibilitäts-Rohsaldo erhalten; die fachliche P13-Aussage ist `stand_cent`, das ohne Anker stets `null` ist.
- Eine Kassazählung ohne bekannten Anker wird mit 422 abgelehnt, weil ein erfundener Rechenwert der Fachvorgabe widerspräche.
- Beim Buchen wird die Kategorie `Kassadifferenz` je Sparte bei Bedarf mit Richtung `beides` angelegt; die ausdrücklich übergebene Kategorie wird dennoch fachlich validiert und verwendet.

## Offene Punkte

- Keine P13-Funktionspunkte offen. Der im Auftrag angegebene Interpreterpfad sollte bei einer späteren Ausführung auf die tatsächlich vorhandene Variante mit `dev\\` korrigiert werden.
- Kein PDF-Parser, kein Frontend und keine Änderungen an Auslagen oder sonstigen Buchungen außerhalb der ausdrücklich angeforderten Kassadifferenzbuchung wurden vorgenommen.

Keine Commits und kein Push ausgeführt.

