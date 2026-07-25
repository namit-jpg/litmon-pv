"""Structured ICSR export packages (JSON + CSV) for case-management handoff."""

from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Article, ExportPackage, User
from app.models.entities import ArticleStatus
from app.services.audit import log_event


def build_icsr_records(db: Session, articles: list[Article]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for a in articles:
        screening = (
            max(a.screening_results, key=lambda s: s.id) if a.screening_results else None
        )
        last_decision = (
            max(a.review_decisions, key=lambda d: d.id) if a.review_decisions else None
        )
        reviewer = db.get(User, last_decision.reviewer_id) if last_decision else None
        records.append(
            {
                "pmid": a.pmid,
                "doi": a.doi,
                "title": a.title,
                "journal": a.journal,
                "publication_date": a.pub_date.isoformat() if a.pub_date else None,
                "pubmed_url": a.pubmed_url,
                "suspect_products": (last_decision.suspect_products if last_decision else None)
                or (screening.entities.get("drugs") if screening else [])
                or [],
                "adverse_events": (last_decision.event_terms if last_decision else None)
                or (screening.entities.get("events") if screening else [])
                or [],
                "patient_age_range": last_decision.patient_age_range if last_decision else None,
                "patient_sex": last_decision.patient_sex if last_decision else None,
                "patient_country": last_decision.patient_country if last_decision else None,
                "identifiable_patient": last_decision.identifiable_patient
                if last_decision
                else None,
                "suspect_drug": last_decision.suspect_drug if last_decision else None,
                "adverse_event": last_decision.adverse_event if last_decision else None,
                "identifiable_reporter": last_decision.identifiable_reporter
                if last_decision
                else None,
                "seriousness": last_decision.seriousness if last_decision else None,
                "listedness": last_decision.listedness if last_decision else None,
                "reviewer": reviewer.email if reviewer else None,
                "decision_date": last_decision.created_at.isoformat()
                if last_decision and last_decision.created_at
                else None,
                "rationale": last_decision.rationale if last_decision else None,
                "ai_model_id": screening.model_id if screening else None,
                "ai_product_match": screening.product_match if screening else None,
                "ai_event_relevance": screening.event_relevance if screening else None,
                "ai_icsr_criteria_match": screening.icsr_criteria_match if screening else None,
                "ai_composite": screening.composite if screening else None,
                "ai_reason_tags": screening.reason_tags if screening else [],
                "ai_prompt_version": screening.prompt_version if screening else None,
                "ai_ruleset_version": screening.ruleset_version if screening else None,
                "ai_threshold_version": screening.threshold_version if screening else None,
            }
        )
    return records


def records_to_csv(records: list[dict[str, Any]]) -> str:
    if not records:
        return "pmid,title,status\n"
    # Flatten list fields for CSV
    flat: list[dict[str, Any]] = []
    for r in records:
        row = dict(r)
        for key in ("suspect_products", "adverse_events", "ai_reason_tags"):
            val = row.get(key)
            if isinstance(val, list):
                row[key] = json.dumps(val, ensure_ascii=False)
        flat.append(row)
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(flat[0].keys()))
    writer.writeheader()
    writer.writerows(flat)
    return buf.getvalue()


def create_icsr_export(
    db: Session,
    *,
    actor: str,
    created_by: int | None,
) -> ExportPackage:
    articles = list(
        db.scalars(
            select(Article).where(Article.status == ArticleStatus.DISPOSITION_VALID_ICSR)
        ).all()
    )
    records = build_icsr_records(db, articles)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    pkg = ExportPackage(
        filename=f"icsr_export_{ts}.json",
        article_ids=[a.id for a in articles],
        record_count=len(records),
        payload_json={
            "generated_at": ts,
            "format": "icsr_handoff_v1",
            "records": records,
            "csv": records_to_csv(records),
        },
        created_by=created_by,
    )
    db.add(pkg)
    log_event(
        db,
        actor=actor,
        action="export_icsr",
        entity_type="export_package",
        entity_id=None,
        payload={"count": len(records)},
    )
    db.commit()
    db.refresh(pkg)
    return pkg


def create_parallel_run_export(
    db: Session,
    *,
    actor: str,
    product_id: int | None,
    created_by: int | None,
) -> ExportPackage:
    """Export AI routing for parallel-run comparison (manual column blank)."""
    q = select(Article)
    if product_id:
        q = q.where(Article.product_id == product_id)
    articles = list(db.scalars(q.order_by(Article.id)).all())
    rows: list[dict[str, Any]] = []
    for a in articles:
        screening = (
            max(a.screening_results, key=lambda s: s.id) if a.screening_results else None
        )
        triage = next((t for t in a.triage_assignments if t.is_active), None)
        rows.append(
            {
                "article_id": a.id,
                "pmid": a.pmid,
                "title": a.title,
                "pub_date": a.pub_date.isoformat() if a.pub_date else None,
                "system_status": a.status.value if hasattr(a.status, "value") else a.status,
                "system_queue": triage.queue.value if triage else None,
                "system_composite": screening.composite if screening else None,
                "system_hard_rules": triage.hard_rules if triage else [],
                "system_summary": screening.summary_for_reviewer if screening else None,
                "manual_disposition": "",  # filled by PV team during parallel run
                "manual_is_icsr": "",
                "manual_notes": "",
                "agreement": "",  # computed offline after manual fill
            }
        )
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    pkg = ExportPackage(
        filename=f"parallel_run_{ts}.json",
        article_ids=[a.id for a in articles],
        record_count=len(rows),
        payload_json={
            "generated_at": ts,
            "format": "parallel_run_v1",
            "records": rows,
            "csv": records_to_csv(rows),
        },
        created_by=created_by,
    )
    db.add(pkg)
    log_event(
        db,
        actor=actor,
        action="export_parallel_run",
        entity_type="export_package",
        entity_id=None,
        payload={"count": len(rows), "product_id": product_id},
    )
    db.commit()
    db.refresh(pkg)
    return pkg
