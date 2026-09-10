-- Bestandsregeln ohne Buchungszuordnung und mit Namen stammen nachvollziehbar
-- aus manueller Pflege; Automatik bleibt dabei deaktiviert.
UPDATE regel
SET quelle = 'manuell', auto_verbuchen = 0
WHERE gelernt_aus_buchung_id IS NULL
  AND trim(name) <> '';
