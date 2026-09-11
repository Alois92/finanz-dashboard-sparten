"""FastAPI-Einstieg: initialisiert die DB, mountet API und statisches Frontend."""
import asyncio
import os
import pathlib
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .auswertung import auswertung_schleife
from .auth import AuthMiddleware, router as auth_router
from .backup import backup_schleife
from .db import get_connection, init_db
from .migrate import MigrationsFehler, status as migrationsstatus
from .routers import (belege, beleg_auswertung, buchungen, dashboard, export,
                      gruppen, import_bank, import_excel, schnellerfassung,
                      stammdaten, konten, auslagen, kredite, kennzahlen, betrieb)

STUDIO_DIR = pathlib.Path(__file__).resolve().parent.parent / "static-studio"
NEU_DIR = pathlib.Path(__file__).resolve().parent.parent / "static-neu"

# Anmeldung, Ersteinrichtung und Passwortwechsel liegen nur im Studio und ihre
# Pfade sind in app/auth.py fest verdrahtet (OEFFENTLICHE_PFADE, Umleitungen).
# Sie bleiben deshalb unter / erreichbar, egal welches Frontend den Root-Mount hat.
AUTH_SEITEN = (
    "login.html", "login.js",
    "password-setup.html", "password-setup.js",
    "password-change.html", "password-change.js",
    "password-recover.html", "password-recover.js",
    "password-common.css",
)


def frontend_verzeichnis(wert: str | None) -> pathlib.Path:
    """Welches Frontend unter / liegt. Unbekannte Werte bleiben beim Studio."""
    return NEU_DIR if (wert or "").strip().lower() == "neu" else STUDIO_DIR


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
app.include_router(betrieb.router, prefix="/api")


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
        "instanz": os.environ.get("FINANZ_INSTANZ", "prod"),
    }


@app.get("/api/betrieb/status")
def betrieb_status():
    con = get_connection()
    try:
        schema = migrationsstatus(con)
    finally:
        con.close()
    # P72: der Schema-/Sicherungsteil ist nach app/routers/betrieb.py ausgelagert,
    # damit GET /api/betrieb/uebersicht dieselbe Logik mitverwenden kann, ohne sie
    # zweimal zu schreiben. Die DB-Verbindung/der Migrationsstatus bleiben bewusst
    # hier (main.get_connection/main.migrationsstatus), damit bestehende Tests, die
    # genau diese beiden Namen patchen, unveraendert gruen bleiben (siehe
    # tests/test_backup.py::test_betriebsstatus_enthaelt_nur_oeffentliche_sicherungsfelder).
    return betrieb.baue_sicherung_und_schema_status(schema, app.state.schreibgeschuetzt)


# Neues Frontend zuerst mounten; die Auth-Middleware schuetzt /neu wie /studio.
# Beide Oberflaechen bleiben unter /neu und /studio erreichbar (alte Lesezeichen
# bleiben gueltig). /api hat Vorrang, da zuerst registriert.
app.mount("/neu", StaticFiles(directory=NEU_DIR, html=True), name="neu")
app.mount("/studio", StaticFiles(directory=STUDIO_DIR, html=True), name="studio")

# Die Anmeldeseiten kommen immer aus dem Studio und werden vor dem Root-Mount
# registriert, damit sie auch dann unter / liegen, wenn / auf static-neu zeigt.
def _auth_seite(datei: str):
    async def ausliefern(request: Request) -> FileResponse:
        return FileResponse(STUDIO_DIR / datei)
    return ausliefern


for _seite in AUTH_SEITEN:
    app.add_route(f"/{_seite}", _auth_seite(_seite), methods=["GET", "HEAD"], name=f"auth-{_seite}")

# Welches Frontend unter / liegt, entscheidet FINANZ_FRONTEND (Standard: studio).
# Die Umstellung auf den Neubau setzt dort per systemd-Drop-In "neu"; der
# Rueckweg entfernt das Drop-In, ohne dass Code geaendert werden muss.
ROOT_DIR = frontend_verzeichnis(os.environ.get("FINANZ_FRONTEND"))
app.mount("/", StaticFiles(directory=ROOT_DIR, html=True), name="root")
