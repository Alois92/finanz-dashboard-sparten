"""FastAPI-Einstieg: initialisiert die DB, mountet API und statisches Frontend."""
import asyncio
import pathlib
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .backup import backup_schleife
from .db import init_db
from .routers import (belege, buchungen, dashboard, import_bank,
                      import_excel, schnellerfassung, stammdaten)

STUDIO_DIR = pathlib.Path(__file__).resolve().parent.parent / "static-studio"


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    sicherung = asyncio.create_task(backup_schleife())
    yield
    sicherung.cancel()


app = FastAPI(title="Finanz-Dashboard Sparten", version="0.1.0", lifespan=lifespan)

app.include_router(stammdaten.router, prefix="/api")
app.include_router(buchungen.router, prefix="/api")
app.include_router(dashboard.router, prefix="/api")
app.include_router(schnellerfassung.router, prefix="/api")
app.include_router(belege.router, prefix="/api")
app.include_router(import_bank.router, prefix="/api")
app.include_router(import_excel.router, prefix="/api")


@app.get("/api/health")
def health():
    return {"status": "ok"}


# Studio ist die einzige Oberflaeche: unter / UND weiterhin unter /studio
# (alte Lesezeichen bleiben gueltig). /api hat Vorrang, da zuerst registriert.
app.mount("/studio", StaticFiles(directory=STUDIO_DIR, html=True), name="studio")
app.mount("/", StaticFiles(directory=STUDIO_DIR, html=True), name="root")
