"""FastAPI-Einstieg: initialisiert die DB, mountet API und statisches Frontend."""
import asyncio
import os
import pathlib
from contextlib import asynccontextmanager

from fastapi import FastAPI
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


@app.get("/api/health")
def health():
    return {"status": "ok"}


# Studio ist die einzige Oberflaeche: unter / UND weiterhin unter /studio
# (alte Lesezeichen bleiben gueltig). /api hat Vorrang, da zuerst registriert.
app.mount("/studio", StaticFiles(directory=STUDIO_DIR, html=True), name="studio")
app.mount("/", StaticFiles(directory=STUDIO_DIR, html=True), name="root")
