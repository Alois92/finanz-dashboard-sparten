"""Geldbewegungen innerhalb der Transaktion des aufrufenden Endpunkts."""
from fastapi import HTTPException

from .bereiche import pruefe_konto, pruefe_sparte, pruefe_umsatz


def kassa_fuer_sparte(con, sparte_id, bereich):
    pruefe_sparte(con, sparte_id, bereich)
    rows = con.execute("SELECT id FROM bankkonto WHERE art='kassa' AND sparte_id=?", (sparte_id,)).fetchall()
    if len(rows)>1:
        raise HTTPException(409, 'Kassa der Sparte ist nicht eindeutig')
    if rows:
        kid = rows[0][0]
        pruefe_konto(con, kid, bereich)
        return kid
    return con.execute("""INSERT INTO bankkonto(name,art,sparte_id,bereich_id)
        SELECT 'Kassa ' || name,'kassa',id,bereich_id FROM sparte WHERE id=?""", (sparte_id,)).lastrowid


def import_bewegung(con, umsatz_id, bereich):
    pruefe_umsatz(con, umsatz_id, bereich)
    con.execute("""INSERT INTO bewegung(konto_id,datum,valuta,betrag_signed_cent,waehrung,
        bankumsatz_id,text,gegenpartei,quelle)
        SELECT u.bankkonto_id,u.datum,u.valuta,u.betrag_cent,k.waehrung,u.id,u.text,u.gegenpartei,'import'
        FROM bankumsatz u JOIN bankkonto k ON k.id=u.bankkonto_id WHERE u.id=?
        AND NOT EXISTS (SELECT 1 FROM bewegung m WHERE m.bankumsatz_id=u.id)""", (umsatz_id,))
    return con.execute('SELECT id FROM bewegung WHERE bankumsatz_id=?',(umsatz_id,)).fetchone()[0]


def pruefe_bewegungsreferenzen(con, buchung_id, bereich):
    for row in con.execute("""SELECT m.konto_id,m.bankumsatz_id,m.transfer_id FROM bewegung m
        JOIN buchung_bewegung x ON x.bewegung_id=m.id WHERE x.buchung_id=?""", (buchung_id,)):
        pruefe_konto(con,row['konto_id'],bereich)
        if row['bankumsatz_id'] is not None:
            pruefe_umsatz(con,row['bankumsatz_id'],bereich)
        if row['transfer_id'] is not None:
            pruefe_transfer(con,row['transfer_id'],bereich)


def pruefe_transfer(con, transfer_id, bereich):
    row = con.execute('SELECT * FROM transfer WHERE id=?',(transfer_id,)).fetchone()
    if row is None or row['von_konto_id'] is None or row['nach_konto_id'] is None:
        # Ohne Konten ist der Bereich nur über die historischen Buchungen belegt.
        if row is None:
            raise HTTPException(404, 'Transfer nicht gefunden')
        marker = row['notiz'] or ''
        gruppe = marker.removeprefix('Nachzug Umbuchung ').removesuffix('; Konten ungeklärt')
        buchungen = con.execute("SELECT s.bereich_id FROM buchung b JOIN sparte s ON s.id=b.sparte_id WHERE b.transfer_gruppe_id=?",(gruppe,)).fetchall()
        if not buchungen or any(r[0]!=bereich.id for r in buchungen):
            raise HTTPException(404,'Transfer nicht gefunden')
    for key in ('von_konto_id','nach_konto_id'):
        if row[key] is not None:
            pruefe_konto(con,row[key],bereich)
    for m in con.execute('SELECT konto_id,bankumsatz_id FROM bewegung WHERE transfer_id=?',(transfer_id,)):
        pruefe_konto(con,m['konto_id'],bereich)
        if m['bankumsatz_id'] is not None:
            pruefe_umsatz(con,m['bankumsatz_id'],bereich)
    return row


def storniere_transfer(con, transfer_id):
    con.execute("UPDATE transfer SET storniert_am=COALESCE(storniert_am,datetime('now')) WHERE id=?",(transfer_id,))
    con.execute("UPDATE bewegung SET storniert_am=COALESCE(storniert_am,datetime('now')) WHERE transfer_id=?",(transfer_id,))


def erzeuge_transfer(con, art, von, nach, datum, cent, notiz=None, quelle='manuell'):
    tid = con.execute('INSERT INTO transfer(art,von_konto_id,nach_konto_id,datum,betrag_cent,notiz) VALUES(?,?,?,?,?,?)',
                      (art,von,nach,datum,cent,notiz)).lastrowid
    mids = []
    if von is not None and nach is not None:
        for kid, sign in ((von,-1),(nach,1)):
            mids.append(con.execute("""INSERT INTO bewegung(konto_id,datum,betrag_signed_cent,waehrung,art,transfer_id,text,quelle)
                SELECT id,?,?,waehrung,'transfer',?,?,? FROM bankkonto WHERE id=?""", (datum,sign*cent,tid,notiz,quelle,kid)).lastrowid)
    return tid,mids


def synchronisiere_buchung(con, buchung_id, bereich):
    b = con.execute('SELECT * FROM buchung WHERE id=?',(buchung_id,)).fetchone()
    pruefe_bewegungsreferenzen(con,buchung_id,bereich)
    if b['transfer_gruppe_id']:
        return
    cent = -b['betrag_cent'] if b['typ']=='ausgabe' else b['betrag_cent']
    alt = con.execute("""SELECT m.* FROM bewegung m JOIN buchung_bewegung x ON x.bewegung_id=m.id
        WHERE x.buchung_id=?""",(buchung_id,)).fetchall()
    mid = None
    if b['bankumsatz_id'] is not None:
        mid = import_bewegung(con,b['bankumsatz_id'],bereich)
        con.execute("UPDATE bankumsatz SET importstatus='verbucht' WHERE id=?",(b['bankumsatz_id'],))
    elif b['typ'] in ('einnahme','ausgabe'):
        kid = kassa_fuer_sparte(con,b['sparte_id'],bereich) if b['zahlungsart']=='bar' else b['bankkonto_id'] if b['zahlungsart'] in ('bank','karte') else None
        if kid is not None:
            pruefe_konto(con,kid,bereich)
            own = [m for m in alt if m['quelle'] in ('manuell','nachzug') and m['transfer_id'] is None and m['storniert_am'] is None]
            if own:
                mid = own[0]['id']
                con.execute("""UPDATE bewegung SET konto_id=?,datum=?,betrag_signed_cent=?,
                    waehrung=(SELECT waehrung FROM bankkonto WHERE id=?),text=? WHERE id=?""",(kid,b['datum'],cent,kid,b['text'],mid))
            else:
                mid = con.execute("""INSERT INTO bewegung(konto_id,datum,betrag_signed_cent,waehrung,text,quelle)
                    SELECT id,?,?,waehrung,?,'manuell' FROM bankkonto WHERE id=?""",(b['datum'],cent,b['text'],kid)).lastrowid
    for m in alt:
        if m['id']!=mid and m['quelle'] in ('manuell','nachzug') and m['transfer_id'] is None:
            con.execute("UPDATE bewegung SET storniert_am=COALESCE(storniert_am,datetime('now')) WHERE id=?",(m['id'],))
    con.execute('DELETE FROM buchung_bewegung WHERE buchung_id=?',(buchung_id,))
    if mid is not None:
        con.execute('INSERT INTO buchung_bewegung VALUES(?,?,?)',(buchung_id,mid,cent))


def storniere_buchungsbewegungen(con, buchung_id):
    for m in con.execute("""SELECT m.* FROM bewegung m JOIN buchung_bewegung x ON x.bewegung_id=m.id
        WHERE x.buchung_id=?""",(buchung_id,)).fetchall():
        if m['transfer_id'] is not None:
            con.execute("UPDATE transfer SET storniert_am=COALESCE(storniert_am,datetime('now')) WHERE id=?",(m['transfer_id'],))
            con.execute("UPDATE bewegung SET storniert_am=COALESCE(storniert_am,datetime('now')) WHERE transfer_id=? AND quelle<>'import'",(m['transfer_id'],))
        elif m['quelle'] in ('manuell','nachzug'):
            con.execute("UPDATE bewegung SET storniert_am=COALESCE(storniert_am,datetime('now')) WHERE id=?",(m['id'],))
