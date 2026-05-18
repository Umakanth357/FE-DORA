from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.routes import router
from app.core.logging import setup_logging
from app.core.config import get_settings

setup_logging()
settings = get_settings()

app = FastAPI(
    title="DORA Platform API",
    version="1.0.0",
    description="Engineering intelligence platform — DORA metrics without the black box",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins.split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")


@app.get("/")
async def root():
    return {"service": "DORA Platform", "version": "1.0.0", "docs": "/docs"}
