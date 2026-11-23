from __future__ import annotations

from contextlib import asynccontextmanager

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from .db import create_all
from .routers import admin, auth, billing, content, learning

WEB_DIR = Path(__file__).resolve().parents[2] / "web"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    create_all()  # TODO: replace with Alembic migrations before production
    yield


app = FastAPI(
    title="Application d'apprentissage IA – API",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(auth.router)
app.include_router(content.router)
app.include_router(learning.router)
app.include_router(billing.router)
app.include_router(admin.router)


@app.get("/health", tags=["meta"])
def health() -> dict:
    return {"status": "ok"}


@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    return RedirectResponse("/app/")


app.mount("/app", StaticFiles(directory=WEB_DIR, html=True), name="web")
