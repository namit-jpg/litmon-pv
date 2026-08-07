"""Regulatory validation, versioned prototype generation and manual filing.

The CDSCO field specification is intentionally deployment configuration rather
than application code. Until a partner supplies it, validation reports that it
is not configured and generation remains blocked through these new endpoints.
The legacy pilot export endpoint stays available for backwards compatibility.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Article, ExportPackage, RegulatoryRecord
from app.services.audit import log_event
from app.services.cdsco_xml import build_ichicsr_xml, validate_ichicsr
from app.services.export_service import build_icsr_records

PROTOTYPE_NOTICE = (
    "Prototype only — not a validated CDSCO submission. The official schema, "
    "mandatory fields and acceptance rules have not been supplied."
)


def mandatory_field_rules() -> list[dict[str, Any]]:
    """Read and validate the deployment-provided mandatory-field registry."""
    raw = (get_settings().regulatory_mandatory_fields_json or "").strip()
    if not raw:
        return []
    try:
        rules = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("REGULATORY_MANDATORY_FIELDS_JSON must be valid JSON") from exc
    if not isinstance(rules, list):
        raise ValueError("REGULATORY_MANDATORY_FIELDS_JSON must be a JSON list")
    cleaned: list[dict[str, Any]] = []
    for rule in rules:
        if not isinstance(rule, dict) or not isinstance(rule.get("field"), str):
            raise ValueError("Each regulatory mandatory-field rule needs a string field")
        cleaned.append(
            {
                "field": rule["field"],
                "label": str(rule.get("label") or rule["field"].replace("_", " ").title()),
                "required": bool(rule.get("required", True)),
            }
        )
    return cleaned


def _record_value(record: dict[str, Any], field: str) -> Any:
    """Resolve dotted fields so the registry can evolve without code changes."""
    value: Any = record
    for part in field.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


def _present(value: Any) -> bool:
    if isinstance(value, (list, tuple, dict)):
        return bool(value)
    return value is not None and str(value).strip() != ""


def validate_article(db: Session, article: Article) -> dict[str, Any]:
    rules = mandatory_field_rules()
    records = build_icsr_records(db, [article])
    record = records[0] if records else {}
    fields = []
    blocking: list[str] = []
    for rule in rules:
        value = _record_value(record, rule["field"])
        present = _present(value)
        state = "present" if present else ("missing" if rule["required"] else "not_stated")
        fields.append({**rule, "value": value, "state": state})
        if rule["required"] and not present:
            blocking.append(f"{rule['label']} is required")
    if not rules:
        blocking.append(
            "Mandatory-field specification is not configured; generation is disabled."
        )
    return {
        "article_id": article.id,
        "rules_configured": bool(rules),
        "prototype_notice": PROTOTYPE_NOTICE,
        "fields": fields,
        "blocking_errors": blocking,
        "can_generate": not blocking,
    }


def _next_version(db: Session, article_id: int) -> int:
    packages = list(db.scalars(select(ExportPackage)).all())
    return 1 + sum(
        1
        for package in packages
        if (package.payload_json or {}).get("regulatory", {}).get("article_id") == article_id
    )


def generate_article_export(
    db: Session,
    *,
    article: Article,
    actor: str,
    created_by: int,
    sender_id: str | None = None,
    receiver_id: str | None = None,
) -> ExportPackage:
    validation = validate_article(db, article)
    if not validation["can_generate"]:
        raise ValueError("; ".join(validation["blocking_errors"]))
    settings = get_settings()
    version = _next_version(db, article.id)
    records = build_icsr_records(db, [article])
    xml_doc = build_ichicsr_xml(
        records,
        sender_id=sender_id or settings.cdsco_sender_id,
        receiver_id=receiver_id or settings.cdsco_receiver_id,
        message_number=f"LITMON-{article.id}-v{version}",
    )
    dtd_path = (settings.cdsco_dtd_path or "").strip()
    dtd_valid, dtd_errors = (
        validate_ichicsr(xml_doc, dtd_path)
        if dtd_path
        else (None, ["CDSCO_DTD_PATH not configured"])
    )
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    package = ExportPackage(
        filename=f"cdsco_icsr_article_{article.id}_v{version}_{timestamp}.xml",
        article_ids=[article.id],
        record_count=1,
        payload_json={
            "generated_at": timestamp,
            "format": "cdsco_e2b_r2_ichicsr",
            "xml": xml_doc,
            "records": records,
            "dtd_valid": dtd_valid,
            "dtd_errors": dtd_errors,
            "notes": PROTOTYPE_NOTICE,
            "regulatory": {"article_id": article.id, "version": version},
        },
        created_by=created_by,
    )
    db.add(package)
    db.flush()
    regulatory = db.scalar(
        select(RegulatoryRecord).where(RegulatoryRecord.article_id == article.id)
    )
    if regulatory is None:
        regulatory = RegulatoryRecord(article_id=article.id, updated_by=created_by)
        db.add(regulatory)
    regulatory.latest_export_id = package.id
    regulatory.updated_by = created_by
    log_event(
        db,
        actor=actor,
        action="regulatory_generated",
        entity_type="article",
        entity_id=article.id,
        payload={"export_id": package.id, "version": version},
    )
    db.commit()
    db.refresh(package)
    return package
