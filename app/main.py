"""
Autonomous AI Software Engineer — FastAPI entrypoint.
"""
from __future__ import annotations

import logging

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from prometheus_fastapi_instrumentator import Instrumentator

from app.api.routes.agent import router as agent_router
from app.api.routes.chat import router as chat_router
from app.api.routes.health import router as health_router
from app.api.routes.manus import router as manus_router
from app.api.routes.tasks import router as tasks_router
from app.api.routes.upload import router as upload_router
from app.config import get_settings

# ------------------------------------------------------------------
# Structured logging
# ------------------------------------------------------------------
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.stdlib.add_log_level,
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    logger_factory=structlog.stdlib.LoggerFactory(),
)
logging.basicConfig(level=logging.INFO)

s = get_settings()

# ------------------------------------------------------------------
# App
# ------------------------------------------------------------------
app = FastAPI(
    title="Autonomous AI Software Engineer",
    description=(
        "Multi-agent system powered by Kimi K2 / Moonshot. "
        "Research → Code → Debug → Test → Evaluate."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Prometheus
Instrumentator().instrument(app).expose(app, endpoint="/metrics")

# Static files (UI)
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Routers
app.include_router(health_router)
app.include_router(agent_router, prefix="/api/v1")
app.include_router(tasks_router, prefix="/api/v1")
app.include_router(manus_router, prefix="/api/v1")
app.include_router(chat_router, prefix="/api/v1")
app.include_router(upload_router, prefix="/api/v1")

# ------------------------------------------------------------------
# Global exception handler
# ------------------------------------------------------------------

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logging.exception("Unhandled error: %s", exc)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


@app.get("/", include_in_schema=False)
async def root():
    return FileResponse("app/static/index.html")
