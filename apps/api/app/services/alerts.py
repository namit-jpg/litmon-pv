from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Alert
from app.services.audit import log_event


def create_alert(
    db: Session,
    *,
    user_id: int | None,
    alert_type: str,
    title: str,
    message: str,
    article_id: int | None = None,
    priority: str = "normal",
    dedupe_key: str | None = None,
) -> Alert | None:
    if not user_id:
        return None
    if dedupe_key:
        existing = db.scalars(
            select(Alert).where(Alert.dedupe_key == dedupe_key)
        ).first()
        if existing:
            return existing
    # This MVP deliberately implements the auditable in-app inbox only.
    # Keeping a list preserves a future extension point without claiming that
    # email, SMS, chat or push delivery occurred.
    channels = ["in_app"]
    alert = Alert(
        user_id=user_id,
        article_id=article_id,
        alert_type=alert_type,
        priority=priority,
        channels=channels,
        title=title,
        message=message,
        dedupe_key=dedupe_key,
    )
    db.add(alert)
    db.flush()
    log_event(
        db,
        actor="system",
        action="alert_created",
        entity_type="alert",
        entity_id=alert.id,
        payload={"user_id": user_id, "article_id": article_id, "type": alert_type},
    )
    return alert


def mark_alert_read(db: Session, alert: Alert, *, actor: str) -> Alert:
    if alert.read_at is None:
        alert.read_at = datetime.now(timezone.utc)
        log_event(
            db,
            actor=actor,
            action="alert_read",
            entity_type="alert",
            entity_id=alert.id,
        )
    return alert
