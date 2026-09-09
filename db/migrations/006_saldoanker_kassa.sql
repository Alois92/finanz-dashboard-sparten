CREATE TABLE IF NOT EXISTS kontostand_anker (
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

CREATE TABLE IF NOT EXISTS kassazaehlung (
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

CREATE INDEX IF NOT EXISTS idx_kontostand_anker_konto_stichtag
    ON kontostand_anker (konto_id, stichtag);
CREATE INDEX IF NOT EXISTS idx_kassazaehlung_konto_datum
    ON kassazaehlung (konto_id, datum);
