"""Phase 3 contracts: workspace folders, sources, tagging and alert triggers."""

import asyncio
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.api.routes import (
    dashboard_metrics,
    exception_summary,
    export_audit,
    list_articles,
    list_literature_sources,
    set_classification,
    set_signal_tags,
    source_connection_health,
    update_literature_source,
    workspace_folders,
)
from app.core.database import Base
from app.models import (
    Alert,
    Article,
    LiteratureSource,
    Product,
    ReviewDecision,
    SearchRun,
    SearchSchedule,
    SearchString,
    User,
)
from app.models.entities import (
    ArticleSignalTag,
    ArticleStatus,
    Classification,
    DecisionAction,
    ExceptionCause,
    Priority,
    Role,
    ScheduleFrequency,
    SearchRunStatus,
    SignalStatus,
    SignalTag,
)
from app.schemas.api import ClassificationIn, LiteratureSourceUpdate, SignalTagsIn
from app.services import triggers
from app.services.import_service import _screen_or_flag
from fastapi import HTTPException


def session():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def fixture(db):
    lead = User(
        email="lead-p3@example.com",
        full_name="PV Lead",
        hashed_password="unused",
        role=Role.PV_LEAD,
    )
    reviewer = User(
        email="reviewer-p3@example.com",
        full_name="R. Menon",
        hashed_password="unused",
        role=Role.REVIEWER,
    )
    db.add_all([lead, reviewer])
    db.flush()
    product = Product(
        name="Phase 3 Product",
        brands=[],
        synonyms=[],
        primary_reviewer_id=reviewer.id,
    )
    source = LiteratureSource(
        name="PubMed", provider="NLM / NCBI", retrieval="E-utilities", is_enabled=True
    )
    db.add_all([product, source])
    db.flush()
    return lead, reviewer, product, source


def folders(db, user, **kwargs):
    """Call the endpoint with its boolean flags resolved.

    Invoked directly rather than over HTTP, FastAPI's ``Query(default=False)``
    sentinels arrive as truthy objects, so every flag has to be passed.
    """
    return workspace_folders(
        queue=None,
        product_id=kwargs.get("product_id"),
        active_ingredient_id=None,
        date_from=None,
        date_to=None,
        literature_source_id=None,
        classification=None,
        priority=None,
        submission_status=None,
        q=None,
        mine_only=kwargs.get("mine_only", False),
        assignee_id=None,
        signal_status=None,
        db=db,
        user=user,
    )


def articles(db, user, **kwargs):
    """As above, for the article list."""
    return list_articles(
        folder=kwargs.get("folder"),
        queue=None,
        status=None,
        product_id=None,
        active_ingredient_id=None,
        date_from=None,
        date_to=None,
        literature_source_id=None,
        classification=None,
        priority=None,
        submission_status=None,
        review_status=kwargs.get("review_status"),
        q=None,
        open_only=kwargs.get("open_only", True),
        include_archive=False,
        overdue_only=False,
        mine_only=False,
        assignee_id=None,
        signal_status=None,
        db=db,
        user=user,
    )


def make_article(db, product, *, status, **kwargs):
    article = Article(
        product_id=product.id,
        pmid=kwargs.pop("pmid", f"p3-{status.value}"),
        title=kwargs.pop("title", "Phase 3 literature case"),
        status=status,
        **kwargs,
    )
    db.add(article)
    db.flush()
    return article


# ── Workspace folders ─────────────────────────────────────────────────


def test_folders_are_views_over_status_plus_signal_tag():
    """A potential signal shows in its tag folder while still awaiting review."""
    db = session()
    lead, reviewer, product, _ = fixture(db)
    awaiting = make_article(
        db, product, status=ArticleStatus.AWAITING_REVIEW, pmid="p3-await"
    )
    db.add(ArticleSignalTag(article_id=awaiting.id, tag=SignalTag.POTENTIAL_SIGNAL))
    make_article(db, product, status=ArticleStatus.ARCHIVED, pmid="p3-arch")
    db.flush()

    result = folders(db, lead)
    counts = {f["key"]: f["count"] for f in result["folders"]}
    assert counts["awaiting_review"] == 1
    # The same article is in both folders — that is the whole point of the split.
    assert counts["potential_signals"] == 1
    assert counts["archived"] == 1
    assert len(result["folders"]) == 9


def test_archived_folder_is_not_emptied_by_the_open_only_default():
    """The list defaults to open work; a folder must override that."""
    db = session()
    lead, _, product, _ = fixture(db)
    archived = make_article(
        db, product, status=ArticleStatus.ARCHIVED, pmid="p3-archived"
    )
    db.flush()
    items = articles(db, lead, folder="archived")
    assert [item.id for item in items] == [archived.id]


def test_unknown_folder_is_rejected():
    db = session()
    lead, _, _, _ = fixture(db)
    with pytest.raises(HTTPException) as exc:
        articles(db, lead, folder="not_a_folder")
    assert exc.value.status_code == 400


def test_workspace_sorts_by_priority_before_due_date():
    """A P1 with time left must outrank an overdue P3."""
    db = session()
    lead, _, product, _ = fixture(db)
    make_article(
        db,
        product,
        status=ArticleStatus.AWAITING_REVIEW,
        pmid="p3-low",
        priority=Priority.P3,
    )
    make_article(
        db,
        product,
        status=ArticleStatus.AWAITING_REVIEW,
        pmid="p3-high",
        priority=Priority.P1,
    )
    db.flush()
    items = articles(db, lead)
    assert [item.priority for item in items] == [Priority.P1, Priority.P3]


# ── Literature sources ────────────────────────────────────────────────


def test_source_models_provider_separately_from_source():
    db = session()
    lead, _, _, source = fixture(db)
    sources = list_literature_sources(db=db, _=lead)
    assert sources[0].name == "PubMed"
    # NLM/NCBI is the provider behind the source, not a source of its own.
    assert sources[0].provider == "NLM / NCBI"


def test_source_without_a_retrieval_path_cannot_be_enabled():
    """Enabling Embase would promise coverage the pilot cannot deliver."""
    db = session()
    lead, _, _, _ = fixture(db)
    embase = LiteratureSource(name="Embase", provider="Elsevier", access_model="subscription")
    db.add(embase)
    db.flush()
    with pytest.raises(HTTPException) as exc:
        update_literature_source(
            embase.id, LiteratureSourceUpdate(is_enabled=True), db=db, user=lead
        )
    assert exc.value.status_code == 400
    assert "retrieval" in exc.value.detail


def test_connection_health_reads_persisted_runs_not_process_counters():
    db = session()
    lead, _, _, _ = fixture(db)
    health = source_connection_health(db=db, _=lead)
    # No runs recorded yet, so it must not claim to be healthy.
    assert health.is_healthy is False
    assert health.rate_limit_per_second in (3, 10)


def test_dashboard_search_completion_includes_manual_and_scheduled_runs():
    """Coverage comes from persisted runs, not only active schedules."""
    db = session()
    lead, reviewer, manual_product, _ = fixture(db)
    now = datetime.now(timezone.utc)
    scheduled_product = Product(name="Scheduled Product", brands=[], synonyms=[])
    schedule_only_product = Product(name="Schedule-only Product", brands=[], synonyms=[])
    untouched_product = Product(name="Untouched Product", brands=[], synonyms=[])
    db.add_all([scheduled_product, schedule_only_product, untouched_product])
    db.flush()

    manual_string = SearchString(
        product_id=manual_product.id, query_text="manual query", is_active=True
    )
    scheduled_string = SearchString(
        product_id=scheduled_product.id, query_text="scheduled query", is_active=True
    )
    db.add_all([manual_string, scheduled_string])
    db.flush()
    db.add_all(
        [
            SearchRun(
                search_string_id=manual_string.id,
                status=SearchRunStatus.COMPLETED,
                query_snapshot="manual query",
                triggered_by=reviewer.email,
                started_at=now - timedelta(minutes=2),
                completed_at=now - timedelta(minutes=1),
                created_at=now - timedelta(minutes=2),
            ),
            SearchRun(
                search_string_id=scheduled_string.id,
                status=SearchRunStatus.FAILED,
                query_snapshot="scheduled query",
                triggered_by="schedule:7",
                started_at=now - timedelta(minutes=4),
                completed_at=now - timedelta(minutes=3),
                created_at=now - timedelta(minutes=4),
            ),
            SearchSchedule(
                product_id=schedule_only_product.id,
                frequency=ScheduleFrequency.DAILY,
                end_date=date.today() + timedelta(days=30),
                next_run_at=now + timedelta(days=1),
                last_run_at=now - timedelta(hours=1),
                last_status="no_active_search_string",
            ),
        ]
    )
    db.flush()

    result = dashboard_metrics(mine_only=False, db=db, user=lead)
    rows = {row["product_name"]: row for row in result["search_completion_status"]}

    assert rows[manual_product.name]["status"] == SearchRunStatus.COMPLETED.value
    assert rows[manual_product.name]["origin"] == "manual"
    assert rows[manual_product.name]["last_run_at"] is not None
    assert rows[scheduled_product.name]["status"] == SearchRunStatus.FAILED.value
    assert rows[scheduled_product.name]["origin"] == "scheduled"
    assert rows[schedule_only_product.name]["status"] == "no_active_search_string"
    assert rows[schedule_only_product.name]["origin"] == "scheduled"
    assert rows[untouched_product.name]["status"] == "not_run"
    assert rows[untouched_product.name]["origin"] is None
    assert rows[untouched_product.name]["last_run_at"] is None


# ── Signal tags and classification ────────────────────────────────────


def test_confirmed_signal_requires_pv_lead_and_a_recorded_decision():
    db = session()
    lead, reviewer, product, _ = fixture(db)
    article = make_article(db, product, status=ArticleStatus.UNDER_ASSESSMENT)
    db.flush()

    # A reviewer may not confirm at all.
    with pytest.raises(HTTPException) as exc:
        set_signal_tags(
            article.id,
            SignalTagsIn(tags=[SignalTag.CONFIRMED_SIGNAL.value]),
            db=db,
            user=reviewer,
        )
    assert exc.value.status_code == 403

    # Nor may a lead, until a human assessment exists.
    with pytest.raises(HTTPException) as exc:
        set_signal_tags(
            article.id,
            SignalTagsIn(tags=[SignalTag.CONFIRMED_SIGNAL.value]),
            db=db,
            user=lead,
        )
    assert exc.value.status_code == 409

    db.add(
        ReviewDecision(
            article_id=article.id,
            reviewer_id=reviewer.id,
            action=DecisionAction.MARK_POTENTIAL_SIGNAL,
        )
    )
    db.flush()
    result = set_signal_tags(
        article.id,
        SignalTagsIn(tags=[SignalTag.CONFIRMED_SIGNAL.value]),
        db=db,
        user=lead,
    )
    assert result["signal_status"] == SignalStatus.CONFIRMED.value


def test_setting_tags_replaces_the_set_and_syncs_signal_status():
    db = session()
    lead, reviewer, product, _ = fixture(db)
    article = make_article(db, product, status=ArticleStatus.UNDER_ASSESSMENT)
    db.flush()

    set_signal_tags(
        article.id,
        SignalTagsIn(
            tags=[SignalTag.POTENTIAL_SIGNAL.value, SignalTag.SERIOUS_ADVERSE_EVENT.value]
        ),
        db=db,
        user=reviewer,
    )
    assert article.signal_status == SignalStatus.POTENTIAL

    # Deselecting the potential-signal tag must not leave the status behind.
    result = set_signal_tags(
        article.id,
        SignalTagsIn(tags=[SignalTag.SERIOUS_ADVERSE_EVENT.value]),
        db=db,
        user=reviewer,
    )
    assert result["signal_tags"] == [SignalTag.SERIOUS_ADVERSE_EVENT.value]
    assert result["signal_status"] == SignalStatus.NOT_ASSESSED.value


def test_human_classification_never_overwrites_the_ai_proposal():
    db = session()
    lead, reviewer, product, _ = fixture(db)
    article = make_article(
        db,
        product,
        status=ArticleStatus.AWAITING_REVIEW,
        ai_classification=Classification.POTENTIALLY_RELEVANT,
    )
    db.flush()
    result = set_classification(
        article.id,
        ClassificationIn(classification=Classification.IRRELEVANT, rationale="Not our product"),
        db=db,
        user=reviewer,
    )
    assert result["ai_classification"] == Classification.POTENTIALLY_RELEVANT.value
    assert result["human_classification"] == Classification.IRRELEVANT.value


# ── Exception queue ───────────────────────────────────────────────────


def test_exception_causes_stay_itemised_rather_than_collapsed():
    db = session()
    lead, reviewer, product, _ = fixture(db)
    for index, cause in enumerate(
        [ExceptionCause.FULL_TEXT_UNAVAILABLE, ExceptionCause.FULL_TEXT_UNAVAILABLE, ExceptionCause.SOURCE_PARSE_ERROR]
    ):
        article = make_article(
            db, product, status=ArticleStatus.AWAITING_REVIEW, pmid=f"p3-exc-{index}"
        )
        triggers.flag_exception(
            db, article=article, cause=cause, user_id=reviewer.id
        )
    db.commit()

    summary = exception_summary(product_id=None, mine_only=False, db=db, user=lead)
    by_cause = {row.cause: row.count for row in summary.causes}
    assert summary.total == 3
    assert by_cause[ExceptionCause.FULL_TEXT_UNAVAILABLE.value] == 2
    assert by_cause[ExceptionCause.SOURCE_PARSE_ERROR.value] == 1
    # Each cause alerted separately, so they can be regrouped later.
    assert all(row.alerted for row in summary.causes if row.count)


def test_flagged_exception_moves_status_and_alerts_the_reviewer():
    db = session()
    _, reviewer, product, _ = fixture(db)
    article = make_article(db, product, status=ArticleStatus.AWAITING_REVIEW)
    triggers.flag_exception(
        db,
        article=article,
        cause=ExceptionCause.INSUFFICIENT_INFORMATION,
        detail="No abstract",
        user_id=reviewer.id,
    )
    db.commit()
    assert article.status == ArticleStatus.EXCEPTION
    assert article.exception_cause == ExceptionCause.INSUFFICIENT_INFORMATION
    alert = db.scalars(select(Alert)).first()
    assert alert.user_id == reviewer.id
    assert alert.alert_type == "exception_insufficient_information"


def test_import_without_abstract_is_retained_in_exception_queue():
    db = session()
    _, reviewer, product, _ = fixture(db)
    article = make_article(
        db,
        product,
        status=ArticleStatus.NEW_ALERT,
        pmid="p3-import-no-abstract",
        abstract=None,
    )
    asyncio.run(
        _screen_or_flag(
            db,
            article=article,
            product=product,
            names=[product.name],
            actor="import-test",
        )
    )
    db.commit()
    assert article.status == ArticleStatus.EXCEPTION
    assert article.exception_cause == ExceptionCause.FULL_TEXT_UNAVAILABLE
    alert = db.scalar(
        select(Alert).where(Alert.article_id == article.id)
    )
    assert alert is not None
    assert alert.user_id == reviewer.id


# ── Alert triggers ────────────────────────────────────────────────────


def test_serious_outcome_detection_excludes_non_serious():
    assert triggers._is_serious("Fatal") is True
    assert triggers._is_serious("life-threatening") is True
    # "non-serious" contains "serious" — the exclusion has to win.
    assert triggers._is_serious("non-serious") is False
    assert triggers._is_serious("Not serious") is False
    assert triggers._is_serious(None) is False


def test_signal_and_serious_triggers_fire_on_scoring():
    db = session()
    _, reviewer, product, _ = fixture(db)
    article = make_article(db, product, status=ArticleStatus.AWAITING_REVIEW)
    triggers.on_article_scored(
        db,
        article=article,
        user_id=reviewer.id,
        classification=Classification.POTENTIAL_SAFETY_SIGNAL,
        confidence=0.94,
        seriousness="Fatal",
    )
    db.commit()
    types = {alert.alert_type for alert in db.scalars(select(Alert)).all()}
    assert types == {"signal_detected", "serious_result"}


def test_unmonitored_product_alerts_when_no_run_completes_in_period():
    db = session()
    _, reviewer, product, _ = fixture(db)
    db.add(
        SearchSchedule(
            product_id=product.id,
            frequency=ScheduleFrequency.WEEKLY,
            end_date=date.today() + timedelta(days=90),
            lookback_days=7,
            max_fetch=30,
            is_active=True,
            next_run_at=datetime.now(timezone.utc) + timedelta(days=1),
            last_run_at=datetime.now(timezone.utc) - timedelta(days=30),
            last_status="failed",
        )
    )
    db.flush()
    stale = triggers.check_unmonitored_products(db)
    assert len(stale) == 1
    assert stale[0]["product_name"] == product.name
    alert = db.scalars(
        select(Alert).where(Alert.alert_type == "no_search_in_period")
    ).first()
    assert alert.user_id == reviewer.id


def test_a_recently_completed_schedule_does_not_alert():
    db = session()
    _, _, product, _ = fixture(db)
    db.add(
        SearchSchedule(
            product_id=product.id,
            frequency=ScheduleFrequency.WEEKLY,
            end_date=date.today() + timedelta(days=90),
            lookback_days=7,
            max_fetch=30,
            is_active=True,
            next_run_at=datetime.now(timezone.utc) + timedelta(days=1),
            last_run_at=datetime.now(timezone.utc) - timedelta(days=2),
            last_status="completed",
        )
    )
    db.flush()
    assert triggers.check_unmonitored_products(db) == []


# ── Audit export ──────────────────────────────────────────────────────


def test_audit_export_returns_csv_and_is_itself_audited():
    db = session()
    lead, reviewer, product, _ = fixture(db)
    article = make_article(db, product, status=ArticleStatus.AWAITING_REVIEW)
    db.flush()
    set_classification(
        article.id,
        ClassificationIn(classification=Classification.IRRELEVANT),
        db=db,
        user=reviewer,
    )
    response = export_audit(
        actor=None,
        entity_type=None,
        entity_id=None,
        action=None,
        created_from=None,
        created_to=None,
        db=db,
        user=lead,
    )
    assert response.media_type == "text/csv"
    body = response.body.decode()
    assert "timestamp,actor,action,entity_type,entity_id,payload" in body
    assert "classification_set" in body
