"""Phase 2 contracts: filterable workspace and human regulatory workflow."""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.api.routes import (
    generate_regulatory_article,
    dashboard_metrics,
    list_articles,
    queue_stats,
    record_manual_submission,
    record_regulatory_decision,
    validate_regulatory_article,
)
from app.core.config import get_settings
from app.core.database import Base
from app.models import Article, LiteratureSource, Product, ReviewDecision, User
from app.models.entities import (
    ArticleStatus,
    Classification,
    DecisionAction,
    Priority,
    Role,
    SubmissionStatus,
)
from app.schemas.api import (
    RegulatoryDecisionIn,
    RegulatoryGenerateIn,
    RegulatorySubmissionIn,
)


def session():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def fixture(db):
    lead = User(
        email="lead-phase2@example.com",
        full_name="PV Lead",
        hashed_password="unused",
        role=Role.PV_LEAD,
    )
    product = Product(name="Phase 2 Product", inn="phase2drug", brands=[], synonyms=[])
    source = LiteratureSource(name="Phase 2 Source", provider="Test", is_enabled=True)
    db.add_all([lead, product, source])
    db.flush()
    article = Article(
        product_id=product.id,
        pmid="phase2-1",
        title="Phase 2 literature case",
        status=ArticleStatus.AWAITING_REVIEW,
        priority=Priority.P1,
        ai_classification=Classification.POTENTIALLY_RELEVANT,
        literature_source_id=source.id,
        assignee_id=lead.id,
    )
    db.add(article)
    db.flush()
    return lead, article, source


def test_workspace_filters_use_effective_classification_priority_and_source():
    db = session()
    lead, article, source = fixture(db)
    items = list_articles(
        queue=None,
        status=None,
        product_id=None,
        active_ingredient_id=None,
        date_from=None,
        date_to=None,
        literature_source_id=source.id,
        classification=Classification.POTENTIALLY_RELEVANT,
        priority=Priority.P1,
        submission_status=None,
        review_status="open",
        q=None,
        open_only=True,
        include_archive=False,
        overdue_only=False,
        mine_only=False,
        assignee_id=None,
        signal_status=None,
        db=db,
        user=lead,
    )
    assert [item.id for item in items] == [article.id]
    assert items[0].effective_classification == Classification.POTENTIALLY_RELEVANT
    assert items[0].literature_source_name == source.name

    stats = queue_stats(mine_only=True, db=db, user=lead)
    assert stats.classification_counts[Classification.POTENTIALLY_RELEVANT.value] == 1
    metrics = dashboard_metrics(mine_only=True, db=db, user=lead)
    potential = next(metric for metric in metrics["metrics"] if metric["key"] == "potential_signals")
    assert potential["filter"] == {
        "signal_status": "potential_signal",
        "review_status": "all",
    }


def test_regulatory_generation_is_configured_and_manual_submission_only(monkeypatch):
    db = session()
    lead, article, _ = fixture(db)
    db.add(
        ReviewDecision(
            article_id=article.id,
            reviewer_id=lead.id,
            action=DecisionAction.PREPARE_FOR_SUBMISSION,
            suspect_products=["Phase 2 Product"],
            event_terms=["Example reaction"],
            identifiable_reporter=True,
        )
    )
    db.commit()

    settings = get_settings()
    monkeypatch.setattr(settings, "regulatory_mandatory_fields_json", "")
    blocked = validate_regulatory_article(article.id, db=db, _=lead)
    assert blocked["can_generate"] is False
    assert "not configured" in blocked["blocking_errors"][0]

    monkeypatch.setattr(
        settings,
        "regulatory_mandatory_fields_json",
        '[{"field":"pmid"},{"field":"suspect_products"},{"field":"adverse_events"}]',
    )
    validation = validate_regulatory_article(article.id, db=db, _=lead)
    assert validation["can_generate"] is True

    record = record_regulatory_decision(
        article.id,
        RegulatoryDecisionIn(
            decision=SubmissionStatus.APPROVED_FOR_SUBMISSION, reason="PV lead approved"
        ),
        db=db,
        user=lead,
    )
    assert record.decision == SubmissionStatus.APPROVED_FOR_SUBMISSION
    package = generate_regulatory_article(
        article.id,
        RegulatoryGenerateIn(),
        db=db,
        user=lead,
    )
    assert package.payload_json["regulatory"]["version"] == 1

    submitted = record_manual_submission(
        article.id,
        RegulatorySubmissionIn(
            gateway="Not yet confirmed", submission_reference="MANUAL-123"
        ),
        db=db,
        user=lead,
    )
    assert submitted.decision == SubmissionStatus.SUBMITTED
    assert article.status == ArticleStatus.SUBMITTED
