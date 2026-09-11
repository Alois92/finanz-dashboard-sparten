-- P50b: Historie je Buchung. P43b: eigener Wiederholungs-Topf fuer die Foto-Uebernahme.

-- IF NOT EXISTS: dieselbe Vorsichtsmassnahme wie bei auslage/ausgleich/request_wiederholung
-- in schema.sql - die Migration muss auch gegen ein bereits aus schema.sql frisch angelegtes
-- Schema (mit nur teilweise nachgezogenem schema_version) fehlerfrei laufen (siehe
-- test_bereiche_migration.py/test_kredit.py, alle_markieren() in app/migrate.py).
CREATE TABLE IF NOT EXISTS buchung_aenderung (
    id          INTEGER PRIMARY KEY,
    buchung_id  INTEGER NOT NULL REFERENCES buchung(id) ON DELETE CASCADE,
    zeitpunkt   TEXT NOT NULL DEFAULT (datetime('now')),
    feld        TEXT NOT NULL,
    alt         TEXT,
    neu         TEXT,
    grund       TEXT,
    quelle      TEXT
);
CREATE INDEX IF NOT EXISTS idx_buchung_aenderung_buchung ON buchung_aenderung (buchung_id, zeitpunkt);

-- request_wiederholung.art bekommt einen eigenen Wert fuer die Foto-Uebernahme (P43b),
-- statt sich den 'buchung'-Topf mit der normalen Erfassung zu teilen. SQLite kennt kein
-- ALTER TABLE ... ALTER CHECK, daher Tabelle mit neuer CHECK-Liste neu anlegen und Daten
-- uebernehmen (gleiches Muster wie bei den Views in Migration 017).
ALTER TABLE request_wiederholung RENAME TO request_wiederholung_alt016;

CREATE TABLE request_wiederholung (
    art TEXT NOT NULL CHECK (art IN ('buchung','ausgleich','beleg_uebernahme')),
    client_request_id TEXT NOT NULL,
    bereich_id INTEGER NOT NULL REFERENCES bereich(id),
    nutzdaten_hash TEXT NOT NULL,
    antwort_json TEXT NOT NULL,
    PRIMARY KEY (art, client_request_id)
);

INSERT INTO request_wiederholung(art, client_request_id, bereich_id, nutzdaten_hash, antwort_json)
SELECT art, client_request_id, bereich_id, nutzdaten_hash, antwort_json FROM request_wiederholung_alt016;

DROP TABLE request_wiederholung_alt016;
