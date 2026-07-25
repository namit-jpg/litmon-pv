"""In-process metrics for pilot dashboards (no Prometheus required)."""

from __future__ import annotations

import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any


@dataclass
class MetricsStore:
    started_at: float = field(default_factory=time.time)
    request_count: int = 0
    request_errors: int = 0
    request_latency_ms_sum: float = 0.0
    path_counts: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    score_count: int = 0
    score_latency_ms_sum: float = 0.0
    score_errors: int = 0
    search_runs: int = 0
    search_failures: int = 0
    search_new_articles: int = 0
    imports: int = 0
    exports: int = 0
    reviews: int = 0
    jobs_enqueued: int = 0
    jobs_completed: int = 0
    jobs_failed: int = 0
    notifications_sent: int = 0
    login_failures: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def record_request(
        self, method: str, path: str, status: int, duration_ms: float
    ) -> None:
        with self._lock:
            self.request_count += 1
            self.request_latency_ms_sum += duration_ms
            key = f"{method} {path}"
            # collapse article ids
            if path.startswith("/api/articles/") and path.count("/") >= 3:
                parts = path.split("/")
                if parts[3].isdigit():
                    key = f"{method} /api/articles/{{id}}" + (
                        "/" + "/".join(parts[4:]) if len(parts) > 4 else ""
                    )
            self.path_counts[key] += 1
            if status >= 400:
                self.request_errors += 1

    def record_score(self, duration_ms: float, ok: bool = True) -> None:
        with self._lock:
            self.score_count += 1
            self.score_latency_ms_sum += duration_ms
            if not ok:
                self.score_errors += 1

    def record_search(self, *, ok: bool, new_articles: int = 0) -> None:
        with self._lock:
            self.search_runs += 1
            if ok:
                self.search_new_articles += new_articles
            else:
                self.search_failures += 1

    def snapshot(self, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        with self._lock:
            req_avg = (
                self.request_latency_ms_sum / self.request_count
                if self.request_count
                else 0.0
            )
            score_avg = (
                self.score_latency_ms_sum / self.score_count if self.score_count else 0.0
            )
            top_paths = sorted(
                self.path_counts.items(), key=lambda x: x[1], reverse=True
            )[:15]
            data = {
                "uptime_seconds": round(time.time() - self.started_at, 1),
                "requests": {
                    "total": self.request_count,
                    "errors": self.request_errors,
                    "avg_latency_ms": round(req_avg, 2),
                    "top_paths": dict(top_paths),
                },
                "scoring": {
                    "total": self.score_count,
                    "errors": self.score_errors,
                    "avg_latency_ms": round(score_avg, 2),
                },
                "search": {
                    "runs": self.search_runs,
                    "failures": self.search_failures,
                    "new_articles": self.search_new_articles,
                },
                "imports": self.imports,
                "exports": self.exports,
                "reviews": self.reviews,
                "jobs": {
                    "enqueued": self.jobs_enqueued,
                    "completed": self.jobs_completed,
                    "failed": self.jobs_failed,
                },
                "notifications_sent": self.notifications_sent,
                "login_failures": self.login_failures,
            }
            if extra:
                data.update(extra)
            return data


metrics = MetricsStore()
