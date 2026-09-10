"""Dauerhafte Request-Identität innerhalb der fachlichen Schreibtransaktion."""
import hashlib
import json

from fastapi import HTTPException
from fastapi.responses import JSONResponse


def kanonisch(daten):
    return json.dumps(daten, sort_keys=True, separators=(',', ':'), ensure_ascii=False)


def nutzdaten_hash(modell):
    daten = modell.model_dump(mode='json', exclude={'client_request_id'})
    return hashlib.sha256(kanonisch(daten).encode('utf-8')).hexdigest()


def wiederhole(con, art, modell, bereich):
    if modell.client_request_id is None:
        return None
    row = con.execute(
        'SELECT * FROM request_wiederholung WHERE art = ? AND client_request_id = ?',
        (art, modell.client_request_id),
    ).fetchone()
    if row is None:
        return None
    if row['bereich_id'] != bereich.id:
        raise HTTPException(409, 'client_request_id bereits verwendet')
    if row['nutzdaten_hash'] != nutzdaten_hash(modell):
        raise HTTPException(409, 'client_request_id mit anderen Nutzdaten verwendet')
    return JSONResponse(json.loads(row['antwort_json']), status_code=200)


def speichere_antwort(con, art, modell, bereich, antwort):
    if modell.client_request_id is not None:
        con.execute(
            'INSERT INTO request_wiederholung '
            '(art, client_request_id, bereich_id, nutzdaten_hash, antwort_json) '
            'VALUES(?, ?, ?, ?, ?)',
            (art, modell.client_request_id, bereich.id, nutzdaten_hash(modell),
             kanonisch(antwort)),
        )
