-- ============================================================================
-- Finanz-Dashboard Sparten 2026 - SQLite-Schema
-- Abgeleitet aus Projektkonzept_Finanz_Dashboard_Sparten_2026.md (Abschnitt 11)
--
-- Grundregeln:
--   * Alle Geldbetraege als Ganzzahl in Cent (..._cent INTEGER), niemals Float.
--   * Waehrung im MVP immer EUR (nicht gespeichert).
--   * Bankumsatz -> buchung (Kopf) -> buchungszeile (Split je Kategorie).
--   * Umbuchungen (typ='umbuchung') werden aus E/A-Auswertungen herausgerechnet.
--   * Status-Felder eindeutig benannt: buchungsstatus, belegstatus, importstatus.
--   * Verein = geschuetzte Sparte, spaeter abtrennbar.
--
-- Konvention Vorzeichen:
--   * bankumsatz.betrag_cent  : SIGNED (wie von der Bank, negativ = Abgang)
--   * buchung.betrag_cent     : positive Magnitude; Richtung ergibt sich aus typ
--   * buchungszeile.betrag_cent: positive Magnitude
-- ============================================================================

PRAGMA foreign_keys = ON;
-- Kein WAL: Standard-Journal (DELETE) funktioniert auch auf Netzlaufwerken (SMB).
-- Einzelnutzer-Betrieb, daher kein WAL noetig.

CREATE TABLE schema_version (
    version        INTEGER PRIMARY KEY,
    name           TEXT    NOT NULL,
    angewendet_am  TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- ---------------------------------------------------------------------------
-- Stammdaten: Sparten, Gruppen, Kategorien
-- ---------------------------------------------------------------------------

CREATE TABLE bereich (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    kuerzel TEXT NOT NULL UNIQUE,
    typ TEXT NOT NULL CHECK (typ IN ('haupt','verein')),
    aktiv INTEGER NOT NULL DEFAULT 1 CHECK (aktiv IN (0,1)),
    sortierung INTEGER NOT NULL DEFAULT 0
);
INSERT OR IGNORE INTO bereich(id, name, kuerzel, typ, sortierung)
VALUES (1, 'Haupt', 'HAUPT', 'haupt', 10), (2, 'Verein', 'VEREIN', 'verein', 20);

CREATE TABLE sparte (
    id          INTEGER PRIMARY KEY,
    name        TEXT    NOT NULL,
    kuerzel     TEXT,
    typ         TEXT    NOT NULL CHECK (typ IN ('privat','vermietung','hof','verein','sonstiges')),
    geschuetzt  INTEGER NOT NULL DEFAULT 0 CHECK (geschuetzt IN (0,1)),  -- 1 = Verein
    aktiv       INTEGER NOT NULL DEFAULT 1 CHECK (aktiv IN (0,1)),
    farbe       TEXT,
    sortierung  INTEGER NOT NULL DEFAULT 0,
    bereich_id INTEGER NOT NULL DEFAULT 1 REFERENCES bereich(id)
);

-- Buendelt Sparten, z. B. "Vermietung gesamt"
CREATE TABLE auswertungsgruppe (
    id          INTEGER PRIMARY KEY,
    name        TEXT    NOT NULL,
    beschreibung TEXT,
    farbe       TEXT,
    aktiv       INTEGER NOT NULL DEFAULT 1 CHECK (aktiv IN (0,1)),
    bereich_id INTEGER NOT NULL DEFAULT 1 REFERENCES bereich(id)
);

CREATE TABLE auswertungsgruppe_sparte (
    auswertungsgruppe_id INTEGER NOT NULL REFERENCES auswertungsgruppe(id) ON DELETE CASCADE,
    sparte_id            INTEGER NOT NULL REFERENCES sparte(id) ON DELETE CASCADE,
    PRIMARY KEY (auswertungsgruppe_id, sparte_id)
);

-- Buendelt Kategorien spartenuebergreifend, z. B. "Versicherungen"
CREATE TABLE globale_kategoriegruppe (
    id          INTEGER PRIMARY KEY,
    name        TEXT    NOT NULL,
    beschreibung TEXT,
    farbe       TEXT,
    aktiv       INTEGER NOT NULL DEFAULT 1 CHECK (aktiv IN (0,1)),
    bereich_id INTEGER NOT NULL DEFAULT 1 REFERENCES bereich(id)
);

CREATE TABLE kategorie (
    id          INTEGER PRIMARY KEY,
    sparte_id   INTEGER NOT NULL REFERENCES sparte(id),
    parent_id   INTEGER REFERENCES kategorie(id),  -- Haupt-/Unter-/Detailkategorie
    name        TEXT    NOT NULL,
    richtung    TEXT    NOT NULL CHECK (richtung IN ('einnahme','ausgabe','beides')),
    aktiv       INTEGER NOT NULL DEFAULT 1 CHECK (aktiv IN (0,1)),
    sortierung  INTEGER NOT NULL DEFAULT 0
);

-- n:m - eine Kategorie kann in mehreren globalen Gruppen sein
CREATE TABLE kategorie_globalgruppe (
    kategorie_id   INTEGER NOT NULL REFERENCES kategorie(id) ON DELETE CASCADE,
    globalgruppe_id INTEGER NOT NULL REFERENCES globale_kategoriegruppe(id) ON DELETE CASCADE,
    PRIMARY KEY (kategorie_id, globalgruppe_id)
);

-- ---------------------------------------------------------------------------
-- Kontakte, Personen, Tags
-- ---------------------------------------------------------------------------

CREATE TABLE kontakt (
    id          INTEGER PRIMARY KEY,
    name        TEXT    NOT NULL,
    typ         TEXT    NOT NULL DEFAULT 'sonstiges'
                    CHECK (typ IN ('lieferant','mieter','mitglied','sonstiges')),
    iban        TEXT,
    notiz       TEXT,
    aktiv       INTEGER NOT NULL DEFAULT 1 CHECK (aktiv IN (0,1))
);

CREATE TABLE person (
    id          INTEGER PRIMARY KEY,
    name        TEXT    NOT NULL,
    aktiv       INTEGER NOT NULL DEFAULT 1 CHECK (aktiv IN (0,1))
);

CREATE TABLE tag (
    id          INTEGER PRIMARY KEY,
    name        TEXT    NOT NULL UNIQUE,
    farbe       TEXT
);

-- ---------------------------------------------------------------------------
-- Bank: Konten, Importlaeufe, Umsaetze
-- ---------------------------------------------------------------------------

CREATE TABLE bankkonto (
    id          INTEGER PRIMARY KEY,
    sparte_id   INTEGER REFERENCES sparte(id),  -- leer = gemischt genutzt
    inhaber     TEXT,
    name        TEXT    NOT NULL,
    iban        TEXT,
    bank        TEXT,
    aktiv       INTEGER NOT NULL DEFAULT 1 CHECK (aktiv IN (0,1)),
    bereich_id INTEGER NOT NULL DEFAULT 1 REFERENCES bereich(id),
    art TEXT NOT NULL DEFAULT 'bank' CHECK (art IN ('bank','karte','kassa','depot','wallet')),
    waehrung TEXT NOT NULL DEFAULT 'EUR',
    kartenendnummer TEXT,
    sortierung INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE import_batch (
    id             INTEGER PRIMARY KEY,
    bankkonto_id   INTEGER NOT NULL REFERENCES bankkonto(id),
    dateiname      TEXT,
    importiert_am  TEXT    NOT NULL DEFAULT (datetime('now')),
    anzahl_zeilen  INTEGER,
    anzahl_neu     INTEGER,
    anzahl_dubletten INTEGER,
    quelle         TEXT,
    dateihash       TEXT,
    parser_version  INTEGER NOT NULL DEFAULT 2,
    zeitraum_von    TEXT,
    zeitraum_bis    TEXT,
    anzahl_ungueltig INTEGER
);

CREATE TABLE bankumsatz (
    id                INTEGER PRIMARY KEY,
    bankkonto_id      INTEGER NOT NULL REFERENCES bankkonto(id),
    import_batch_id   INTEGER REFERENCES import_batch(id),
    datum             TEXT    NOT NULL,          -- ISO 8601 (YYYY-MM-DD)
    valuta            TEXT,
    betrag_cent       INTEGER NOT NULL,          -- SIGNED (negativ = Abgang)
    saldo_nachher_cent INTEGER,                  -- fuer Kontostand-Abgleich
    text              TEXT,
    gegenpartei       TEXT,
    iban_gegenpartei  TEXT,
    import_hash       TEXT    NOT NULL,          -- Dublettenerkennung, je Konto eindeutig
    importstatus      TEXT    NOT NULL DEFAULT 'offen'
                          CHECK (importstatus IN ('offen','verbucht','ignoriert')),
    UNIQUE (bankkonto_id, import_hash)
);

-- ---------------------------------------------------------------------------
-- Buchungen: Kopf + Zeilen (Split), Belege, Tags
-- ---------------------------------------------------------------------------

CREATE TABLE buchung (
    id                INTEGER PRIMARY KEY,
    sparte_id         INTEGER NOT NULL REFERENCES sparte(id),
    datum             TEXT    NOT NULL,          -- ISO 8601
    typ               TEXT    NOT NULL CHECK (typ IN ('einnahme','ausgabe','umbuchung')),
    betrag_cent       INTEGER NOT NULL DEFAULT 0 CHECK (betrag_cent >= 0),  -- = SUM(zeilen)
    kontakt_id        INTEGER REFERENCES kontakt(id),
    person_id         INTEGER REFERENCES person(id),
    bankkonto_id      INTEGER REFERENCES bankkonto(id),
    bankumsatz_id     INTEGER REFERENCES bankumsatz(id),
    zahlungsart       TEXT    NOT NULL DEFAULT 'bank'
                          CHECK (zahlungsart IN ('bar','bank','karte','sonstiges')),
    transfer_gruppe_id TEXT,                     -- verknuepft Abgang+Zugang einer Umbuchung
    belegstatus       TEXT    NOT NULL DEFAULT 'beleg_fehlt'
                          CHECK (belegstatus IN ('kein_beleg_noetig','beleg_fehlt',
                                                 'beleg_vorhanden','eigenbeleg','beleg_unklar')),
    buchungsstatus    TEXT    NOT NULL DEFAULT 'offen'
                          CHECK (buchungsstatus IN ('offen','zugeordnet','bestaetigt')),
    text              TEXT,
    notiz             TEXT,
    erstellt_am       TEXT    NOT NULL DEFAULT (datetime('now')),
    geaendert_am      TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE buchungszeile (
    id              INTEGER PRIMARY KEY,
    buchung_id      INTEGER NOT NULL REFERENCES buchung(id) ON DELETE CASCADE,
    kategorie_id    INTEGER NOT NULL REFERENCES kategorie(id),
    betrag_cent     INTEGER NOT NULL CHECK (betrag_cent >= 0),
    notiz           TEXT,
    -- Steuer-Felder: im MVP leer, spaeter fuer Vermietung/Bauernhof-Export
    brutto_cent     INTEGER,
    netto_cent      INTEGER,
    ust_cent        INTEGER,
    ust_satz        REAL,
    steuer_relevant INTEGER NOT NULL DEFAULT 0 CHECK (steuer_relevant IN (0,1)),
    steuer_notiz    TEXT,
    neutral         INTEGER NOT NULL DEFAULT 0 CHECK (neutral IN (0,1))
);

CREATE TABLE beleg (
    id                INTEGER PRIMARY KEY,
    -- sparte_id optional: ein Beleg kann zuerst ohne Sparte im Eingangskorb
    -- landen und spaeter zugeordnet werden.
    sparte_id         INTEGER REFERENCES sparte(id),
    kontakt_id        INTEGER REFERENCES kontakt(id),  -- erkannter Lieferant
    dateiname         TEXT    NOT NULL,
    pfad              TEXT    NOT NULL,
    sha256_hash       TEXT,
    belegdatum        TEXT,
    betrag_erkannt_cent INTEGER,
    notiz             TEXT,
    bereich_id INTEGER NOT NULL DEFAULT 1 REFERENCES bereich(id)
);

-- n:m Buchung <-> Beleg
CREATE TABLE buchung_beleg (
    buchung_id  INTEGER NOT NULL REFERENCES buchung(id) ON DELETE CASCADE,
    beleg_id    INTEGER NOT NULL REFERENCES beleg(id) ON DELETE CASCADE,
    PRIMARY KEY (buchung_id, beleg_id)
);

CREATE TABLE export_profil (
    id INTEGER PRIMARY KEY,
    bereich_id INTEGER NOT NULL REFERENCES bereich(id),
    sparte_id INTEGER REFERENCES sparte(id),
    jahr INTEGER NOT NULL,
    name TEXT NOT NULL DEFAULT 'Steuer',
    erstellt_am TEXT NOT NULL DEFAULT (datetime('now')),
    aktualisiert_am TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (bereich_id, sparte_id, jahr, name)
);

CREATE TABLE export_profil_ausschluss (
    profil_id INTEGER NOT NULL REFERENCES export_profil(id) ON DELETE CASCADE,
    kategorie_id INTEGER REFERENCES kategorie(id),
    buchung_id INTEGER REFERENCES buchung(id),
    CHECK ((kategorie_id IS NULL) <> (buchung_id IS NULL))
);

CREATE INDEX idx_export_ausschluss_profil ON export_profil_ausschluss (profil_id);

CREATE TABLE buchung_tag (
    buchung_id  INTEGER NOT NULL REFERENCES buchung(id) ON DELETE CASCADE,
    tag_id      INTEGER NOT NULL REFERENCES tag(id) ON DELETE CASCADE,
    PRIMARY KEY (buchung_id, tag_id)
);

-- ---------------------------------------------------------------------------
-- Regeln (ab Phase 2; machen nur Vorschlaege)
-- ---------------------------------------------------------------------------

CREATE TABLE regel (
    id                     INTEGER PRIMARY KEY,
    name                   TEXT    NOT NULL,
    aktiv                  INTEGER NOT NULL DEFAULT 1 CHECK (aktiv IN (0,1)),
    prioritaet             INTEGER NOT NULL DEFAULT 100,
    bedingung_text         TEXT,
    bedingung_betrag_von_cent INTEGER,
    bedingung_betrag_bis_cent INTEGER,
    bankkonto_id           INTEGER REFERENCES bankkonto(id),
    ziel_sparte_id         INTEGER REFERENCES sparte(id),
    ziel_kategorie_id      INTEGER REFERENCES kategorie(id),
    ziel_typ               TEXT    CHECK (ziel_typ IN ('einnahme','ausgabe','umbuchung')),
    ziel_tag_id            INTEGER REFERENCES tag(id),
    bereich_id INTEGER NOT NULL DEFAULT 1 REFERENCES bereich(id),
    quelle TEXT NOT NULL DEFAULT 'gelernt' CHECK (quelle IN ('gelernt','stichwort','manuell')),
    auto_verbuchen INTEGER NOT NULL DEFAULT 0 CHECK (auto_verbuchen IN (0,1)),
    eingabe_sparte_id INTEGER REFERENCES sparte(id),
    gelernt_aus_buchung_id INTEGER REFERENCES buchung(id) ON DELETE SET NULL,
    erstellt_am TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE kennzahl (
    id INTEGER PRIMARY KEY,
    sparte_id INTEGER NOT NULL REFERENCES sparte(id),
    name TEXT NOT NULL,
    sortierung INTEGER NOT NULL DEFAULT 0,
    aktiv INTEGER NOT NULL DEFAULT 1 CHECK (aktiv IN (0,1))
);

CREATE TABLE kennzahl_term (
    id INTEGER PRIMARY KEY,
    kennzahl_id INTEGER NOT NULL REFERENCES kennzahl(id) ON DELETE CASCADE,
    kategorie_id INTEGER NOT NULL REFERENCES kategorie(id),
    messgroesse TEXT NOT NULL CHECK (messgroesse IN ('einnahmen','ausgaben','netto')),
    vorzeichen INTEGER NOT NULL CHECK (vorzeichen IN (1,-1))
);

CREATE INDEX idx_kennzahl_sparte ON kennzahl(sparte_id);
CREATE INDEX idx_kennzahl_term_kennzahl ON kennzahl_term(kennzahl_id);

-- ---------------------------------------------------------------------------
-- Beleg-Auswertung (ab Phase 4; lokale Foto-Auswertung via Ollama)
-- ---------------------------------------------------------------------------

CREATE TABLE beleg_auswertung (
    id             INTEGER PRIMARY KEY,
    beleg_id       INTEGER NOT NULL REFERENCES beleg(id) ON DELETE CASCADE,
    status         TEXT    NOT NULL DEFAULT 'offen'
                       CHECK (status IN ('offen','laeuft','fertig','fehler',
                                        'verbucht','verworfen')),
    ergebnis_json  TEXT,
    fehler         TEXT,
    versuche       INTEGER NOT NULL DEFAULT 0,
    erstellt       TEXT    NOT NULL DEFAULT (datetime('now')),
    aktualisiert   TEXT
);

CREATE INDEX idx_beleg_auswertung_status ON beleg_auswertung (status);
CREATE INDEX idx_beleg_auswertung_beleg  ON beleg_auswertung (beleg_id);

-- ---------------------------------------------------------------------------
-- Indizes fuer haeufige Filter (Zeitraum, Sparte, Kategorie)
-- ---------------------------------------------------------------------------

CREATE INDEX idx_buchung_sparte_datum  ON buchung (sparte_id, datum);
CREATE INDEX idx_buchung_datum         ON buchung (datum);
CREATE INDEX idx_buchung_typ           ON buchung (typ);
CREATE INDEX idx_buchung_bankumsatz    ON buchung (bankumsatz_id);
CREATE INDEX idx_buchung_transfer      ON buchung (transfer_gruppe_id);
CREATE INDEX idx_zeile_buchung         ON buchungszeile (buchung_id);
CREATE INDEX idx_zeile_kategorie       ON buchungszeile (kategorie_id);
CREATE INDEX idx_bankumsatz_konto_datum ON bankumsatz (bankkonto_id, datum);
CREATE INDEX idx_kategorie_sparte       ON kategorie (sparte_id);

-- ---------------------------------------------------------------------------
-- Views: Auswertungsbasis (Umbuchungen ausgeblendet)
-- ---------------------------------------------------------------------------

-- Eine Zeile je Buchungszeile mit vorzeichenbehaftetem Betrag.
-- Umbuchungen sind ENTHALTEN, aber ueber ist_transfer=1 erkennbar und
-- werden in v_einnahmen_ausgaben herausgefiltert.
CREATE VIEW v_zeile AS
SELECT
    bz.id            AS zeile_id,
    b.id             AS buchung_id,
    b.sparte_id      AS sparte_id,
    b.datum          AS datum,
    b.typ            AS typ,
    CASE b.typ WHEN 'ausgabe' THEN -bz.betrag_cent ELSE bz.betrag_cent END AS betrag_signed_cent,
    bz.betrag_cent   AS betrag_cent,
    bz.kategorie_id  AS kategorie_id,
    bz.neutral       AS neutral,
    CASE WHEN b.typ = 'umbuchung' THEN 1 ELSE 0 END AS ist_transfer
FROM buchungszeile bz
JOIN buchung b ON b.id = bz.buchung_id;

-- Nur echte Einnahmen/Ausgaben (Transfers raus) - Basis fuer Dashboards.
CREATE VIEW v_einnahmen_ausgaben AS
SELECT * FROM v_zeile WHERE ist_transfer = 0 AND neutral = 0;

-- ---------------------------------------------------------------------------
-- Trigger: geaendert_am pflegen; Kopfbetrag aus Zeilen aktuell halten
-- ---------------------------------------------------------------------------

CREATE TRIGGER trg_buchung_touch
AFTER UPDATE ON buchung
FOR EACH ROW
BEGIN
    UPDATE buchung SET geaendert_am = datetime('now') WHERE id = NEW.id;
END;

CREATE TRIGGER trg_zeile_ai AFTER INSERT ON buchungszeile
BEGIN
    UPDATE buchung
       SET betrag_cent = (SELECT COALESCE(SUM(betrag_cent),0) FROM buchungszeile WHERE buchung_id = NEW.buchung_id)
     WHERE id = NEW.buchung_id;
END;

CREATE TRIGGER trg_zeile_au AFTER UPDATE ON buchungszeile
BEGIN
    UPDATE buchung
       SET betrag_cent = (SELECT COALESCE(SUM(betrag_cent),0) FROM buchungszeile WHERE buchung_id = NEW.buchung_id)
     WHERE id = NEW.buchung_id;
END;

CREATE TRIGGER trg_zeile_ad AFTER DELETE ON buchungszeile
BEGIN
    UPDATE buchung
       SET betrag_cent = (SELECT COALESCE(SUM(betrag_cent),0) FROM buchungszeile WHERE buchung_id = OLD.buchung_id)
     WHERE id = OLD.buchung_id;
END;

CREATE INDEX idx_sparte_bereich ON sparte (bereich_id);
CREATE INDEX idx_bankkonto_bereich ON bankkonto (bereich_id);
CREATE INDEX idx_beleg_bereich ON beleg (bereich_id);

-- P11: Geldbewegungen getrennt von Kostenbuchungen.

CREATE TABLE transfer (
    id INTEGER PRIMARY KEY,
    art TEXT NOT NULL CHECK (art IN ('bankomat','umbuchung','ausgleich','kartenabrechnung','sonstig')),
    von_konto_id INTEGER REFERENCES bankkonto(id),
    nach_konto_id INTEGER REFERENCES bankkonto(id),
    datum TEXT NOT NULL,
    betrag_cent INTEGER NOT NULL CHECK (betrag_cent > 0),
    notiz TEXT,
    storniert_am TEXT,
    erstellt_am TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE bewegung (
    id INTEGER PRIMARY KEY,
    konto_id INTEGER NOT NULL REFERENCES bankkonto(id),
    datum TEXT NOT NULL,
    valuta TEXT,
    betrag_signed_cent INTEGER NOT NULL,
    waehrung TEXT NOT NULL DEFAULT 'EUR',
    art TEXT NOT NULL DEFAULT 'zahlung' CHECK (art IN ('zahlung','transfer','gebuehr','zins','trade')),
    transfer_id INTEGER REFERENCES transfer(id),
    bankumsatz_id INTEGER UNIQUE REFERENCES bankumsatz(id),
    text TEXT,
    gegenpartei TEXT,
    quelle TEXT NOT NULL CHECK (quelle IN ('manuell','import','ausgleich','kredit','nachzug')),
    storniert_am TEXT,
    erstellt_am TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE buchung_bewegung (
    buchung_id INTEGER NOT NULL REFERENCES buchung(id) ON DELETE CASCADE,
    bewegung_id INTEGER NOT NULL REFERENCES bewegung(id) ON DELETE CASCADE,
    anteil_signed_cent INTEGER NOT NULL,
    PRIMARY KEY (buchung_id, bewegung_id)
);
CREATE INDEX idx_bewegung_konto_datum ON bewegung (konto_id, datum);
CREATE INDEX idx_bewegung_transfer ON bewegung (transfer_id);
CREATE INDEX idx_buchung_bewegung_bewegung ON buchung_bewegung (bewegung_id);

-- P13: Tagesendstaende und Kassazaehlungen.
CREATE TABLE kontostand_anker (
    id          INTEGER PRIMARY KEY,
    konto_id    INTEGER NOT NULL REFERENCES bankkonto(id),
    stichtag    TEXT NOT NULL,
    saldo_cent  INTEGER NOT NULL,
    quelle      TEXT NOT NULL CHECK (quelle IN ('auszug','manuell','import')),
    beleg_id    INTEGER REFERENCES beleg(id),
    notiz       TEXT,
    erstellt_am TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (konto_id, stichtag)
);
CREATE TABLE kassazaehlung (
    id             INTEGER PRIMARY KEY,
    konto_id       INTEGER NOT NULL REFERENCES bankkonto(id),
    datum          TEXT NOT NULL,
    gerechnet_cent INTEGER NOT NULL,
    gezaehlt_cent  INTEGER NOT NULL,
    differenz_cent INTEGER NOT NULL,
    status         TEXT NOT NULL DEFAULT 'offen' CHECK (status IN ('offen','geklaert')),
    notiz          TEXT,
    buchung_id     INTEGER REFERENCES buchung(id),
    erstellt_am    TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_kontostand_anker_konto_stichtag ON kontostand_anker (konto_id, stichtag);
CREATE INDEX idx_kassazaehlung_konto_datum ON kassazaehlung (konto_id, datum);
-- P12: Auslagen, Ausgleich und wiederholbare Geldaktionen.
ALTER TABLE buchung ADD COLUMN version INTEGER NOT NULL DEFAULT 1;
ALTER TABLE buchung ADD COLUMN client_request_id TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS idx_buchung_client_request
    ON buchung (client_request_id) WHERE client_request_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS auslage (
    id INTEGER PRIMARY KEY,
    buchung_id INTEGER NOT NULL UNIQUE REFERENCES buchung(id) ON DELETE CASCADE,
    zahler_sparte_id INTEGER NOT NULL REFERENCES sparte(id),
    zahler_konto_id INTEGER REFERENCES bankkonto(id),
    betrag_cent INTEGER NOT NULL CHECK (betrag_cent > 0),
    erstellt_am TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS ausgleich (
    id INTEGER PRIMARY KEY,
    transfer_id INTEGER NOT NULL REFERENCES transfer(id),
    datum TEXT NOT NULL,
    von_sparte_id INTEGER NOT NULL REFERENCES sparte(id),
    nach_sparte_id INTEGER NOT NULL REFERENCES sparte(id),
    betrag_cent INTEGER NOT NULL CHECK (betrag_cent > 0),
    zahlungsart TEXT NOT NULL CHECK (zahlungsart IN ('bar','bank')),
    client_request_id TEXT UNIQUE,
    aufgehoben_am TEXT,
    notiz TEXT,
    erstellt_am TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS ausgleich_zuordnung (
    ausgleich_id INTEGER NOT NULL REFERENCES ausgleich(id) ON DELETE CASCADE,
    auslage_id INTEGER NOT NULL REFERENCES auslage(id) ON DELETE CASCADE,
    betrag_cent INTEGER NOT NULL CHECK (betrag_cent > 0),
    PRIMARY KEY (ausgleich_id, auslage_id)
);
CREATE INDEX IF NOT EXISTS idx_auslage_zahler ON auslage (zahler_sparte_id);

-- Technische Wiederholungsdaten bleiben auch nach Änderung/Rücknahme erhalten.
CREATE TABLE IF NOT EXISTS request_wiederholung (
    art TEXT NOT NULL CHECK (art IN ('buchung','ausgleich')),
    client_request_id TEXT NOT NULL,
    bereich_id INTEGER NOT NULL REFERENCES bereich(id),
    nutzdaten_hash TEXT NOT NULL,
    antwort_json TEXT NOT NULL,
    PRIMARY KEY (art, client_request_id)
);
-- P14: Kredite mit getrennten Zins- und neutralen Tilgungszeilen.
CREATE TABLE kredit (
    id                 INTEGER PRIMARY KEY,
    sparte_id          INTEGER NOT NULL REFERENCES sparte(id),
    konto_id           INTEGER REFERENCES bankkonto(id),
    name               TEXT NOT NULL,
    monatsrate_cent    INTEGER NOT NULL CHECK (monatsrate_cent > 0),
    zinssatz           REAL,
    beginn             TEXT NOT NULL,
    kategorie_zins_id  INTEGER NOT NULL REFERENCES kategorie(id),
    kategorie_rate_id  INTEGER NOT NULL REFERENCES kategorie(id),
    aktiv              INTEGER NOT NULL DEFAULT 1 CHECK (aktiv IN (0,1))
);

CREATE TABLE kredit_jahr (
    kredit_id        INTEGER NOT NULL REFERENCES kredit(id) ON DELETE CASCADE,
    jahr             INTEGER NOT NULL,
    zins_cent        INTEGER NOT NULL,
    restschuld_cent  INTEGER,
    status           TEXT NOT NULL CHECK (status IN ('geschaetzt','bestaetigt')),
    beleg_id         INTEGER REFERENCES beleg(id),
    aktualisiert_am  TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (kredit_id, jahr)
);
CREATE INDEX idx_kredit_sparte ON kredit (sparte_id);
CREATE INDEX idx_kredit_jahr_jahr ON kredit_jahr (kredit_id, jahr);

-- P12: Dauerhaftes Protokoll fuer nicht eindeutig aufgeloeste Nachzugsfaelle.
CREATE TABLE migrationsprotokoll (
    id INTEGER PRIMARY KEY,
    version INTEGER NOT NULL,
    zeitpunkt TEXT NOT NULL DEFAULT (datetime('now')),
    art TEXT NOT NULL,
    objektkennung TEXT NOT NULL,
    hinweis TEXT NOT NULL,
    UNIQUE (version, art, objektkennung)
);
CREATE INDEX idx_migrationsprotokoll_zeitpunkt ON migrationsprotokoll (zeitpunkt, id);
