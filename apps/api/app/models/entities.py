from __future__ import annotations

import enum
from datetime import date, datetime
from typing import Any, Optional

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Role(str, enum.Enum):
    REVIEWER = "reviewer"
    SENIOR_REVIEWER = "senior_reviewer"
    PV_LEAD = "pv_lead"
    ADMIN = "admin"


class PresenceStatus(str, enum.Enum):
    OFFLINE = "offline"
    AVAILABLE = "available"
    BUSY = "busy"


class SearchRunStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ScheduleFrequency(str, enum.Enum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


class ArticleStatus(str, enum.Enum):
    """Where an article sits in the workflow — nothing about *what* it is.

    What the article turned out to be is :class:`Classification`; whether it is
    a signal is :class:`SignalTag`. Keeping the three apart is what lets a
    "potential safety signal" article still be "awaiting review".

    The old enum's ``disposition_*`` and ``auto_clear`` members described
    outcomes, not position, and have moved to Classification. ``deferred``,
    ``second_review`` and ``qc_sample`` stay: they are genuinely about where an
    article sits, even though the wireframe has no folder for them. The
    workspace folders are *views* over this enum plus the signal tags, not a
    one-to-one mapping — see ``WORKSPACE_FOLDERS``.
    """

    NEW_ALERT = "new_alert"
    AWAITING_REVIEW = "awaiting_review"
    UNDER_ASSESSMENT = "under_assessment"
    DEFERRED = "deferred"
    SECOND_REVIEW = "second_review"
    QC_SAMPLE = "qc_sample"
    EXCEPTION = "exception"
    APPROVED_FOR_SUBMISSION = "approved_for_submission"
    NOT_FOR_SUBMISSION = "not_for_submission"
    SUBMITTED = "submitted"
    ARCHIVED = "archived"


class Classification(str, enum.Enum):
    """What the article is. Proposed by the pipeline, confirmed by a human."""

    POTENTIALLY_RELEVANT = "potentially_relevant"
    POTENTIAL_SAFETY_SIGNAL = "potential_safety_signal"
    ADVERSE_EVENT_RELATED = "adverse_event_related"
    PRODUCT_QUALITY_RELATED = "product_quality_related"
    DUPLICATE = "duplicate"
    IRRELEVANT = "irrelevant"
    INVALID = "invalid"
    INSUFFICIENT_INFORMATION = "insufficient_information"
    REQUIRES_HUMAN_REVIEW = "requires_human_review"


class SignalTag(str, enum.Enum):
    """Multi-select tags. Distinct from classification and from decision."""

    POTENTIAL_SIGNAL = "potential_signal"
    CONFIRMED_SIGNAL = "confirmed_signal"
    UNDER_REVIEW = "under_review"
    ADVERSE_EVENT = "adverse_event"
    SERIOUS_ADVERSE_EVENT = "serious_adverse_event"
    PRODUCT_QUALITY_ISSUE = "product_quality_issue"
    LACK_OF_EFFICACY = "lack_of_efficacy"
    DRUG_INTERACTION = "drug_interaction"
    SPECIAL_SITUATION = "special_situation"
    DUPLICATE = "duplicate"
    INVALID = "invalid"
    NOT_RELEVANT = "not_relevant"
    SUBMISSION_REQUIRED = "submission_required"
    SUBMISSION_NOT_REQUIRED = "submission_not_required"


class ExceptionCause(str, enum.Enum):
    """Why the pipeline could not finish.

    The partner's meaning of "invalid" is unresolved (feedback section 8), so
    causes stay itemised rather than collapsed into one bucket. They can be
    regrouped in one place once the definition is confirmed.
    """

    FULL_TEXT_UNAVAILABLE = "full_text_unavailable"
    INSUFFICIENT_INFORMATION = "insufficient_information"
    SOURCE_PARSE_ERROR = "source_parse_error"
    SEARCH_FAILED = "search_failed"
    EXTRACTION_FAILED = "extraction_failed"


class Priority(str, enum.Enum):
    P1 = "p1"
    P2 = "p2"
    P3 = "p3"


class SubmissionStatus(str, enum.Enum):
    """The regulatory disposition, independent of the review workflow."""

    PENDING_DECISION = "pending_decision"
    APPROVED_FOR_SUBMISSION = "approved_for_submission"
    RETAINED_INTERNALLY = "retained_internally"
    SUBMITTED = "submitted"


#: The nine folders the wireframe shows, as views over status + signal tag.
#: "Potential signals" is a tag filter rather than a status because an article
#: can be a potential signal *and* awaiting review at the same time — which is
#: the whole reason the old enum had to be split.
#: Labels live here rather than in the client so the folder list, its counts
#: and its ordering all come from one place.
WORKSPACE_FOLDERS: dict[str, dict[str, Any]] = {
    "new_alerts": {
        "label": "New alerts",
        "statuses": [ArticleStatus.NEW_ALERT],
    },
    "awaiting_review": {
        "label": "Awaiting review",
        "statuses": [ArticleStatus.AWAITING_REVIEW, ArticleStatus.QC_SAMPLE],
    },
    "potential_signals": {
        "label": "Potential signals",
        "signal_tags": [SignalTag.POTENTIAL_SIGNAL],
    },
    "under_assessment": {
        "label": "Under assessment",
        "statuses": [
            ArticleStatus.UNDER_ASSESSMENT,
            ArticleStatus.DEFERRED,
            ArticleStatus.SECOND_REVIEW,
        ],
    },
    "exceptions": {
        "label": "Invalid / failed",
        "statuses": [ArticleStatus.EXCEPTION],
    },
    "approved_for_submission": {
        "label": "Approved for submission",
        "statuses": [ArticleStatus.APPROVED_FOR_SUBMISSION],
    },
    "not_for_submission": {
        "label": "Not for submission",
        "statuses": [ArticleStatus.NOT_FOR_SUBMISSION],
    },
    "submitted": {
        "label": "Submitted",
        "statuses": [ArticleStatus.SUBMITTED],
    },
    "archived": {
        "label": "Archived",
        "statuses": [ArticleStatus.ARCHIVED],
    },
}

#: Terminal states — an article here needs no further reviewer action. Several
#: call sites previously spelled this set out inline as the three disposition
#: statuses; naming it once keeps SLA, omnichannel routing and queue counts
#: from drifting apart.
CLOSED_STATUSES: tuple[ArticleStatus, ...] = (
    ArticleStatus.APPROVED_FOR_SUBMISSION,
    ArticleStatus.NOT_FOR_SUBMISSION,
    ArticleStatus.SUBMITTED,
    ArticleStatus.ARCHIVED,
)


class QueueType(str, enum.Enum):
    AUTO_CLEAR = "auto_clear"
    STANDARD = "standard"
    PRIORITY = "priority"
    EXPEDITED = "expedited"
    QC_SAMPLE = "qc_sample"


class DecisionAction(str, enum.Enum):
    CONFIRM_NOT_CASE = "confirm_not_case"
    CONFIRM_VALID_ICSR = "confirm_valid_icsr"
    OVERRIDE_AI = "override_ai"
    REQUEST_SECOND_REVIEW = "request_second_review"
    DEFER_FULL_TEXT = "defer_full_text"
    RECALL_TO_REVIEW = "recall_to_review"
    MARK_POTENTIAL_SIGNAL = "mark_potential_signal"
    CONFIRM_SIGNAL = "confirm_signal"
    REJECT_SIGNAL = "reject_signal"
    MARK_INVALID = "mark_invalid"
    MARK_DUPLICATE = "mark_duplicate"
    MARK_NOT_RELEVANT = "mark_not_relevant"
    PREPARE_FOR_SUBMISSION = "prepare_for_submission"
    RETAIN_INTERNALLY = "retain_internally"
    CLOSE_REPORT = "close_report"


class SignalStatus(str, enum.Enum):
    NOT_ASSESSED = "not_assessed"
    POTENTIAL = "potential_signal"
    CONFIRMED = "confirmed_signal"
    REJECTED = "rejected_signal"


class JobStatus(str, enum.Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(255))
    hashed_password: Mapped[str] = mapped_column(String(255))
    role: Mapped[Role] = mapped_column(Enum(Role), default=Role.REVIEWER)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    presence_status: Mapped[PresenceStatus] = mapped_column(
        Enum(PresenceStatus), default=PresenceStatus.AVAILABLE, index=True
    )
    capacity_limit: Mapped[int] = mapped_column(Integer, default=20)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


product_active_ingredients = Table(
    "product_active_ingredients",
    Base.metadata,
    Column(
        "product_id",
        ForeignKey("products.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "active_ingredient_id",
        ForeignKey("active_ingredients.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class ActiveIngredient(Base):
    """An Active Pharmaceutical Ingredient (API).

    Per ICH Q7 the API is the substance that furnishes pharmacological
    activity, as distinct from the excipients it is formulated with. It is
    modelled as a tag rather than a column on Product because the
    relationship is genuinely many-to-many: a combination product carries
    several APIs, and one API appears across many branded products.

    On regulatory export this maps to E2B activesubstancename
    (G.k.2.3.r), which is the element CDSCO/PvPI expects for the substance
    behind a suspect medicinal product.
    """

    __tablename__ = "active_ingredients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Substance name as used on the label, e.g. "metformin hydrochloride"
    name: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    # International Nonproprietary Name, e.g. "metformin"
    inn: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    # WHO Anatomical Therapeutic Chemical code, e.g. "A10BA02"
    atc_code: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    # FDA Unique Ingredient Identifier
    unii: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    products: Mapped[list[Product]] = relationship(
        secondary=product_active_ingredients, back_populates="active_ingredients"
    )


class DrugConcept(Base):
    """A drug concept mirrored from NLM RxNorm.

    This is the reference catalogue the "add a product" picker searches. It is
    a local mirror rather than a live call per keystroke so the picker stays
    instant and keeps working without a network. Nothing here is hand-written:
    rows are synced from RxNorm and can be refreshed at any time.
    """

    __tablename__ = "drug_concepts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # RxNorm concept unique identifier.
    rxcui: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(512), index=True)
    # Lower-cased copy so SQLite LIKE matching is predictable across collations.
    name_lower: Mapped[str] = mapped_column(String(512), index=True)
    # RxNorm term type: IN = ingredient, MIN = multi-ingredient, BN = brand.
    tty: Mapped[str] = mapped_column(String(8), index=True)
    synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True)
    inn: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    brands: Mapped[list[Any]] = mapped_column(JSON, default=list)
    synonyms: Mapped[list[Any]] = mapped_column(JSON, default=list)
    atc_code: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    # Marketing authorisation holder, and the markets the product is sold in.
    # Both are regulatory facts about the licence rather than the molecule, so
    # they cannot come from RxNorm and have to be entered. Everything else the
    # partner listed under step 1 is already covered: molecule identity by
    # DrugConcept/ActiveIngredient, frequency by SearchSchedule, and the
    # responsible user by primary_reviewer_id below.
    mah: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    markets: Mapped[list[Any]] = mapped_column(JSON, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    primary_reviewer_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    search_strings: Mapped[list[SearchString]] = relationship(back_populates="product")
    articles: Mapped[list[Article]] = relationship(back_populates="product")
    active_ingredients: Mapped[list[ActiveIngredient]] = relationship(
        secondary=product_active_ingredients,
        back_populates="products",
        lazy="selectin",
    )


class SearchString(Base):
    __tablename__ = "search_strings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    query_text: Mapped[str] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    approved_by: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    effective_from: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    product: Mapped[Product] = relationship(back_populates="search_strings")
    runs: Mapped[list[SearchRun]] = relationship(back_populates="search_string")


class SearchSchedule(Base):
    """A recurring PubMed search for one product.

    The runner fires a schedule when ``next_run_at`` is due, then advances it by
    the frequency. ``next_run_at`` is persisted rather than derived from a timer
    so schedules survive a restart, and ``end_date`` bounds the whole series so
    an automated search can never run forever unattended.
    """

    __tablename__ = "search_schedules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    frequency: Mapped[ScheduleFrequency] = mapped_column(Enum(ScheduleFrequency))
    # Inclusive last day the series may run. Past this the schedule goes idle.
    end_date: Mapped[date] = mapped_column(Date)
    # How many days back each run should look. Defaults to one interval so a
    # weekly schedule covers the week it just waited through, with no gap.
    lookback_days: Mapped[int] = mapped_column(Integer, default=7)
    max_fetch: Mapped[int] = mapped_column(Integer, default=30)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    next_run_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True
    )
    last_run_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_status: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    run_count: Mapped[int] = mapped_column(Integer, default=0)
    created_by: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    product: Mapped[Product] = relationship()


class SearchRun(Base):
    __tablename__ = "search_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    search_string_id: Mapped[int] = mapped_column(
        ForeignKey("search_strings.id"), index=True
    )
    status: Mapped[SearchRunStatus] = mapped_column(
        Enum(SearchRunStatus), default=SearchRunStatus.PENDING
    )
    query_snapshot: Mapped[str] = mapped_column(Text)
    date_from: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    date_to: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    hit_count: Mapped[int] = mapped_column(Integer, default=0)
    new_article_count: Mapped[int] = mapped_column(Integer, default=0)
    rehit_count: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    raw_response_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    triggered_by: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    search_string: Mapped[SearchString] = relationship(back_populates="runs")
    appearances: Mapped[list[ArticleAppearance]] = relationship(
        back_populates="search_run"
    )


class Article(Base):
    __tablename__ = "articles"
    __table_args__ = (
        UniqueConstraint("product_id", "pmid", name="uq_articles_product_pmid"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    pmid: Mapped[str] = mapped_column(String(32), index=True)
    doi: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    title: Mapped[str] = mapped_column(Text)
    abstract: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    journal: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    authors: Mapped[list[Any]] = mapped_column(JSON, default=list)
    pub_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    mesh_terms: Mapped[list[Any]] = mapped_column(JSON, default=list)
    publication_types: Mapped[list[Any]] = mapped_column(JSON, default=list)
    pubmed_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    content_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    status: Mapped[ArticleStatus] = mapped_column(
        Enum(ArticleStatus), default=ArticleStatus.NEW_ALERT, index=True
    )
    # The AI proposal is written once and never overwritten; the human value is
    # what the reviewer confirmed or overrode it with. Keeping both is what
    # makes the override rate measurable.
    ai_classification: Mapped[Optional[Classification]] = mapped_column(
        Enum(Classification), nullable=True, index=True
    )
    human_classification: Mapped[Optional[Classification]] = mapped_column(
        Enum(Classification), nullable=True, index=True
    )
    priority: Mapped[Priority] = mapped_column(
        Enum(Priority), default=Priority.P3, index=True
    )
    exception_cause: Mapped[Optional[ExceptionCause]] = mapped_column(
        Enum(ExceptionCause), nullable=True, index=True
    )
    literature_source_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("literature_sources.id"), nullable=True, index=True
    )
    assignee_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    signal_status: Mapped[SignalStatus] = mapped_column(
        Enum(SignalStatus), default=SignalStatus.NOT_ASSESSED, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    product: Mapped[Product] = relationship(back_populates="articles")
    appearances: Mapped[list[ArticleAppearance]] = relationship(
        back_populates="article"
    )
    screening_results: Mapped[list[ScreeningResult]] = relationship(
        back_populates="article"
    )
    triage_assignments: Mapped[list[TriageAssignment]] = relationship(
        back_populates="article"
    )
    review_decisions: Mapped[list[ReviewDecision]] = relationship(
        back_populates="article"
    )
    signal_tags: Mapped[list[ArticleSignalTag]] = relationship(
        back_populates="article", lazy="selectin", cascade="all, delete-orphan"
    )
    literature_source: Mapped[Optional[LiteratureSource]] = relationship()
    regulatory_records: Mapped[list[RegulatoryRecord]] = relationship(
        back_populates="article", cascade="all, delete-orphan"
    )


class ArticleSignalTag(Base):
    """One signal tag on one article.

    A row per tag rather than a JSON list so the workspace can filter on it and
    so we keep who applied it. ``confirmed_signal`` is guarded at the service
    layer: pv_lead only, and only once a ReviewDecision exists.
    """

    __tablename__ = "article_signal_tags"
    __table_args__ = (
        UniqueConstraint("article_id", "tag", name="uq_article_signal_tags"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    article_id: Mapped[int] = mapped_column(
        ForeignKey("articles.id", ondelete="CASCADE"), index=True
    )
    tag: Mapped[SignalTag] = mapped_column(Enum(SignalTag), index=True)
    is_ai_proposed: Mapped[bool] = mapped_column(Boolean, default=False)
    set_by_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    article: Mapped[Article] = relationship(back_populates="signal_tags")


class LiteratureSource(Base):
    """A searchable literature source.

    PubMed and PMC are *sources*; NLM/NCBI is the *provider* behind them. The
    partner's step 2 calls this distinction out explicitly, so provider is a
    field rather than a separate row — otherwise NLM and NCBI look like two
    more databases to tick.
    """

    __tablename__ = "literature_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True)
    kind: Mapped[str] = mapped_column(String(64), default="bibliographic")
    provider: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    access_model: Mapped[str] = mapped_column(String(64), default="public")
    retrieval: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    coverage: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ArticleAppearance(Base):
    __tablename__ = "article_appearances"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    article_id: Mapped[int] = mapped_column(ForeignKey("articles.id"), index=True)
    search_run_id: Mapped[int] = mapped_column(ForeignKey("search_runs.id"), index=True)
    is_first_seen: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    article: Mapped[Article] = relationship(back_populates="appearances")
    search_run: Mapped[SearchRun] = relationship(back_populates="appearances")


class ScreeningResult(Base):
    __tablename__ = "screening_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    article_id: Mapped[int] = mapped_column(ForeignKey("articles.id"), index=True)
    product_match: Mapped[float] = mapped_column(Float)
    event_relevance: Mapped[float] = mapped_column(Float)
    icsr_criteria_match: Mapped[float] = mapped_column(Float)
    composite: Mapped[float] = mapped_column(Float, index=True)
    entities: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    # Promoted out of the ``entities`` blob above so the workspace can filter
    # and the regulatory validator can check them. ``entities`` stays as the
    # raw model output; these are the fields we commit to.
    indication: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    dosage: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    outcome: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    seriousness: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    country_of_occurrence: Mapped[Optional[str]] = mapped_column(
        String(128), nullable=True, index=True
    )
    reporter_type: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    concomitant_medication: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    article_excerpts: Mapped[list[Any]] = mapped_column(JSON, default=list)
    relevance_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    processed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    icsr_precheck: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    reason_tags: Mapped[list[Any]] = mapped_column(JSON, default=list)
    hard_rule_candidates: Mapped[list[Any]] = mapped_column(JSON, default=list)
    summary_for_reviewer: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    model_id: Mapped[str] = mapped_column(String(128))
    prompt_version: Mapped[str] = mapped_column(String(64))
    ruleset_version: Mapped[str] = mapped_column(String(64))
    threshold_version: Mapped[str] = mapped_column(String(64))
    is_mock: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    article: Mapped[Article] = relationship(back_populates="screening_results")


class TriageAssignment(Base):
    __tablename__ = "triage_assignments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    article_id: Mapped[int] = mapped_column(ForeignKey("articles.id"), index=True)
    screening_result_id: Mapped[int] = mapped_column(
        ForeignKey("screening_results.id"), index=True
    )
    queue: Mapped[QueueType] = mapped_column(Enum(QueueType), index=True)
    sla_hours: Mapped[int] = mapped_column(Integer)
    sla_due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    hard_rule_triggered: Mapped[bool] = mapped_column(Boolean, default=False)
    hard_rules: Mapped[list[Any]] = mapped_column(JSON, default=list)
    ruleset_version: Mapped[str] = mapped_column(String(64))
    threshold_version: Mapped[str] = mapped_column(String(64))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    article: Mapped[Article] = relationship(back_populates="triage_assignments")


class ReviewDecision(Base):
    __tablename__ = "review_decisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    article_id: Mapped[int] = mapped_column(ForeignKey("articles.id"), index=True)
    reviewer_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    action: Mapped[DecisionAction] = mapped_column(Enum(DecisionAction))
    rationale: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # ICSR checklist (explicit, not silent)
    identifiable_patient: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    suspect_drug: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    adverse_event: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    identifiable_reporter: Mapped[Optional[bool]] = mapped_column(
        Boolean, nullable=True
    )
    seriousness: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    listedness: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    patient_age_range: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    patient_sex: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    patient_country: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    event_terms: Mapped[list[Any]] = mapped_column(JSON, default=list)
    suspect_products: Mapped[list[Any]] = mapped_column(JSON, default=list)
    override_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Names or URLs in the controlled document repository. The pilot records
    # references without taking custody of regulated files in local storage.
    supporting_documents: Mapped[list[Any]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    article: Mapped[Article] = relationship(back_populates="review_decisions")


class ExportPackage(Base):
    __tablename__ = "export_packages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    filename: Mapped[str] = mapped_column(String(255))
    article_ids: Mapped[list[Any]] = mapped_column(JSON, default=list)
    record_count: Mapped[int] = mapped_column(Integer, default=0)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_by: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class RegulatoryRecord(Base):
    """Human regulatory decision and manual gateway evidence for one article.

    This record deliberately has no transport credentials or automatic-send
    state. A PV user downloads a generated package and uploads it outside the
    application; the resulting gateway reference is the audit evidence kept
    here.
    """

    __tablename__ = "regulatory_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    article_id: Mapped[int] = mapped_column(
        ForeignKey("articles.id", ondelete="CASCADE"), unique=True, index=True
    )
    latest_export_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("export_packages.id"), nullable=True
    )
    decision: Mapped[SubmissionStatus] = mapped_column(
        Enum(SubmissionStatus), default=SubmissionStatus.PENDING_DECISION, index=True
    )
    decision_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    gateway: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    submission_reference: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True
    )
    acknowledgement: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    submitted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_by: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    article: Mapped[Article] = relationship(back_populates="regulatory_records")


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    actor: Mapped[str] = mapped_column(String(255))  # email or "system"
    action: Mapped[str] = mapped_column(String(128), index=True)
    entity_type: Mapped[str] = mapped_column(String(64), index=True)
    entity_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class Alert(Base):
    """Persistent in-app alert for the pilot reviewer workspace."""

    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    article_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("articles.id"), nullable=True, index=True
    )
    alert_type: Mapped[str] = mapped_column(String(64), index=True)
    priority: Mapped[str] = mapped_column(String(16), default="normal", index=True)
    # Which channels this alert actually went out on. In-app and email only for
    # the pilot; the list shape is what lets SMS/Teams/Slack land later without
    # a further migration.
    channels: Mapped[list[Any]] = mapped_column(JSON, default=list)
    title: Mapped[str] = mapped_column(String(255))
    message: Mapped[str] = mapped_column(Text)
    dedupe_key: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True, unique=True
    )
    read_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class Job(Base):
    """Background job / dead-letter capable work unit."""

    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_type: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus), default=JobStatus.QUEUED, index=True
    )
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    result: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    created_by: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
