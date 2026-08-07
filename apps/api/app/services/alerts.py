from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Alert
from app.core.config import get_settings
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
    channels = ["in_app"]
    if get_settings().notify_email_enabled:
        channels.append("email")
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
