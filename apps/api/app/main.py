from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.api.routes import router
from app.core.config import get_settings
from app.core.database import SessionLocal, engine
from app.core.logging_config import RequestLoggingMiddleware, setup_logging
from app.core.metrics import metrics
from app.core.migrate import run_migrations
from app.services.jobs import requeue_pending, start_worker
from app.services.schedules import start_runner as start_schedule_runner
from app.services.schedules import stop_runner as stop_schedule_runner
from app.services.sla import sla_summary

settings = get_settings()
setup_logging(settings.log_level)
logger = logging.getLogger("litmon")


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-LitMon-Pilot"] = "not-gxp-validated"
        if settings.app_env != "development":
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )
        return response


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Import models so metadata includes all tables (e.g. jobs)
    import app.models  # noqa: F401

    mode = run_migrations(engine)
    logger.info("Schema ready via %s", mode)
    await start_worker()
    n = await requeue_pending()
    start_schedule_runner()
    logger.info("LitMon-PV API started (requeued_jobs=%s)", n)
    yield
    await stop_schedule_runner()
    logger.info("LitMon-PV API shutting down")


app = FastAPI(
    title="LitMon-PV API",
    description=(
        "Literature Monitoring Automation for Pharmacovigilance — Phase 1 Pilot. "
        "PubMed via NCBI E-utilities API. AI ranks/flags/explains; humans decide."
    ),
    version="0.2.1",
    lifespan=lifespan,
)

app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "env": settings.app_env,
        "llm_mock": settings.llm_mock,
        "ncbi_tool": settings.ncbi_tool,
        "version": "0.2.1",
    }


@app.get("/health/ready")
def health_ready() -> dict:
    """Readiness: DB reachable."""
    try:
        db = SessionLocal()
        try:
            db.execute(__import__("sqlalchemy").text("SELECT 1"))
        finally:
            db.close()
        return {"status": "ready", "database": "ok"}
    except Exception as exc:
        return {"status": "not_ready", "database": str(exc)}


@app.get("/api/metrics")
def public_metrics() -> dict:
    """Lightweight metrics (authenticated routes also available under /api/ops/metrics)."""
    db = SessionLocal()
    try:
        extra = {"sla": sla_summary(db)}
    finally:
        db.close()
    return metrics.snapshot(extra=extra)
