"""Local mirror of the NLM RxNorm drug catalogue.

The product picker searches this table rather than calling RxNorm per
keystroke, so it responds instantly and keeps working offline once synced.
Nothing in here is hand-authored — every row comes from RxNorm.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import ActiveIngredient, DrugConcept
from app.services.audit import log_event
from app.services.rxnorm import RxNormClient, RxNormError
from app.services.rxnorm.client import TTY_LABEL

logger = logging.getLogger("litmon.drug_catalog")

# Ingredient beats brand beats combination when scores tie: searching
# "atorvastatin" should surface the substance before "Lipitor".
_TTY_RANK = {"IN": 0, "BN": 1, "MIN": 2}


def catalog_size(db: Session) -> int:
    return db.scalar(select(func.count(DrugConcept.id))) or 0


def last_synced_at(db: Session) -> datetime | None:
    return db.scalar(select(func.max(DrugConcept.synced_at)))


async def sync_catalog(db: Session, *, actor: str = "system") -> dict[str, int]:
    """Refresh the local catalogue from RxNorm.

    Upserts by rxcui so a refresh never orphans a product that already points
    at a concept, and never duplicates rows.
    """
    async with RxNormClient() as client:
        concepts = await client.fetch_catalog()

    existing = {
        c.rxcui: c for c in db.scalars(select(DrugConcept)).all()
    }
    now = datetime.now(timezone.utc)
    added = updated = 0
    for dto in concepts:
        row = existing.get(dto.rxcui)
        if row is None:
            db.add(
                DrugConcept(
                    rxcui=dto.rxcui,
                    name=dto.name,
                    name_lower=dto.name.lower(),
                    tty=dto.tty,
                    synced_at=now,
                )
            )
            added += 1
        else:
            if row.name != dto.name or row.tty != dto.tty:
                row.name = dto.name
                row.name_lower = dto.name.lower()
                row.tty = dto.tty
                updated += 1
            row.synced_at = now

    result = {"added": added, "updated": updated, "total": len(concepts)}
    log_event(
        db,
        actor=actor,
        action="drug_catalog_synced",
        entity_type="drug_catalog",
        entity_id="0",
        payload=result,
    )
    db.commit()
    return result


async def derive_ingredient_names(
    rxcui: str | None, name: str, tty: str | None
) -> list[str]:
    """Work out the active substances behind a picked drug concept.

    Ingredients are themselves the substance; a combination carries several,
    separated by "/" in RxNorm; a brand needs a lookup to find what is in it.
    Returns lower-cased names ready to become ActiveIngredient tags.

    Best-effort by design — a product must still be creatable when RxNorm is
    unreachable, just without tags.
    """
    if tty == "MIN" or "/" in name:
        parts = [p.strip().lower() for p in name.split("/")]
        return [p for p in parts if p]
    if tty == "IN":
        return [name.strip().lower()]
    if tty == "BN" and rxcui:
        try:
            async with RxNormClient() as client:
                related = await client.related_names(rxcui)
        except Exception:  # noqa: BLE001 - tags are best-effort, creation is not
            logger.warning(
                "Could not resolve ingredients for brand %s; creating it untagged",
                name,
                exc_info=True,
            )
            return []
        names = related.get("IN") or related.get("MIN") or []
        out: list[str] = []
        for n in names:
            for part in n.split("/"):
                part = part.strip().lower()
                if part and part not in out:
                    out.append(part)
        return out
    return []


def get_or_create_ingredients(db: Session, names: list[str]) -> list[ActiveIngredient]:
    """Resolve substance names to tag rows, reusing any that already exist.

    Names are matched case-insensitively so "Metformin" and "metformin" cannot
    become two separate substances.
    """
    tags: list[ActiveIngredient] = []
    for raw in names:
        cleaned = (raw or "").strip().lower()
        if not cleaned:
            continue
        row = db.scalars(
            select(ActiveIngredient).where(
                func.lower(ActiveIngredient.name) == cleaned
            )
        ).first()
        if row is None:
            row = db.scalars(
                select(ActiveIngredient).where(
                    func.lower(ActiveIngredient.inn) == cleaned
                )
            ).first()
        if row is None:
            row = ActiveIngredient(name=cleaned, inn=cleaned, is_active=True)
            db.add(row)
            db.flush()
        if row not in tags:
            tags.append(row)
    return tags


def search_drugs(db: Session, query: str, limit: int | None = None) -> list[dict]:
    """Rank drug concepts against a typed query.

    Ordering is prefix match first, then substring, then term type, then
    shortest name — so "atorva" puts "atorvastatin" above
    "atorvastatin / amlodipine".
    """
    settings = get_settings()
    cap = limit or settings.drug_search_limit
    term = (query or "").strip().lower()
    if len(term) < 2:
        return []

    like = f"%{term}%"
    rows = db.scalars(
        select(DrugConcept)
        .where(or_(DrugConcept.name_lower.like(like)))
        # Over-fetch so Python-side ranking has candidates to sort, but stay
        # bounded: without this a query like "a" would pull the whole table.
        .limit(cap * 10)
    ).all()

    def rank(c: DrugConcept) -> tuple:
        n = c.name_lower
        if n == term:
            bucket = 0
        elif n.startswith(term):
            bucket = 1
        elif f" {term}" in n or f"/{term}" in n:
            bucket = 2
        else:
            bucket = 3
        return (bucket, _TTY_RANK.get(c.tty, 9), len(n), n)

    rows = sorted(rows, key=rank)[:cap]
    return [
        {
            "rxcui": c.rxcui,
            "name": c.name,
            "tty": c.tty,
            "kind": TTY_LABEL.get(c.tty, c.tty),
        }
        for c in rows
    ]
