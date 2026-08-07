"""SLA helpers — overdue open articles for expedited/standard/priority queues."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Article, TriageAssignment
from app.models.entities import CLOSED_STATUSES, QueueType

CLOSED = set(CLOSED_STATUSES)


def list_overdue_articles(db: Session, now: datetime | None = None) -> list[dict[str, Any]]:
    now = now or datetime.now(timezone.utc)
    # SQLite may store naive datetimes — compare carefully
    rows = db.scalars(
        select(TriageAssignment)
        .where(TriageAssignment.is_active.is_(True))
        .where(
            TriageAssignment.queue.in_(
                [
                    QueueType.EXPEDITED,
                    QueueType.PRIORITY,
                    QueueType.STANDARD,
                    QueueType.QC_SAMPLE,
                ]
            )
        )
    ).all()

    out: list[dict[str, Any]] = []
    for t in rows:
        article = db.get(Article, t.article_id)
        if not article or article.status in CLOSED:
            continue
        due = t.sla_due_at
        if due is None:
            continue
        if due.tzinfo is None:
            due_cmp = due.replace(tzinfo=timezone.utc)
        else:
            due_cmp = due
        if due_cmp < now:
            hours_over = (now - due_cmp).total_seconds() / 3600
            out.append(
                {
                    "id": article.id,
                    "pmid": article.pmid,
                    "title": article.title,
                    "status": article.status.value,
                    "queue": t.queue.value,
                    "sla_due_at": due_cmp.isoformat(),
                    "hours_overdue": round(hours_over, 2),
                    "hard_rule_triggered": t.hard_rule_triggered,
                }
            )
    out.sort(key=lambda x: x["hours_overdue"], reverse=True)
    return out


def list_due_soon_articles(
    db: Session, *, within_hours: int = 24, now: datetime | None = None
) -> list[dict[str, Any]]:
    """Open articles inside their SLA warning window but not yet breached.

    Separate from :func:`list_overdue_articles` on purpose: warning someone a
    deadline is coming and telling them it has passed are different alerts with
    different priorities, and collapsing them would mean the warning only ever
    arrives too late.
    """
    now = now or datetime.now(timezone.utc)
    horizon = now + timedelta(hours=within_hours)
    out: list[dict[str, Any]] = []
    rows = db.scalars(
        select(TriageAssignment).where(TriageAssignment.is_active.is_(True))
    ).all()
    for t in rows:
        article = db.get(Article, t.article_id)
        if not article or article.status in CLOSED:
            continue
        due = t.sla_due_at
        if due is None:
            continue
        due_cmp = due.replace(tzinfo=timezone.utc) if due.tzinfo is None else due
        if now <= due_cmp <= horizon:
            out.append(
                {
                    "id": article.id,
                    "pmid": article.pmid,
                    "title": article.title,
                    "queue": t.queue.value,
                    "sla_due_at": due_cmp.isoformat(),
                    "hours_left": round((due_cmp - now).total_seconds() / 3600, 2),
                }
            )
    out.sort(key=lambda x: x["hours_left"])
    return out


def sla_summary(db: Session) -> dict[str, Any]:
    overdue = list_overdue_articles(db)
    by_queue: dict[str, int] = {}
    for item in overdue:
        by_queue[item["queue"]] = by_queue.get(item["queue"], 0) + 1
    return {
        "overdue_total": len(overdue),
        "by_queue": by_queue,
        "worst": overdue[:10],
    }
