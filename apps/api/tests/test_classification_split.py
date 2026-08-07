"""The status / classification / signal-tag split.

The old ArticleStatus conflated workflow position with outcome. These tests pin
down the three things that separation is supposed to buy us: an article can be
a signal *and* awaiting review, the AI's proposal survives a human override,
and a confirmed signal needs a PV lead plus a recorded decision.
"""

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.api.routes import _set_signal_tag, submit_review
from app.core.database import Base
from app.models import (
    Article,
    ArticleSignalTag,
    AuditEvent,
    Product,
    RegulatoryRecord,
    User,
)
from app.models.entities import (
    CLOSED_STATUSES,
    WORKSPACE_FOLDERS,
    ArticleStatus,
    Classification,
    DecisionAction,
    Role,
    SignalTag,
    SubmissionStatus,
)
from app.schemas.api import ReviewIn


def session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _fixture(db, role=Role.REVIEWER):
    user = User(
        email=f"{role.value}@example.com",
        full_name="Reviewer",
        hashed_password="unused",
        role=role,
    )
    db.add(user)
    db.flush()
    product = Product(name="Split Product", inn="splitdrug", brands=[], synonyms=[])
    db.add(product)
    db.flush()
    article = Article(
        product_id=product.id,
        pmid="split-1",
        title="A case report",
        status=ArticleStatus.AWAITING_REVIEW,
        ai_classification=Classification.POTENTIALLY_RELEVANT,
    )
    db.add(article)
    db.flush()
    return user, product, article


def test_signal_tag_and_workflow_status_are_independent():
    """The point of the split: being a signal says nothing about position."""
    db = session()
    user, _, article = _fixture(db)

    submit_review(
        article.id,
        ReviewIn(action=DecisionAction.MARK_POTENTIAL_SIGNAL, rationale="fatal outcome"),
        db=db,
        user=user,
    )

    tags = db.scalars(
        select(ArticleSignalTag.tag).where(ArticleSignalTag.article_id == article.id)
    ).all()
    assert SignalTag.POTENTIAL_SIGNAL in tags
    # Still open work, not a terminal state — impossible under the old enum.
    assert article.status not in CLOSED_STATUSES


def test_human_classification_does_not_overwrite_the_ai_proposal():
    db = session()
    user, _, article = _fixture(db)
    assert article.ai_classification == Classification.POTENTIALLY_RELEVANT

    submit_review(
        article.id,
        ReviewIn(action=DecisionAction.MARK_NOT_RELEVANT, rationale="off-target"),
        db=db,
        user=user,
    )

    assert article.human_classification == Classification.IRRELEVANT
    assert article.ai_classification == Classification.POTENTIALLY_RELEVANT


def test_confirmed_signal_requires_pv_lead():
    db = session()
    reviewer, _, article = _fixture(db)
    with pytest.raises(HTTPException) as exc:
        _set_signal_tag(db, article, SignalTag.CONFIRMED_SIGNAL, reviewer)
    assert exc.value.status_code == 403


def test_confirmed_signal_requires_a_recorded_decision():
    """No report becomes a confirmed signal without a human assessment."""
    db = session()
    lead, _, article = _fixture(db, role=Role.PV_LEAD)
    with pytest.raises(HTTPException) as exc:
        _set_signal_tag(db, article, SignalTag.CONFIRMED_SIGNAL, lead)
    assert exc.value.status_code == 409

    # With a decision on file, the same call succeeds.
    submit_review(
        article.id,
        ReviewIn(action=DecisionAction.MARK_POTENTIAL_SIGNAL, rationale="raising"),
        db=db,
        user=lead,
    )
    tag = _set_signal_tag(db, article, SignalTag.CONFIRMED_SIGNAL, lead)
    assert tag.tag == SignalTag.CONFIRMED_SIGNAL
    assert tag.is_ai_proposed is False


def test_signal_tags_are_idempotent():
    db = session()
    lead, _, article = _fixture(db, role=Role.PV_LEAD)
    first = _set_signal_tag(db, article, SignalTag.SERIOUS_ADVERSE_EVENT, lead)
    db.flush()
    again = _set_signal_tag(db, article, SignalTag.SERIOUS_ADVERSE_EVENT, lead)
    assert first is again


def test_every_workspace_folder_resolves_to_real_statuses_or_tags():
    """The nine wireframe folders must not reference members that don't exist."""
    assert len(WORKSPACE_FOLDERS) == 9
    for name, spec in WORKSPACE_FOLDERS.items():
        assert spec.get("statuses") or spec.get("signal_tags"), name
        for status in spec.get("statuses", []):
            assert isinstance(status, ArticleStatus)
        for tag in spec.get("signal_tags", []):
            assert isinstance(tag, SignalTag)


def test_new_decision_actions_land_on_the_right_folder():
    cases = [
        (DecisionAction.MARK_INVALID, ArticleStatus.EXCEPTION),
        (DecisionAction.MARK_DUPLICATE, ArticleStatus.ARCHIVED),
        (DecisionAction.PREPARE_FOR_SUBMISSION, ArticleStatus.APPROVED_FOR_SUBMISSION),
        (DecisionAction.RETAIN_INTERNALLY, ArticleStatus.NOT_FOR_SUBMISSION),
        (DecisionAction.CLOSE_REPORT, ArticleStatus.ARCHIVED),
    ]
    for action, expected in cases:
        db = session()
        user, _, article = _fixture(db)
        submit_review(
            article.id, ReviewIn(action=action, rationale="x"), db=db, user=user
        )
        assert article.status == expected, action


def test_submission_decision_syncs_regulatory_record_tags_and_audit_evidence():
    db = session()
    user, _, article = _fixture(db)
    submit_review(
        article.id,
        ReviewIn(
            action=DecisionAction.PREPARE_FOR_SUBMISSION,
            rationale="Meets the four minimum criteria",
            supporting_documents=["controlled://full-text/123"],
        ),
        db=db,
        user=user,
    )

    record = db.scalar(
        select(RegulatoryRecord).where(RegulatoryRecord.article_id == article.id)
    )
    assert record is not None
    assert record.decision == SubmissionStatus.APPROVED_FOR_SUBMISSION
    assert record.decision_reason == "Meets the four minimum criteria"
    assert SignalTag.SUBMISSION_REQUIRED in {
        row.tag for row in article.signal_tags
    }
    assert article.review_decisions[0].supporting_documents == [
        "controlled://full-text/123"
    ]
    event = db.scalar(
        select(AuditEvent)
        .where(AuditEvent.action == "review_prepare_for_submission")
        .order_by(AuditEvent.id.desc())
    )
    assert event.payload["previous_status"] == ArticleStatus.AWAITING_REVIEW.value
    assert event.payload["new_status"] == ArticleStatus.APPROVED_FOR_SUBMISSION.value
