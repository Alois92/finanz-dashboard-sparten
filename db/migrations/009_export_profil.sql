CREATE TABLE IF NOT EXISTS export_profil (
    id INTEGER PRIMARY KEY,
    bereich_id INTEGER NOT NULL REFERENCES bereich(id),
    sparte_id INTEGER REFERENCES sparte(id),
    jahr INTEGER NOT NULL,
    name TEXT NOT NULL DEFAULT 'Steuer',
    erstellt_am TEXT NOT NULL DEFAULT (datetime('now')),
    aktualisiert_am TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (bereich_id, sparte_id, jahr, name)
);
CREATE TABLE IF NOT EXISTS export_profil_ausschluss (
    profil_id INTEGER NOT NULL REFERENCES export_profil(id) ON DELETE CASCADE,
    kategorie_id INTEGER REFERENCES kategorie(id),
    buchung_id INTEGER REFERENCES buchung(id),
    CHECK ((kategorie_id IS NULL) <> (buchung_id IS NULL))
);
CREATE INDEX IF NOT EXISTS idx_export_ausschluss_profil ON export_profil_ausschluss (profil_id);
