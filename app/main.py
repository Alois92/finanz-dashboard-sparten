"""FastAPI-Einstieg: initialisiert die DB, mountet API und statisches Frontend."""
import pathlib
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .db import init_db
from .routers import buchungen, dashboard, schnellerfassung, stammdaten

STATIC_DIR = pathlib.Path(__file__).resolve().parent.parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Finanz-Dashboard Sparten", version="0.1.0", lifespan=lifespan)

app.include_router(stammdaten.router, prefix="/api")
app.include_router(buchungen.router, prefix="/api")
app.include_router(dashboard.router, prefix="/api")
app.include_router(schnellerfassung.router, prefix="/api")


@app.get("/api/health")
def health():
    return {"status": "ok"}


# Statisches Frontend zuletzt mounten, damit /api Vorrang hat.
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
