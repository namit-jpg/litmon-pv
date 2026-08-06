from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.encoders import jsonable_encoder
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
    ActiveIngredient,
    Alert,
    Article,
    AuditEvent,
    ExportPackage,
    Job,
    Product,
    ReviewDecision,
    ScreeningResult,
    SearchRun,
    SearchSchedule,
    SearchString,
    TriageAssignment,
    User,
)
from app.models.entities import (
    ArticleStatus,
    DecisionAction,
    QueueType,
    Role,
    SignalStatus,
    PresenceStatus,
    product_active_ingredients,
)
from app.schemas.api import (
    ActiveIngredientIn,
    ActiveIngredientOut,
    ActiveIngredientUpdate,
    ArticleDetail,
    ArticleListItem,
    AlertOut,
    AuditOut,
    ExportOut,
    DrugCatalogStatus,
    DrugConceptOut,
    DrugRef,
    ImportCsvIn,
    ImportPmidsIn,
    ProductCreate,
    ProductOut,
    ProductUpdate,
    QueueStats,
    RecallIn,
    RetrySearchRunIn,
    ReviewIn,
    ReviewOut,
    RunSearchIn,
    RunSearchNowIn,
    SearchRunArticleItem,
    SearchRunDetail,
    SearchRunOut,
    SearchScheduleCreate,
    SearchScheduleOut,
    SearchScheduleUpdate,
    SearchStringCreate,
    SearchStringOut,
    ThresholdsOut,
    TokenOut,
    UserOut,
)
from app.services.audit import log_event
from app.services.alerts import create_alert, mark_alert_read
from app.services.drug_catalog import (
    catalog_size,
    derive_ingredient_names,
    get_or_create_ingredients,
    last_synced_at,
    list_drugs,
    resolve_drug_to_product,
    sync_catalog,
)
from app.services.rxnorm import RxNormError
from app.services.schedules import (
    active_search_string,
    default_lookback_days,
    run_due_schedules,
)
from app.services.omnichannel import active_work_count, route_article
from app.services.evaluation import evaluate_gold_set
from app.services.export_service import (
    create_cdsco_export,
    create_icsr_export,
    create_parallel_run_export,
)
from app.services.import_service import (
    import_csv_rows,
    import_pmids_from_pubmed,
    parse_articles_csv,
    parse_pmid_list,
)
from app.services.jobs import enqueue_job
from app.services.pipeline import (
    product_name_list,
    recall_article_to_review,
    rescore_article,
    retry_search_run,
    run_search,
)
from app.services.pubmed.errors import PubMedError
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


@router.get("/users", response_model=list[UserOut])
def list_users(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[UserOut]:
    users = list(
        db.scalars(select(User).where(User.is_active.is_(True)).order_by(User.full_name)).all()
    )
    return [
        UserOut(
            id=u.id,
            email=u.email,
            full_name=u.full_name,
            role=u.role,
            presence_status=u.presence_status,
            capacity_limit=u.capacity_limit,
            active_work_count=active_work_count(db, u.id),
        )
        for u in users
    ]


class PresenceUpdate(BaseModel):
    status: PresenceStatus


@router.get("/presence")
def get_presence(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    return {
        "user_id": user.id,
        "status": user.presence_status.value,
        "capacity_limit": user.capacity_limit,
        "active_work_count": active_work_count(db, user.id),
        "available_capacity": max((user.capacity_limit or 20) - active_work_count(db, user.id), 0),
    }


@router.patch("/presence")
def update_presence(
    body: PresenceUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    previous = user.presence_status
    user.presence_status = body.status
    log_event(
        db,
        actor=user.email,
        action="presence_changed",
        entity_type="user",
        entity_id=user.id,
        payload={"previous": previous.value, "current": body.status.value},
    )
    db.commit()
    return get_presence(db=db, user=user)


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
    key_ok = bool((settings.llm_api_key or "").strip())
    if settings.llm_mock:
        llm_mode = "mock"
    elif not key_ok:
        llm_mode = "mock_no_key"
    else:
        llm_mode = "live"
    email = (settings.ncbi_email or "").strip()
    email_ok = bool(email) and email not in (
        "dev@example.com",
        "your.email@company.com",
    )
    return ThresholdsOut(
        prompt_version=settings.prompt_version,
        ruleset_version=settings.ruleset_version,
        threshold_version=settings.threshold_version,
        bands=bands,
        auto_clear_qc_sample_rate=settings.auto_clear_qc_sample_rate,
        llm_mock=settings.llm_mock or not key_ok,
        llm_model=settings.llm_model,
        llm_base_url=settings.llm_base_url,
        llm_api_key_configured=key_ok,
        llm_mode=llm_mode,
        fail_open_on_llm_error=True,
        ncbi_email_configured=email_ok,
        ncbi_api_key_configured=bool((settings.ncbi_api_key or "").strip()),
    )


# ── Products & search strings ─────────────────────────────────────────


@router.get("/products", response_model=list[ProductOut])
def list_products(
    include_inactive: bool = Query(default=False),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[Product]:
    q = select(Product)
    if not include_inactive:
        q = q.where(Product.is_active.is_(True))
    return list(db.scalars(q.order_by(Product.name)).all())


# Standard pharmacovigilance literature-monitoring terms. Paired with the
# product's own names to form a starter PubMed query the PV lead can then edit.
_SAFETY_TERMS = (
    'adverse OR toxicity OR safety OR "case report" OR "adverse drug reaction" '
    "OR interaction OR pregnancy OR overdose OR hypersensitivity"
)


def build_starter_query(names: list[str]) -> str:
    """Compose a PubMed query from a product's names plus safety terms."""
    unique: list[str] = []
    for n in names:
        n = (n or "").strip()
        if n and n.lower() not in {u.lower() for u in unique}:
            unique.append(n)
    if not unique:
        raise ValueError("At least one product name is required")
    # Quote multi-word terms so PubMed treats them as phrases.
    terms = " OR ".join(f'"{n}"' if " " in n else n for n in unique)
    return f"({terms}) AND ({_SAFETY_TERMS})"


@router.post("/products", response_model=ProductOut, status_code=201)
async def create_product(
    body: ProductCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.PV_LEAD, Role.ADMIN)),
) -> Product:
    """Create a monitored product and its first search string."""
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "Product name is required")

    existing = db.scalars(
        select(Product).where(func.lower(Product.name) == name.lower())
    ).first()
    if existing:
        if existing.is_active:
            raise HTTPException(409, f"A product named '{existing.name}' already exists")
        # Reactivate rather than create a duplicate row, so the product keeps
        # its article history and audit trail.
        existing.is_active = True
        # A product retired before tag derivation existed comes back untagged,
        # which would silently empty its substance column — so backfill here.
        if not existing.active_ingredients:
            derived = await derive_ingredient_names(
                body.rxcui, existing.name, body.tty
            )
            if derived:
                existing.active_ingredients = get_or_create_ingredients(db, derived)
                if not existing.inn:
                    existing.inn = derived[0]
        log_event(
            db,
            actor=user.email,
            action="product_reactivated",
            entity_type="product",
            entity_id=str(existing.id),
            payload={
                "name": existing.name,
                "active_ingredients": [t.name for t in existing.active_ingredients],
            },
        )
        db.commit()
        db.refresh(existing)
        return existing

    if body.primary_reviewer_id is not None:
        reviewer = db.get(User, body.primary_reviewer_id)
        if not reviewer or not reviewer.is_active:
            raise HTTPException(400, "primary_reviewer_id is not an active user")

    product = Product(
        name=name,
        inn=(body.inn or "").strip() or None,
        brands=[b for b in (body.brands or []) if str(b).strip()],
        synonyms=[s for s in (body.synonyms or []) if str(s).strip()],
        atc_code=(body.atc_code or "").strip() or None,
        is_active=True,
        primary_reviewer_id=body.primary_reviewer_id,
    )

    db.add(product)
    db.flush()

    if body.active_ingredient_ids:
        tags = list(
            db.scalars(
                select(ActiveIngredient).where(
                    ActiveIngredient.id.in_(body.active_ingredient_ids)
                )
            ).all()
        )
        found = {t.id for t in tags}
        missing = [i for i in body.active_ingredient_ids if i not in found]
        if missing:
            raise HTTPException(400, f"Unknown active_ingredient_ids: {missing}")
        product.active_ingredients = tags
    else:
        # Derive the substances from the picked RxNorm concept. Without this a
        # product created through the picker would carry no API tags at all,
        # which empties the reviewer's substance column and drops
        # activesubstancename from the E2B export.
        derived = await derive_ingredient_names(body.rxcui, product.name, body.tty)
        if derived:
            product.active_ingredients = get_or_create_ingredients(db, derived)
            if not product.inn:
                product.inn = derived[0]

    query_text = (body.query_text or "").strip()
    if not query_text:
        names = [product.name, product.inn or "", *product.brands, *product.synonyms]
        query_text = build_starter_query([n for n in names if n])
    db.add(
        SearchString(
            product_id=product.id,
            version=1,
            query_text=query_text,
            is_active=True,
            approved_by=user.email,
            notes="Created with the product; review before relying on it.",
        )
    )

    log_event(
        db,
        actor=user.email,
        action="product_created",
        entity_type="product",
        entity_id=str(product.id),
        payload={
            "name": product.name,
            "inn": product.inn,
            "rxcui": body.rxcui,
            "brands": product.brands,
            "query_text": query_text,
        },
    )
    db.commit()
    db.refresh(product)
    return product


@router.delete("/products/{product_id}", response_model=ProductOut)
def deactivate_product(
    product_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.PV_LEAD, Role.ADMIN)),
) -> Product:
    """Stop monitoring a product.

    Deliberately a soft delete: articles, decisions and audit history for a
    monitored product must survive, so the row is deactivated rather than
    removed. Any recurring schedules are stopped at the same time.
    """
    product = db.get(Product, product_id)
    if not product:
        raise HTTPException(404, "Product not found")

    product.is_active = False
    stopped = 0
    for schedule in db.scalars(
        select(SearchSchedule).where(
            SearchSchedule.product_id == product_id,
            SearchSchedule.is_active.is_(True),
        )
    ).all():
        schedule.is_active = False
        stopped += 1

    log_event(
        db,
        actor=user.email,
        action="product_deactivated",
        entity_type="product",
        entity_id=str(product_id),
        payload={"name": product.name, "schedules_stopped": stopped},
    )
    db.commit()
    db.refresh(product)
    return product


# ── Drug catalogue (NLM RxNorm mirror) ────────────────────────────────


@router.get("/drugs", response_model=list[DrugConceptOut])
def list_drug_catalog(
    q: str = Query(default="", description="Optional drug name filter"),
    limit: Optional[int] = Query(default=None, ge=1, le=500),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[dict]:
    """Drugs for the picker, annotated with which are already monitored.

    With no filter this returns the opening page of the catalogue.
    """
    return list_drugs(db, q, limit)


@router.get("/drugs/search", response_model=list[DrugConceptOut])
def search_drug_catalog(
    q: str = Query(min_length=2, description="Drug name fragment"),
    limit: Optional[int] = Query(default=None, ge=1, le=500),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[dict]:
    return list_drugs(db, q, limit)


@router.get("/drugs/status", response_model=DrugCatalogStatus)
def drug_catalog_status(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> DrugCatalogStatus:
    return DrugCatalogStatus(
        total=catalog_size(db), last_synced_at=last_synced_at(db)
    )


@router.post("/drugs/sync", response_model=DrugCatalogStatus)
async def sync_drug_catalog(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.PV_LEAD, Role.ADMIN)),
) -> DrugCatalogStatus:
    """Refresh the local drug catalogue from NLM RxNorm."""
    try:
        await sync_catalog(db, actor=user.email)
    except RxNormError as exc:
        raise HTTPException(
            502,
            detail={
                "message": exc.user_message,
                "retryable": exc.retryable,
                "error_type": "rxnorm",
            },
        )
    return DrugCatalogStatus(
        total=catalog_size(db), last_synced_at=last_synced_at(db)
    )


# ── Active Pharmaceutical Ingredients (API tags) ──────────────────────


@router.get("/active-ingredients", response_model=list[ActiveIngredientOut])
def list_active_ingredients(
    include_inactive: bool = Query(default=False),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[ActiveIngredient]:
    q = select(ActiveIngredient)
    if not include_inactive:
        q = q.where(ActiveIngredient.is_active.is_(True))
    return list(db.scalars(q.order_by(ActiveIngredient.name)).all())


@router.post("/active-ingredients", response_model=ActiveIngredientOut)
def create_active_ingredient(
    body: ActiveIngredientIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.PV_LEAD, Role.ADMIN)),
) -> ActiveIngredient:
    # Substance names are matched case-insensitively; store them normalised so
    # "Metformin" and "metformin" cannot become two different APIs.
    name = (body.name or "").strip().lower()
    if not name:
        raise HTTPException(400, "Active ingredient name is required")
    existing = db.scalars(
        select(ActiveIngredient).where(func.lower(ActiveIngredient.name) == name)
    ).first()
    if existing:
        raise HTTPException(409, f"Active ingredient '{name}' already exists")
    ingredient = ActiveIngredient(
        name=name,
        inn=(body.inn or "").strip().lower() or None,
        atc_code=(body.atc_code or "").strip() or None,
        unii=(body.unii or "").strip() or None,
    )
    db.add(ingredient)
    db.flush()
    log_event(
        db,
        actor=user.email,
        action="active_ingredient_created",
        entity_type="active_ingredient",
        entity_id=ingredient.id,
        payload={"name": ingredient.name},
    )
    db.commit()
    db.refresh(ingredient)
    return ingredient


@router.patch("/active-ingredients/{ingredient_id}", response_model=ActiveIngredientOut)
def update_active_ingredient(
    ingredient_id: int,
    body: ActiveIngredientUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.PV_LEAD, Role.ADMIN)),
) -> ActiveIngredient:
    ingredient = db.get(ActiveIngredient, ingredient_id)
    if not ingredient:
        raise HTTPException(404, "Active ingredient not found")
    data = body.model_dump(exclude_unset=True)
    if "name" in data and data["name"]:
        data["name"] = data["name"].strip().lower()
    if "inn" in data and data["inn"]:
        data["inn"] = data["inn"].strip().lower()
    for k, v in data.items():
        setattr(ingredient, k, v)
    log_event(
        db,
        actor=user.email,
        action="active_ingredient_updated",
        entity_type="active_ingredient",
        entity_id=ingredient.id,
        payload=data,
    )
    db.commit()
    db.refresh(ingredient)
    return ingredient


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
    reviewer_id = data.get("primary_reviewer_id")
    if reviewer_id is not None:
        reviewer = db.get(User, reviewer_id)
        if not reviewer or not reviewer.is_active:
            raise HTTPException(400, "Primary reviewer must be an active user")
    # API tags are a relationship, not a column — resolve before the setattr loop.
    ingredient_ids = data.pop("active_ingredient_ids", None)
    if ingredient_ids is not None:
        ingredients = list(
            db.scalars(
                select(ActiveIngredient).where(ActiveIngredient.id.in_(ingredient_ids))
            ).all()
        )
        missing = set(ingredient_ids) - {i.id for i in ingredients}
        if missing:
            raise HTTPException(
                400, f"Unknown active ingredient id(s): {sorted(missing)}"
            )
        product.active_ingredients = ingredients
    for k, v in data.items():
        setattr(product, k, v)
    reassigned = 0
    if "primary_reviewer_id" in data:
        open_articles = list(
            db.scalars(
                select(Article).where(
                    Article.product_id == product.id,
                    Article.status.notin_(
                        [
                            ArticleStatus.AUTO_CLEAR,
                            ArticleStatus.DISPOSITION_NOT_CASE,
                            ArticleStatus.DISPOSITION_VALID_ICSR,
                        ]
                    ),
                )
            ).all()
        )
        for article in open_articles:
            assignee, routing_reason = route_article(
                db, product=product, article=article
            )
            if article.assignee_id == (assignee.id if assignee else None):
                continue
            article.assignee_id = assignee.id if assignee else None
            reassigned += 1
            create_alert(
                db,
                user_id=assignee.id if assignee else None,
                article_id=article.id,
                alert_type="work_assigned",
                priority="normal",
                title=f"{product.name} review assigned",
                message=f"{article.title} ({routing_reason.replace('_', ' ')})",
                dedupe_key=f"product-reassignment:{article.id}:{assignee.id if assignee else 'unassigned'}",
            )
    log_event(
        db,
        actor=user.email,
        action="product_updated",
        entity_type="product",
        entity_id=product.id,
        payload={**data, "open_articles_reassigned": reassigned},
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


@router.get("/search-runs/{run_id}", response_model=SearchRunDetail)
def get_search_run(
    run_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> SearchRunDetail:
    run = db.get(SearchRun, run_id)
    if not run:
        raise HTTPException(404, "Search run not found")
    ss = db.get(SearchString, run.search_string_id)
    product = db.get(Product, ss.product_id) if ss else None
    articles: list[SearchRunArticleItem] = []
    for app in run.appearances:
        art = app.article
        if not art:
            continue
        triage = next((t for t in art.triage_assignments if t.is_active), None)
        screening = (
            max(art.screening_results, key=lambda s: s.id)
            if art.screening_results
            else None
        )
        articles.append(
            SearchRunArticleItem(
                id=art.id,
                pmid=art.pmid,
                title=art.title,
                status=art.status,
                is_first_seen=app.is_first_seen,
                composite=screening.composite if screening else None,
                queue=triage.queue if triage else None,
            )
        )
    articles.sort(key=lambda a: (not a.is_first_seen, a.id))
    return SearchRunDetail(
        id=run.id,
        search_string_id=run.search_string_id,
        status=run.status,
        query_snapshot=run.query_snapshot,
        date_from=run.date_from,
        date_to=run.date_to,
        hit_count=run.hit_count,
        new_article_count=run.new_article_count,
        rehit_count=run.rehit_count,
        error_message=run.error_message,
        triggered_by=run.triggered_by,
        started_at=run.started_at,
        completed_at=run.completed_at,
        created_at=run.created_at,
        articles=articles,
        product_id=product.id if product else None,
        product_name=product.name if product else None,
    )


@router.post("/search-runs", response_model=SearchRunOut)
async def trigger_search(
    body: RunSearchIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.PV_LEAD, Role.ADMIN, Role.REVIEWER)),
) -> SearchRun:
    from datetime import date, timedelta

    date_from = body.date_from
    date_to = body.date_to
    if body.days is not None:
        date_to = date.today()
        date_from = date_to - timedelta(days=body.days)
    try:
        return await run_search(
            db,
            body.search_string_id,
            date_from=date_from,
            date_to=date_to,
            triggered_by=user.email,
            max_fetch=body.max_fetch,
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except PubMedError as e:
        # Run is already persisted as FAILED — surface operator-friendly text
        raise HTTPException(
            status_code=502,
            detail={
                "message": e.user_message,
                "retryable": e.retryable,
                "error_type": "PubMedError",
            },
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail={
                "message": f"PubMed search failed: {e}",
                "retryable": True,
                "error_type": type(e).__name__,
            },
        ) from e


async def _resolve_targets(
    db: Session,
    *,
    drugs: list[DrugRef],
    product_ids: list[int],
    actor: str,
) -> list[Product]:
    """Turn a picked drug list into the products to search.

    Products are an internal record, so selecting a drug that is not yet
    monitored provisions one rather than making the user set it up first.
    """
    if not drugs and not product_ids:
        raise HTTPException(400, "Select at least one drug")

    targets: list[Product] = []
    seen: set[int] = set()

    for pid in product_ids:
        product = db.get(Product, pid)
        if not product:
            raise HTTPException(400, f"Product {pid} not found")
        if product.id not in seen:
            seen.add(product.id)
            targets.append(product)

    for drug in drugs:
        product = await resolve_drug_to_product(
            db,
            name=drug.name,
            rxcui=drug.rxcui,
            tty=drug.tty,
            actor=actor,
            build_query=build_starter_query,
        )
        if product.id not in seen:
            seen.add(product.id)
            targets.append(product)

    db.commit()
    return targets


@router.post("/search-runs/run-now")
async def run_search_now(
    body: RunSearchNowIn,
    db: Session = Depends(get_db),
    user: User = Depends(
        require_roles(Role.PV_LEAD, Role.ADMIN, Role.REVIEWER, Role.SENIOR_REVIEWER)
    ),
) -> dict:
    """Run a manual search across several drugs at once.

    Each drug is searched independently and one failing does not abort the
    rest — the caller gets a per-drug result either way.
    """
    date_from = body.date_from
    date_to = body.date_to
    if body.days is not None:
        date_to = date.today()
        date_from = date_to - timedelta(days=body.days)
    if date_from and date_to and date_from > date_to:
        raise HTTPException(400, "date_from must be on or before date_to")

    targets = await _resolve_targets(
        db, drugs=body.drugs, product_ids=body.product_ids, actor=user.email
    )

    results: list[dict] = []
    for product in targets:
        product_id = product.id
        search_string = active_search_string(db, product_id)
        if not search_string:
            results.append(
                {
                    "product_id": product_id,
                    "product_name": product.name,
                    "status": "failed",
                    "error": "No active search string for this drug",
                }
            )
            continue
        try:
            run = await run_search(
                db,
                search_string.id,
                date_from=date_from,
                date_to=date_to,
                triggered_by=user.email,
                max_fetch=body.max_fetch,
            )
            results.append(
                {
                    "product_id": product_id,
                    "product_name": product.name,
                    "status": "completed",
                    "search_run_id": run.id,
                    "hit_count": run.hit_count,
                    "new_articles": run.new_article_count,
                    "rehits": run.rehit_count,
                }
            )
        except PubMedError as e:
            results.append(
                {
                    "product_id": product_id,
                    "product_name": product.name,
                    "status": "failed",
                    "error": e.user_message,
                    "retryable": e.retryable,
                }
            )
        except Exception as e:  # noqa: BLE001 - one product must not sink the batch
            results.append(
                {
                    "product_id": product_id,
                    "product_name": product.name,
                    "status": "failed",
                    "error": str(e)[:300],
                    "retryable": True,
                }
            )

    ok = [r for r in results if r["status"] == "completed"]
    return {
        "requested": len(targets),
        "succeeded": len(ok),
        "failed": len(results) - len(ok),
        "new_articles": sum(r.get("new_articles", 0) for r in ok),
        "results": results,
    }


# ── Scheduled (automated) searches ────────────────────────────────────


def _schedule_out(schedule: SearchSchedule) -> SearchScheduleOut:
    out = SearchScheduleOut.model_validate(schedule)
    out.product_name = schedule.product.name if schedule.product else None
    return out


@router.get("/search-schedules", response_model=list[SearchScheduleOut])
def list_search_schedules(
    include_inactive: bool = Query(default=True),
    product_id: Optional[int] = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[SearchScheduleOut]:
    q = select(SearchSchedule)
    if not include_inactive:
        q = q.where(SearchSchedule.is_active.is_(True))
    if product_id:
        q = q.where(SearchSchedule.product_id == product_id)
    rows = db.scalars(q.order_by(SearchSchedule.id.desc())).all()
    return [_schedule_out(s) for s in rows]


@router.post("/search-schedules", response_model=list[SearchScheduleOut], status_code=201)
async def create_search_schedules(
    body: SearchScheduleCreate,
    db: Session = Depends(get_db),
    user: User = Depends(
        require_roles(Role.PV_LEAD, Role.ADMIN, Role.REVIEWER, Role.SENIOR_REVIEWER)
    ),
) -> list[SearchScheduleOut]:
    """Automate a recurring search for one or more drugs."""
    today = datetime.now(timezone.utc).date()
    if body.end_date < today:
        raise HTTPException(400, "end_date cannot be in the past")

    start_at = body.start_at or datetime.now(timezone.utc)
    if start_at.tzinfo is None:
        start_at = start_at.replace(tzinfo=timezone.utc)

    lookback = body.lookback_days or default_lookback_days(body.frequency)
    targets = await _resolve_targets(
        db, drugs=body.drugs, product_ids=body.product_ids, actor=user.email
    )

    created: list[SearchSchedule] = []
    for product in targets:
        product_id = product.id
        if not active_search_string(db, product_id):
            raise HTTPException(
                400,
                f"'{product.name}' has no active search string to schedule",
            )
        # One active schedule per drug keeps the runner predictable; a new one
        # supersedes the old rather than doubling up on NCBI calls.
        for old in db.scalars(
            select(SearchSchedule).where(
                SearchSchedule.product_id == product_id,
                SearchSchedule.is_active.is_(True),
            )
        ).all():
            old.is_active = False

        schedule = SearchSchedule(
            product_id=product_id,
            frequency=body.frequency,
            end_date=body.end_date,
            lookback_days=lookback,
            max_fetch=body.max_fetch,
            is_active=True,
            next_run_at=start_at,
            created_by=user.email,
        )
        db.add(schedule)
        created.append(schedule)

    db.flush()
    for schedule in created:
        log_event(
            db,
            actor=user.email,
            action="search_schedule_created",
            entity_type="search_schedule",
            entity_id=str(schedule.id),
            payload={
                "product_id": schedule.product_id,
                "frequency": schedule.frequency.value,
                "end_date": schedule.end_date.isoformat(),
                "next_run_at": schedule.next_run_at.isoformat(),
            },
        )
    db.commit()
    for schedule in created:
        db.refresh(schedule)
    return [_schedule_out(s) for s in created]


@router.patch("/search-schedules/{schedule_id}", response_model=SearchScheduleOut)
def update_search_schedule(
    schedule_id: int,
    body: SearchScheduleUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(
        require_roles(Role.PV_LEAD, Role.ADMIN, Role.REVIEWER, Role.SENIOR_REVIEWER)
    ),
) -> SearchScheduleOut:
    schedule = db.get(SearchSchedule, schedule_id)
    if not schedule:
        raise HTTPException(404, "Schedule not found")

    data = body.model_dump(exclude_unset=True)
    if "end_date" in data and data["end_date"] is not None:
        if data["end_date"] < datetime.now(timezone.utc).date():
            raise HTTPException(400, "end_date cannot be in the past")
    for field, value in data.items():
        setattr(schedule, field, value)

    # Resuming a schedule whose next run is in the past would fire immediately;
    # roll it forward instead.
    if schedule.is_active:
        now = datetime.now(timezone.utc)
        nxt = schedule.next_run_at
        if nxt is not None and nxt.tzinfo is None:
            nxt = nxt.replace(tzinfo=timezone.utc)
        if nxt is None or nxt < now:
            schedule.next_run_at = now

    log_event(
        db,
        actor=user.email,
        action="search_schedule_updated",
        entity_type="search_schedule",
        entity_id=str(schedule_id),
        payload=jsonable_encoder(data),
    )
    db.commit()
    db.refresh(schedule)
    return _schedule_out(schedule)


@router.delete("/search-schedules/{schedule_id}", response_model=SearchScheduleOut)
def delete_search_schedule(
    schedule_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(
        require_roles(Role.PV_LEAD, Role.ADMIN, Role.REVIEWER, Role.SENIOR_REVIEWER)
    ),
) -> SearchScheduleOut:
    """Stop a recurring search (soft delete, so the audit trail survives)."""
    schedule = db.get(SearchSchedule, schedule_id)
    if not schedule:
        raise HTTPException(404, "Schedule not found")
    schedule.is_active = False
    log_event(
        db,
        actor=user.email,
        action="search_schedule_stopped",
        entity_type="search_schedule",
        entity_id=str(schedule_id),
        payload={"product_id": schedule.product_id},
    )
    db.commit()
    db.refresh(schedule)
    return _schedule_out(schedule)


@router.post("/search-schedules/run-due")
async def trigger_due_schedules(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.PV_LEAD, Role.ADMIN)),
) -> dict:
    """Fire every schedule that is currently due.

    The in-process runner already does this on a timer; this endpoint exists so
    an external scheduler (cron, Windows Task Scheduler) can drive it instead,
    and so schedules can be tested without waiting for the next tick.
    """
    results = await run_due_schedules(db)
    return {"fired": len(results), "results": results}


@router.post("/search-runs/{run_id}/retry", response_model=SearchRunOut)
async def retry_failed_search_run(
    run_id: int,
    body: RetrySearchRunIn | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.PV_LEAD, Role.ADMIN, Role.REVIEWER)),
) -> SearchRun:
    """Retry a search run (typically FAILED) with the same string and date window."""
    max_fetch = body.max_fetch if body else 30
    try:
        return await retry_search_run(
            db,
            run_id,
            triggered_by=user.email,
            max_fetch=max_fetch,
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except PubMedError as e:
        raise HTTPException(
            status_code=502,
            detail={
                "message": e.user_message,
                "retryable": e.retryable,
                "error_type": "PubMedError",
            },
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail={
                "message": f"PubMed search retry failed: {e}",
                "retryable": True,
                "error_type": type(e).__name__,
            },
        ) from e


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
    mine_only: bool = Query(default=False),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> QueueStats:
    closed = [
        ArticleStatus.DISPOSITION_NOT_CASE,
        ArticleStatus.DISPOSITION_VALID_ICSR,
    ]

    def count_queue(q: QueueType) -> int:
        query = (
            select(func.count())
            .select_from(TriageAssignment)
            .join(Article, Article.id == TriageAssignment.article_id)
            .where(
                TriageAssignment.is_active.is_(True),
                TriageAssignment.queue == q,
                Article.status.notin_(closed),
            )
        )
        if mine_only:
            query = query.where(Article.assignee_id == user.id)
        return db.scalar(query) or 0

    def count_status(st: ArticleStatus) -> int:
        query = select(func.count()).select_from(Article).where(Article.status == st)
        if mine_only:
            query = query.where(Article.assignee_id == user.id)
        return db.scalar(query) or 0

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
    active_ingredient_id: Optional[int] = None,
    q: Optional[str] = None,
    open_only: bool = Query(default=True),
    include_archive: bool = Query(default=False),
    overdue_only: bool = Query(default=False),
    mine_only: bool = Query(default=False),
    assignee_id: Optional[int] = None,
    signal_status: Optional[SignalStatus] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[ArticleListItem]:
    query = select(Article)
    if product_id:
        query = query.where(Article.product_id == product_id)
    if active_ingredient_id:
        # The point of tagging the API: one substance spans many products, so
        # this returns every article for every product carrying that API.
        query = query.where(
            Article.product_id.in_(
                select(product_active_ingredients.c.product_id).where(
                    product_active_ingredients.c.active_ingredient_id
                    == active_ingredient_id
                )
            )
        )
    if status:
        query = query.where(Article.status == status)
        open_only = False  # explicit status wins
    if mine_only:
        query = query.where(Article.assignee_id == user.id)
    elif assignee_id:
        query = query.where(Article.assignee_id == assignee_id)
    if signal_status:
        query = query.where(Article.signal_status == signal_status)
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
    assignee_ids = {a.assignee_id for a in articles if a.assignee_id is not None}
    assignee_names = (
        {
            u.id: u.full_name
            for u in db.scalars(select(User).where(User.id.in_(assignee_ids))).all()
        }
        if assignee_ids
        else {}
    )
    # Batch-load products (with their API tags) once rather than per-row, so
    # reviewers see the substance behind each product without an N+1 query.
    product_ids = {a.product_id for a in articles}
    products_by_id = (
        {
            p.id: p
            for p in db.scalars(
                select(Product).where(Product.id.in_(product_ids))
            ).all()
        }
        if product_ids
        else {}
    )
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
        product = products_by_id.get(a.product_id)
        items.append(
            ArticleListItem(
                id=a.id,
                pmid=a.pmid,
                title=a.title,
                journal=a.journal,
                pub_date=a.pub_date,
                status=a.status,
                product_id=a.product_id,
                product_name=product.name if product else None,
                active_ingredients=product.active_ingredients if product else [],
                composite=screening.composite if screening else None,
                queue=triage.queue if triage else None,
                sla_due_at=triage.sla_due_at if triage else None,
                hard_rule_triggered=bool(triage and triage.hard_rule_triggered),
                assignee_id=a.assignee_id,
                assignee_name=assignee_names.get(a.assignee_id) if a.assignee_id else None,
                signal_status=a.signal_status,
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
        product_name=a.product.name if a.product else None,
        active_ingredients=a.product.active_ingredients if a.product else [],
        assignee_id=a.assignee_id,
        signal_status=a.signal_status,
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
    db.flush()

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
    elif body.action == DecisionAction.MARK_POTENTIAL_SIGNAL:
        a.signal_status = SignalStatus.POTENTIAL
        a.status = ArticleStatus.UNDER_REVIEW
    elif body.action == DecisionAction.CONFIRM_SIGNAL:
        if user.role not in (Role.PV_LEAD, Role.ADMIN, Role.SENIOR_REVIEWER):
            raise HTTPException(403, "Senior reviewer or PV lead required to confirm a signal")
        a.signal_status = SignalStatus.CONFIRMED
        a.status = ArticleStatus.UNDER_REVIEW
    elif body.action == DecisionAction.REJECT_SIGNAL:
        a.signal_status = SignalStatus.REJECTED
        a.status = ArticleStatus.UNDER_REVIEW

    if body.action in (
        DecisionAction.MARK_POTENTIAL_SIGNAL,
        DecisionAction.CONFIRM_SIGNAL,
        DecisionAction.REJECT_SIGNAL,
    ):
        create_alert(
            db,
            user_id=a.assignee_id or user.id,
            article_id=a.id,
            alert_type="signal_status_changed",
            priority="high" if a.signal_status != SignalStatus.REJECTED else "normal",
            title=a.signal_status.value.replace("_", " ").title(),
            message=f"{a.title} — {body.rationale or 'Signal assessment updated'}",
            dedupe_key=f"signal:{a.id}:{decision.id}",
        )

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


# ── Pilot dashboard & alert inbox ─────────────────────────────────────


@router.get("/dashboard/summary")
def dashboard_summary(
    mine_only: bool = Query(default=False),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    article_filter = Article.assignee_id == user.id if mine_only else None

    def count_where(*conditions: Any) -> int:
        q = select(func.count()).select_from(Article)
        if article_filter is not None:
            q = q.where(article_filter)
        if conditions:
            q = q.where(*conditions)
        return db.scalar(q) or 0

    open_statuses = [
        ArticleStatus.INGESTED,
        ArticleStatus.SCORED,
        ArticleStatus.ROUTED,
        ArticleStatus.UNDER_REVIEW,
        ArticleStatus.DEFERRED,
        ArticleStatus.SECOND_REVIEW,
        ArticleStatus.QC_SAMPLE,
    ]
    by_product_q = (
        select(Product.id, Product.name, func.count(Article.id))
        .join(Article, Article.product_id == Product.id)
        # Retired products keep their articles for audit, but they would
        # otherwise skew the dashboard against the live monitoring set.
        .where(Product.is_active.is_(True))
        .group_by(Product.id, Product.name)
        .order_by(Product.name)
    )
    if article_filter is not None:
        by_product_q = by_product_q.where(article_filter)
    by_product = [
        {"product_id": pid, "product_name": name, "count": count}
        for pid, name, count in db.execute(by_product_q).all()
    ]
    # ── Chart series ──────────────────────────────────────────────────
    # Triage queue mix across open work.
    by_queue_q = (
        select(TriageAssignment.queue, func.count(TriageAssignment.id))
        .join(Article, Article.id == TriageAssignment.article_id)
        .where(
            TriageAssignment.is_active.is_(True),
            Article.status.in_(open_statuses),
        )
        .group_by(TriageAssignment.queue)
    )
    if article_filter is not None:
        by_queue_q = by_queue_q.where(article_filter)
    queue_counts = {q.value: c for q, c in db.execute(by_queue_q).all()}
    by_queue = [
        {"queue": q.value, "count": queue_counts.get(q.value, 0)}
        for q in QueueType
    ]

    # Screening composite distribution, in the bands the triage engine uses.
    buckets = [
        ("0.0-0.2", 0.0, 0.2),
        ("0.2-0.4", 0.2, 0.4),
        ("0.4-0.6", 0.4, 0.6),
        ("0.6-0.8", 0.6, 0.8),
        ("0.8-1.0", 0.8, 1.01),
    ]
    score_buckets = []
    for label, lo, hi in buckets:
        q = (
            select(func.count(ScreeningResult.id))
            .join(Article, Article.id == ScreeningResult.article_id)
            .where(ScreeningResult.composite >= lo, ScreeningResult.composite < hi)
        )
        if article_filter is not None:
            q = q.where(article_filter)
        score_buckets.append({"band": label, "count": db.scalar(q) or 0})

    # Literature volume by publication date, bucketed into weeks.
    #
    # Weekly rather than daily on purpose: PubMed records frequently omit the
    # day component, and the parser falls back to the 1st of the month, so a
    # daily series shows large artificial spikes on the 1st. Weekly buckets
    # smooth that artefact and match the cadence PV teams actually review on.
    today = datetime.now(timezone.utc).date()
    weeks = 8
    # Anchor to the start of the current week (Monday).
    week_start = today - timedelta(days=today.weekday())
    since_day = week_start - timedelta(weeks=weeks - 1)
    trend_q = (
        select(Article.pub_date, func.count(Article.id))
        .join(Product, Product.id == Article.product_id)
        .where(
            Article.pub_date.is_not(None),
            Article.pub_date >= since_day,
            Product.is_active.is_(True),
        )
        .group_by(Article.pub_date)
    )
    if article_filter is not None:
        trend_q = trend_q.where(article_filter)

    week_counts: dict[str, int] = {}
    for pub_day, count in db.execute(trend_q).all():
        if not pub_day:
            continue
        if isinstance(pub_day, str):
            pub_day = datetime.strptime(pub_day, "%Y-%m-%d").date()
        bucket = pub_day - timedelta(days=pub_day.weekday())
        week_counts[bucket.isoformat()] = week_counts.get(bucket.isoformat(), 0) + count

    intake_trend = []
    for i in range(weeks):
        day = since_day + timedelta(weeks=i)
        intake_trend.append(
            {"date": day.isoformat(), "count": week_counts.get(day.isoformat(), 0)}
        )

    unread = db.scalar(
        select(func.count())
        .select_from(Alert)
        .where(Alert.user_id == user.id, Alert.read_at.is_(None))
    ) or 0
    overdue = list_overdue_articles(db)
    if mine_only:
        overdue = [
            i
            for i in overdue
            if (article := db.get(Article, i["id"])) is not None
            and article.assignee_id == user.id
        ]
    return {
        "scope": "mine" if mine_only else "all",
        "total_articles": count_where(),
        "awaiting_review": count_where(Article.status.in_(open_statuses)),
        "unassigned": count_where(
            Article.status.in_(open_statuses), Article.assignee_id.is_(None)
        ),
        "potential_signals": count_where(Article.signal_status == SignalStatus.POTENTIAL),
        "confirmed_signals": count_where(Article.signal_status == SignalStatus.CONFIRMED),
        "valid_icsr": count_where(Article.status == ArticleStatus.DISPOSITION_VALID_ICSR),
        "not_relevant": count_where(Article.status == ArticleStatus.DISPOSITION_NOT_CASE),
        "deferred": count_where(Article.status == ArticleStatus.DEFERRED),
        "overdue": len(overdue),
        "unread_alerts": unread,
        "by_product": by_product,
        "by_queue": by_queue,
        "score_buckets": score_buckets,
        "intake_trend": intake_trend,
    }


@router.get("/alerts", response_model=list[AlertOut])
def list_alerts(
    unread_only: bool = Query(default=False),
    limit: int = Query(default=30, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[Alert]:
    q = select(Alert).where(Alert.user_id == user.id)
    if unread_only:
        q = q.where(Alert.read_at.is_(None))
    return list(db.scalars(q.order_by(Alert.id.desc()).limit(limit)).all())


@router.post("/alerts/{alert_id}/read", response_model=AlertOut)
def read_alert(
    alert_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Alert:
    alert = db.get(Alert, alert_id)
    if not alert or alert.user_id != user.id:
        raise HTTPException(404, "Alert not found")
    mark_alert_read(db, alert, actor=user.email)
    db.commit()
    db.refresh(alert)
    return alert


@router.post("/alerts/read-all")
def read_all_alerts(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    alerts = list(
        db.scalars(
            select(Alert).where(Alert.user_id == user.id, Alert.read_at.is_(None))
        ).all()
    )
    for alert in alerts:
        mark_alert_read(db, alert, actor=user.email)
    db.commit()
    return {"updated": len(alerts)}


# ── Export ────────────────────────────────────────────────────────────


@router.post("/exports/icsr", response_model=ExportOut)
def export_icsr(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ExportPackage:
    pkg = create_icsr_export(db, actor=user.email, created_by=user.id)
    metrics.exports += 1
    return pkg


class CdscoExportIn(BaseModel):
    sender_id: Optional[str] = None
    receiver_id: Optional[str] = None


@router.post("/exports/cdsco-xml", response_model=ExportOut)
def export_cdsco_xml(
    body: Optional[CdscoExportIn] = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.PV_LEAD, Role.ADMIN)),
) -> ExportPackage:
    """Build the CDSCO / NCC-PvPI E2B(R2) XML package for confirmed ICSRs."""
    pkg = create_cdsco_export(
        db,
        actor=user.email,
        created_by=user.id,
        sender_id=body.sender_id if body else None,
        receiver_id=body.receiver_id if body else None,
    )
    metrics.exports += 1
    return pkg


@router.get("/exports/{export_id}/xml")
def download_cdsco_xml(
    export_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> Response:
    """Serve a CDSCO export package as a downloadable XML file."""
    pkg = db.get(ExportPackage, export_id)
    if not pkg:
        raise HTTPException(404, "Export not found")
    xml_doc = (pkg.payload_json or {}).get("xml")
    if not xml_doc:
        raise HTTPException(400, "This export package has no XML payload")
    return Response(
        content=xml_doc,
        media_type="application/xml",
        headers={"Content-Disposition": f'attachment; filename="{pkg.filename}"'},
    )


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
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(Role.PV_LEAD, Role.ADMIN)),
) -> dict:
    """Run gold-label evaluation (sensitivity primary KPI).

    Scores the validation set against the products actually being monitored,
    so the KPI reflects the live configuration rather than a fixture.
    """
    names: list[str] = []
    for product in db.scalars(
        select(Product).where(Product.is_active.is_(True))
    ).all():
        names.extend(product_name_list(product))
    if not names:
        return {
            "configured": False,
            "message": "Add at least one monitored product before running evaluation.",
            "total": 0,
        }
    try:
        return await evaluate_gold_set(product_names=names)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


# ── Audit ─────────────────────────────────────────────────────────────


@router.get("/audit", response_model=list[AuditOut])
def list_audit(
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    action: Optional[str] = None,
    limit: int = Query(default=100, le=500),
    db: Session = Depends(get_db),
    # The audit trail is a controlled record covering every reviewer's actions,
    # so it is an oversight function rather than something a reviewer browses.
    _: User = Depends(require_roles(Role.PV_LEAD, Role.ADMIN)),
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
    _: User = Depends(require_roles(Role.PV_LEAD, Role.ADMIN)),
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
    _: User = Depends(require_roles(Role.PV_LEAD, Role.ADMIN)),
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
