ALTER TABLE buchung ADD COLUMN kredit_id INTEGER REFERENCES kredit(id);

CREATE INDEX IF NOT EXISTS idx_buchung_kredit ON buchung (kredit_id);

UPDATE buchung
SET kredit_id = CAST(substr(notiz, 12) AS INTEGER)
WHERE notiz LIKE 'Kreditrate:%'
  AND substr(notiz, 12) <> ''
  AND substr(notiz, 12) NOT GLOB '*[^0-9]*'
  AND EXISTS (
      SELECT 1 FROM kredit k
      WHERE k.id = CAST(substr(notiz, 12) AS INTEGER)
  );

INSERT OR IGNORE INTO migrationsprotokoll(version, art, objektkennung, hinweis)
SELECT 15,
       'kreditrate_ungeklaert',
       'buchung:' || b.id,
       'Buchung ' || b.id || ': Kreditrate verweist auf nicht vorhandenen Kredit.'
FROM buchung b
WHERE b.notiz LIKE 'Kreditrate:%'
  AND substr(b.notiz, 12) <> ''
  AND substr(b.notiz, 12) NOT GLOB '*[^0-9]*'
  AND NOT EXISTS (
      SELECT 1 FROM kredit k
      WHERE k.id = CAST(substr(b.notiz, 12) AS INTEGER)
  );
