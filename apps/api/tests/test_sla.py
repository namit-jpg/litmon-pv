from datetime import datetime, timedelta, timezone

from app.services.sla import list_overdue_articles
from app.models.entities import (
    Article,
    ArticleStatus,
    Product,
    QueueType,
    ScreeningResult,
    TriageAssignment,
)
from app.core.database import Base, SessionLocal, engine
import app.models  # noqa: F401


def test_list_overdue():
    import uuid

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        suffix = uuid.uuid4().hex[:8]
        p = Product(
            name=f"SLA Test Product {suffix}",
            brands=[],
            synonyms=["X"],
            is_active=True,
        )
        db.add(p)
        db.flush()
        a = Article(
            product_id=p.id,
            pmid=f"sla{suffix}",
            title="Overdue test",
            status=ArticleStatus.ROUTED,
        )
        db.add(a)
        db.flush()
        s = ScreeningResult(
            article_id=a.id,
            product_match=0.9,
            event_relevance=0.9,
            icsr_criteria_match=0.9,
            composite=0.9,
            entities={},
            icsr_precheck={},
            reason_tags=[],
            hard_rule_candidates=[],
            model_id="t",
            prompt_version="v",
            ruleset_version="v",
            threshold_version="v",
        )
        db.add(s)
        db.flush()
        t = TriageAssignment(
            article_id=a.id,
            screening_result_id=s.id,
            queue=QueueType.EXPEDITED,
            sla_hours=24,
            sla_due_at=datetime.now(timezone.utc) - timedelta(hours=5),
            hard_rule_triggered=True,
            hard_rules=["death_with_product"],
            ruleset_version="v",
            threshold_version="v",
            is_active=True,
        )
        db.add(t)
        db.commit()
        items = list_overdue_articles(db)
        assert any(i["pmid"] == f"sla{suffix}" for i in items)
    finally:
        db.close()
