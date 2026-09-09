"""Berechnung von Kontostaenden aus Tagesendankern und Bewegungen."""
from datetime import date


def kontostand(con, konto_id: int, stichtag: str) -> dict:
    """Ermittelt den Stand aus dem letzten Anker und spaeteren Bewegungen."""
    anker = con.execute(
        "SELECT stichtag, saldo_cent, quelle FROM kontostand_anker "
        "WHERE konto_id=? AND stichtag<=? ORDER BY stichtag DESC, id DESC LIMIT 1",
        (konto_id, stichtag),
    ).fetchone()
    bewegungen = ()
    if anker:
        bewegungen = con.execute(
            "SELECT COALESCE(SUM(betrag_signed_cent), 0) AS summe, COUNT(*) AS anzahl "
            "FROM bewegung WHERE konto_id=? AND storniert_am IS NULL "
            "AND datum>? AND datum<=?",
            (konto_id, anker["stichtag"], stichtag),
        ).fetchone()
        stand = anker["saldo_cent"] + bewegungen["summe"]
        anzahl = bewegungen["anzahl"]
        anker_json = dict(anker)
    else:
        stand = None
        anzahl = 0
        anker_json = None

    rohsaldo = con.execute(
        "SELECT COALESCE(SUM(betrag_signed_cent), 0) FROM bewegung "
        "WHERE konto_id=? AND datum<=? AND storniert_am IS NULL",
        (konto_id, stichtag),
    ).fetchone()[0]

    voranker = con.execute(
        "SELECT 1 FROM bewegung WHERE konto_id=? AND datum<? "
        "AND storniert_am IS NULL LIMIT 1",
        (konto_id, anker["stichtag"] if anker else stichtag),
    ).fetchone() if anker else None

    letzter = con.execute(
        "SELECT MAX(importiert_am) AS importiert_am FROM import_batch WHERE bankkonto_id=?",
        (konto_id,),
    ).fetchone()["importiert_am"]
    letzter_import = letzter[:10] if letzter else None
    import_alter = None
    if letzter_import:
        import_alter = (date.fromisoformat(stichtag) - date.fromisoformat(letzter_import)).days

    offen_pruefen = con.execute(
        "SELECT 1 FROM kassazaehlung z JOIN bankkonto k ON k.id=z.konto_id "
        "WHERE z.konto_id=? AND z.status='offen' AND z.datum<? "
        "AND EXISTS (SELECT 1 FROM bewegung m WHERE m.konto_id=z.konto_id "
        "AND m.datum>z.datum AND m.storniert_am IS NULL) LIMIT 1",
        (konto_id, stichtag),
    ).fetchone()
    hinweise = []
    if voranker:
        hinweise.append("Bewegung vor dem letzten Anker")
    if offen_pruefen:
        hinweise.append("Zählung prüfen")
    datenstand = "unbekannt" if anker is None else "aktuell"
    if import_alter is not None and import_alter > 30:
        datenstand = "veraltet"
    return {
        "konto_id": konto_id,
        "stichtag": stichtag,
        "stand_cent": stand,
        "saldo_cent": rohsaldo,
        "anker": anker_json,
        "bewegungen_seit_anker": anzahl,
        "letzter_import": letzter_import,
        "import_alter_tage": import_alter,
        "datenstand": datenstand,
        "hinweis": "; ".join(hinweise),
    }
