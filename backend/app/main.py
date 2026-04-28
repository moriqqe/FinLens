from __future__ import annotations
from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.startup import run_startup
from app.routers import auth, dashboard, analyze, admin


@asynccontextmanager
async def lifespan(app: FastAPI):
    await run_startup()
    yield


app = FastAPI(title="FinLens", lifespan=lifespan)

app.include_router(auth.router, prefix="/api/auth")
app.include_router(dashboard.router, prefix="/api/dashboard")
app.include_router(analyze.router, prefix="/api")
app.include_router(admin.router, prefix="/api/admin")


@app.get("/health")
async def health():
    return {"status": "ok"}
