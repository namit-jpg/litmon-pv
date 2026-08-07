"""The eight alert triggers from the partner's step 7, in one place.

Before this module the pipeline had exactly one trigger — an SLA breach — and
it was surfaced as a single button on the Ops page. The triggers were listed as
a numbered set in the feedback, so they are defined here as a numbered set
rather than scattered across the call sites that happen to fire them. Every one
routes through :func:`app.services.alerts.create_alert`, so an alert is a
record with a recipient, a priority, channels and a read state — not a log line
that disappears.

Each function is a no-op when there is no recipient. Alerting nobody is a
silent failure, so the caller's routing decision is respected rather than
guessed at here.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Alert, Article, Product, SearchSchedule
from app.models.entities import (
    ArticleStatus,
    Classification,
    ExceptionCause,
    ScheduleFrequency,
)
from app.services.alerts import create_alert

#: Terms that make a result serious enough to alert on immediately. Matched as
#: substrings because the extractor returns free text ("fatal outcome",
#: "life-threatening"), not a controlled vocabulary.
SERIOUS_TERMS = (
    "fatal",
    "death",
    "died",
    "life-threatening",
    "life threatening",
    "hospitali",
    "disabling",
    "congenital",
    "anomaly",
)

#: How long after a scheduled run's due time we wait before calling a product
#: unmonitored. One extra period, so a single late run is not an incident.
FREQUENCY_DAYS: dict[ScheduleFrequency, int] = {
    ScheduleFrequency.DAILY: 1,
    ScheduleFrequency.WEEKLY: 7,
    ScheduleFrequency.MONTHLY: 31,
}


def _is_serious(seriousness: str | None) -> bool:
    if not seriousness:
        return False
    text = seriousness.strip().lower()
    # "non-serious" contains "serious", so an exclusion has to come first.
    if text.startswith("non") or text.startswith("not "):
        return False
    return any(term in text for term in SERIOUS_TERMS)


# ── 1 · Signal detected ───────────────────────────────────────────────


def signal_detected(
    db: Session, *, article: Article, user_id: int | None, confidence: float | None = None
) -> Alert | None:
    """The pipeline classified an article as a potential safety signal."""
    detail = f"Confidence {confidence:.2f}. " if confidence is not None else ""
    return create_alert(
        db,
        user_id=user_id,
        article_id=article.id,
        alert_type="signal_detected",
        priority="high",
        title=f"Potential safety signal detected — {article.product.name if article.product else 'product'}",
        message=f"{detail}{article.title}",
        dedupe_key=f"signal-detected:{article.id}",
    )


# ── 2 · Serious result ────────────────────────────────────────────────


def serious_result(
    db: Session, *, article: Article, user_id: int | None, seriousness: str
) -> Alert | None:
    """Extraction reported a serious outcome — death, life-threatening, etc."""
    return create_alert(
        db,
        user_id=user_id,
        article_id=article.id,
        alert_type="serious_result",
        priority="high",
        title=f"Serious outcome reported — {article.product.name if article.product else 'product'}",
        message=f"Seriousness: {seriousness}. {article.title}",
        dedupe_key=f"serious:{article.id}",
    )


# ── 3 · Processing failure ────────────────────────────────────────────


def processing_exception(
    db: Session,
    *,
    article: Article,
    user_id: int | None,
    cause: ExceptionCause,
    detail: str = "",
) -> Alert | None:
    """Something the pipeline could not complete landed in the exception queue.

    The alert type carries the cause so the exception summary can report which
    causes have been alerted on, rather than collapsing them into one bucket
    while the meaning of "invalid" is still unresolved.
    """
    label = cause.value.replace("_", " ")
    return create_alert(
        db,
        user_id=user_id,
        article_id=article.id,
        alert_type=f"exception_{cause.value}",
        priority="normal",
        title=f"Processing exception — {label}",
        message=f"{article.title}{f' — {detail}' if detail else ''}",
        dedupe_key=f"exception:{article.id}:{cause.value}",
    )


# ── 4 · Awaiting review ───────────────────────────────────────────────


def awaiting_review(
    db: Session, *, article: Article, user_id: int | None, queue: str, high: bool
) -> Alert | None:
    """New literature was routed to a reviewer and is waiting on them."""
    return create_alert(
        db,
        user_id=user_id,
        article_id=article.id,
        alert_type="work_assigned",
        priority="high" if high else "normal",
        title=f"{queue.replace('_', ' ').title()} literature review assigned",
        message=article.title,
        dedupe_key=f"assignment:{article.id}",
    )


# ── 5 · Deadline approaching ──────────────────────────────────────────


def review_deadline_approaching(
    db: Session, *, article: Article, hours_left: float
) -> Alert | None:
    """An open review is inside its warning window but not yet breached."""
    return create_alert(
        db,
        user_id=article.assignee_id,
        article_id=article.id,
        alert_type="review_deadline_approaching",
        priority="normal",
        title="Review deadline approaching",
        message=f"{article.title} is due in {hours_left:.0f} hours.",
        dedupe_key=f"due-soon:{article.id}",
    )


# ── 6 · Unresolved past review period ─────────────────────────────────


def review_overdue(db: Session, *, article: Article, hours_overdue: float) -> Alert | None:
    """An open review has passed its SLA."""
    return create_alert(
        db,
        user_id=article.assignee_id,
        article_id=article.id,
        alert_type="review_overdue",
        priority="high",
        title="Literature review overdue",
        message=f"{article.title} is {hours_overdue:.0f} hours overdue.",
        dedupe_key=f"overdue:{article.id}",
    )


# ── 7 · Scheduled search failed ───────────────────────────────────────


def search_failed(
    db: Session, *, product: Product, user_id: int | None, run_id: int | str, error: str
) -> Alert | None:
    """A scheduled or manual search run failed after its retries."""
    return create_alert(
        db,
        user_id=user_id,
        alert_type="search_failed",
        priority="high",
        title=f"Scheduled search failed — {product.name}",
        message=error,
        dedupe_key=f"search-failed:{run_id}",
    )


# ── 8 · No search completed in the expected period ────────────────────


def check_unmonitored_products(db: Session, now: datetime | None = None) -> list[dict[str, Any]]:
    """Alert on any product with no completed search in its monitoring period.

    This is the trigger that catches the silent failure mode: a schedule that
    stops firing produces no error anywhere, so without this check a product
    can go unmonitored indefinitely and nothing says so. Two of the wireframe's
    banners depend on it.
    """
    now = now or datetime.now(timezone.utc)
    stale: list[dict[str, Any]] = []
    schedules = db.scalars(
        select(SearchSchedule).where(SearchSchedule.is_active.is_(True))
    ).all()
    for schedule in schedules:
        product = db.get(Product, schedule.product_id)
        if not product or not product.is_active:
            continue
        period = FREQUENCY_DAYS.get(schedule.frequency, 7)
        # One full period of grace on top of the interval, so a run that is
        # merely late does not read as an outage.
        deadline = now - timedelta(days=period * 2)
        last_run = schedule.last_run_at
        if last_run is not None and last_run.tzinfo is None:
            last_run = last_run.replace(tzinfo=timezone.utc)
        succeeded_recently = (
            last_run is not None
            and last_run >= deadline
            and schedule.last_status == "completed"
        )
        if succeeded_recently:
            continue
        days = int((now - last_run).total_seconds() // 86400) if last_run else None
        stale.append(
            {
                "product_id": product.id,
                "product_name": product.name,
                "frequency": schedule.frequency.value,
                "last_run_at": last_run.isoformat() if last_run else None,
                "days_since_last_run": days,
            }
        )
        create_alert(
            db,
            user_id=product.primary_reviewer_id,
            alert_type="no_search_in_period",
            priority="high",
            title=f"No search completed in the expected period — {product.name}",
            message=(
                f"Configured {schedule.frequency.value}. "
                + (
                    f"Last successful run was {last_run:%d %b %Y}, {days} days ago."
                    if last_run
                    else "No successful run has been recorded."
                )
            ),
            # Re-alert once per day rather than once ever: an unmonitored
            # product stays a live problem until someone fixes it.
            dedupe_key=f"no-search:{product.id}:{now:%Y-%m-%d}",
        )
    db.commit()
    return stale


def run_time_driven_alerts(db: Session) -> dict[str, Any]:
    """Fire deadline, overdue, and monitoring-gap alerts.

    These three triggers depend on elapsed time rather than a pipeline event.
    The schedule runner calls this on every tick; dedupe keys keep frequent
    checks idempotent while the daily monitoring-gap key permits a reminder
    on the next day if the issue remains unresolved.
    """
    from app.services.sla import list_due_soon_articles, list_overdue_articles

    overdue = list_overdue_articles(db)
    for item in overdue:
        article = db.get(Article, int(item["id"]))
        if article:
            review_overdue(
                db, article=article, hours_overdue=float(item["hours_overdue"])
            )

    due_soon = list_due_soon_articles(db)
    for item in due_soon:
        article = db.get(Article, int(item["id"]))
        if article:
            review_deadline_approaching(
                db, article=article, hours_left=float(item["hours_left"])
            )

    db.commit()
    unmonitored = check_unmonitored_products(db)
    return {
        "overdue": len(overdue),
        "due_soon": len(due_soon),
        "unmonitored_products": len(unmonitored),
        "items": overdue[:100],
    }


# ── Pipeline entry point ──────────────────────────────────────────────


def on_article_scored(
    db: Session,
    *,
    article: Article,
    user_id: int | None,
    classification: Classification,
    confidence: float | None,
    seriousness: str | None,
) -> None:
    """Fire the content-driven triggers for a freshly scored article.

    Called once from the pipeline so that adding a trigger does not mean
    editing the scoring path again.
    """
    if classification == Classification.POTENTIAL_SAFETY_SIGNAL:
        signal_detected(db, article=article, user_id=user_id, confidence=confidence)
    if _is_serious(seriousness):
        serious_result(
            db, article=article, user_id=user_id, seriousness=str(seriousness)
        )


def flag_exception(
    db: Session,
    *,
    article: Article,
    cause: ExceptionCause,
    detail: str = "",
    user_id: int | None = None,
) -> None:
    """Move an article into the exception queue and alert on it.

    Nothing the pipeline cannot finish is allowed to be dropped — that was the
    explicit ask. The article keeps its assignee so the exception lands with a
    person rather than in a shared void.
    """
    article.status = ArticleStatus.EXCEPTION
    article.exception_cause = cause
    if article.ai_classification is None:
        article.ai_classification = (
            Classification.INSUFFICIENT_INFORMATION
            if cause == ExceptionCause.INSUFFICIENT_INFORMATION
            else Classification.REQUIRES_HUMAN_REVIEW
        )
    processing_exception(
        db,
        article=article,
        user_id=user_id or article.assignee_id,
        cause=cause,
        detail=detail,
    )
