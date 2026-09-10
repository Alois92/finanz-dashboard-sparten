"""FastAPI-Einstieg: initialisiert die DB, mountet API und statisches Frontend."""
import asyncio
import os
import pathlib
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .auswertung import auswertung_schleife
from .auth import AuthMiddleware, router as auth_router
from . import backup
from .backup import backup_schleife
from .db import get_connection, init_db
from .migrate import MigrationsFehler, status as migrationsstatus
from .routers import (belege, beleg_auswertung, buchungen, dashboard, export,
                      gruppen, import_bank, import_excel, schnellerfassung,
                      stammdaten, konten, auslagen, kredite, kennzahlen)

STUDIO_DIR = pathlib.Path(__file__).resolve().parent.parent / "static-studio"


@asynccontextmanager
async def lifespan(app: FastAPI):
    sicherung = None
    auswertung = None
    app.state.schreibgeschuetzt = False
    app.state.migrationsfehler = None
    try:
        init_db()
    except MigrationsFehler as exc:
        app.state.schreibgeschuetzt = True
        app.state.migrationsfehler = str(exc)
    else:
        sicherung = asyncio.create_task(backup_schleife())
        auswertung = asyncio.create_task(auswertung_schleife())
    yield
    if sicherung is not None:
        sicherung.cancel()
    if auswertung is not None:
        auswertung.cancel()


app = FastAPI(title="Finanz-Dashboard Sparten", version="0.1.0", lifespan=lifespan)
app.state.schreibgeschuetzt = False
app.state.migrationsfehler = None
app.add_middleware(AuthMiddleware)
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=[
        host.strip()
        for host in os.environ.get(
            "FINANZ_ALLOWED_HOSTS",
            "finanz.tailb1b087.ts.net,localhost,127.0.0.1",
        ).split(",")
        if host.strip()
    ],
)

app.include_router(auth_router)
app.include_router(export.router)
app.include_router(stammdaten.router, prefix="/api")
app.include_router(konten.router, prefix="/api")
app.include_router(auslagen.router, prefix="/api")
app.include_router(buchungen.router, prefix="/api")
app.include_router(dashboard.router, prefix="/api")
app.include_router(gruppen.router, prefix="/api")
app.include_router(schnellerfassung.router, prefix="/api")
app.include_router(belege.router, prefix="/api")
app.include_router(beleg_auswertung.router, prefix="/api")
app.include_router(import_bank.router, prefix="/api")
app.include_router(import_excel.router, prefix="/api")
app.include_router(kredite.router, prefix="/api")
app.include_router(kennzahlen.router, prefix="/api")


@app.middleware("http")
async def schreibschutz_middleware(request: Request, call_next):
    if (
        request.method in {"POST", "PUT", "PATCH", "DELETE"}
        and not request.url.path.startswith("/api/auth/")
        and getattr(request.app.state, "schreibgeschuetzt", False)
    ):
        fehler = getattr(request.app.state, "migrationsfehler", None) or "unbekannt"
        return JSONResponse(
            {"detail": f"Datenbank-Nachzug fehlgeschlagen: {fehler}"},
            status_code=503,
        )
    return await call_next(request)


def _saubere_validierungswert(wert):
    """Ersetzt nicht JSON-serialisierbare Werte (z.B. rohe Bytes aus Multipart-
    Uploads) in Validierungsfehlern durch eine unschaedliche Platzhalter-Beschreibung.
    """
    if isinstance(wert, bytes):
        return f"<binaere Daten, {len(wert)} Bytes>"
    if isinstance(wert, dict):
        return {schluessel: _saubere_validierungswert(teilwert)
                for schluessel, teilwert in wert.items()}
    if isinstance(wert, (list, tuple)):
        return [_saubere_validierungswert(teilwert) for teilwert in wert]
    try:
        jsonable_encoder(wert)
    except Exception:
        return f"<nicht darstellbare Daten: {type(wert).__name__}>"
    return wert


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    # Den ganzen Eintrag bereinigen, nicht nur 'input': auch 'ctx' kann bei
    # eigenen Validatoren nicht serialisierbare Objekte (z.B. ValueError) fuehren.
    fehler = [_saubere_validierungswert(dict(eintrag)) for eintrag in exc.errors()]
    return JSONResponse(status_code=422, content={"detail": jsonable_encoder(fehler)})


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/schema")
def schema_status():
    con = get_connection()
    try:
        stand = migrationsstatus(con)
    finally:
        con.close()
    return {
        "aktuell": stand["aktuell"],
        "anstehend": stand["anstehend"],
        "schreibgeschuetzt": app.state.schreibgeschuetzt,
        "fehler": app.state.migrationsfehler,
    }


@app.get("/api/betrieb/status")
def betrieb_status():
    con = get_connection()
    try:
        schema = migrationsstatus(con)
    finally:
        con.close()
    ordner = backup.DB_PATH.parent / "backup"
    sicherungen = sorted(ordner.glob("finanz-????-??-??.db"))
    letzte = sicherungen[-1].stem.removeprefix("finanz-") if sicherungen else None
    pruefung = backup.pruefe_sicherung(letzte) if letzte else {
        "db_ok": False,
        "belege_ok": 0,
        "belege_fehlend": 0,
        "manifest_ok": False,
    }
    if backup.BACKUP_ZIEL2 is None:
        zweitziel = "nicht konfiguriert"
    elif letzte and backup._vollstaendiger_satz(backup.BACKUP_ZIEL2, letzte):
        zweitziel = "ok"
    else:
        zweitziel = "fehlt"
    return {
        "schema": {"aktuell": schema["aktuell"], "anstehend": schema["anstehend"]},
        "sicherung": {
            "letzte": letzte,
            "db_ok": pruefung["db_ok"],
            "belege_ok": pruefung["belege_ok"],
            "belege_fehlend": pruefung["belege_fehlend"],
            "zweitziel": zweitziel,
        },
        "schreibgeschuetzt": app.state.schreibgeschuetzt,
    }


# Studio ist die einzige Oberflaeche: unter / UND weiterhin unter /studio
# (alte Lesezeichen bleiben gueltig). /api hat Vorrang, da zuerst registriert.
app.mount("/studio", StaticFiles(directory=STUDIO_DIR, html=True), name="studio")
app.mount("/", StaticFiles(directory=STUDIO_DIR, html=True), name="root")
