from __future__ import annotations

import enum
from datetime import date, datetime
from typing import Any, Optional

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
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


class ArticleStatus(str, enum.Enum):
    INGESTED = "ingested"
    SCORED = "scored"
    ROUTED = "routed"
    UNDER_REVIEW = "under_review"
    DEFERRED = "deferred"
    SECOND_REVIEW = "second_review"
    AUTO_CLEAR = "auto_clear"
    QC_SAMPLE = "qc_sample"
    DISPOSITION_NOT_CASE = "disposition_not_case"
    DISPOSITION_VALID_ICSR = "disposition_valid_icsr"


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


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True)
    inn: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    brands: Mapped[list[Any]] = mapped_column(JSON, default=list)
    synonyms: Mapped[list[Any]] = mapped_column(JSON, default=list)
    atc_code: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    primary_reviewer_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    search_strings: Mapped[list[SearchString]] = relationship(back_populates="product")
    articles: Mapped[list[Article]] = relationship(back_populates="product")


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
        Enum(ArticleStatus), default=ArticleStatus.INGESTED, index=True
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
