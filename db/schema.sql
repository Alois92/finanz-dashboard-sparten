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

-- ---------------------------------------------------------------------------
-- Stammdaten: Sparten, Gruppen, Kategorien
-- ---------------------------------------------------------------------------

CREATE TABLE sparte (
    id          INTEGER PRIMARY KEY,
    name        TEXT    NOT NULL,
    kuerzel     TEXT,
    typ         TEXT    NOT NULL CHECK (typ IN ('privat','vermietung','hof','verein','sonstiges')),
    geschuetzt  INTEGER NOT NULL DEFAULT 0 CHECK (geschuetzt IN (0,1)),  -- 1 = Verein
    aktiv       INTEGER NOT NULL DEFAULT 1 CHECK (aktiv IN (0,1)),
    farbe       TEXT,
    sortierung  INTEGER NOT NULL DEFAULT 0
);

-- Buendelt Sparten, z. B. "Vermietung gesamt"
CREATE TABLE auswertungsgruppe (
    id          INTEGER PRIMARY KEY,
    name        TEXT    NOT NULL,
    beschreibung TEXT,
    farbe       TEXT,
    aktiv       INTEGER NOT NULL DEFAULT 1 CHECK (aktiv IN (0,1))
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
    aktiv       INTEGER NOT NULL DEFAULT 1 CHECK (aktiv IN (0,1))
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
    aktiv       INTEGER NOT NULL DEFAULT 1 CHECK (aktiv IN (0,1))
);

CREATE TABLE import_batch (
    id             INTEGER PRIMARY KEY,
    bankkonto_id   INTEGER NOT NULL REFERENCES bankkonto(id),
    dateiname      TEXT,
    importiert_am  TEXT    NOT NULL DEFAULT (datetime('now')),
    anzahl_zeilen  INTEGER,
    anzahl_neu     INTEGER,
    anzahl_dubletten INTEGER,
    quelle         TEXT
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
    steuer_notiz    TEXT
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
    notiz             TEXT
);

-- n:m Buchung <-> Beleg
CREATE TABLE buchung_beleg (
    buchung_id  INTEGER NOT NULL REFERENCES buchung(id) ON DELETE CASCADE,
    beleg_id    INTEGER NOT NULL REFERENCES beleg(id) ON DELETE CASCADE,
    PRIMARY KEY (buchung_id, beleg_id)
);

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
    ziel_tag_id            INTEGER REFERENCES tag(id)
);

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
    CASE WHEN b.typ = 'umbuchung' THEN 1 ELSE 0 END AS ist_transfer
FROM buchungszeile bz
JOIN buchung b ON b.id = bz.buchung_id;

-- Nur echte Einnahmen/Ausgaben (Transfers raus) - Basis fuer Dashboards.
CREATE VIEW v_einnahmen_ausgaben AS
SELECT * FROM v_zeile WHERE ist_transfer = 0;

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
