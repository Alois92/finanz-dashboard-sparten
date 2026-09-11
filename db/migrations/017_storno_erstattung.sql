-- P51: Storno (beidseitig) und Erstattung als verknuepfte Gegenbuchung.

ALTER TABLE buchung ADD COLUMN original_id INTEGER REFERENCES buchung(id);
ALTER TABLE buchung ADD COLUMN storniert_am TEXT;

-- Verknuepft eine Erstattungszeile mit der erstatteten Zeile der Original-Buchung, damit
-- sich der bereits erstattete Betrag je Original-Zeile ermitteln laesst (siehe
-- app/routers/buchungen.py::erstatten_buchung). Nicht Teil der Auftragskarte-SQL-Vorlage,
-- aber notwendig fuer die dort verlangte Regel "Summe aller Erstattungen je Zeile <= betrag_cent".
ALTER TABLE buchungszeile ADD COLUMN original_zeile_id INTEGER REFERENCES buchungszeile(id);

DROP VIEW v_einnahmen_ausgaben;
DROP VIEW v_zeile;

CREATE VIEW v_zeile AS
SELECT
    bz.id            AS zeile_id,
    b.id             AS buchung_id,
    b.sparte_id      AS sparte_id,
    b.datum          AS datum,
    b.typ            AS typ,
    CASE b.typ WHEN 'ausgabe' THEN -bz.betrag_cent ELSE bz.betrag_cent END AS betrag_signed_cent,
    bz.betrag_cent   AS betrag_cent,
    bz.kategorie_id  AS kategorie_id,
    bz.neutral       AS neutral,
    b.storniert_am   AS storniert_am,
    CASE WHEN b.typ = 'umbuchung' THEN 1 ELSE 0 END AS ist_transfer
FROM buchungszeile bz
JOIN buchung b ON b.id = bz.buchung_id;

CREATE VIEW v_einnahmen_ausgaben AS
SELECT * FROM v_zeile WHERE ist_transfer = 0 AND neutral = 0 AND storniert_am IS NULL;
