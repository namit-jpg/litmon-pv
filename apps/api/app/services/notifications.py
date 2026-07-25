"""Notification stub — logs SLA breaches; optional SMTP later."""

from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage
from typing import Any

from app.core.config import get_settings
from app.core.metrics import metrics

logger = logging.getLogger("litmon.notify")


def notify(
    subject: str,
    body: str,
    *,
    level: str = "info",
    meta: dict[str, Any] | None = None,
) -> None:
    settings = get_settings()
    log = logger.info if level == "info" else logger.warning
    log("NOTIFY %s | %s | meta=%s", subject, body, meta or {})
    metrics.notifications_sent += 1

    if not settings.notify_email_enabled or not settings.notify_smtp_host:
        return
    if not settings.notify_to:
        return

    msg = EmailMessage()
    msg["Subject"] = f"[LitMon-PV] {subject}"
    msg["From"] = settings.notify_from
    msg["To"] = settings.notify_to
    msg.set_content(body + "\n\n" + str(meta or {}))

    try:
        with smtplib.SMTP(
            settings.notify_smtp_host, settings.notify_smtp_port, timeout=15
        ) as smtp:
            if settings.notify_smtp_tls:
                smtp.starttls()
            if settings.notify_smtp_user:
                smtp.login(settings.notify_smtp_user, settings.notify_smtp_password)
            smtp.send_message(msg)
    except Exception:
        logger.exception("SMTP notification failed")


def notify_sla_breaches(items: list[dict[str, Any]]) -> None:
    if not items:
        return
    lines = [
        f"- article #{i['id']} PMID {i['pmid']} queue={i['queue']} due={i['sla_due_at']}"
        for i in items[:50]
    ]
    notify(
        f"SLA breach: {len(items)} article(s) overdue",
        "The following open articles have passed their SLA due time:\n"
        + "\n".join(lines),
        level="warning",
        meta={"count": len(items)},
    )
