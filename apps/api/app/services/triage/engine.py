"""Deterministic triage: score bands + hard-rule overrides + SLA timers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app.models.entities import QueueType
from app.services.ai.schemas import ScreeningOutput


@dataclass
class TriageDecision:
    queue: QueueType
    sla_hours: int
    sla_due_at: datetime
    hard_rule_triggered: bool
    hard_rules: list[str]
    band: str


# Starting thresholds — versioned as threshold_version in settings
BANDS = [
    # (max_exclusive composite upper... we use inclusive ranges carefully)
    ("auto_clear", 0.0, 0.15, QueueType.AUTO_CLEAR, 5 * 24, False),
    ("uncertain", 0.15, 0.65, QueueType.STANDARD, 5 * 24, False),
    ("likely_relevant", 0.65, 0.85, QueueType.PRIORITY, 2 * 24, False),
    ("high_icsr", 0.85, 1.01, QueueType.EXPEDITED, 24, False),
]


def route_screening(output: ScreeningOutput, now: datetime | None = None) -> TriageDecision:
    now = now or datetime.now(timezone.utc)
    composite = output.composite
    hard_rules = list(output.hard_rule_candidates or [])
    hard = len(hard_rules) > 0

    if hard:
        return TriageDecision(
            queue=QueueType.EXPEDITED,
            sla_hours=24,
            sla_due_at=now + timedelta(hours=24),
            hard_rule_triggered=True,
            hard_rules=hard_rules,
            band="hard_rule_expedited",
        )

    for name, lo, hi, queue, sla_h, _ in BANDS:
        if lo <= composite < hi:
            return TriageDecision(
                queue=queue,
                sla_hours=sla_h,
                sla_due_at=now + timedelta(hours=sla_h),
                hard_rule_triggered=False,
                hard_rules=[],
                band=name,
            )

    # Fallback — never drop
    return TriageDecision(
        queue=QueueType.STANDARD,
        sla_hours=5 * 24,
        sla_due_at=now + timedelta(hours=5 * 24),
        hard_rule_triggered=False,
        hard_rules=[],
        band="fallback_standard",
    )
