from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_roles
from app.core.config import get_settings
from app.core.database import get_db
from app.core.metrics import metrics
from app.core.rate_limit import login_limiter
from app.core.security import create_access_token, verify_password
from app.models import (
    Article,
    AuditEvent,
    ExportPackage,
    Job,
    Product,
    ReviewDecision,
    SearchRun,
    SearchString,
    TriageAssignment,
    User,
)
from app.models.entities import (
    ArticleStatus,
    DecisionAction,
    QueueType,
    Role,
)
from app.schemas.api import (
    ArticleDetail,
    ArticleListItem,
    AuditOut,
    ExportOut,
    ImportCsvIn,
    ImportPmidsIn,
    ProductOut,
    ProductUpdate,
    QueueStats,
    RecallIn,
    ReviewIn,
    ReviewOut,
    RunSearchIn,
    SearchRunOut,
    SearchStringCreate,
    SearchStringOut,
    ThresholdsOut,
    TokenOut,
    UserOut,
)
from app.services.audit import log_event
from app.services.evaluation import evaluate_gold_set
from app.services.export_service import create_icsr_export, create_parallel_run_export
from app.services.import_service import (
    import_csv_rows,
    import_pmids_from_pubmed,
    parse_articles_csv,
    parse_pmid_list,
)
from app.services.jobs import enqueue_job
from app.services.pipeline import (
    recall_article_to_review,
    rescore_article,
    run_search,
    seed_demo_articles_async,
)
from app.services.sla import list_overdue_articles, sla_summary
from app.services.triage.engine import BANDS
from pydantic import BaseModel, Field

router = APIRouter()


class BatchRescoreIn(BaseModel):
    article_ids: list[int] = Field(default_factory=list)
    all_open: bool = False


class JobOut(BaseModel):
    id: int
    job_type: str
    status: str
    payload: dict[str, Any]
    result: dict[str, Any]
    error_message: str | None
    attempts: int
    created_by: str | None
    started_at: Any = None
    completed_at: Any = None
    created_at: Any = None

    model_config = {"from_attributes": True}


# ── Auth ──────────────────────────────────────────────────────────────


@router.post("/auth/login", response_model=TokenOut)
def login(
    request: Request,
    form: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
) -> TokenOut:
    client = request.client.host if request.client else "unknown"
    key = f"{client}:{form.username}"
    if not login_limiter.allow(key):
        raise HTTPException(
            status_code=429,
            detail="Too many login attempts. Try again in a few minutes.",
        )
    user = db.scalars(select(User).where(User.email == form.username)).first()
    if not user or not verify_password(form.password, user.hashed_password):
        metrics.login_failures += 1
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    token = create_access_token(user.email, extra={"role": user.role.value})
    return TokenOut(access_token=token)


@router.get("/auth/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> User:
    return user


# ── Config / thresholds ───────────────────────────────────────────────


@router.get("/config/thresholds", response_model=ThresholdsOut)
def get_thresholds(_: User = Depends(get_current_user)) -> ThresholdsOut:
    settings = get_settings()
    bands = [
        {
            "name": name,
            "min": lo,
            "max": hi,
            "queue": queue.value,
            "sla_hours": sla,
        }
        for name, lo, hi, queue, sla, _ in BANDS
    ]
    return ThresholdsOut(
        prompt_version=settings.prompt_version,
        ruleset_version=settings.ruleset_version,
        threshold_version=settings.threshold_version,
        bands=bands,
        auto_clear_qc_sample_rate=settings.auto_clear_qc_sample_rate,
        llm_mock=settings.llm_mock,
        llm_model=settings.llm_model,
    )


# ── Products & search strings ─────────────────────────────────────────


@router.get("/products", response_model=list[ProductOut])
def list_products(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[Product]:
    return list(db.scalars(select(Product).order_by(Product.name)).all())


@router.patch("/products/{product_id}", response_model=ProductOut)
def update_product(
    product_id: int,
    body: ProductUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.PV_LEAD, Role.ADMIN)),
) -> Product:
    product = db.get(Product, product_id)
    if not product:
        raise HTTPException(404, "Product not found")
    data = body.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(product, k, v)
    log_event(
        db,
        actor=user.email,
        action="product_updated",
        entity_type="product",
        entity_id=product.id,
        payload=data,
    )
    db.commit()
    db.refresh(product)
    return product


@router.get("/search-strings", response_model=list[SearchStringOut])
def list_search_strings(
    product_id: Optional[int] = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[SearchString]:
    q = select(SearchString)
    if product_id:
        q = q.where(SearchString.product_id == product_id)
    return list(db.scalars(q.order_by(SearchString.id.desc())).all())


@router.post("/search-strings", response_model=SearchStringOut)
def create_search_string(
    body: SearchStringCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.PV_LEAD, Role.ADMIN)),
) -> SearchString:
    product = db.get(Product, body.product_id)
    if not product:
        raise HTTPException(404, "Product not found")
    for ss in db.scalars(
        select(SearchString).where(
            SearchString.product_id == body.product_id, SearchString.is_active.is_(True)
        )
    ).all():
        ss.is_active = False
    prev = db.scalars(
        select(func.max(SearchString.version)).where(
            SearchString.product_id == body.product_id
        )
    ).first()
    version = (prev or 0) + 1
    ss = SearchString(
        product_id=body.product_id,
        version=version,
        query_text=body.query_text,
        is_active=True,
        approved_by=body.approved_by or user.email,
        notes=body.notes,
    )
    db.add(ss)
    log_event(
        db,
        actor=user.email,
        action="search_string_created",
        entity_type="search_string",
        entity_id=None,
        payload={"version": version, "query": body.query_text},
    )
    db.commit()
    db.refresh(ss)
    return ss


# ── Search runs (PubMed E-utilities) ──────────────────────────────────


@router.get("/search-runs", response_model=list[SearchRunOut])
def list_search_runs(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[SearchRun]:
    return list(
        db.scalars(select(SearchRun).order_by(SearchRun.id.desc()).limit(50)).all()
    )


@router.post("/search-runs", response_model=SearchRunOut)
async def trigger_search(
    body: RunSearchIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.PV_LEAD, Role.ADMIN, Role.REVIEWER)),
) -> SearchRun:
    try:
        return await run_search(
            db,
            body.search_string_id,
            date_from=body.date_from,
            date_to=body.date_to,
            triggered_by=user.email,
            max_fetch=body.max_fetch,
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except Exception as e:
        raise HTTPException(502, f"PubMed search failed: {e}") from e


@router.post("/demo/seed-articles")
async def seed_demo(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.PV_LEAD, Role.ADMIN)),
) -> dict:
    product = db.scalars(select(Product).where(Product.is_active.is_(True))).first()
    if not product:
        raise HTTPException(400, "No active product")
    arts = await seed_demo_articles_async(db, product)
    log_event(
        db,
        actor=user.email,
        action="demo_seed",
        entity_type="product",
        entity_id=product.id,
        payload={"count": len(arts)},
    )
    db.commit()
    return {"seeded": len(arts), "product_id": product.id}


# ── Import ────────────────────────────────────────────────────────────


@router.post("/imports/pmids")
async def import_pmids(
    body: ImportPmidsIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.PV_LEAD, Role.ADMIN, Role.REVIEWER)),
) -> dict:
    pmids = parse_pmid_list(body.pmids_text)
    if not pmids:
        raise HTTPException(400, "No valid PMIDs found")
    try:
        result = await import_pmids_from_pubmed(
            db, product_id=body.product_id, pmids=pmids, actor=user.email
        )
        metrics.imports += 1
        return result
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except Exception as e:
        raise HTTPException(502, f"PubMed EFetch failed: {e}") from e


@router.post("/imports/csv")
async def import_csv(
    body: ImportCsvIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.PV_LEAD, Role.ADMIN)),
) -> dict:
    try:
        rows = parse_articles_csv(body.csv_text)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    if not rows:
        raise HTTPException(400, "No data rows in CSV")
    try:
        result = await import_csv_rows(
            db,
            product_id=body.product_id,
            rows=rows,
            actor=user.email,
            fetch_missing_from_pubmed=body.fetch_missing_from_pubmed,
        )
        metrics.imports += 1
        return result
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except Exception as e:
        raise HTTPException(502, f"Import failed: {e}") from e


# ── Queues & articles ─────────────────────────────────────────────────


@router.get("/queues/stats", response_model=QueueStats)
def queue_stats(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> QueueStats:
    closed = [
        ArticleStatus.DISPOSITION_NOT_CASE,
        ArticleStatus.DISPOSITION_VALID_ICSR,
    ]

    def count_queue(q: QueueType) -> int:
        return (
            db.scalar(
                select(func.count())
                .select_from(TriageAssignment)
                .join(Article, Article.id == TriageAssignment.article_id)
                .where(
                    TriageAssignment.is_active.is_(True),
                    TriageAssignment.queue == q,
                    Article.status.notin_(closed),
                )
            )
            or 0
        )

    def count_status(st: ArticleStatus) -> int:
        return (
            db.scalar(
                select(func.count()).select_from(Article).where(Article.status == st)
            )
            or 0
        )

    return QueueStats(
        expedited=count_queue(QueueType.EXPEDITED),
        priority=count_queue(QueueType.PRIORITY),
        standard=count_queue(QueueType.STANDARD),
        qc_sample=count_queue(QueueType.QC_SAMPLE),
        auto_clear=count_status(ArticleStatus.AUTO_CLEAR),
        valid_icsr=count_status(ArticleStatus.DISPOSITION_VALID_ICSR),
        not_case=count_status(ArticleStatus.DISPOSITION_NOT_CASE),
        deferred=count_status(ArticleStatus.DEFERRED),
        second_review=count_status(ArticleStatus.SECOND_REVIEW),
    )


@router.get("/articles", response_model=list[ArticleListItem])
def list_articles(
    queue: Optional[QueueType] = None,
    status: Optional[ArticleStatus] = None,
    product_id: Optional[int] = None,
    q: Optional[str] = None,
    open_only: bool = Query(default=True),
    include_archive: bool = Query(default=False),
    overdue_only: bool = Query(default=False),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[ArticleListItem]:
    query = select(Article)
    if product_id:
        query = query.where(Article.product_id == product_id)
    if status:
        query = query.where(Article.status == status)
        open_only = False  # explicit status wins
    if include_archive:
        # Archive browse: auto-clear + not-case + valid icsr
        query = query.where(
            Article.status.in_(
                [
                    ArticleStatus.AUTO_CLEAR,
                    ArticleStatus.DISPOSITION_NOT_CASE,
                    ArticleStatus.DISPOSITION_VALID_ICSR,
                ]
            )
        )
    elif open_only and not status:
        query = query.where(
            Article.status.notin_(
                [
                    ArticleStatus.DISPOSITION_NOT_CASE,
                    ArticleStatus.DISPOSITION_VALID_ICSR,
                    ArticleStatus.AUTO_CLEAR,
                ]
            )
        )
    if q:
        like = f"%{q}%"
        query = query.where(
            or_(Article.title.ilike(like), Article.pmid.ilike(like), Article.abstract.ilike(like))
        )

    articles = list(db.scalars(query.order_by(Article.id.desc()).limit(300)).all())
    items: list[ArticleListItem] = []
    now = datetime.now(timezone.utc)
    for a in articles:
        triage = next((t for t in a.triage_assignments if t.is_active), None)
        if queue and (not triage or triage.queue != queue):
            continue
        if overdue_only:
            if not triage or not triage.sla_due_at:
                continue
            due = triage.sla_due_at
            if due.tzinfo is None:
                due = due.replace(tzinfo=timezone.utc)
            if due >= now:
                continue
        screening = (
            max(a.screening_results, key=lambda s: s.id) if a.screening_results else None
        )
        items.append(
            ArticleListItem(
                id=a.id,
                pmid=a.pmid,
                title=a.title,
                journal=a.journal,
                pub_date=a.pub_date,
                status=a.status,
                product_id=a.product_id,
                composite=screening.composite if screening else None,
                queue=triage.queue if triage else None,
                sla_due_at=triage.sla_due_at if triage else None,
                hard_rule_triggered=bool(triage and triage.hard_rule_triggered),
                assignee_id=a.assignee_id,
            )
        )
    items.sort(key=lambda x: (x.sla_due_at is None, x.sla_due_at or datetime.max))
    return items


@router.get("/articles/{article_id}", response_model=ArticleDetail)
def get_article(
    article_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> ArticleDetail:
    a = db.get(Article, article_id)
    if not a:
        raise HTTPException(404, "Article not found")
    screening = (
        max(a.screening_results, key=lambda s: s.id) if a.screening_results else None
    )
    triage = next((t for t in a.triage_assignments if t.is_active), None)
    decisions = [
        {
            "id": d.id,
            "action": d.action.value,
            "rationale": d.rationale,
            "reviewer_id": d.reviewer_id,
            "identifiable_patient": d.identifiable_patient,
            "suspect_drug": d.suspect_drug,
            "adverse_event": d.adverse_event,
            "identifiable_reporter": d.identifiable_reporter,
            "created_at": d.created_at.isoformat() if d.created_at else None,
        }
        for d in sorted(a.review_decisions, key=lambda d: d.id, reverse=True)
    ]
    audit = list(
        db.scalars(
            select(AuditEvent)
            .where(
                AuditEvent.entity_type == "article",
                AuditEvent.entity_id == str(article_id),
            )
            .order_by(AuditEvent.id.desc())
            .limit(50)
        ).all()
    )
    audit_events = [
        {
            "id": e.id,
            "actor": e.actor,
            "action": e.action,
            "payload": e.payload,
            "created_at": e.created_at.isoformat() if e.created_at else None,
        }
        for e in audit
    ]
    return ArticleDetail(
        id=a.id,
        pmid=a.pmid,
        doi=a.doi,
        title=a.title,
        abstract=a.abstract,
        journal=a.journal,
        authors=a.authors or [],
        pub_date=a.pub_date,
        mesh_terms=a.mesh_terms or [],
        publication_types=a.publication_types or [],
        pubmed_url=a.pubmed_url,
        status=a.status,
        product_id=a.product_id,
        assignee_id=a.assignee_id,
        latest_screening=screening,
        active_triage=triage,
        decisions=decisions,
        audit_events=audit_events,
    )


@router.post("/articles/{article_id}/claim")
def claim_article(
    article_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    a = db.get(Article, article_id)
    if not a:
        raise HTTPException(404, "Article not found")
    a.assignee_id = user.id
    if a.status in (
        ArticleStatus.ROUTED,
        ArticleStatus.QC_SAMPLE,
        ArticleStatus.SECOND_REVIEW,
        ArticleStatus.DEFERRED,
    ):
        a.status = ArticleStatus.UNDER_REVIEW
    log_event(
        db,
        actor=user.email,
        action="article_claimed",
        entity_type="article",
        entity_id=a.id,
    )
    db.commit()
    return {"article_id": a.id, "assignee_id": user.id}


@router.post("/articles/{article_id}/review", response_model=ReviewOut)
def submit_review(
    article_id: int,
    body: ReviewIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ReviewDecision:
    a = db.get(Article, article_id)
    if not a:
        raise HTTPException(404, "Article not found")

    decision = ReviewDecision(
        article_id=a.id,
        reviewer_id=user.id,
        action=body.action,
        rationale=body.rationale,
        identifiable_patient=body.identifiable_patient,
        suspect_drug=body.suspect_drug,
        adverse_event=body.adverse_event,
        identifiable_reporter=body.identifiable_reporter,
        seriousness=body.seriousness,
        listedness=body.listedness,
        patient_age_range=body.patient_age_range,
        patient_sex=body.patient_sex,
        patient_country=body.patient_country,
        event_terms=body.event_terms,
        suspect_products=body.suspect_products,
        override_notes=body.override_notes,
    )
    db.add(decision)

    if body.action == DecisionAction.CONFIRM_NOT_CASE:
        a.status = ArticleStatus.DISPOSITION_NOT_CASE
    elif body.action == DecisionAction.CONFIRM_VALID_ICSR:
        a.status = ArticleStatus.DISPOSITION_VALID_ICSR
    elif body.action == DecisionAction.REQUEST_SECOND_REVIEW:
        a.status = ArticleStatus.SECOND_REVIEW
    elif body.action == DecisionAction.DEFER_FULL_TEXT:
        a.status = ArticleStatus.DEFERRED
    elif body.action == DecisionAction.RECALL_TO_REVIEW:
        a.status = ArticleStatus.UNDER_REVIEW
    elif body.action == DecisionAction.OVERRIDE_AI:
        a.status = ArticleStatus.UNDER_REVIEW

    log_event(
        db,
        actor=user.email,
        action=f"review_{body.action.value}",
        entity_type="article",
        entity_id=a.id,
        payload={"rationale": body.rationale},
    )
    db.commit()
    db.refresh(decision)
    metrics.reviews += 1
    return decision


@router.post("/articles/{article_id}/rescore")
async def rescore(
    article_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.PV_LEAD, Role.ADMIN, Role.SENIOR_REVIEWER)),
) -> dict:
    try:
        screening = await rescore_article(db, article_id, actor=user.email)
    except ValueError as e:
        raise HTTPException(404, str(e)) from e
    return {
        "article_id": article_id,
        "screening_id": screening.id,
        "composite": screening.composite,
        "model_id": screening.model_id,
    }


@router.post("/articles/{article_id}/recall")
def recall(
    article_id: int,
    body: RecallIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    try:
        art = recall_article_to_review(
            db, article_id, actor=user.email, rationale=body.rationale
        )
    except ValueError as e:
        raise HTTPException(404, str(e)) from e
    return {"article_id": art.id, "status": art.status.value}


# ── Export ────────────────────────────────────────────────────────────


@router.post("/exports/icsr", response_model=ExportOut)
def export_icsr(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ExportPackage:
    pkg = create_icsr_export(db, actor=user.email, created_by=user.id)
    metrics.exports += 1
    return pkg


@router.post("/exports/parallel-run", response_model=ExportOut)
def export_parallel_run(
    product_id: Optional[int] = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.PV_LEAD, Role.ADMIN)),
) -> ExportPackage:
    return create_parallel_run_export(
        db, actor=user.email, product_id=product_id, created_by=user.id
    )


@router.get("/exports", response_model=list[ExportOut])
def list_exports(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[ExportPackage]:
    return list(
        db.scalars(select(ExportPackage).order_by(ExportPackage.id.desc()).limit(20)).all()
    )


@router.get("/exports/{export_id}")
def get_export(
    export_id: int,
    format: str = Query(default="json", pattern="^(json|csv)$"),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> Response:
    pkg = db.get(ExportPackage, export_id)
    if not pkg:
        raise HTTPException(404, "Export not found")
    if format == "csv":
        csv_body = (pkg.payload_json or {}).get("csv") or ""
        return Response(
            content=csv_body,
            media_type="text/csv",
            headers={
                "Content-Disposition": f'attachment; filename="{pkg.filename.replace(".json", ".csv")}"'
            },
        )
    import json

    body = json.dumps(pkg.payload_json, indent=2)
    return Response(
        content=body,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{pkg.filename}"'},
    )


# ── Evaluation ────────────────────────────────────────────────────────


@router.post("/evaluation/run")
async def run_evaluation(
    _: User = Depends(require_roles(Role.PV_LEAD, Role.ADMIN)),
) -> dict:
    """Run gold-label evaluation (sensitivity primary KPI)."""
    return await evaluate_gold_set()


# ── Audit ─────────────────────────────────────────────────────────────


@router.get("/audit", response_model=list[AuditOut])
def list_audit(
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    action: Optional[str] = None,
    limit: int = Query(default=100, le=500),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[AuditEvent]:
    q = select(AuditEvent).order_by(AuditEvent.id.desc()).limit(limit)
    if entity_type:
        q = q.where(AuditEvent.entity_type == entity_type)
    if entity_id:
        q = q.where(AuditEvent.entity_id == entity_id)
    if action:
        q = q.where(AuditEvent.action == action)
    return list(db.scalars(q).all())


# ── SLA / ops / jobs ──────────────────────────────────────────────────


@router.get("/sla/overdue")
def sla_overdue(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> dict:
    items = list_overdue_articles(db)
    return {"count": len(items), "items": items}


@router.get("/sla/summary")
def get_sla_summary(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> dict:
    return sla_summary(db)


@router.post("/sla/notify")
def sla_notify(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.PV_LEAD, Role.ADMIN)),
) -> dict:
    """Enqueue SLA check job (logs + optional email)."""
    job = enqueue_job(
        db,
        job_type="sla_check",
        payload={"requested_by": user.email},
        created_by=user.email,
    )
    return {"job_id": job.id, "status": job.status.value}


@router.get("/ops/metrics")
def ops_metrics(
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(Role.PV_LEAD, Role.ADMIN)),
) -> dict:
    return metrics.snapshot(extra={"sla": sla_summary(db)})


@router.post("/jobs/batch-rescore", response_model=JobOut)
def job_batch_rescore(
    body: BatchRescoreIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.PV_LEAD, Role.ADMIN, Role.SENIOR_REVIEWER)),
) -> Job:
    ids = list(body.article_ids)
    if body.all_open:
        open_arts = db.scalars(
            select(Article).where(
                Article.status.notin_(
                    [
                        ArticleStatus.DISPOSITION_NOT_CASE,
                        ArticleStatus.DISPOSITION_VALID_ICSR,
                        ArticleStatus.AUTO_CLEAR,
                    ]
                )
            )
        ).all()
        ids = [a.id for a in open_arts]
    if not ids:
        raise HTTPException(400, "No article_ids provided")
    if len(ids) > 500:
        raise HTTPException(400, "Max 500 articles per batch rescore job")
    job = enqueue_job(
        db,
        job_type="batch_rescore",
        payload={"article_ids": ids, "actor": user.email},
        created_by=user.email,
    )
    return job


@router.post("/jobs/run-search", response_model=JobOut)
def job_run_search(
    search_string_id: int,
    max_fetch: int = 50,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.PV_LEAD, Role.ADMIN)),
) -> Job:
    job = enqueue_job(
        db,
        job_type="run_search",
        payload={
            "search_string_id": search_string_id,
            "max_fetch": max_fetch,
            "actor": user.email,
        },
        created_by=user.email,
    )
    return job


@router.get("/jobs", response_model=list[JobOut])
def list_jobs(
    status: Optional[str] = None,
    limit: int = Query(default=50, le=200),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[Job]:
    q = select(Job).order_by(Job.id.desc()).limit(limit)
    if status:
        from app.models.entities import JobStatus

        try:
            q = q.where(Job.status == JobStatus(status))
        except ValueError:
            raise HTTPException(400, f"Invalid status: {status}")
    return list(db.scalars(q).all())


@router.get("/jobs/{job_id}", response_model=JobOut)
def get_job(
    job_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> Job:
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return job


@router.post("/jobs/{job_id}/retry", response_model=JobOut)
def retry_job(
    job_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.PV_LEAD, Role.ADMIN)),
) -> Job:
    """Re-enqueue a failed job with the same payload (dead-letter recovery)."""
    old = db.get(Job, job_id)
    if not old:
        raise HTTPException(404, "Job not found")
    if old.status.value != "failed":
        raise HTTPException(400, "Only failed jobs can be retried")
    job = enqueue_job(
        db,
        job_type=old.job_type,
        payload=old.payload or {},
        created_by=user.email,
    )
    log_event(
        db,
        actor=user.email,
        action="job_retried",
        entity_type="job",
        entity_id=job.id,
        payload={"from_job_id": old.id},
    )
    db.commit()
    db.refresh(job)
    return job
