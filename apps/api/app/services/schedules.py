"""Recurring PubMed searches.

A schedule stores its own ``next_run_at`` instead of relying on a live timer,
so restarting the API never loses or double-fires a run. The runner simply
asks "what is due?" on each tick.
"""

from __future__ import annotations

import asyncio
import calendar
import logging
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.models import Product, ScheduleFrequency, SearchSchedule, SearchString
from app.services.audit import log_event

logger = logging.getLogger("litmon.schedules")

# Each run looks back slightly further than its own interval so an article
# published right on a boundary — or a run that fired late — is never skipped.
_LOOKBACK_DAYS = {
    ScheduleFrequency.DAILY: 2,
    ScheduleFrequency.WEEKLY: 8,
    ScheduleFrequency.MONTHLY: 32,
}


def default_lookback_days(frequency: ScheduleFrequency) -> int:
    return _LOOKBACK_DAYS.get(frequency, 7)


def _add_month(dt: datetime) -> datetime:
    """Advance one calendar month, clamping to the end of a shorter month.

    31 Jan + 1 month is 28 Feb (or 29 in a leap year), not 3 March.
    """
    year, month = dt.year, dt.month
    if month == 12:
        year, month = year + 1, 1
    else:
        month += 1
    day = min(dt.day, calendar.monthrange(year, month)[1])
    return dt.replace(year=year, month=month, day=day)


def compute_next_run(current: datetime, frequency: ScheduleFrequency) -> datetime:
    if frequency == ScheduleFrequency.DAILY:
        return current + timedelta(days=1)
    if frequency == ScheduleFrequency.WEEKLY:
        return current + timedelta(weeks=1)
    if frequency == ScheduleFrequency.MONTHLY:
        return _add_month(current)
    raise ValueError(f"Unsupported frequency: {frequency}")


def advance_past(current: datetime, frequency: ScheduleFrequency, now: datetime) -> datetime:
    """Roll ``current`` forward until it is in the future.

    If the API was down for a week, a daily schedule should resume tomorrow —
    not fire seven catch-up runs at once against NCBI.
    """
    nxt = compute_next_run(current, frequency)
    guard = 0
    while nxt <= now and guard < 1000:
        nxt = compute_next_run(nxt, frequency)
        guard += 1
    return nxt


def _as_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def is_expired(schedule: SearchSchedule, today: date | None = None) -> bool:
    return (today or datetime.now(timezone.utc).date()) > schedule.end_date


def due_schedules(db: Session, now: datetime | None = None) -> list[SearchSchedule]:
    now = now or datetime.now(timezone.utc)
    rows = db.scalars(
        select(SearchSchedule)
        .where(SearchSchedule.is_active.is_(True))
        .order_by(SearchSchedule.next_run_at)
    ).all()
    return [s for s in rows if (_as_utc(s.next_run_at) or now) <= now]


def active_search_string(db: Session, product_id: int) -> SearchString | None:
    return db.scalars(
        select(SearchString)
        .where(
            SearchString.product_id == product_id,
            SearchString.is_active.is_(True),
        )
        .order_by(SearchString.version.desc())
    ).first()


async def run_schedule(db: Session, schedule: SearchSchedule) -> dict:
    """Fire one schedule and advance it.

    The schedule is always advanced, success or failure, so a persistently
    failing product cannot wedge the runner in a retry loop.
    """
    # Imported here to avoid a circular import at module load.
    from app.services.pipeline import run_search

    now = datetime.now(timezone.utc)
    outcome: dict = {"schedule_id": schedule.id, "product_id": schedule.product_id}

    if is_expired(schedule, now.date()):
        schedule.is_active = False
        schedule.last_status = "expired"
        db.commit()
        return {**outcome, "status": "expired"}

    search_string = active_search_string(db, schedule.product_id)
    if not search_string:
        schedule.last_status = "no_active_search_string"
        schedule.last_error = "Product has no active search string"
        schedule.last_run_at = now
        schedule.next_run_at = advance_past(now, schedule.frequency, now)
        from app.services import triggers

        product = db.get(Product, schedule.product_id)
        if product:
            triggers.search_failed(
                db,
                product=product,
                user_id=product.primary_reviewer_id,
                run_id=f"schedule-{schedule.id}-no-string-{now:%Y-%m-%d}",
                error=schedule.last_error,
            )
        db.commit()
        return {**outcome, "status": "no_active_search_string"}

    date_to = now.date()
    date_from = date_to - timedelta(days=schedule.lookback_days)
    try:
        run = await run_search(
            db,
            search_string.id,
            date_from=date_from,
            date_to=date_to,
            triggered_by=f"schedule:{schedule.id}",
            max_fetch=schedule.max_fetch,
        )
        schedule.last_status = "completed"
        schedule.last_error = None
        outcome.update(
            {
                "status": "completed",
                "search_run_id": run.id,
                "new_articles": run.new_article_count,
            }
        )
    except Exception as exc:  # noqa: BLE001 - schedule must survive any failure
        logger.exception("Scheduled search failed for schedule %s", schedule.id)
        schedule.last_status = "failed"
        schedule.last_error = str(exc)[:1000]
        outcome.update({"status": "failed", "error": str(exc)[:300]})

    schedule.last_run_at = now
    schedule.run_count = (schedule.run_count or 0) + 1
    schedule.next_run_at = advance_past(now, schedule.frequency, now)
    # A schedule whose next run falls past the end date is finished.
    if schedule.next_run_at.date() > schedule.end_date:
        schedule.is_active = False

    log_event(
        db,
        actor=f"schedule:{schedule.id}",
        action="scheduled_search_run",
        entity_type="search_schedule",
        entity_id=str(schedule.id),
        payload=outcome,
    )
    db.commit()
    return outcome


async def run_due_schedules(db: Session) -> list[dict]:
    results = []
    for schedule in due_schedules(db):
        results.append(await run_schedule(db, schedule))
    return results


# ── Background runner ────────────────────────────────────────────────────────

_runner_task: asyncio.Task | None = None


async def _runner_loop() -> None:
    interval = get_settings().schedule_tick_seconds
    logger.info("Schedule runner started (tick=%ss)", interval)
    while True:
        try:
            await asyncio.sleep(interval)
            db = SessionLocal()
            try:
                fired = await run_due_schedules(db)
                from app.services import triggers

                time_alerts = triggers.run_time_driven_alerts(db)
                if fired:
                    logger.info("Fired %d scheduled search(es)", len(fired))
                if any(time_alerts[key] for key in ("overdue", "due_soon", "unmonitored_products")):
                    logger.info("Time-driven alerts: %s", time_alerts)
            finally:
                db.close()
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - the loop must never die
            logger.exception("Schedule runner tick failed")


def start_runner() -> None:
    global _runner_task
    if _runner_task and not _runner_task.done():
        return
    _runner_task = asyncio.create_task(_runner_loop())


async def stop_runner() -> None:
    global _runner_task
    if _runner_task and not _runner_task.done():
        _runner_task.cancel()
        try:
            await _runner_task
        except asyncio.CancelledError:
            pass
    _runner_task = None
