"""Structured logging setup for pilot observability."""

from __future__ import annotations

import logging
import sys
import time
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


def setup_logging(level: str = "INFO") -> None:
    root = logging.getLogger()
    if root.handlers:
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
    )
    root.addHandler(handler)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    # Quiet noisy libs
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("passlib").setLevel(logging.WARNING)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        start = time.perf_counter()
        response: Response | None = None
        try:
            response = await call_next(request)
            return response
        finally:
            duration_ms = (time.perf_counter() - start) * 1000
            status = response.status_code if response else 500
            # Skip health spam in logs at DEBUG only — still record metrics
            logger = logging.getLogger("litmon.http")
            path = request.url.path
            if path not in ("/health", "/api/metrics") or status >= 400:
                logger.info(
                    "%s %s -> %s (%.1fms)",
                    request.method,
                    path,
                    status,
                    duration_ms,
                )
            try:
                from app.core.metrics import metrics

                metrics.record_request(request.method, path, status, duration_ms)
            except Exception:
                pass
