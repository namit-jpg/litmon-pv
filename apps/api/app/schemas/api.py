from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

from pydantic import BaseModel, EmailStr, Field

from app.models.entities import (
    ArticleStatus,
    DecisionAction,
    QueueType,
    Role,
    ScheduleFrequency,
    SearchRunStatus,
    SignalStatus,
    PresenceStatus,
)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: int
    # Pilot users intentionally use the reserved .local domain.
    email: str
    full_name: str
    role: Role
    presence_status: PresenceStatus = PresenceStatus.AVAILABLE
    capacity_limit: int = 20
    active_work_count: int = 0

    model_config = {"from_attributes": True}


class ActiveIngredientOut(BaseModel):
    """An Active Pharmaceutical Ingredient (API) tag."""

    id: int
    name: str
    inn: Optional[str] = None
    atc_code: Optional[str] = None
    unii: Optional[str] = None
    is_active: bool = True

    model_config = {"from_attributes": True}


class ActiveIngredientIn(BaseModel):
    name: str
    inn: Optional[str] = None
    atc_code: Optional[str] = None
    unii: Optional[str] = None


class ActiveIngredientUpdate(BaseModel):
    name: Optional[str] = None
    inn: Optional[str] = None
    atc_code: Optional[str] = None
    unii: Optional[str] = None
    is_active: Optional[bool] = None


class ProductOut(BaseModel):
    id: int
    name: str
    inn: Optional[str]
    brands: list[Any]
    synonyms: list[Any]
    atc_code: Optional[str]
    is_active: bool
    primary_reviewer_id: Optional[int] = None
    active_ingredients: list[ActiveIngredientOut] = []

    model_config = {"from_attributes": True}


class DrugConceptOut(BaseModel):
    """A drug from the RxNorm catalogue, offered in the product picker."""

    rxcui: str
    name: str
    tty: str
    kind: str


class DrugCatalogStatus(BaseModel):
    total: int
    last_synced_at: Optional[datetime] = None


class ProductCreate(BaseModel):
    """Create a monitored product, normally from a picked RxNorm concept."""

    name: str = Field(min_length=1, max_length=255)
    inn: Optional[str] = None
    rxcui: Optional[str] = None
    brands: list[Any] = Field(default_factory=list)
    synonyms: list[Any] = Field(default_factory=list)
    atc_code: Optional[str] = None
    primary_reviewer_id: Optional[int] = None
    active_ingredient_ids: list[int] = Field(default_factory=list)
    # Optional custom PubMed query. When omitted a starter query is generated
    # from the product's names and standard safety terms.
    query_text: Optional[str] = None


class ProductUpdate(BaseModel):
    name: Optional[str] = None
    inn: Optional[str] = None
    brands: Optional[list[Any]] = None
    synonyms: Optional[list[Any]] = None
    atc_code: Optional[str] = None
    is_active: Optional[bool] = None
    primary_reviewer_id: Optional[int] = None
    # Replaces the product's API tag set when provided.
    active_ingredient_ids: Optional[list[int]] = None


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


class SearchScheduleOut(BaseModel):
    id: int
    product_id: int
    product_name: Optional[str] = None
    frequency: ScheduleFrequency
    end_date: date
    lookback_days: int
    max_fetch: int
    is_active: bool
    next_run_at: Optional[datetime] = None
    last_run_at: Optional[datetime] = None
    last_status: Optional[str] = None
    last_error: Optional[str] = None
    run_count: int = 0
    created_by: Optional[str] = None

    model_config = {"from_attributes": True}


class SearchScheduleCreate(BaseModel):
    """Automate a recurring search for one or more products."""

    product_ids: list[int] = Field(min_length=1)
    frequency: ScheduleFrequency
    # Inclusive last day the series may run — automated searches are always
    # bounded so nothing keeps hitting NCBI unattended.
    end_date: date
    lookback_days: Optional[int] = Field(default=None, ge=1, le=365)
    max_fetch: int = Field(default=30, ge=1, le=200)
    # When the first run should happen. Defaults to immediately.
    start_at: Optional[datetime] = None


class SearchScheduleUpdate(BaseModel):
    frequency: Optional[ScheduleFrequency] = None
    end_date: Optional[date] = None
    lookback_days: Optional[int] = Field(default=None, ge=1, le=365)
    max_fetch: Optional[int] = Field(default=None, ge=1, le=200)
    is_active: Optional[bool] = None


class RunSearchNowIn(BaseModel):
    """Run a manual search across several products at once."""

    product_ids: list[int] = Field(min_length=1)
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    days: Optional[int] = Field(default=None, ge=1, le=365)
    max_fetch: int = Field(default=30, ge=1, le=200)


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


class SearchRunArticleItem(BaseModel):
    id: int
    pmid: str
    title: str
    status: ArticleStatus
    is_first_seen: bool
    composite: Optional[float] = None
    queue: Optional[QueueType] = None


class SearchRunDetail(SearchRunOut):
    """Search run with article appearances for the detail page."""

    articles: list[SearchRunArticleItem] = Field(default_factory=list)
    product_id: Optional[int] = None
    product_name: Optional[str] = None


class RunSearchIn(BaseModel):
    search_string_id: int
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    max_fetch: int = Field(default=30, ge=1, le=200)
    # Convenience: days window ending today (overrides date_from if set)
    days: Optional[int] = Field(default=None, ge=1, le=365)


class RetrySearchRunIn(BaseModel):
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
    product_name: Optional[str] = None
    active_ingredients: list[ActiveIngredientOut] = []
    composite: Optional[float] = None
    queue: Optional[QueueType] = None
    sla_due_at: Optional[datetime] = None
    hard_rule_triggered: bool = False
    assignee_id: Optional[int] = None
    assignee_name: Optional[str] = None
    signal_status: SignalStatus = SignalStatus.NOT_ASSESSED

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
    product_name: Optional[str] = None
    active_ingredients: list[ActiveIngredientOut] = []
    assignee_id: Optional[int]
    signal_status: SignalStatus = SignalStatus.NOT_ASSESSED
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
    llm_base_url: str = ""
    llm_api_key_configured: bool = False
    llm_mode: str = "mock"  # mock | live | mock_no_key
    fail_open_on_llm_error: bool = True
    ncbi_email_configured: bool = False
    ncbi_api_key_configured: bool = False


class AlertOut(BaseModel):
    id: int
    user_id: int
    article_id: Optional[int]
    alert_type: str
    priority: str
    title: str
    message: str
    read_at: Optional[datetime]
    created_at: datetime

    model_config = {"from_attributes": True}
