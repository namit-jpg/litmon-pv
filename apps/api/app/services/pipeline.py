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
    Product,
    ScreeningResult,
    SearchRun,
    SearchString,
    TriageAssignment,
)
from app.models.entities import ArticleStatus, QueueType, SearchRunStatus
from app.services.ai.scorer import score_article
from app.services.audit import log_event
from app.services.pubmed.client import PubMedClient
from app.services.triage.engine import route_screening


def product_name_list(product: Product) -> list[str]:
    names = [product.name]
    if product.inn:
        names.append(product.inn)
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
                    select(Article).where(Article.pmid.in_(pmids))
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
                    status=ArticleStatus.INGESTED,
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
                await score_and_route_article(db, article, product, names)
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
        run.status = SearchRunStatus.FAILED
        run.error_message = str(exc)
        run.completed_at = datetime.now(timezone.utc)
        log_event(
            db,
            actor=triggered_by,
            action="search_run_failed",
            entity_type="search_run",
            entity_id=run.id,
            payload={"error": str(exc)},
        )
        db.commit()
        db.refresh(run)
        from app.core.metrics import metrics

        metrics.record_search(ok=False)
        raise


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
        output, model_id, is_mock = await score_article(
            title=article.title,
            abstract=article.abstract,
            product_names=names,
            mesh_terms=list(article.mesh_terms or []),
            journal=article.journal,
        )
        metrics.record_score((time.perf_counter() - t0) * 1000, ok=True)
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

    decision = route_screening(output)
    queue = decision.queue
    status = ArticleStatus.ROUTED

    if queue == QueueType.AUTO_CLEAR:
        # 10% QC sample
        if random.random() < settings.auto_clear_qc_sample_rate:
            queue = QueueType.QC_SAMPLE
            status = ArticleStatus.QC_SAMPLE
        else:
            status = ArticleStatus.AUTO_CLEAR
    elif queue == QueueType.EXPEDITED:
        status = ArticleStatus.ROUTED
    elif queue == QueueType.PRIORITY:
        status = ArticleStatus.ROUTED
    else:
        status = ArticleStatus.ROUTED

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
    article.status = ArticleStatus.UNDER_REVIEW
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


async def seed_demo_articles_async(db: Session, product: Product) -> list[Article]:
    samples: list[dict[str, Any]] = [
        {
            "pmid": "90000001",
            "title": "Fatal hepatotoxicity associated with DrugX in a 67-year-old woman: a case report",
            "abstract": (
                "We report a 67-year-old woman who developed acute liver failure and death "
                "after exposure to DrugX for hypertension. Authors describe the adverse reaction "
                "and hospital course. This case suggests a possible drug-induced liver injury."
            ),
            "journal": "Demo Journal of Drug Safety",
        },
        {
            "pmid": "90000002",
            "title": "Efficacy of DrugX in phase III hypertension trial",
            "abstract": (
                "A randomized controlled trial of DrugX versus placebo demonstrated significant "
                "blood pressure reduction. Safety was similar between arms with mild headache only. "
                "No serious adverse events related to DrugX were observed."
            ),
            "journal": "Demo Cardiology",
        },
        {
            "pmid": "90000003",
            "title": "Pregnancy outcome after first-trimester DrugX exposure: case series",
            "abstract": (
                "We describe three pregnant patients exposed to DrugX during the first trimester. "
                "One neonate had congenital anomaly. Reporter is the treating obstetrician."
            ),
            "journal": "Demo Reproductive Toxicology",
        },
        {
            "pmid": "90000004",
            "title": "Molecular mechanisms of calcium channel signaling in vascular smooth muscle",
            "abstract": (
                "This review discusses ion channel biophysics and preclinical models. "
                "No clinical adverse event data are presented."
            ),
            "journal": "Demo Physiology",
        },
        {
            "pmid": "90000005",
            "title": "Anaphylaxis in a child following DrugX administration",
            "abstract": (
                "A 9-year-old boy developed anaphylaxis minutes after DrugX infusion. "
                "The pediatric team reports successful treatment with epinephrine."
            ),
            "journal": "Demo Pediatrics",
        },
    ]
    created: list[Article] = []
    names = product_name_list(product)
    for s in samples:
        existing = db.scalars(select(Article).where(Article.pmid == s["pmid"])).first()
        if existing:
            created.append(existing)
            continue
        art = Article(
            product_id=product.id,
            pmid=s["pmid"],
            title=s["title"],
            abstract=s["abstract"],
            journal=s["journal"],
            authors=["Demo Author"],
            pub_date=date.today() - timedelta(days=3),
            mesh_terms=["Drug-Related Side Effects and Adverse Reactions"],
            publication_types=["Case Reports"],
            pubmed_url=f"https://pubmed.ncbi.nlm.nih.gov/{s['pmid']}/",
            status=ArticleStatus.INGESTED,
        )
        db.add(art)
        db.flush()
        await score_and_route_article(db, art, product, names)
        created.append(art)
    db.commit()
    return created
