"""Search → ingest → score → triage orchestration."""

from __future__ import annotations

import random
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import (
    Article,
    ArticleAppearance,
    LiteratureSource,
    Product,
    ScreeningResult,
    SearchRun,
    SearchString,
    TriageAssignment,
)
from app.models.entities import (
    ArticleStatus,
    Classification,
    ExceptionCause,
    Priority,
    QueueType,
    SearchRunStatus,
)
from app.services.ai.scorer import score_article
from app.services import triggers
from app.services.omnichannel import route_article
from app.services.audit import log_event
from app.services.pubmed.client import PubMedClient
from app.services.pubmed.errors import PubMedError
from app.services.triage.engine import route_screening


#: Priority follows the queue the triage engine already picked, so the two
#: cannot disagree. Expedited work is P1, priority P2, everything else P3.
_QUEUE_PRIORITY = {
    QueueType.EXPEDITED: Priority.P1,
    QueueType.PRIORITY: Priority.P2,
}


def _priority_for_queue(queue: QueueType) -> Priority:
    return _QUEUE_PRIORITY.get(queue, Priority.P3)


def pubmed_source_id(db: Session) -> int | None:
    """The LiteratureSource row for PubMed, which is what the pilot retrieves from.

    Returns ``None`` rather than raising if the row is absent: a missing source
    label is not a reason to refuse to ingest safety literature.
    """
    return db.scalar(select(LiteratureSource.id).where(LiteratureSource.name == "PubMed"))


def product_name_list(product: Product) -> list[str]:
    names = [product.name]
    if product.inn:
        names.append(product.inn)
    # Tagged Active Pharmaceutical Ingredients widen the match set — a
    # combination product is recognised by any of its substances.
    for ingredient in product.active_ingredients or []:
        names.append(ingredient.name)
        if ingredient.inn:
            names.append(ingredient.inn)
    names.extend(product.brands or [])
    names.extend(product.synonyms or [])
    # de-dupe preserve order
    seen: set[str] = set()
    out: list[str] = []
    for n in names:
        key = n.strip().lower()
        if key and key not in seen:
            seen.add(key)
            out.append(n.strip())
    return out


async def run_search(
    db: Session,
    search_string_id: int,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    triggered_by: str = "system",
    max_fetch: int = 50,
) -> SearchRun:
    """Execute PubMed ESearch/EFetch, ingest, score, and triage new articles."""
    settings = get_settings()
    ss = db.get(SearchString, search_string_id)
    if not ss:
        raise ValueError("Search string not found")
    product = db.get(Product, ss.product_id)
    if not product:
        raise ValueError("Product not found")

    if date_to is None:
        date_to = date.today()
    if date_from is None:
        date_from = date_to - timedelta(days=7)

    run = SearchRun(
        search_string_id=ss.id,
        status=SearchRunStatus.RUNNING,
        query_snapshot=ss.query_text,
        date_from=date_from,
        date_to=date_to,
        triggered_by=triggered_by,
        started_at=datetime.now(timezone.utc),
    )
    db.add(run)
    db.flush()
    log_event(
        db,
        actor=triggered_by,
        action="search_run_started",
        entity_type="search_run",
        entity_id=run.id,
        payload={"query": ss.query_text, "date_from": str(date_from), "date_to": str(date_to)},
    )
    db.commit()
    db.refresh(run)

    try:
        async with PubMedClient() as client:
            es = await client.esearch(
                ss.query_text, date_from=date_from, date_to=date_to
            )
            run.hit_count = es.count
            run.raw_response_hash = es.raw_hash
            run.query_snapshot = es.query

            pmids = es.pmids[:max_fetch]
            existing = {
                a.pmid: a
                for a in db.scalars(
                    select(Article).where(
                        Article.product_id == product.id,
                        Article.pmid.in_(pmids),
                    )
                ).all()
            } if pmids else {}

            new_pmids = [p for p in pmids if p not in existing]
            rehit_pmids = [p for p in pmids if p in existing]

            for pmid in rehit_pmids:
                art = existing[pmid]
                db.add(
                    ArticleAppearance(
                        article_id=art.id,
                        search_run_id=run.id,
                        is_first_seen=False,
                    )
                )
            run.rehit_count = len(rehit_pmids)

            fetched = await client.efetch(new_pmids) if new_pmids else []
            names = product_name_list(product)
            new_count = 0
            source_id = pubmed_source_id(db)

            for dto in fetched:
                article = Article(
                    product_id=product.id,
                    pmid=dto.pmid,
                    doi=dto.doi,
                    title=dto.title,
                    abstract=dto.abstract,
                    journal=dto.journal,
                    authors=dto.authors,
                    pub_date=dto.pub_date,
                    mesh_terms=dto.mesh_terms,
                    publication_types=dto.publication_types,
                    pubmed_url=dto.pubmed_url,
                    content_hash=dto.content_hash,
                    status=ArticleStatus.NEW_ALERT,
                    # Without this every newly ingested article is source-less
                    # and drops out of the source filter and the dashboard's
                    # by-source breakdown. The migration backfilled the old
                    # rows; the ingest path has to stamp the new ones.
                    literature_source_id=source_id,
                )
                db.add(article)
                db.flush()
                db.add(
                    ArticleAppearance(
                        article_id=article.id,
                        search_run_id=run.id,
                        is_first_seen=True,
                    )
                )
                if not (dto.abstract or "").strip():
                    # Nothing to screen against. Auto-clearing this as
                    # irrelevant would be a silent discard of a possibly
                    # reportable article, so it goes to a human instead.
                    triggers.flag_exception(
                        db,
                        article=article,
                        cause=ExceptionCause.FULL_TEXT_UNAVAILABLE,
                        detail="PubMed returned no abstract for this record.",
                        user_id=product.primary_reviewer_id,
                    )
                else:
                    try:
                        await score_and_route_article(db, article, product, names)
                    except Exception as score_exc:  # noqa: BLE001
                        # One unscoreable article must not fail the whole run
                        # and lose the other results with it.
                        triggers.flag_exception(
                            db,
                            article=article,
                            cause=ExceptionCause.EXTRACTION_FAILED,
                            detail=str(score_exc),
                            user_id=product.primary_reviewer_id,
                        )
                        log_event(
                            db,
                            actor=triggered_by,
                            action="article_scoring_failed",
                            entity_type="article",
                            entity_id=article.id,
                            payload={
                                "error": str(score_exc),
                                "error_type": type(score_exc).__name__,
                            },
                        )
                new_count += 1

            run.new_article_count = new_count
            run.status = SearchRunStatus.COMPLETED
            run.completed_at = datetime.now(timezone.utc)
            log_event(
                db,
                actor=triggered_by,
                action="search_run_completed",
                entity_type="search_run",
                entity_id=run.id,
                payload={
                    "hit_count": run.hit_count,
                    "new": run.new_article_count,
                    "rehit": run.rehit_count,
                    "fetched_limit": max_fetch,
                },
            )
            db.commit()
            db.refresh(run)
            from app.core.metrics import metrics

            metrics.record_search(ok=True, new_articles=new_count)
            return run
    except Exception as exc:
        if isinstance(exc, PubMedError):
            err_text = exc.user_message
            retryable = exc.retryable
        else:
            err_text = str(exc)
            retryable = True
        run.status = SearchRunStatus.FAILED
        run.error_message = err_text
        run.completed_at = datetime.now(timezone.utc)
        triggers.search_failed(
            db,
            product=product,
            user_id=product.primary_reviewer_id,
            run_id=run.id,
            error=err_text,
        )
        log_event(
            db,
            actor=triggered_by,
            action="search_run_failed",
            entity_type="search_run",
            entity_id=run.id,
            payload={
                "error": err_text,
                "error_type": type(exc).__name__,
                "retryable": retryable,
            },
        )
        db.commit()
        db.refresh(run)
        from app.core.metrics import metrics

        metrics.record_search(ok=False)
        # Attach for API layer; still raise so callers can surface HTTP errors
        if isinstance(exc, PubMedError):
            raise
        raise PubMedError(
            str(exc),
            user_message=f"PubMed search failed: {exc}",
            retryable=True,
        ) from exc


async def retry_search_run(
    db: Session,
    search_run_id: int,
    *,
    triggered_by: str = "system",
    max_fetch: int = 50,
) -> SearchRun:
    """Re-run a failed (or any) SearchRun with the same string and date window."""
    prior = db.get(SearchRun, search_run_id)
    if not prior:
        raise ValueError("Search run not found")
    if prior.status == SearchRunStatus.RUNNING:
        raise ValueError("Search run is still running")
    new_run = await run_search(
        db,
        prior.search_string_id,
        date_from=prior.date_from,
        date_to=prior.date_to,
        triggered_by=triggered_by,
        max_fetch=max_fetch,
    )
    log_event(
        db,
        actor=triggered_by,
        action="search_run_retried",
        entity_type="search_run",
        entity_id=new_run.id,
        payload={"from_run_id": prior.id, "prior_status": prior.status.value},
    )
    db.commit()
    db.refresh(new_run)
    return new_run


async def score_and_route_article(
    db: Session,
    article: Article,
    product: Product,
    names: list[str] | None = None,
) -> ScreeningResult:
    import time

    from app.core.metrics import metrics

    settings = get_settings()
    names = names or product_name_list(product)
    t0 = time.perf_counter()
    try:
        output, model_id, is_mock, meta = await score_article(
            title=article.title,
            abstract=article.abstract,
            product_names=names,
            mesh_terms=list(article.mesh_terms or []),
            journal=article.journal,
        )
        metrics.record_score(
            (time.perf_counter() - t0) * 1000,
            ok=True,
            used_fallback=bool(meta.get("llm_fallback")),
            llm_timeout=bool(meta.get("llm_timeout")),
            llm_retry=int(meta.get("llm_retries") or 0),
        )
    except Exception:
        metrics.record_score((time.perf_counter() - t0) * 1000, ok=False)
        raise
    screening = ScreeningResult(
        article_id=article.id,
        product_match=output.product_match,
        event_relevance=output.event_relevance,
        icsr_criteria_match=output.icsr_criteria_match,
        composite=output.composite,
        entities=output.entities,
        indication=output.indication,
        dosage=output.dosage,
        outcome=output.outcome,
        seriousness=output.seriousness,
        country_of_occurrence=output.country_of_occurrence,
        reporter_type=output.reporter_type,
        concomitant_medication=output.concomitant_medication,
        article_excerpts=output.article_excerpts,
        relevance_reason=output.relevance_reason,
        confidence=output.confidence,
        processed_at=datetime.now(timezone.utc),
        icsr_precheck=output.icsr_precheck.model_dump(),
        reason_tags=[t.model_dump() for t in output.reason_tags],
        hard_rule_candidates=list(output.hard_rule_candidates),
        summary_for_reviewer=output.summary_for_reviewer,
        model_id=model_id,
        prompt_version=settings.prompt_version,
        ruleset_version=settings.ruleset_version,
        threshold_version=settings.threshold_version,
        is_mock=is_mock,
    )
    db.add(screening)
    db.flush()
    if meta.get("llm_fallback"):
        log_event(
            db,
            actor="system",
            action="llm_fallback_heuristic",
            entity_type="article",
            entity_id=article.id,
            payload={
                "model_id": model_id,
                "error": meta.get("error"),
                "llm_timeout": meta.get("llm_timeout"),
                "llm_retries": meta.get("llm_retries"),
                "fail_open": True,
            },
        )

    decision = route_screening(output)
    queue = decision.queue
    status = ArticleStatus.AWAITING_REVIEW
    # The AI proposal. Written once here and never overwritten — the reviewer's
    # verdict lands in human_classification instead, so the override rate stays
    # measurable.
    classification = Classification.POTENTIALLY_RELEVANT
    priority = _priority_for_queue(queue)

    if queue == QueueType.AUTO_CLEAR:
        # 10% QC sample
        if random.random() < settings.auto_clear_qc_sample_rate:
            queue = QueueType.QC_SAMPLE
            status = ArticleStatus.QC_SAMPLE
        else:
            status = ArticleStatus.ARCHIVED
            classification = Classification.IRRELEVANT
    if decision.hard_rule_triggered:
        classification = Classification.POTENTIAL_SAFETY_SIGNAL

    # Deactivate prior triage
    for t in article.triage_assignments:
        t.is_active = False

    triage = TriageAssignment(
        article_id=article.id,
        screening_result_id=screening.id,
        queue=queue,
        sla_hours=decision.sla_hours,
        sla_due_at=decision.sla_due_at,
        hard_rule_triggered=decision.hard_rule_triggered,
        hard_rules=decision.hard_rules,
        ruleset_version=settings.ruleset_version,
        threshold_version=settings.threshold_version,
        is_active=True,
    )
    db.add(triage)
    article.status = status
    article.ai_classification = classification
    article.priority = priority
    if status != ArticleStatus.ARCHIVED:
        assignee, routing_reason = route_article(db, product=product, article=article)
        article.assignee_id = assignee.id if assignee else None
        if assignee:
            triggers.awaiting_review(
                db,
                article=article,
                user_id=assignee.id,
                queue=queue.value,
                high=queue in (QueueType.EXPEDITED, QueueType.PRIORITY),
            )
        # Content-driven triggers: a potential signal or a serious outcome is
        # worth its own alert regardless of which queue the article landed in.
        triggers.on_article_scored(
            db,
            article=article,
            user_id=article.assignee_id or product.primary_reviewer_id,
            classification=classification,
            confidence=screening.confidence,
            seriousness=screening.seriousness,
        )
        log_event(
            db,
            actor="system",
            action="omni_work_routed",
            entity_type="article",
            entity_id=article.id,
            payload={
                "assignee_id": assignee.id if assignee else None,
                "routing_reason": routing_reason,
                "queue": queue.value,
            },
        )
    log_event(
        db,
        actor="system",
        action="article_scored_routed",
        entity_type="article",
        entity_id=article.id,
        payload={
            "composite": screening.composite,
            "queue": queue.value,
            "band": decision.band,
            "model_id": model_id,
            "is_mock": is_mock,
            "llm_fallback": bool(meta.get("llm_fallback")),
        },
    )
    return screening


async def rescore_article(
    db: Session,
    article_id: int,
    *,
    actor: str = "system",
) -> ScreeningResult:
    """Re-run AI scoring + triage for an existing article (append-only scores)."""
    article = db.get(Article, article_id)
    if not article:
        raise ValueError("Article not found")
    product = db.get(Product, article.product_id)
    if not product:
        raise ValueError("Product not found")
    screening = await score_and_route_article(db, article, product)
    log_event(
        db,
        actor=actor,
        action="article_rescored",
        entity_type="article",
        entity_id=article.id,
        payload={"screening_id": screening.id, "composite": screening.composite},
    )
    db.commit()
    db.refresh(screening)
    return screening


def recall_article_to_review(
    db: Session,
    article_id: int,
    *,
    actor: str,
    rationale: str | None = None,
) -> Article:
    """Bring auto-cleared or disposed article back into active review (reversible archive)."""
    article = db.get(Article, article_id)
    if not article:
        raise ValueError("Article not found")
    article.status = ArticleStatus.UNDER_ASSESSMENT
    # Ensure there is an active triage on standard queue if none
    triage = next((t for t in article.triage_assignments if t.is_active), None)
    if triage and triage.queue == QueueType.AUTO_CLEAR:
        triage.is_active = False
        from datetime import datetime, timedelta, timezone
        from app.core.config import get_settings

        settings = get_settings()
        now = datetime.now(timezone.utc)
        screening = (
            max(article.screening_results, key=lambda s: s.id)
            if article.screening_results
            else None
        )
        if screening:
            db.add(
                TriageAssignment(
                    article_id=article.id,
                    screening_result_id=screening.id,
                    queue=QueueType.STANDARD,
                    sla_hours=5 * 24,
                    sla_due_at=now + timedelta(hours=5 * 24),
                    hard_rule_triggered=False,
                    hard_rules=[],
                    ruleset_version=settings.ruleset_version,
                    threshold_version=settings.threshold_version,
                    is_active=True,
                )
            )
    log_event(
        db,
        actor=actor,
        action="article_recalled",
        entity_type="article",
        entity_id=article.id,
        payload={"rationale": rationale},
    )
    db.commit()
    db.refresh(article)
    return article
