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
from .backup import backup_schleife
from .db import init_db
from .routers import (belege, beleg_auswertung, buchungen, dashboard, export,
                      gruppen, import_bank, import_excel, schnellerfassung,
                      stammdaten)

STUDIO_DIR = pathlib.Path(__file__).resolve().parent.parent / "static-studio"


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    sicherung = asyncio.create_task(backup_schleife())
    auswertung = asyncio.create_task(auswertung_schleife())
    yield
    sicherung.cancel()
    auswertung.cancel()


app = FastAPI(title="Finanz-Dashboard Sparten", version="0.1.0", lifespan=lifespan)
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
app.include_router(buchungen.router, prefix="/api")
app.include_router(dashboard.router, prefix="/api")
app.include_router(gruppen.router, prefix="/api")
app.include_router(schnellerfassung.router, prefix="/api")
app.include_router(belege.router, prefix="/api")
app.include_router(beleg_auswertung.router, prefix="/api")
app.include_router(import_bank.router, prefix="/api")
app.include_router(import_excel.router, prefix="/api")


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


# Studio ist die einzige Oberflaeche: unter / UND weiterhin unter /studio
# (alte Lesezeichen bleiben gueltig). /api hat Vorrang, da zuerst registriert.
app.mount("/studio", StaticFiles(directory=STUDIO_DIR, html=True), name="studio")
app.mount("/", StaticFiles(directory=STUDIO_DIR, html=True), name="root")
