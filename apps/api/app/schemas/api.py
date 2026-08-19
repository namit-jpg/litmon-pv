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
    Classification,
    Priority,
    SubmissionStatus,
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
    # Regulatory facts about the licence rather than the molecule, so they
    # cannot come from RxNorm and have to be entered by hand.
    mah: Optional[str] = None
    markets: list[Any] = []
    is_active: bool
    primary_reviewer_id: Optional[int] = None
    active_ingredients: list[ActiveIngredientOut] = []

    model_config = {"from_attributes": True}


class DrugConceptOut(BaseModel):
    """A drug from the RxNorm catalogue, as offered in the picker."""

    rxcui: str
    name: str
    tty: str
    kind: str
    is_monitored: bool = False
    product_id: Optional[int] = None
    article_count: int = 0


class DrugRef(BaseModel):
    """A drug the user picked. The backing product is created on demand."""

    name: str = Field(min_length=1, max_length=255)
    rxcui: Optional[str] = None
    tty: Optional[str] = None


class DrugCatalogStatus(BaseModel):
    total: int
    last_synced_at: Optional[datetime] = None


class ProductCreate(BaseModel):
    """Create a monitored product, normally from a picked RxNorm concept."""

    name: str = Field(min_length=1, max_length=255)
    inn: Optional[str] = None
    rxcui: Optional[str] = None
    # RxNorm term type of the picked concept (IN / MIN / BN). Used to derive
    # the active substances when no explicit tags are supplied.
    tty: Optional[str] = None
    brands: list[Any] = Field(default_factory=list)
    synonyms: list[Any] = Field(default_factory=list)
    atc_code: Optional[str] = None
    mah: Optional[str] = None
    markets: list[Any] = Field(default_factory=list)
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
    mah: Optional[str] = None
    markets: Optional[list[Any]] = None
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
    """Automate a recurring search for one or more drugs."""

    # Either pick drugs (normal path) or name existing products directly.
    drugs: list[DrugRef] = Field(default_factory=list)
    product_ids: list[int] = Field(default_factory=list)
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
    """Run a manual search across several drugs at once."""

    # Either pick drugs (normal path) or name existing products directly.
    drugs: list[DrugRef] = Field(default_factory=list)
    product_ids: list[int] = Field(default_factory=list)
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
    indication: Optional[str] = None
    dosage: Optional[str] = None
    outcome: Optional[str] = None
    seriousness: Optional[str] = None
    country_of_occurrence: Optional[str] = None
    reporter_type: Optional[str] = None
    concomitant_medication: Optional[str] = None
    article_excerpts: list[Any] = []
    relevance_reason: Optional[str] = None
    confidence: Optional[float] = None
    processed_at: Optional[datetime] = None
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
    priority: Priority = Priority.P3
    ai_classification: Optional[Classification] = None
    human_classification: Optional[Classification] = None
    effective_classification: Optional[Classification] = None
    signal_tags: list[str] = []
    literature_source_id: Optional[int] = None
    literature_source_name: Optional[str] = None

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
    assignee_name: Optional[str] = None
    signal_status: SignalStatus = SignalStatus.NOT_ASSESSED
    priority: Priority = Priority.P3
    ai_classification: Optional[Classification] = None
    human_classification: Optional[Classification] = None
    signal_tags: list[str] = []
    literature_source_id: Optional[int] = None
    literature_source_name: Optional[str] = None
    search_date: Optional[datetime] = None
    search_terms: Optional[str] = None
    submission_status: SubmissionStatus = SubmissionStatus.PENDING_DECISION
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
    supporting_documents: list[str] = Field(default_factory=list)


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
    classification_counts: dict[str, int] = Field(default_factory=dict)


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
    channels: list[Any] = []
    title: str
    message: str
    read_at: Optional[datetime]
    created_at: datetime

    model_config = {"from_attributes": True}


class AlertSettingsOut(BaseModel):
    """Pilot notification capabilities, not an unscoped omnichannel contract."""

    enabled_channels: list[str]
    available_channels: list[str]
    email_configured: bool


class LiteratureSourceOut(BaseModel):
    """A searchable source. Provider is a field, not a separate row."""

    id: int
    name: str
    kind: str
    provider: Optional[str] = None
    access_model: str
    retrieval: Optional[str] = None
    coverage: Optional[str] = None
    is_enabled: bool
    article_count: int = 0

    model_config = {"from_attributes": True}


class LiteratureSourceIn(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    kind: str = Field(default="bibliographic", max_length=64)
    provider: Optional[str] = Field(default=None, max_length=128)
    access_model: str = Field(default="public", max_length=64)
    retrieval: Optional[str] = Field(default=None, max_length=255)
    coverage: Optional[str] = Field(default=None, max_length=255)
    is_enabled: bool = False


class LiteratureSourceUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=128)
    kind: Optional[str] = Field(default=None, max_length=64)
    provider: Optional[str] = Field(default=None, max_length=128)
    access_model: Optional[str] = Field(default=None, max_length=64)
    retrieval: Optional[str] = Field(default=None, max_length=255)
    coverage: Optional[str] = Field(default=None, max_length=255)
    is_enabled: Optional[bool] = None


class SourceConnectionOut(BaseModel):
    """Live health for the one source the pilot actually retrieves from."""

    source_name: str
    contact_email: Optional[str] = None
    contact_email_configured: bool
    api_key_configured: bool
    api_key_hint: Optional[str] = None
    rate_limit_per_second: int
    retry_policy: str
    last_successful_call: Optional[datetime] = None
    failures_last_7d: int
    is_healthy: bool


class SignalTagsIn(BaseModel):
    """The reviewer's full tag selection — this replaces the existing set."""

    tags: list[str] = Field(default_factory=list)


class ClassificationIn(BaseModel):
    """A human classification. The AI's proposal is never overwritten."""

    classification: Classification
    rationale: Optional[str] = None


class ExceptionCauseCount(BaseModel):
    cause: str
    label: str
    count: int
    alerted: bool


class ExceptionSummaryOut(BaseModel):
    total: int
    causes: list[ExceptionCauseCount]
    notice: str


class RegulatoryValidationField(BaseModel):
    field: str
    label: str
    required: bool
    value: Any = None
    state: str


class RegulatoryValidationOut(BaseModel):
    article_id: int
    rules_configured: bool
    prototype_notice: str
    fields: list[RegulatoryValidationField]
    blocking_errors: list[str]
    can_generate: bool


class RegulatoryGenerateIn(BaseModel):
    sender_id: Optional[str] = None
    receiver_id: Optional[str] = None


class RegulatoryDecisionIn(BaseModel):
    decision: SubmissionStatus
    reason: str = Field(min_length=1)


class RegulatorySubmissionIn(BaseModel):
    gateway: str = Field(min_length=1, max_length=255)
    submission_reference: str = Field(min_length=1, max_length=255)
    submitted_at: Optional[datetime] = None
    acknowledgement: Optional[str] = None


class RegulatoryRecordOut(BaseModel):
    id: int
    article_id: int
    latest_export_id: Optional[int]
    decision: SubmissionStatus
    decision_reason: Optional[str]
    gateway: Optional[str]
    submission_reference: Optional[str]
    acknowledgement: Optional[str]
    submitted_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── Literature assistant ─────────────────────────────────────────────


class AssistantTurn(BaseModel):
    """One prior exchange, so a follow-up can be resolved against it."""

    question: str = Field(min_length=1, max_length=1000)
    answer: str = Field(min_length=1, max_length=8000)


class AssistantAskIn(BaseModel):
    question: str = Field(min_length=3, max_length=1000)
    # How many papers to ground the answer in. Kept small: more sources means a
    # longer wait and a vaguer answer, not a better one.
    limit: int = Field(default=6, ge=1, le=12)
    #: Prior turns of this conversation, oldest first. Used only to resolve the
    #: question — each answer is grounded in its own fresh retrieval.
    history: list[AssistantTurn] = Field(default_factory=list, max_length=20)


class AssistantSourceOut(BaseModel):
    number: int
    pmid: str
    title: str
    journal: Optional[str]
    pub_date: Optional[str]
    url: str
    #: Set when this paper is already a monitored article, so the client can
    #: link to its detection report instead of sending the reviewer to PubMed.
    article_id: Optional[int]
    #: Whether the answer actually drew on it. Retrieved is not cited.
    cited: bool = False


class AssistantSegmentOut(BaseModel):
    """A span of answer text with the citations the API attached to it."""

    text: str
    citations: list[int] = Field(default_factory=list)
    #: The sentence each citation quotes, parallel to `citations`.
    quotes: list[str] = Field(default_factory=list)


class AssistantAnswerOut(BaseModel):
    question: str
    #: The self-contained form of the question. Differs from `question` when the
    #: reviewer asked a follow-up that needed the conversation to make sense.
    interpreted_question: str
    answer: str
    segments: list[AssistantSegmentOut]
    sources: list[AssistantSourceOut]
    pubmed_query: str
    total_matches: int
    model_id: str
    #: False when the answer is the extractive fallback rather than synthesis.
    synthesised: bool
    notice: str
    warning: Optional[str] = None
