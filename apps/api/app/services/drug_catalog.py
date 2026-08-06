"""Local mirror of the NLM RxNorm drug catalogue.

The drug picker searches this table rather than calling RxNorm per keystroke,
so it responds instantly and keeps working offline once synced. Nothing in here
is hand-authored — every row is a real, currently-marketed drug from RxNorm.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import ActiveIngredient, Article, DrugConcept, Product, SearchString
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


async def resolve_drug_to_product(
    db: Session,
    *,
    name: str,
    rxcui: str | None,
    tty: str | None,
    actor: str,
    build_query,
) -> Product:
    """Return the product backing a drug, creating it on first use.

    Monitoring a drug needs a product row to hang articles, search strings and
    triage off, but that is bookkeeping the user should never have to perform.
    Picking a drug and searching is enough; this fills in the rest.
    """
    clean = name.strip()
    product = db.scalars(
        select(Product).where(func.lower(Product.name) == clean.lower())
    ).first()

    if product:
        if not product.is_active:
            product.is_active = True
            log_event(
                db,
                actor=actor,
                action="product_reactivated",
                entity_type="product",
                entity_id=str(product.id),
                payload={"name": product.name, "via": "drug_search"},
            )
        if not product.active_ingredients:
            derived = await derive_ingredient_names(rxcui, product.name, tty)
            if derived:
                product.active_ingredients = get_or_create_ingredients(db, derived)
                if not product.inn:
                    product.inn = derived[0]
        db.flush()
        return product

    product = Product(
        name=clean,
        inn=clean.lower() if tty == "IN" else None,
        brands=[clean] if tty == "BN" else [],
        synonyms=[],
        is_active=True,
    )
    db.add(product)
    db.flush()

    derived = await derive_ingredient_names(rxcui, clean, tty)
    if derived:
        product.active_ingredients = get_or_create_ingredients(db, derived)
        if not product.inn:
            product.inn = derived[0]

    names = [product.name, product.inn or "", *product.brands]
    names += [t.name for t in product.active_ingredients]
    db.add(
        SearchString(
            product_id=product.id,
            version=1,
            query_text=build_query([n for n in names if n]),
            is_active=True,
            approved_by=actor,
            notes="Generated when the drug was first searched; review before relying on it.",
        )
    )
    log_event(
        db,
        actor=actor,
        action="product_created",
        entity_type="product",
        entity_id=str(product.id),
        payload={"name": product.name, "rxcui": rxcui, "via": "drug_search"},
    )
    db.flush()
    return product


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


# Characters that mark an RxNorm entry as a chemical descriptor rather than a
# name a person would recognise, e.g. "(-)-ambroxide" or a bis(...)ester.
_UNREADABLE = set("()[]{},;")


def _is_readable(name: str) -> bool:
    """Whether a concept name reads as a medicine rather than a formula."""
    if len(name) > 45:
        return False
    return not any(ch in _UNREADABLE for ch in name)


def _monitored_index(db: Session) -> dict[str, dict]:
    """Map lower-cased product name to its monitoring state.

    Lets the picker show what is already being watched without the caller
    issuing a query per drug.
    """
    counts = dict(
        db.execute(
            select(Article.product_id, func.count(Article.id)).group_by(
                Article.product_id
            )
        ).all()
    )
    index: dict[str, dict] = {}
    for p in db.scalars(select(Product).where(Product.is_active.is_(True))).all():
        index[p.name.lower()] = {
            "product_id": p.id,
            "article_count": counts.get(p.id, 0),
            "name": p.name,
        }
    return index


def _monitored_entries(
    monitored: dict[str, dict], by_name: dict[str, DrugConcept], term: str
) -> list[dict]:
    """Picker rows for drugs already being watched.

    Built from what is monitored rather than from the catalogue, so a drug
    stays visible even if the catalogue has not been synced or no longer
    carries that concept. Otherwise a user could be monitoring something they
    can no longer see or stop.
    """
    out: list[dict] = []
    for key, state in sorted(monitored.items()):
        if term and term not in key:
            continue
        concept = by_name.get(key)
        out.append(
            {
                "rxcui": concept.rxcui if concept else f"local:{state['product_id']}",
                "name": state["name"],
                "tty": concept.tty if concept else "IN",
                "kind": TTY_LABEL.get(concept.tty, "drug") if concept else "drug",
                "is_monitored": True,
                "product_id": state["product_id"],
                "article_count": state["article_count"],
            }
        )
    return out


def list_drugs(db: Session, query: str = "", limit: int | None = None) -> list[dict]:
    """Drugs for the picker, annotated with what is already monitored.

    With no query this returns the opening page of the catalogue; with one it
    ranks exact match, then prefix, then substring, so "atorva" puts
    "atorvastatin" above "atorvastatin / amlodipine".
    """
    settings = get_settings()
    cap = limit or settings.drug_search_limit
    term = (query or "").strip().lower()
    monitored = _monitored_index(db)

    def decorate(c: DrugConcept) -> dict:
        state = monitored.get(c.name.lower())
        return {
            "rxcui": c.rxcui,
            "name": c.name,
            "tty": c.tty,
            "kind": TTY_LABEL.get(c.tty, c.tty),
            "is_monitored": state is not None,
            "product_id": state["product_id"] if state else None,
            "article_count": state["article_count"] if state else 0,
        }

    # Whatever is already monitored goes first and always appears, so the
    # picker doubles as the list of what is being watched.
    watched_concepts = {
        c.name_lower: c
        for c in db.scalars(
            select(DrugConcept).where(DrugConcept.name_lower.in_(monitored.keys()))
        ).all()
    }
    head = _monitored_entries(monitored, watched_concepts, term)
    remaining = max(cap - len(head), 0)

    if not term:
        # Opening page. Names sorting below "a" are punctuation-led chemical
        # descriptors, so start at the letters and drop the rest in Python.
        rows = db.scalars(
            select(DrugConcept)
            .where(DrugConcept.tty == "IN", DrugConcept.name_lower >= "a")
            .order_by(DrugConcept.name_lower)
            .limit(cap * 30)
        ).all()
        # International Nonproprietary Names are single tokens — "atorvastatin",
        # "metformin". Requiring that keeps the opening list to recognisable
        # medicines instead of botanical entries like "Acacia bark extract".
        # The filter still reaches every concept, multi-word ones included.
        tail = [
            c
            for c in rows
            if _is_readable(c.name)
            and " " not in c.name.strip()
            and c.name_lower not in monitored
        ][:remaining]
        return head + [decorate(c) for c in tail]

    like = f"%{term}%"
    rows = db.scalars(
        select(DrugConcept)
        .where(DrugConcept.name_lower.like(like))
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

    ranked = [c for c in sorted(rows, key=rank) if c.name_lower not in monitored]
    return head + [decorate(c) for c in ranked[:remaining]]
