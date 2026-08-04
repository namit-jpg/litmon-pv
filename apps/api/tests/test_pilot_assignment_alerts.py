import asyncio

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.api.routes import submit_review, update_product
from app.core.database import Base
from app.models import Alert, Article, Product, User
from app.models.entities import ArticleStatus, Role, SignalStatus
from app.schemas.api import ProductUpdate, ReviewIn
from app.services.alerts import create_alert, mark_alert_read
from app.services.pipeline import score_and_route_article


def session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_screening_assigns_product_reviewer_and_creates_alert(monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "llm_mock", True)
    db = session()
    reviewer = User(
        email="pilot-reviewer@example.com",
        full_name="Pilot Reviewer",
        hashed_password="unused",
        role=Role.REVIEWER,
    )
    db.add(reviewer)
    db.flush()
    product = Product(
        name="Pilot Product",
        inn="pilotdrug",
        brands=["PilotBrand"],
        synonyms=["pilotdrug"],
        primary_reviewer_id=reviewer.id,
    )
    db.add(product)
    db.flush()
    article = Article(
        product_id=product.id,
        pmid="pilot-assignment-1",
        title="Fatal reaction after PilotBrand: a case report",
        abstract="A patient died after receiving PilotBrand.",
        status=ArticleStatus.INGESTED,
    )
    db.add(article)
    db.flush()

    asyncio.run(score_and_route_article(db, article, product))
    db.commit()

    assert article.assignee_id == reviewer.id
    alert = db.scalars(select(Alert).where(Alert.article_id == article.id)).first()
    assert alert is not None
    assert alert.user_id == reviewer.id
    assert alert.alert_type == "work_assigned"


def test_signal_action_is_human_recorded_and_alerted():
    db = session()
    reviewer = User(
        email="signal-reviewer@example.com",
        full_name="Signal Reviewer",
        hashed_password="unused",
        role=Role.REVIEWER,
    )
    db.add(reviewer)
    db.flush()
    product = Product(name="Signal Product", primary_reviewer_id=reviewer.id)
    db.add(product)
    db.flush()
    article = Article(
        product_id=product.id,
        pmid="pilot-signal-1",
        title="Potential safety pattern",
        status=ArticleStatus.ROUTED,
        assignee_id=reviewer.id,
    )
    db.add(article)
    db.commit()

    decision = submit_review(
        article.id,
        ReviewIn(action="mark_potential_signal", rationale="PV review required"),
        db=db,
        user=reviewer,
    )

    assert decision.reviewer_id == reviewer.id
    assert article.signal_status == SignalStatus.POTENTIAL
    assert db.scalars(
        select(Alert).where(Alert.alert_type == "signal_status_changed")
    ).first()


def test_alert_deduplication_and_read_state():
    db = session()
    reviewer = User(
        email="alert-reviewer@example.com",
        full_name="Alert Reviewer",
        hashed_password="unused",
        role=Role.REVIEWER,
    )
    db.add(reviewer)
    db.flush()
    first = create_alert(
        db,
        user_id=reviewer.id,
        alert_type="demo",
        title="Demo",
        message="Pilot alert",
        dedupe_key="demo:1",
    )
    second = create_alert(
        db,
        user_id=reviewer.id,
        alert_type="demo",
        title="Demo duplicate",
        message="Should reuse existing",
        dedupe_key="demo:1",
    )
    assert first is not None
    assert second is not None
    assert first.id == second.id
    mark_alert_read(db, first, actor=reviewer.email)
    db.commit()
    assert first.read_at is not None


def test_product_reviewer_change_reassigns_open_work():
    db = session()
    admin = User(
        email="assignment-admin@example.com",
        full_name="Assignment Admin",
        hashed_password="unused",
        role=Role.ADMIN,
    )
    reviewer = User(
        email="new-reviewer@example.com",
        full_name="New Reviewer",
        hashed_password="unused",
        role=Role.REVIEWER,
    )
    db.add_all([admin, reviewer])
    db.flush()
    product = Product(name="Reassignment Product")
    db.add(product)
    db.flush()
    article = Article(
        product_id=product.id,
        pmid="pilot-reassignment-1",
        title="Open literature review",
        status=ArticleStatus.ROUTED,
    )
    db.add(article)
    db.commit()

    update_product(
        product.id,
        ProductUpdate(primary_reviewer_id=reviewer.id),
        db=db,
        user=admin,
    )

    assert product.primary_reviewer_id == reviewer.id
    assert article.assignee_id == reviewer.id
    assert db.scalars(
        select(Alert).where(Alert.article_id == article.id, Alert.user_id == reviewer.id)
    ).first()


def test_same_pmid_can_be_monitored_for_two_products():
    db = session()
    first_product = Product(name="PMID Product One")
    second_product = Product(name="PMID Product Two")
    db.add_all([first_product, second_product])
    db.flush()
    first = Article(
        product_id=first_product.id,
        pmid="shared-pmid-1",
        title="Shared article for first product",
    )
    second = Article(
        product_id=second_product.id,
        pmid="shared-pmid-1",
        title="Shared article for second product",
    )
    db.add_all([first, second])
    db.commit()

    matches = list(
        db.scalars(select(Article).where(Article.pmid == "shared-pmid-1")).all()
    )
    assert {article.product_id for article in matches} == {
        first_product.id,
        second_product.id,
    }
