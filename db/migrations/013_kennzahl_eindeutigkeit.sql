CREATE UNIQUE INDEX IF NOT EXISTS idx_kennzahl_term_eindeutig
    ON kennzahl_term (kennzahl_id, kategorie_id, vorzeichen);
