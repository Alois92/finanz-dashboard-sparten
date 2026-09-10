ALTER TABLE regel ADD COLUMN quelle TEXT NOT NULL DEFAULT 'gelernt' CHECK (quelle IN ('gelernt','stichwort','manuell'));
ALTER TABLE regel ADD COLUMN auto_verbuchen INTEGER NOT NULL DEFAULT 0 CHECK (auto_verbuchen IN (0,1));
ALTER TABLE regel ADD COLUMN eingabe_sparte_id INTEGER REFERENCES sparte(id);
ALTER TABLE regel ADD COLUMN gelernt_aus_buchung_id INTEGER REFERENCES buchung(id);
ALTER TABLE regel ADD COLUMN erstellt_am TEXT NOT NULL DEFAULT (datetime('now'));
UPDATE regel SET auto_verbuchen = 1 WHERE quelle = 'gelernt';

CREATE TABLE IF NOT EXISTS kennzahl (
    id INTEGER PRIMARY KEY,
    sparte_id INTEGER NOT NULL REFERENCES sparte(id),
    name TEXT NOT NULL,
    sortierung INTEGER NOT NULL DEFAULT 0,
    aktiv INTEGER NOT NULL DEFAULT 1 CHECK (aktiv IN (0,1))
);

CREATE TABLE IF NOT EXISTS kennzahl_term (
    id INTEGER PRIMARY KEY,
    kennzahl_id INTEGER NOT NULL REFERENCES kennzahl(id) ON DELETE CASCADE,
    kategorie_id INTEGER NOT NULL REFERENCES kategorie(id),
    messgroesse TEXT NOT NULL CHECK (messgroesse IN ('einnahmen','ausgaben','netto')),
    vorzeichen INTEGER NOT NULL CHECK (vorzeichen IN (1,-1))
);

CREATE INDEX IF NOT EXISTS idx_kennzahl_sparte ON kennzahl(sparte_id);
CREATE INDEX IF NOT EXISTS idx_kennzahl_term_kennzahl ON kennzahl_term(kennzahl_id);
