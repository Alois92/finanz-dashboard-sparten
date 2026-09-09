# P11 – Konten, Bewegungen und Transfers, Runde 1

**Ergebnis:** P11 umgesetzt. Gesamtsuite: 172 Tests in 262,269 Sekunden, 0 Fehler, 0 Fehlschläge, 1 vorhandener Windows-/POSIX-Skip. Doppelter Nachzug: `[4]`, danach `[]`, Bestandsdaten unverändert.

Arbeitsverzeichnis: `C:\Users\lblet\dev\wt-p11`, Branch `pkt/p11-konten-bewegungen`.
Grundlage: vollständige Auftragskarte `docs/neubau/pakete/P11-konten-bewegungen.md`, Architektur insbesondere Abschnitte 3, 4 und 13, P10-Bereichshelfer und die dort genannten Router/Tests. Keine Commits, kein Push, keine Änderungen an Hauptklon oder `wt-p15`.

## Umsetzung und Dateien

Der Umsetzungsablauf war: Bestandsstruktur und Referenzen prüfen; Migration und Schema abgleichen; gemeinsame Bewegungslogik und bereichsgebundene Endpunkte ergänzen; Buchung/Import/Transfer integrieren; Regressionen und unabhängigen Review bearbeiten; Bestandsprobe zweimal ausführen; gesamte Testsuite und Bericht abschließen.

| Datei | Änderung |
| --- | --- |
| `db/migrations/004_konten_bewegungen.py` (neu) | Führt idempotente Konto-DDL und die Bestandsübertragung einschließlich Kassen, Import-/Barbewegungen, Buchungsverknüpfungen, Transfers und fallbezogenem Log innerhalb der Runner-Transaktion aus. |
| `db/schema.sql` | Ergänzt exakt die vier Kontospalten, drei Tabellen und drei Indizes der Auftragskarte. |
| `app/bewegungen.py` (neu) | Bündelt Kassaauflösung, Importbewegung, Synchronisierung, Transfererzeugung, Bereichsprüfung verknüpfter Bewegungen und differenziertes Stornieren. |
| `app/routers/konten.py` (neu) | Implementiert Kontenverwaltung, Bankkonten-Alias, paginierte Bewegungen, manuelle Bewegungen, Transfers und Kontostand. |
| `app/main.py` | Registriert den Kontenrouter unter `/api` ohne globale Bereichsdependency. |
| `app/schemas.py` | Ergänzt die optionale `bankumsatz_id` zur ausdrücklichen Zuordnung einer Buchung zu einem Import. |
| `app/routers/buchungen.py` | Synchronisiert Bewegungen bei POST/PUT/DELETE, erstellt kompatible Umbuchungstransfers und liefert den Zahlungsstatus einschließlich „Zahlung unbekannt“. |
| `app/routers/import_bank.py` | Erzeugt die Importbewegung beim CSV-Einlesen, verknüpft beim Verbuchen und weist Kassenkonten für CSV zurück. |
| `app/routers/import_excel.py` | Synchronisiert importierte Barbuchungen innerhalb der vorhandenen Importtransaktion mit der Kassa. |
| `tests/test_konten_bewegungen.py` (neu, vorhandenen unversionierten Entwurf erweitert) | Prüft Migration, Kontenschema, Bestände, Buchungslebenszyklus, CSV, Transfers, Cursor, Bereichsgrenzen und die Review-Regressionen über echtes Schema und echte ASGI-Endpunkte. |
| `tests/fixtures/schema_p10.sql` (neu, vorhandene unversionierte Datei übernommen) | Bewahrt das ursprüngliche vollständige P10-Schema als echte Bestandsfixture; Textidentität mit `git show HEAD:db/schema.sql` wurde geprüft. |
| `tests/test_import_bank.py` | Bereinigt Bewegungen und Transfers vor Umsätzen und Konten entsprechend der tatsächlichen Fremdschlüsselstruktur. |
| `tests/test_import_excel.py` | Prüft zusätzlich die signierten Kassa-Bewegungen nach dem Einspielen. |
| `tests/test_regeln.py` | Aktualisiert die Fixture-Bereinigung für die neuen referenzierenden Tabellen. |
| `tests/test_migrate.py` | Erwartet Schema-Version 4 einschließlich ihres Namens und der unveränderten allgemeinen Runner-Semantik. |
| `tests/test_bereiche_migration.py` | Bildet beim Rückbau das echte ältere Schema ohne P11-Spalten nach und prüft zusätzlich die Bereichszuordnung der nachgezogenen Kassen. |
| `scripts/p11_nachzug_probe.py` (neu) | Erstellt die verlangte synthetische Bestandsdatenbank aus P10-Schema und aktuellem Seed, sichert sie und beweist beide Runner-Läufe sowie Daten- und Summengleichheit. |
| `docs/neubau/berichte/P11-runde1.md` (neu) | Dokumentiert Änderungen, Bereichsprüfungen, Entscheidungen und vollständige Prüfnachweise. |

`app/migrate.py`, Authentifizierung, Abhängigkeiten und Frontend sind unverändert. Keine Saldoanker, Kassazählungen, Auslagen oder Kategorienumdeutungen wurden eingeführt.

## Endpunkte und Bereichsprüfung

Alle unten genannten Datenendpunkte lösen den angefragten Bereich über `BereichDep` / `bereich_dep` auf (Standard 1); ungültige/inaktive Bereiche werden abgewiesen. Die Dependency wurde nicht an `/api/auth/*`, `/api/health`, `/api/schema` oder `/api/betrieb/status` gehängt.

| Endpunkt | Bereichsprüfung |
| --- | --- |
| `GET /api/konten` | SQL-Filter `bankkonto.bereich_id = bereich.id`. |
| `POST /api/konten` | Bereich wird serverseitig gesetzt; optionale Sparte mit `pruefe_sparte`. |
| `PATCH /api/konten/{id}` | Konto mit `pruefe_konto`, neue/beibehaltene Sparte mit `pruefe_sparte`. |
| `GET /api/konten/{id}/bewegungen?von=&bis=&limit=100&cursor=` | Konto mit `pruefe_konto`, danach ausschließlich Bewegungen dieses Kontos. |
| `GET /api/konten/{id}/stand` | Konto mit `pruefe_konto`, Summe ausschließlich seiner nicht stornierten Bewegungen. |
| `POST /api/bewegungen` | Konto mit `pruefe_konto`; Währung aus dem Konto, Quelle stets `manuell`. |
| `POST /api/transfers` | Beide Konten mit `pruefe_konto`; keine bereichsübergreifenden Transfers. |
| `DELETE /api/transfers/{id}` | `pruefe_transfer` prüft beide Konten und alle zugehörigen Bewegungs-/Umsatzreferenzen mit P10-Helfern; bei historisch unbekannten Konten erfolgt die Bereichszuordnung über die zugehörigen Umbuchungsbuchungen. |
| `GET, POST /api/bankkonten` | Dieselben Routerfunktionen, Antworten und Prüfungen wie `/api/konten`. |
| `POST, PUT, DELETE /api/buchungen` (erweitert) | Bestehende Sparten-/Kategorie-/Buchungs-/Belegprüfung bleibt; Konto, Umsatz und bereits verknüpfte Bewegungen/Transfers werden zusätzlich mit P10-Helfern geprüft, einschließlich erhaltener PUT-Felder und gekoppelter Löschung. |
| `POST /api/umbuchungen` (erweitert) | Beide Sparten und alle explizit oder automatisch bestimmten Konten mit P10-Helfern; bestehende Ablehnung identischer Sparten bleibt, Bankomat innerhalb einer Sparte läuft über `/api/transfers`. |
| `POST /api/import/csv`, `POST /api/bankumsaetze/{id}/verbuchen`, `POST /api/import/excel` (erweitert) | Vorhandene Bereichsprüfungen bleiben; gemeinsame Bewegungsfunktionen prüfen referenzierte Konten, Sparten und Umsätze erneut. |

Bewegungslisten sortieren nach Datum und ID absteigend; Cursor enthält dieses Paar, Datumfilter und Limit werden validiert. Stornierte Bewegungen bleiben sichtbar. Unbekannte Bank-/Kartenzahlungen erhalten in Buchungsliste, Suche und Detail `zahlungsstatus: "Zahlung unbekannt"`; aktive Verknüpfungen erhalten `verknuepft`.

## Annahmen und begründete Entscheidungen

1. **Eine Datei für Version 004:** SQL ist in `004_konten_bewegungen.py` eingebettet. Der vorhandene allgemeine Runner lehnt zwei Dateien derselben Versionsnummer ab; die Auftragskarte erlaubt die Python-Migration für SQL plus Datenübertragung. Es gibt deshalb keine zusätzliche gleichnummerierte SQL-Datei und keine Runner-Sonderbehandlung.
2. **Richtung alter Umbuchungen:** Der abgenommene Erzeuger in P10 schreibt zuerst die abgehende, dann die eingehende Buchung. Nachzug verwendet daher die aufsteigende Buchungs-ID. Ungültige Gruppen (nicht genau zwei Buchungen, abweichende Beträge/Datumswerte oder Betrag nicht positiv) werden protokolliert, ohne Betrag/Datum zu erfinden.
3. **Unbekannte Konten:** Fehlt bei einem historischen Paar eine eindeutige Kontoreferenz, bleiben beide Transferkonten NULL und die Notiz enthält „Konten ungeklärt“; es entstehen keine erfundenen Kontobewegungen. Der Gruppenbezug wird in einer internen Notiz festgehalten, weil die verbindliche Transfertabelle keine zusätzliche Gruppen-ID vorsieht.
4. **Kompatible neue Umbuchungen:** Alte Aufrufer ohne Kontofelder bleiben zulässig. Bei Bankzahlung wird nur genau ein aktives Bankkonto je Sparte automatisch gewählt, sonst entsteht ein ausdrücklich ungeklärter Transfer. Optional stehen `zahlungsart`, `von_konto_id` und `nach_konto_id` zur eindeutigen Auswahl zur Verfügung; bei bar wird die jeweilige Kassa verwendet.
5. **Neue/leere Sparten:** Kassen entstehen beim Nachzug je aktiver Sparte und bei Bedarf beim ersten Barvorgang einer neuen Sparte. Historische Barbuchungen einer inaktiven Sparte ohne eindeutige Kassa bleiben ungeklärt und werden mit IDs im Log genannt.
6. **Importabgleich:** Eine ausdrückliche PUT-Zuordnung mit `bankumsatz_id` ersetzt die vorläufige Verknüpfung und storniert die bisherige manuelle Bewegung; kein heuristischer Abgleich anhand gleicher Beträge oder Texte. Die importierte Bewegung wird genau einmal gespeichert. Buchungslöschung erhält importierte Bewegungen auch bei historischen Transfers; ausdrückliche Transferstornierung setzt dagegen den Storno an Transfer und seinen Bewegungen.
7. **Geteilte Importzuordnung:** Mehrere Buchungen dürfen eine Importbewegung anteilig referenzieren. Lösen/Löschen öffnet den Umsatz erst wieder, wenn keine Buchung mehr auf ihn verweist. Die n:m-Tabelle und signierten Anteile bleiben maßgeblich.
8. **Kontoverwaltung:** Der Alias liefert genau dieselbe Kontenliste, einschließlich Aktivkennzeichen. Standardart ist aus Kompatibilitätsgründen `bank`, Standardwährung `EUR`; Kassa ohne Sparte wird mit 422, eine zweite Kassa derselben Sparte mit 409 abgewiesen. Art/Währung/Sparte eines Kontos mit Bewegungen dürfen nicht nachträglich wechseln (409), damit bestehende Bewegungen nicht umgedeutet werden.
9. **Transfers:** Neue Transfers brauchen zwei verschiedene Konten derselben Währung; Währungsumrechnung ist nicht spezifiziert. Manuelle `art='transfer'`-Einzelbewegungen werden an `/api/transfers` verwiesen, damit Transfers stets zwei Gegenbewegungen haben.
10. **Weitere Bar-Erfassung:** Excel-Kassabücher erzeugen bereits Barbuchungen; diese vorhandene Schreibroute wurde deshalb ebenfalls synchronisiert, ohne das Importformat zu verändern.
11. **Testumgebung:** Python 3.12 legt in dieser Windows-Ausführungsumgebung `TemporaryDirectory` mit Modus 0700 an, worauf selbst Dateierzeugung und Cleanup mit Zugriff-verweigert scheitern. Ausschließlich im Prüflauf-Bootstrap wird `os.mkdir` mit Modus 0777/vererbten Windows-Rechten aufgerufen. Testdaten bleiben unter `C:\Users\lblet\AppData\Local\Temp`; keine Änderung an Produktcode, Auth oder Validierung. Ein ursprünglicher Lauf hat den Infrastrukturfehler nachgewiesen; der korrigierte Bootstrap lässt dieselben Tests unverändert ausführen.

## Review und gezielte Verifikation

Die unabhängige Prüfung fand vier konkrete Fehlerpfade: fehlende Excel-Kassa-Bewegungen, Stornierung eines fremden Transfers über eine kollidierende frei gesetzte Notiz, Storno importierter Bewegungen beim Löschen historischer Umbuchungen und zu frühes Öffnen eines noch zugeordneten Bankumsatzes. Alle vier wurden korrigiert und durch Regressionen abgedeckt. Zusätzliche Tests prüfen erhaltene PUT-Referenzen und die explizite Ablösung eines Imports.

Der gezielte Lauf über P11, Migration, P10-Nachzug, Bankimport, Excelimport und Regeln ergab 48 Tests ohne Fehler. Die Bestandsfixture wird in `TemporaryDirectory()` kopiert; Tabellen, Spalten, Fremdschlüssel und Indizes werden gegen das neue Schema verglichen. Neben dem zweiten Runner-Lauf wird auch `up(con)` unmittelbar erneut aufgerufen und gegen den vollständigen SQL-Dump geprüft. `git diff --check` meldete keine Whitespacefehler.

## Bestandsprobe

Die verlangte Datei `C:\Users\lblet\AppData\Local\Temp\p11-bestand.db` wurde selbst erzeugt; es wurde keine Produktionsdatenbank verwendet. Ausgangsschema ist die textidentische Kopie des beim Arbeitsbeginn aktuellen `db/schema.sql` aus P10, dazu das unveränderte aktuelle `db/seed.sql`. Zwei synthetische zusätzliche Sparten, zwei Bankkonten, drei Umsätze und neun Buchungen decken die geforderten Fälle ab. Die Sicherung liegt daneben als `p11-bestand-vorher.db`.

Die Probe vergleicht sämtliche ursprünglichen Zeilen und Spalten von Buchungen, Zeilen, Umsätzen, Konten, Sparten und Kategorien, die Summen je Sparte/Jahr/Typ sowie den vollständigen SQL-Dump nach Lauf 1 gegen Lauf 2. Das Skript überschreibt keine vorhandene Datenbank.

## Offene Punkte

Keine fachlichen P11-Restarbeiten offen. Historisch ungeklärte Konten/Zahlungen bleiben absichtlich ungeklärt und werden ausgewiesen; Anfangsstände, Saldoanker, Kassazählung, Auslagen und Frontend gehören zu den ausdrücklich ausgeschlossenen Folgepaketen. Der vorhandene Test für POSIX-Dateirechte ist unter Windows plattformbedingt übersprungen; Authentifizierungstests selbst werden vollständig ausgeführt.

## Vollständiges Protokoll der doppelten Bestandsprobe

```text
Ausgangsdatenbank: aktuelles P10-schema.sql (Fixture) + db/seed.sql, synthetische Ergänzungen
Datenbank: C:\Users\lblet\AppData\Local\Temp\p11-bestand.db
Vorher: {'buchung': 9, 'buchungszeile': 9, 'bankumsatz': 3, 'bankkonto': 2, 'sparte': 8, 'kategorie': 2}
DB-Sicherung vor Schema-Nachzug: C:\Users\lblet\AppData\Local\Temp\p11-bestand-vorher.db
Migration 004: Kassen=8, Bewegungen=7, Transfers=2, ungeklärte Transfers=1, ungeklärte Barbuchungen=0
Migration 004: Zahlung unbekannt: Anzahl=1; Buchungs-IDs=[9]; Barbuchungs-IDs=[]
Erster Runner-Lauf: [4]
Zweiter Runner-Lauf: []
Vollständiger SQL-Dump nach Lauf 1 und 2 identisch; SHA256: 96d4f8d8d24e8196f4160ee78577a40907da0907a5d245dd106fd90e6d0c4f73
Alle ursprünglichen Zeilen und Spalten unverändert; Summen je Sparte/Jahr/Typ: [(7, '2026', 'ausgabe', 190), (7, '2026', 'einnahme', 200), (7, '2026', 'umbuchung', 160), (8, '2026', 'einnahme', 80), (8, '2026', 'umbuchung', 160)]
Nachzug: {'bewegung': 7, 'transfer': 2, 'buchung_bewegung': 6}
Kontosummen: [(1, 330), (2, 70), (9, -50), (10, 80)]
Fremdschlüsselprüfung: fehlerfrei; Status: {'aktuell': 4, 'anstehend': [], 'basis': False}
```

## Reproduktion des Testlaufs

Interpreter: `C:\Users\lblet\dev\finanz-dashboard-sparten\.venv\Scripts\python.exe`, Arbeitsverzeichnis dieser Worktree. Der folgende Bootstrap wurde per PowerShell-Here-String an den Interpreter übergeben (vollständige Suite, kein Filter, kein zusätzlicher Skip):

```python
import os, unittest, sys
original = os.mkdir

def mkdir(path, mode=0o777, *, dir_fd=None):
    return original(path, 0o777, dir_fd=dir_fd)

os.mkdir = mkdir
result = unittest.TextTestRunner(verbosity=2).run(
    unittest.defaultTestLoader.discover("tests")
)
sys.exit(not result.wasSuccessful())
```

Vorher wurde `FINANZ_DB=C:\Users\lblet\AppData\Local\Temp\p11-final-suite.db` gesetzt. Die tatsächliche Protokollierung leitet stdout und stderr gemeinsam in eine UTF-8-Datei im Temp-Verzeichnis um und übernimmt deren vollständigen Inhalt unten. Erwartete Fehlerlogs aus absichtlich simulierten Backup-/Bildfehlern sind Bestandteil der Testausgabe und keine fehlgeschlagenen Tests.

## Vollständige Ausgabe der abschließenden Gesamtsuite

```text
FINANZ_DB=C:/Users/lblet/AppData/Local/Temp/p11-final-suite.db
Interpreter=C:\Users\lblet\dev\finanz-dashboard-sparten\.venv\Scripts\python.exe
Arbeitsverzeichnis=C:\Users\lblet\dev\wt-p11
unittest discover -s tests -v; Temp-Verzeichnisse mit vererbten Windows-Rechten im Testprozess
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
  File "C:\Users\lblet\dev\wt-p11\app\backup.py", line 262, in sichere_datenbank
    quelle.backup(kopie)
  File "C:\Users\lblet\dev\wt-p11\tests\test_backup.py", line 231, in backup
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
  File "<stdin>", line 4, in mkdir
PermissionError: [WinError 5] Zugriff verweigert: '\\\\kein-host-xyz-existiert\\share\\backup'

During handling of the above exception, another exception occurred:

Traceback (most recent call last):
  File "C:\Users\lblet\dev\wt-p11\app\backup.py", line 292, in _sichere_auf_zweitziel
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
  File "C:\Users\lblet\dev\wt-p11\app\auswertung.py", line 108, in _lade_bild_base64
    bild = Image.open(io.BytesIO(roh))
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "C:\Users\lblet\dev\finanz-dashboard-sparten\.venv\Lib\site-packages\PIL\Image.py", line 3532, in open
    raise UnidentifiedImageError(msg)
PIL.UnidentifiedImageError: cannot identify image file <_io.BytesIO object at 0x00000299C8DDDB20>
ok
test_auftrag_anlegen_und_dedupe (test_beleg_auswertung.BelegAuswertungTest.test_auftrag_anlegen_und_dedupe) ... ok
test_brutto_mit_mwst_je_position (test_beleg_auswertung.BelegAuswertungTest.test_brutto_mit_mwst_je_position) ... Bild-Verkleinerung fehlgeschlagen - sende Original
Traceback (most recent call last):
  File "C:\Users\lblet\dev\wt-p11\app\auswertung.py", line 108, in _lade_bild_base64
    bild = Image.open(io.BytesIO(roh))
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "C:\Users\lblet\dev\finanz-dashboard-sparten\.venv\Lib\site-packages\PIL\Image.py", line 3532, in open
    raise UnidentifiedImageError(msg)
PIL.UnidentifiedImageError: cannot identify image file <_io.BytesIO object at 0x00000299CA2A7150>
ok
test_brutto_proportional_ohne_mwst (test_beleg_auswertung.BelegAuswertungTest.test_brutto_proportional_ohne_mwst) ... Bild-Verkleinerung fehlgeschlagen - sende Original
Traceback (most recent call last):
  File "C:\Users\lblet\dev\wt-p11\app\auswertung.py", line 108, in _lade_bild_base64
    bild = Image.open(io.BytesIO(roh))
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "C:\Users\lblet\dev\finanz-dashboard-sparten\.venv\Lib\site-packages\PIL\Image.py", line 3532, in open
    raise UnidentifiedImageError(msg)
PIL.UnidentifiedImageError: cannot identify image file <_io.BytesIO object at 0x00000299CA2A7380>
ok
test_ollama_nicht_erreichbar_bleibt_offen (test_beleg_auswertung.BelegAuswertungTest.test_ollama_nicht_erreichbar_bleibt_offen) ... Bild-Verkleinerung fehlgeschlagen - sende Original
Traceback (most recent call last):
  File "C:\Users\lblet\dev\wt-p11\app\auswertung.py", line 108, in _lade_bild_base64
    bild = Image.open(io.BytesIO(roh))
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "C:\Users\lblet\dev\finanz-dashboard-sparten\.venv\Lib\site-packages\PIL\Image.py", line 3532, in open
    raise UnidentifiedImageError(msg)
PIL.UnidentifiedImageError: cannot identify image file <_io.BytesIO object at 0x00000299CA2A7560>
ok
test_rabatt_wird_mitskaliert (test_beleg_auswertung.BelegAuswertungTest.test_rabatt_wird_mitskaliert) ... Bild-Verkleinerung fehlgeschlagen - sende Original
Traceback (most recent call last):
  File "C:\Users\lblet\dev\wt-p11\app\auswertung.py", line 108, in _lade_bild_base64
    bild = Image.open(io.BytesIO(roh))
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "C:\Users\lblet\dev\finanz-dashboard-sparten\.venv\Lib\site-packages\PIL\Image.py", line 3532, in open
    raise UnidentifiedImageError(msg)
PIL.UnidentifiedImageError: cannot identify image file <_io.BytesIO object at 0x00000299CA2A7BA0>
ok
test_status_endpoint_erlaubt_nur_verworfen_oder_verbucht (test_beleg_auswertung.BelegAuswertungTest.test_status_endpoint_erlaubt_nur_verworfen_oder_verbucht) ... ok
test_stimmige_bruttosumme_unveraendert (test_beleg_auswertung.BelegAuswertungTest.test_stimmige_bruttosumme_unveraendert) ... Bild-Verkleinerung fehlgeschlagen - sende Original
Traceback (most recent call last):
  File "C:\Users\lblet\dev\wt-p11\app\auswertung.py", line 108, in _lade_bild_base64
    bild = Image.open(io.BytesIO(roh))
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "C:\Users\lblet\dev\finanz-dashboard-sparten\.venv\Lib\site-packages\PIL\Image.py", line 3532, in open
    raise UnidentifiedImageError(msg)
PIL.UnidentifiedImageError: cannot identify image file <_io.BytesIO object at 0x00000299CA2A7DD0>
ok
test_verarbeitung_gemockt_setzt_fertig_und_mapped_kategorie (test_beleg_auswertung.BelegAuswertungTest.test_verarbeitung_gemockt_setzt_fertig_und_mapped_kategorie) ... Bild-Verkleinerung fehlgeschlagen - sende Original
Traceback (most recent call last):
  File "C:\Users\lblet\dev\wt-p11\app\auswertung.py", line 108, in _lade_bild_base64
    bild = Image.open(io.BytesIO(roh))
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "C:\Users\lblet\dev\finanz-dashboard-sparten\.venv\Lib\site-packages\PIL\Image.py", line 3532, in open
    raise UnidentifiedImageError(msg)
PIL.UnidentifiedImageError: cannot identify image file <_io.BytesIO object at 0x00000299CA2A7FB0>
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
test_neue_datenbank_ist_auf_version_4_ohne_anstehende_migrationen (test_migrate.MigrationTest.test_neue_datenbank_ist_auf_version_4_ohne_anstehende_migrationen) ... ok
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
test_nur_recovery_code_ohne_bestehende_datei_scheitert_sauber (test_set_auth_password.SetAuthPasswordTest.test_nur_recovery_code_ohne_bestehende_datei_scheitert_sauber) ... Keine bestehende Auth-Datei unter C:\Users\lblet\AppData\Local\Temp\tmpkg_grx4m\auth.json gefunden. Ohne bestehendes Passwort kann kein Recovery-Code erzeugt werden.
ok
test_suchfeld_nutzt_server_suche_mit_debounce_und_normale_leerliste (test_studio_suche.StudioSucheTest.test_suchfeld_nutzt_server_suche_mit_debounce_und_normale_leerliste) ... ok
test_betrag_0_oder_negativ_wird_abgelehnt (test_umbuchungen.UmbuchungenApiTest.test_betrag_0_oder_negativ_wird_abgelehnt) ... ok
test_gleiche_sparte_wird_abgelehnt (test_umbuchungen.UmbuchungenApiTest.test_gleiche_sparte_wird_abgelehnt) ... ok
test_umbuchung_erzeugt_zwei_gekoppelte_buchungen (test_umbuchungen.UmbuchungenApiTest.test_umbuchung_erzeugt_zwei_gekoppelte_buchungen) ... ok
test_umbuchung_ist_erfolgsneutral_im_dashboard (test_umbuchungen.UmbuchungenApiTest.test_umbuchung_ist_erfolgsneutral_im_dashboard) ... ok

----------------------------------------------------------------------
Ran 172 tests in 262.269s

OK (skipped=1)
```
