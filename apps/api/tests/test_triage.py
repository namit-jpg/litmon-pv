from app.services.ai.schemas import ScreeningOutput
from app.services.triage.engine import route_screening
from app.models.entities import QueueType


def test_auto_clear_band():
    out = ScreeningOutput(
        product_match=0.05,
        event_relevance=0.05,
        icsr_criteria_match=0.05,
    )
    d = route_screening(out)
    assert d.queue == QueueType.AUTO_CLEAR


def test_hard_rule_forces_expedited():
    out = ScreeningOutput(
        product_match=0.1,
        event_relevance=0.1,
        icsr_criteria_match=0.1,
        hard_rule_candidates=["death_with_product"],
    )
    d = route_screening(out)
    assert d.queue == QueueType.EXPEDITED
    assert d.hard_rule_triggered is True


def test_priority_band():
    out = ScreeningOutput(
        product_match=0.8,
        event_relevance=0.7,
        icsr_criteria_match=0.7,
    )
    # composite ~ 0.735
    d = route_screening(out)
    assert d.queue == QueueType.PRIORITY
