ALTER TABLE buchungszeile ADD COLUMN neutral INTEGER NOT NULL DEFAULT 0 CHECK (neutral IN (0,1));

DROP VIEW IF EXISTS v_einnahmen_ausgaben;
DROP VIEW IF EXISTS v_zeile;

CREATE VIEW v_zeile AS
SELECT
    bz.id AS zeile_id,
    b.id AS buchung_id,
    b.sparte_id AS sparte_id,
    b.datum AS datum,
    b.typ AS typ,
    CASE b.typ WHEN 'ausgabe' THEN -bz.betrag_cent ELSE bz.betrag_cent END AS betrag_signed_cent,
    bz.betrag_cent AS betrag_cent,
    bz.kategorie_id AS kategorie_id,
    bz.neutral AS neutral,
    CASE WHEN b.typ = 'umbuchung' THEN 1 ELSE 0 END AS ist_transfer
FROM buchungszeile bz
JOIN buchung b ON b.id = bz.buchung_id;

CREATE VIEW v_einnahmen_ausgaben AS
SELECT * FROM v_zeile WHERE ist_transfer = 0 AND neutral = 0;

CREATE TABLE IF NOT EXISTS kredit (
    id INTEGER PRIMARY KEY,
    sparte_id INTEGER NOT NULL REFERENCES sparte(id),
    konto_id INTEGER REFERENCES bankkonto(id),
    name TEXT NOT NULL,
    monatsrate_cent INTEGER NOT NULL CHECK (monatsrate_cent > 0),
    zinssatz REAL,
    beginn TEXT NOT NULL,
    kategorie_zins_id INTEGER NOT NULL REFERENCES kategorie(id),
    kategorie_rate_id INTEGER NOT NULL REFERENCES kategorie(id),
    aktiv INTEGER NOT NULL DEFAULT 1 CHECK (aktiv IN (0,1))
);

CREATE TABLE IF NOT EXISTS kredit_jahr (
    kredit_id INTEGER NOT NULL REFERENCES kredit(id) ON DELETE CASCADE,
    jahr INTEGER NOT NULL,
    zins_cent INTEGER NOT NULL,
    restschuld_cent INTEGER,
    status TEXT NOT NULL CHECK (status IN ('geschaetzt','bestaetigt')),
    beleg_id INTEGER REFERENCES beleg(id),
    aktualisiert_am TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (kredit_id, jahr)
);

CREATE INDEX IF NOT EXISTS idx_kredit_sparte ON kredit(sparte_id);
CREATE INDEX IF NOT EXISTS idx_kredit_jahr_jahr ON kredit_jahr(kredit_id, jahr);
