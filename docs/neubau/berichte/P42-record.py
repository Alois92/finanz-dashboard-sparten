"""Hilfsskript (Runde 1): zeichnet woertliche Antworten der P42-relevanten
Endpunkte mit einem echten ASGI-Aufruf (wie tests/test_bereiche.py) auf einer
Wegwerf-DB auf. Kein Teil der Testsuite, nur zur Berichtserstellung."""
import asyncio
import json
import os
import pathlib
import sqlite3
import sys
import tempfile
from urllib.parse import urlsplit

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

tmp = tempfile.mkdtemp(prefix="finanz-p42-record-")
dbpath = pathlib.Path(tmp) / "p42record.db"
os.environ["FINANZ_DB"] = str(dbpath)
os.environ["FINANZ_TEST_AUTH_BYPASS"] = "1"

from app import db
from app.main import app

con = sqlite3.connect(dbpath, check_same_thread=False)
con.row_factory = sqlite3.Row
con.executescript(db.SCHEMA.read_text(encoding="utf-8"))
con.executescript(db.SEED.read_text(encoding="utf-8"))

def connection():
    yield con
app.dependency_overrides[db.db_dep] = connection


def request(method, url, body=None, raw=None, content_type=None):
    parts = urlsplit(url)
    data = raw if raw is not None else json.dumps(body).encode() if body is not None else b""
    headers = [(b"host", b"localhost")]
    if body is not None or content_type:
        headers.append((b"content-type", (content_type or "application/json").encode()))
    scope = {"type": "http", "asgi": {"version": "3.0", "spec_version": "2.4"},
             "http_version": "1.1", "method": method, "scheme": "http",
             "path": parts.path, "raw_path": parts.path.encode(), "query_string": parts.query.encode(),
             "headers": headers, "client": ("127.0.0.1", 50000), "server": ("localhost", 80), "root_path": ""}
    messages = []

    async def run():
        sent = False
        complete = asyncio.Event()

        async def receive():
            nonlocal sent
            if not sent:
                sent = True
                return {"type": "http.request", "body": data}
            await complete.wait()
            return {"type": "http.disconnect"}

        async def send(message):
            messages.append(message)
            if message["type"] == "http.response.body" and not message.get("more_body"):
                complete.set()
        await app(scope, receive, send)
    asyncio.run(run())
    status = next(m["status"] for m in messages if m["type"] == "http.response.start")
    content = b"".join(m.get("body", b"") for m in messages if m["type"] == "http.response.body")
    try:
        return status, json.loads(content)
    except (ValueError, UnicodeDecodeError):
        return status, content


def multipart(bankkonto_id, dateiname, inhalt):
    boundary = "p42rec"
    raw = (
        f'--{boundary}\r\nContent-Disposition: form-data; name="bankkonto_id"\r\n\r\n{bankkonto_id}\r\n'
        f'--{boundary}\r\nContent-Disposition: form-data; name="datei"; filename="{dateiname}"\r\n'
        'Content-Type: text/csv\r\n\r\n'
    ).encode() + inhalt + f'\r\n--{boundary}--\r\n'.encode()
    return raw, f'multipart/form-data; boundary={boundary}'


out = []


def show(label, method, url, body=None, raw=None, content_type=None):
    status, result = request(method, url, body=body, raw=raw, content_type=content_type)
    out.append(f"### {method} {url}\n\nHTTP {status}\n\n```json\n{json.dumps(result, ensure_ascii=False)}\n```\n")
    return status, result


haupt = con.execute("SELECT id FROM sparte WHERE typ <> 'verein' ORDER BY id").fetchone()[0]
_, kat = show('kategorie-anlegen', 'POST', '/api/kategorien', {'sparte_id': haupt, 'name': 'Testkategorie', 'richtung': 'ausgabe'})
kid = kat['id']
_, konto = show('konto-anlegen', 'POST', '/api/konten', {'name': 'Testbank', 'art': 'bank', 'sparte_id': haupt})
bankkonto_id = konto['id']

show('konten-liste', 'GET', '/api/konten')

csv_inhalt = (
    "Buchungstag;Betrag;Verwendungszweck;Beguenstigter\n"
    "01.03.2026;-123,45;Einkauf Supermarkt;Handelskette AG\n"
    "02.03.2026;250,00;Gehalt Maerz;Arbeitgeber GmbH\n"
).encode("utf-8-sig")
raw, ct = multipart(bankkonto_id, 'umsaetze.csv', csv_inhalt)
show('import-csv-erster-import', 'POST', '/api/import/csv', raw=raw, content_type=ct)
raw, ct = multipart(bankkonto_id, 'umsaetze.csv', csv_inhalt)
show('import-csv-dublette', 'POST', '/api/import/csv', raw=raw, content_type=ct)

_, umsaetze = show('bankumsaetze-liste', 'GET', f'/api/bankumsaetze?bankkonto_id={bankkonto_id}')
uid = next(u for u in umsaetze if u['betrag_cent'] < 0)['id']
uid2 = next(u for u in umsaetze if u['betrag_cent'] > 0)['id']

show('verbuchen', 'POST', f'/api/bankumsaetze/{uid}/verbuchen', {'sparte_id': haupt, 'kategorie_id': kid})
show('ignorieren', 'PATCH', f'/api/bankumsaetze/{uid2}', {'importstatus': 'ignoriert'})

status, buchung = show('manuelle-buchung-anlegen', 'POST', '/api/buchungen', {
    'sparte_id': haupt, 'datum': '2026-04-02', 'typ': 'ausgabe', 'zahlungsart': 'bank',
    'bankkonto_id': bankkonto_id, 'text': 'Manuell erfasst',
    'zeilen': [{'kategorie_id': kid, 'betrag_cent': 500}],
})
manuelle_buchung_id = buchung['id']

csv2 = (
    "Buchungstag;Betrag;Verwendungszweck\n"
    "03.04.2026;-5,00;Bereits erfasste Zahlung\n"
).encode("utf-8-sig")
raw, ct = multipart(bankkonto_id, 'abgleich.csv', csv2)
show('import-csv-mit-manueller-buchung', 'POST', '/api/import/csv', raw=raw, content_type=ct)

_, umsaetze2 = show('bankumsaetze-liste-nach-zweitem-import', 'GET', f'/api/bankumsaetze?bankkonto_id={bankkonto_id}')
uid3 = next(u for u in umsaetze2 if u['text'] == 'Bereits erfasste Zahlung')['id']

show('kandidaten', 'GET', f'/api/bankumsaetze/{uid3}/kandidaten')
show('offene-abgleiche', 'GET', f'/api/konten/{bankkonto_id}/offene-abgleiche')
show('zuordnen', 'POST', f'/api/bankumsaetze/{uid3}/zuordnen', {'buchung_id': manuelle_buchung_id})
show('zuordnung-loesen', 'POST', f'/api/bankumsaetze/{uid3}/zuordnung-loesen')

pathlib.Path(__file__).parent.joinpath('P42-record-output.md').write_text('\n'.join(out), encoding='utf-8')
print('\n'.join(out))
con.close()
