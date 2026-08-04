"""Lightweight background job runner (in-process asyncio queue)."""

from __future__ import annotations

import asyncio
import logging
import traceback
from datetime import datetime, timezone
from typing import Any, Callable, Coroutine

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.metrics import metrics
from app.models.entities import Job, JobStatus
from app.services.audit import log_event

logger = logging.getLogger("litmon.jobs")

_queue: asyncio.Queue[int] | None = None
_worker_task: asyncio.Task | None = None
_main_loop: asyncio.AbstractEventLoop | None = None


def ensure_queue() -> asyncio.Queue[int]:
    global _queue
    if _queue is None:
        _queue = asyncio.Queue()
    return _queue


async def start_worker() -> None:
    global _worker_task, _main_loop
    q = ensure_queue()
    _main_loop = asyncio.get_running_loop()
    if _worker_task and not _worker_task.done():
        return

    async def _loop() -> None:
        logger.info("Background job worker started")
        while True:
            job_id = await q.get()
            try:
                await _run_job(job_id)
            except Exception:
                logger.exception("Unhandled job error id=%s", job_id)
            finally:
                q.task_done()

    _worker_task = asyncio.create_task(_loop())


def _schedule_job(job_id: int) -> None:
    """Thread-safe enqueue for sync FastAPI routes (threadpool)."""
    loop = _main_loop
    if loop is None or not loop.is_running():
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            logger.warning("No event loop to schedule job %s — will requeue on restart", job_id)
            return

    def _put_nowait() -> None:
        ensure_queue().put_nowait(job_id)

    try:
        loop.call_soon_threadsafe(_put_nowait)
    except Exception:
        logger.exception("Failed to schedule job %s", job_id)


def enqueue_job(
    db: Session,
    *,
    job_type: str,
    payload: dict[str, Any] | None = None,
    created_by: str = "system",
) -> Job:
    job = Job(
        job_type=job_type,
        status=JobStatus.QUEUED,
        payload=payload or {},
        created_by=created_by,
    )
    db.add(job)
    db.flush()
    log_event(
        db,
        actor=created_by,
        action="job_enqueued",
        entity_type="job",
        entity_id=job.id,
        payload={"job_type": job_type},
    )
    db.commit()
    db.refresh(job)
    metrics.jobs_enqueued += 1
    _schedule_job(job.id)
    return job


async def requeue_pending() -> int:
    """On startup, re-queue QUEUED/RUNNING jobs."""
    db = SessionLocal()
    try:
        from sqlalchemy import select

        jobs = list(
            db.scalars(
                select(Job).where(
                    Job.status.in_([JobStatus.QUEUED, JobStatus.RUNNING])
                )
            ).all()
        )
        for j in jobs:
            if j.status == JobStatus.RUNNING:
                j.status = JobStatus.QUEUED
                j.error_message = (j.error_message or "") + " | requeued after restart"
            await ensure_queue().put(j.id)
        db.commit()
        return len(jobs)
    finally:
        db.close()


async def _run_job(job_id: int) -> None:
    db = SessionLocal()
    try:
        job = db.get(Job, job_id)
        if not job:
            return
        if job.status == JobStatus.COMPLETED:
            return
        job.status = JobStatus.RUNNING
        job.started_at = datetime.now(timezone.utc)
        job.attempts = (job.attempts or 0) + 1
        db.commit()

        handlers: dict[str, Callable[[Session, dict[str, Any]], Coroutine[Any, Any, dict]] ] = {
            "batch_rescore": _handle_batch_rescore,
            "sla_check": _handle_sla_check,
            "run_search": _handle_run_search,
        }
        handler = handlers.get(job.job_type)
        if not handler:
            raise ValueError(f"Unknown job_type: {job.job_type}")

        result = await handler(db, job.payload or {})
        job.status = JobStatus.COMPLETED
        job.result = result
        job.completed_at = datetime.now(timezone.utc)
        job.error_message = None
        log_event(
            db,
            actor=job.created_by or "system",
            action="job_completed",
            entity_type="job",
            entity_id=job.id,
            payload={"job_type": job.job_type, "result": result},
        )
        db.commit()
        metrics.jobs_completed += 1
        logger.info("Job %s completed: %s", job_id, job.job_type)
    except Exception as exc:
        logger.exception("Job %s failed", job_id)
        job = db.get(Job, job_id)
        if job:
            job.status = JobStatus.FAILED
            job.error_message = f"{exc}\n{traceback.format_exc()[-1500:]}"
            job.completed_at = datetime.now(timezone.utc)
            log_event(
                db,
                actor=job.created_by or "system",
                action="job_failed",
                entity_type="job",
                entity_id=job.id,
                payload={"error": str(exc)},
            )
            db.commit()
        metrics.jobs_failed += 1
    finally:
        db.close()


async def _handle_batch_rescore(db: Session, payload: dict[str, Any]) -> dict:
    from app.services.pipeline import rescore_article

    ids = payload.get("article_ids") or []
    ok = 0
    errors: list[dict[str, Any]] = []
    for aid in ids:
        try:
            await rescore_article(db, int(aid), actor=payload.get("actor") or "job")
            ok += 1
        except Exception as e:
            errors.append({"article_id": aid, "error": str(e)})
    return {"rescored": ok, "errors": errors}


async def _handle_sla_check(db: Session, payload: dict[str, Any]) -> dict:
    from app.services.sla import list_overdue_articles
    from app.services.notifications import notify_sla_breaches

    items = list_overdue_articles(db)
    from app.models import Article
    from app.services.alerts import create_alert

    for item in items:
        article = db.get(Article, int(item["id"]))
        if article and article.assignee_id:
            create_alert(
                db,
                user_id=article.assignee_id,
                article_id=article.id,
                alert_type="review_overdue",
                priority="high",
                title="Literature review overdue",
                message=f"{article.title} is {item['hours_overdue']} hours overdue.",
                dedupe_key=f"overdue:{article.id}",
            )
    db.commit()
    notify_sla_breaches(items)
    return {"overdue": len(items), "items": items[:100]}


async def _handle_run_search(db: Session, payload: dict[str, Any]) -> dict:
    from app.services.pipeline import run_search

    run = await run_search(
        db,
        int(payload["search_string_id"]),
        date_from=None,
        date_to=None,
        triggered_by=payload.get("actor") or "job",
        max_fetch=int(payload.get("max_fetch") or 50),
    )
    return {
        "search_run_id": run.id,
        "status": run.status.value,
        "hit_count": run.hit_count,
        "new_article_count": run.new_article_count,
        "error_message": run.error_message,
    }
