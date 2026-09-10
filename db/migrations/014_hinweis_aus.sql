CREATE TABLE IF NOT EXISTS hinweis_aus (
    id INTEGER PRIMARY KEY,
    bereich_id INTEGER NOT NULL REFERENCES bereich(id),
    schluessel TEXT NOT NULL,
    bis_wert TEXT,
    erstellt_am TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(bereich_id, schluessel)
);
