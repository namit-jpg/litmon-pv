from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

from pydantic import BaseModel, EmailStr, Field

from app.models.entities import (
    ArticleStatus,
    DecisionAction,
    QueueType,
    Role,
    SearchRunStatus,
)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: int
    email: EmailStr
    full_name: str
    role: Role

    model_config = {"from_attributes": True}


class ProductOut(BaseModel):
    id: int
    name: str
    inn: Optional[str]
    brands: list[Any]
    synonyms: list[Any]
    atc_code: Optional[str]
    is_active: bool

    model_config = {"from_attributes": True}


class ProductUpdate(BaseModel):
    name: Optional[str] = None
    inn: Optional[str] = None
    brands: Optional[list[Any]] = None
    synonyms: Optional[list[Any]] = None
    atc_code: Optional[str] = None
    is_active: Optional[bool] = None


class SearchStringOut(BaseModel):
    id: int
    product_id: int
    version: int
    query_text: str
    is_active: bool
    approved_by: Optional[str]
    notes: Optional[str]

    model_config = {"from_attributes": True}


class SearchStringCreate(BaseModel):
    product_id: int
    query_text: str
    approved_by: Optional[str] = None
    notes: Optional[str] = None


class SearchRunOut(BaseModel):
    id: int
    search_string_id: int
    status: SearchRunStatus
    query_snapshot: str
    date_from: Optional[date]
    date_to: Optional[date]
    hit_count: int
    new_article_count: int
    rehit_count: int
    error_message: Optional[str]
    triggered_by: Optional[str]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    created_at: datetime

    model_config = {"from_attributes": True}


class RunSearchIn(BaseModel):
    search_string_id: int
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    max_fetch: int = Field(default=30, ge=1, le=200)


class ScreeningOut(BaseModel):
    id: int
    product_match: float
    event_relevance: float
    icsr_criteria_match: float
    composite: float
    entities: dict[str, Any]
    icsr_precheck: dict[str, Any]
    reason_tags: list[Any]
    hard_rule_candidates: list[Any]
    summary_for_reviewer: Optional[str]
    model_id: str
    prompt_version: str
    ruleset_version: str
    threshold_version: str
    is_mock: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class TriageOut(BaseModel):
    id: int
    queue: QueueType
    sla_hours: int
    sla_due_at: datetime
    hard_rule_triggered: bool
    hard_rules: list[Any]
    is_active: bool

    model_config = {"from_attributes": True}


class ArticleListItem(BaseModel):
    id: int
    pmid: str
    title: str
    journal: Optional[str]
    pub_date: Optional[date]
    status: ArticleStatus
    product_id: int
    composite: Optional[float] = None
    queue: Optional[QueueType] = None
    sla_due_at: Optional[datetime] = None
    hard_rule_triggered: bool = False
    assignee_id: Optional[int] = None

    model_config = {"from_attributes": True}


class ArticleDetail(BaseModel):
    id: int
    pmid: str
    doi: Optional[str]
    title: str
    abstract: Optional[str]
    journal: Optional[str]
    authors: list[Any]
    pub_date: Optional[date]
    mesh_terms: list[Any]
    publication_types: list[Any]
    pubmed_url: Optional[str]
    status: ArticleStatus
    product_id: int
    assignee_id: Optional[int]
    latest_screening: Optional[ScreeningOut] = None
    active_triage: Optional[TriageOut] = None
    decisions: list[Any] = []
    audit_events: list[Any] = []

    model_config = {"from_attributes": True}


class ReviewIn(BaseModel):
    action: DecisionAction
    rationale: Optional[str] = None
    identifiable_patient: Optional[bool] = None
    suspect_drug: Optional[bool] = None
    adverse_event: Optional[bool] = None
    identifiable_reporter: Optional[bool] = None
    seriousness: Optional[str] = None
    listedness: Optional[str] = None
    patient_age_range: Optional[str] = None
    patient_sex: Optional[str] = None
    patient_country: Optional[str] = None
    event_terms: list[Any] = Field(default_factory=list)
    suspect_products: list[Any] = Field(default_factory=list)
    override_notes: Optional[str] = None


class ReviewOut(BaseModel):
    id: int
    article_id: int
    reviewer_id: int
    action: DecisionAction
    rationale: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class ExportOut(BaseModel):
    id: int
    filename: str
    record_count: int
    article_ids: list[Any]
    payload_json: dict[str, Any]
    created_at: datetime

    model_config = {"from_attributes": True}


class AuditOut(BaseModel):
    id: int
    actor: str
    action: str
    entity_type: str
    entity_id: Optional[str]
    payload: dict[str, Any]
    created_at: datetime

    model_config = {"from_attributes": True}


class QueueStats(BaseModel):
    expedited: int
    priority: int
    standard: int
    qc_sample: int
    auto_clear: int
    valid_icsr: int
    not_case: int
    deferred: int = 0
    second_review: int = 0


class ImportPmidsIn(BaseModel):
    product_id: int
    pmids_text: str = Field(
        ..., description="Whitespace/comma/semicolon-separated PMIDs"
    )


class ImportCsvIn(BaseModel):
    product_id: int
    csv_text: str
    fetch_missing_from_pubmed: bool = True


class RecallIn(BaseModel):
    rationale: Optional[str] = None


class ThresholdsOut(BaseModel):
    prompt_version: str
    ruleset_version: str
    threshold_version: str
    bands: list[dict[str, Any]]
    auto_clear_qc_sample_rate: float
    llm_mock: bool
    llm_model: str
