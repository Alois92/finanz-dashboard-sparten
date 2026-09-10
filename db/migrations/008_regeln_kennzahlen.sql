ALTER TABLE regel ADD COLUMN quelle TEXT NOT NULL DEFAULT 'gelernt' CHECK (quelle IN ('gelernt','stichwort','manuell'));
ALTER TABLE regel ADD COLUMN auto_verbuchen INTEGER NOT NULL DEFAULT 0 CHECK (auto_verbuchen IN (0,1));
ALTER TABLE regel ADD COLUMN eingabe_sparte_id INTEGER REFERENCES sparte(id);
ALTER TABLE regel ADD COLUMN gelernt_aus_buchung_id INTEGER REFERENCES buchung(id) ON DELETE SET NULL;
-- ADD COLUMN erlaubt auf gefuellten Tabellen keinen dynamischen Default.
-- Zwischenwert ergaenzen und die Tabelle in derselben Migration neu aufbauen;
-- vorhandene Zeitstempel bleiben auch bei erneutem Nachzug erhalten.
ALTER TABLE regel ADD COLUMN erstellt_am TEXT NOT NULL DEFAULT '';
CREATE TABLE regel_p15_neu (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    aktiv INTEGER NOT NULL DEFAULT 1 CHECK (aktiv IN (0,1)),
    prioritaet INTEGER NOT NULL DEFAULT 100,
    bedingung_text TEXT,
    bedingung_betrag_von_cent INTEGER,
    bedingung_betrag_bis_cent INTEGER,
    bankkonto_id INTEGER REFERENCES bankkonto(id),
    ziel_sparte_id INTEGER REFERENCES sparte(id),
    ziel_kategorie_id INTEGER REFERENCES kategorie(id),
    ziel_typ TEXT CHECK (ziel_typ IN ('einnahme','ausgabe','umbuchung')),
    ziel_tag_id INTEGER REFERENCES tag(id),
    bereich_id INTEGER NOT NULL DEFAULT 1 REFERENCES bereich(id),
    quelle TEXT NOT NULL DEFAULT 'gelernt' CHECK (quelle IN ('gelernt','stichwort','manuell')),
    auto_verbuchen INTEGER NOT NULL DEFAULT 0 CHECK (auto_verbuchen IN (0,1)),
    eingabe_sparte_id INTEGER REFERENCES sparte(id),
    gelernt_aus_buchung_id INTEGER REFERENCES buchung(id) ON DELETE SET NULL,
    erstellt_am TEXT NOT NULL DEFAULT (datetime('now'))
);
INSERT INTO regel_p15_neu (
    id, name, aktiv, prioritaet, bedingung_text,
    bedingung_betrag_von_cent, bedingung_betrag_bis_cent, bankkonto_id,
    ziel_sparte_id, ziel_kategorie_id, ziel_typ, ziel_tag_id, bereich_id,
    quelle, auto_verbuchen, eingabe_sparte_id, gelernt_aus_buchung_id, erstellt_am
)
SELECT id, name, aktiv, prioritaet, bedingung_text,
    bedingung_betrag_von_cent, bedingung_betrag_bis_cent, bankkonto_id,
    ziel_sparte_id, ziel_kategorie_id, ziel_typ, ziel_tag_id, bereich_id,
    quelle, auto_verbuchen, eingabe_sparte_id, gelernt_aus_buchung_id,
    COALESCE(NULLIF(erstellt_am, ''), datetime('now'))
FROM regel;
DROP TABLE regel;
ALTER TABLE regel_p15_neu RENAME TO regel;
-- Bestandsregeln bleiben Vorschlaege. Automatik wird nur ueber eine
-- ausdrueckliche Freigabe der einzelnen Regel aktiviert.
UPDATE regel SET auto_verbuchen = 0 WHERE quelle = 'gelernt';

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
