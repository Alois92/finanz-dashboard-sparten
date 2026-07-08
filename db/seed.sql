-- ============================================================================
-- Seed-Daten: Sparten, globale Kategoriegruppen, Auswertungsgruppen
-- Startvorschlaege aus dem Konzept (Abschnitt 2, 5.3, 9.3). In der App
-- spaeter bearbeitbar. Kategorien je Sparte werden bewusst NICHT hier
-- verdrahtet, sondern in der Oberflaeche gepflegt.
-- Ausfuehren NACH schema.sql.
-- ============================================================================

-- Sparten (Verein = geschuetzt)
INSERT INTO sparte (name, kuerzel, typ, geschuetzt, sortierung) VALUES
  ('Privatvermietung',      'PV',  'vermietung', 0, 10),
  ('Zimmervermietung Hof',  'ZVH', 'vermietung', 0, 20),
  ('Bauernhof',             'HOF', 'hof',        0, 30),
  ('Verein',                'VER', 'verein',     1, 40),
  ('Alois privat',          'AL',  'privat',     0, 50),
  ('Frau privat',           'FR',  'privat',     0, 60);

-- Globale Kategoriegruppen (spartenuebergreifend)
INSERT INTO globale_kategoriegruppe (name) VALUES
  ('Versicherungen'),
  ('Auto und Mobilitaet'),
  ('Gebaeude'),
  ('Instandhaltung'),
  ('Tiere'),
  ('Lebensmittel und Leben'),
  ('Energie'),
  ('Steuern und Abgaben'),
  ('Vermietung'),
  ('Hofbetrieb'),
  ('Verein'),
  ('Gesundheit'),
  ('Freizeit');

-- Auswertungsgruppen (Buendel von Sparten)
INSERT INTO auswertungsgruppe (name, beschreibung) VALUES
  ('Vermietung gesamt', 'Privatvermietung + Zimmervermietung Hof'),
  ('Privat gesamt',     'Alois privat + Frau privat'),
  ('Hof gesamt',        'Bauernhof + Zimmervermietung Hof'),
  ('Alles ohne Verein', 'Alle Sparten ausser Verein'),
  ('Gesamtuebersicht',  'Alle Sparten');

-- Zuordnung Auswertungsgruppe -> Sparte (per Name aufgeloest)
-- Vermietung gesamt
INSERT INTO auswertungsgruppe_sparte (auswertungsgruppe_id, sparte_id)
SELECT g.id, s.id FROM auswertungsgruppe g, sparte s
WHERE g.name = 'Vermietung gesamt' AND s.name IN ('Privatvermietung','Zimmervermietung Hof');
-- Privat gesamt
INSERT INTO auswertungsgruppe_sparte (auswertungsgruppe_id, sparte_id)
SELECT g.id, s.id FROM auswertungsgruppe g, sparte s
WHERE g.name = 'Privat gesamt' AND s.name IN ('Alois privat','Frau privat');
-- Hof gesamt
INSERT INTO auswertungsgruppe_sparte (auswertungsgruppe_id, sparte_id)
SELECT g.id, s.id FROM auswertungsgruppe g, sparte s
WHERE g.name = 'Hof gesamt' AND s.name IN ('Bauernhof','Zimmervermietung Hof');
-- Alles ohne Verein
INSERT INTO auswertungsgruppe_sparte (auswertungsgruppe_id, sparte_id)
SELECT g.id, s.id FROM auswertungsgruppe g, sparte s
WHERE g.name = 'Alles ohne Verein' AND s.typ <> 'verein';
-- Gesamtuebersicht
INSERT INTO auswertungsgruppe_sparte (auswertungsgruppe_id, sparte_id)
SELECT g.id, s.id FROM auswertungsgruppe g, sparte s
WHERE g.name = 'Gesamtuebersicht';

-- Personen fuer den Personen-Filter
INSERT INTO person (name) VALUES ('Alois'), ('Frau');
