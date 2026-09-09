CREATE TABLE IF NOT EXISTS bereich (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    kuerzel TEXT NOT NULL UNIQUE,
    typ TEXT NOT NULL CHECK (typ IN ('haupt','verein')),
    aktiv INTEGER NOT NULL DEFAULT 1 CHECK (aktiv IN (0,1)),
    sortierung INTEGER NOT NULL DEFAULT 0
);
INSERT OR IGNORE INTO bereich(id, name, kuerzel, typ, sortierung)
VALUES (1, 'Haupt', 'HAUPT', 'haupt', 10), (2, 'Verein', 'VEREIN', 'verein', 20);

-- Der Runner ueberspringt bereits vorhandene ADD COLUMN-Spalten.
ALTER TABLE sparte ADD COLUMN bereich_id INTEGER NOT NULL DEFAULT 1 REFERENCES bereich(id);
ALTER TABLE bankkonto ADD COLUMN bereich_id INTEGER NOT NULL DEFAULT 1 REFERENCES bereich(id);
ALTER TABLE beleg ADD COLUMN bereich_id INTEGER NOT NULL DEFAULT 1 REFERENCES bereich(id);
ALTER TABLE regel ADD COLUMN bereich_id INTEGER NOT NULL DEFAULT 1 REFERENCES bereich(id);
ALTER TABLE globale_kategoriegruppe ADD COLUMN bereich_id INTEGER NOT NULL DEFAULT 1 REFERENCES bereich(id);
ALTER TABLE auswertungsgruppe ADD COLUMN bereich_id INTEGER NOT NULL DEFAULT 1 REFERENCES bereich(id);

UPDATE sparte SET bereich_id = 2 WHERE typ = 'verein';
UPDATE bankkonto SET bereich_id = (SELECT bereich_id FROM sparte WHERE sparte.id = bankkonto.sparte_id) WHERE sparte_id IS NOT NULL;
UPDATE beleg SET bereich_id = (SELECT bereich_id FROM sparte WHERE sparte.id = beleg.sparte_id) WHERE sparte_id IS NOT NULL;
UPDATE regel SET bereich_id = (SELECT bereich_id FROM sparte WHERE sparte.id = regel.ziel_sparte_id) WHERE ziel_sparte_id IS NOT NULL;

-- Erste Sparte bzw. Kategorie bedeutet kleinste fachliche ID, nicht Einfuegereihenfolge.
UPDATE auswertungsgruppe SET bereich_id = COALESCE((
    SELECT s.bereich_id FROM auswertungsgruppe_sparte x
    JOIN sparte s ON s.id = x.sparte_id
    WHERE x.auswertungsgruppe_id = auswertungsgruppe.id ORDER BY s.id LIMIT 1
), bereich_id);
UPDATE globale_kategoriegruppe SET bereich_id = COALESCE((
    SELECT s.bereich_id FROM kategorie_globalgruppe x
    JOIN kategorie k ON k.id = x.kategorie_id JOIN sparte s ON s.id = k.sparte_id
    WHERE x.globalgruppe_id = globale_kategoriegruppe.id ORDER BY k.id LIMIT 1
), bereich_id);

DELETE FROM auswertungsgruppe_sparte WHERE EXISTS (
    SELECT 1 FROM sparte s JOIN auswertungsgruppe g ON g.id = auswertungsgruppe_sparte.auswertungsgruppe_id
    WHERE s.id = auswertungsgruppe_sparte.sparte_id AND s.bereich_id <> g.bereich_id
);
SELECT 'Entfernte fremde Zuordnungen auswertungsgruppe_sparte: ' || changes();
DELETE FROM kategorie_globalgruppe WHERE EXISTS (
    SELECT 1 FROM kategorie k JOIN sparte s ON s.id = k.sparte_id
    JOIN globale_kategoriegruppe g ON g.id = kategorie_globalgruppe.globalgruppe_id
    WHERE k.id = kategorie_globalgruppe.kategorie_id AND s.bereich_id <> g.bereich_id
);
SELECT 'Entfernte fremde Zuordnungen kategorie_globalgruppe: ' || changes();

CREATE INDEX IF NOT EXISTS idx_sparte_bereich ON sparte (bereich_id);
CREATE INDEX IF NOT EXISTS idx_bankkonto_bereich ON bankkonto (bereich_id);
CREATE INDEX IF NOT EXISTS idx_beleg_bereich ON beleg (bereich_id);
