"""Betriebliche, lesende Informationen fuer angemeldete Nutzer."""
import sqlite3

from fastapi import APIRouter, Depends

from ..bereiche import Bereich, BereichDep
from ..db import db_dep

router = APIRouter(prefix="/betrieb", tags=["betrieb"])


@router.get("/migrationsprotokoll")
def migrationsprotokoll(con: sqlite3.Connection = Depends(db_dep), bereich: BereichDep = Bereich(1)):
    return [dict(row) for row in con.execute(
        "SELECT id, version, zeitpunkt, art, objektkennung, hinweis "
        "FROM migrationsprotokoll ORDER BY zeitpunkt, id"
    )]
