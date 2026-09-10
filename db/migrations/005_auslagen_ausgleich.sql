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
