"""Konten und Geldbewegungen; keine erfundenen Zahlungen oder Anfangsstände.

SQL ist hier eingebettet, damit der allgemeine Runner Version 004 genau einmal
erkennt. Alle Anweisungen laufen in seiner Transaktion, ohne executescript.
"""
import logging
import sqlite3

log = logging.getLogger('finanz.migrate')


def _protokoll(con, art, objektkennung, hinweis):
    """Schreibt einen Nachzug-Hinweis, wenn Migration 012 bereits vorhanden ist."""
    if con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='migrationsprotokoll'").fetchone():
        con.execute(
            "INSERT OR IGNORE INTO migrationsprotokoll(version, art, objektkennung, hinweis) "
            "VALUES(4, ?, ?, ?)", (art, objektkennung, hinweis),
        )

KONTO_SPALTEN = {
    'art': "TEXT NOT NULL DEFAULT 'bank' CHECK (art IN ('bank','karte','kassa','depot','wallet'))",
    'waehrung': "TEXT NOT NULL DEFAULT 'EUR'",
    'kartenendnummer': 'TEXT',
    'sortierung': 'INTEGER NOT NULL DEFAULT 0',
}

SQL = """
CREATE TABLE IF NOT EXISTS transfer (
    id INTEGER PRIMARY KEY,
    art TEXT NOT NULL CHECK (art IN ('bankomat','umbuchung','ausgleich','kartenabrechnung','sonstig')),
    von_konto_id INTEGER REFERENCES bankkonto(id),
    nach_konto_id INTEGER REFERENCES bankkonto(id),
    datum TEXT NOT NULL,
    betrag_cent INTEGER NOT NULL CHECK (betrag_cent > 0),
    notiz TEXT,
    storniert_am TEXT,
    erstellt_am TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS bewegung (
    id INTEGER PRIMARY KEY,
    konto_id INTEGER NOT NULL REFERENCES bankkonto(id),
    datum TEXT NOT NULL,
    valuta TEXT,
    betrag_signed_cent INTEGER NOT NULL,
    waehrung TEXT NOT NULL DEFAULT 'EUR',
    art TEXT NOT NULL DEFAULT 'zahlung' CHECK (art IN ('zahlung','transfer','gebuehr','zins','trade')),
    transfer_id INTEGER REFERENCES transfer(id),
    bankumsatz_id INTEGER UNIQUE REFERENCES bankumsatz(id),
    text TEXT,
    gegenpartei TEXT,
    quelle TEXT NOT NULL CHECK (quelle IN ('manuell','import','ausgleich','kredit','nachzug')),
    storniert_am TEXT,
    erstellt_am TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS buchung_bewegung (
    buchung_id INTEGER NOT NULL REFERENCES buchung(id) ON DELETE CASCADE,
    bewegung_id INTEGER NOT NULL REFERENCES bewegung(id) ON DELETE CASCADE,
    anteil_signed_cent INTEGER NOT NULL,
    PRIMARY KEY (buchung_id, bewegung_id)
);
CREATE INDEX IF NOT EXISTS idx_bewegung_konto_datum ON bewegung (konto_id, datum);
CREATE INDEX IF NOT EXISTS idx_bewegung_transfer ON bewegung (transfer_id);
CREATE INDEX IF NOT EXISTS idx_buchung_bewegung_bewegung ON buchung_bewegung (bewegung_id);
"""


def up(con):
    spalten = {r[1] for r in con.execute('PRAGMA table_info(bankkonto)')}
    for name, definition in KONTO_SPALTEN.items():
        if name not in spalten:
            con.execute(f'ALTER TABLE bankkonto ADD COLUMN {name} {definition}')
    for sql in SQL.split(';'):
        if sql.strip():
            con.execute(sql)
    vorher = {t: con.execute(f'SELECT count(*) FROM {t}').fetchone()[0]
              for t in ('bankkonto', 'bewegung', 'transfer')}
    con.execute("""INSERT INTO bankkonto(name,art,sparte_id,bereich_id)
        SELECT 'Kassa ' || s.name, 'kassa', s.id, s.bereich_id FROM sparte s
        WHERE s.aktiv=1 AND NOT EXISTS
          (SELECT 1 FROM bankkonto k WHERE k.art='kassa' AND k.sparte_id=s.id)""")
    con.execute("""INSERT INTO bewegung(konto_id,datum,valuta,betrag_signed_cent,waehrung,
        bankumsatz_id,text,gegenpartei,quelle)
        SELECT u.bankkonto_id,u.datum,u.valuta,u.betrag_cent,k.waehrung,u.id,u.text,u.gegenpartei,'import'
        FROM bankumsatz u JOIN bankkonto k ON k.id=u.bankkonto_id
        WHERE NOT EXISTS (SELECT 1 FROM bewegung m WHERE m.bankumsatz_id=u.id)""")
    con.execute("""INSERT OR IGNORE INTO buchung_bewegung
        SELECT b.id,m.id,CASE WHEN b.typ='ausgabe' THEN -b.betrag_cent ELSE b.betrag_cent END
        FROM buchung b JOIN bewegung m ON m.bankumsatz_id=b.bankumsatz_id""")
    # Die Cursor liefern unabhängig von der Row-Factory des Aufrufers Dictionaries.
    def rows(sql, params=()):
        cursor = con.execute(sql, params)
        return [dict(zip([c[0] for c in cursor.description], r)) for r in cursor.fetchall()]

    bar_ungeklaert = []
    for b in rows("""SELECT b.* FROM buchung b WHERE zahlungsart='bar'
            AND typ IN ('einnahme','ausgabe') AND bankumsatz_id IS NULL
            AND NOT EXISTS (SELECT 1 FROM buchung_bewegung x WHERE x.buchung_id=b.id)"""):
        kassen = rows("SELECT id,waehrung FROM bankkonto WHERE art='kassa' AND sparte_id=?", (b['sparte_id'],))
        if len(kassen) != 1:
            bar_ungeklaert.append(b['id'])
            _protokoll(con, 'barbuchung_ungeklaert', f"buchung:{b['id']}",
                       f"Buchung {b['id']}: Barbuchung konnte keiner eindeutigen Kassa zugeordnet werden.")
            continue
        k = kassen[0]
        cent = -b['betrag_cent'] if b['typ']=='ausgabe' else b['betrag_cent']
        mid = con.execute("""INSERT INTO bewegung(konto_id,datum,betrag_signed_cent,waehrung,text,quelle)
            VALUES(?,?,?,?,?,'nachzug')""", (k['id'],b['datum'],cent,k['waehrung'],b['text'])).lastrowid
        con.execute('INSERT INTO buchung_bewegung VALUES(?,?,?)', (b['id'],mid,cent))
    ungeklaert = 0
    for gruppe in rows("SELECT DISTINCT transfer_gruppe_id AS g FROM buchung WHERE typ='umbuchung' AND transfer_gruppe_id IS NOT NULL"):
        paar = rows("SELECT * FROM buchung WHERE transfer_gruppe_id=? ORDER BY id", (gruppe['g'],))
        # Historischer Erzeuger schreibt zuerst Abgang, dann Zugang (P10).
        marker = 'Nachzug Umbuchung ' + gruppe['g']
        if con.execute('SELECT 1 FROM transfer WHERE notiz=? OR notiz=?', (marker,marker+'; Konten ungeklärt')).fetchone():
            continue
        if len(paar)!=2 or paar[0]['betrag_cent']<=0 or paar[0]['betrag_cent']!=paar[1]['betrag_cent'] or paar[0]['datum']!=paar[1]['datum']:
            log.info('Migration 004: Umbuchungsgruppe %s nicht eindeutig; kein Betrag erfunden',gruppe['g'])
            _protokoll(con, 'umbuchung_ungeklaert', f"umbuchungsgruppe:{gruppe['g']}",
                       f"Umbuchungsgruppe {gruppe['g']}: Die beiden Buchungen konnten nicht eindeutig aufgeloest werden.")
            ungeklaert += 1
            continue
        konten = [b['bankkonto_id'] for b in paar]
        bekannt = all(k is not None for k in konten)
        if not bekannt:
            konten = [None,None]
            _protokoll(con, 'umbuchung_ungeklaert', f"umbuchungsgruppe:{gruppe['g']}",
                       f"Umbuchungsgruppe {gruppe['g']}: Die Konten konnten nicht eindeutig bestimmt werden.")
            ungeklaert += 1
        tid = con.execute("INSERT INTO transfer(art,von_konto_id,nach_konto_id,datum,betrag_cent,notiz) VALUES('umbuchung',?,?,?,?,?)",
            (*konten,paar[0]['datum'],paar[0]['betrag_cent'],marker if bekannt else marker+'; Konten ungeklärt')).lastrowid
        if bekannt:
            for b, kid, sign in zip(paar,konten,(-1,1)):
                cent = sign*b['betrag_cent']
                # Ein vorhandener Import bleibt die einzige Geldbewegung.
                existing = con.execute('SELECT id FROM bewegung WHERE bankumsatz_id=?',(b['bankumsatz_id'],)).fetchone()
                if existing:
                    mid = existing[0]
                    con.execute("UPDATE bewegung SET art='transfer',transfer_id=? WHERE id=?",(tid,mid))
                else:
                    mid = con.execute("""INSERT INTO bewegung(konto_id,datum,betrag_signed_cent,waehrung,art,transfer_id,quelle)
                        SELECT id,?,?,waehrung,'transfer',?,'nachzug' FROM bankkonto WHERE id=?""", (b['datum'],cent,tid,kid)).lastrowid
                con.execute('INSERT OR REPLACE INTO buchung_bewegung VALUES(?,?,?)',(b['id'],mid,cent))
    unbekannt = [r[0] for r in con.execute("SELECT id FROM buchung WHERE zahlungsart IN ('bank','karte') AND bankumsatz_id IS NULL AND typ IN ('einnahme','ausgabe') ORDER BY id")]
    for buchung_id in unbekannt:
        _protokoll(con, 'zahlung_ungeklaert', f"buchung:{buchung_id}",
                   f"Buchung {buchung_id}: Bank- oder Kartenbuchung ohne zugehoerigen Umsatz.")
    if con.execute('PRAGMA foreign_key_check').fetchone() is not None:
        raise sqlite3.IntegrityError('Fremdschlüsselprüfung nach Migration 004 fehlgeschlagen')
    anzahl = {t: con.execute(f'SELECT count(*) FROM {t}').fetchone()[0]-n for t,n in vorher.items()}
    log.info('Migration 004: Kassen=%s, Bewegungen=%s, Transfers=%s, ungeklärte Transfers=%s, ungeklärte Barbuchungen=%s',
             anzahl['bankkonto'],anzahl['bewegung'],anzahl['transfer'],ungeklaert,len(bar_ungeklaert))
    log.info('Migration 004: Zahlung unbekannt: Anzahl=%s; Buchungs-IDs=%s; Barbuchungs-IDs=%s',len(unbekannt),unbekannt,bar_ungeklaert)
