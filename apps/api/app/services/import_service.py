"""Manual article import (CSV / PMID list) — backup when PubMed search is unavailable."""

from __future__ import annotations

import csv
import io
import re
from datetime import date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Article, Product
from app.models.entities import ArticleStatus
from app.services.audit import log_event
from app.services.pipeline import product_name_list, score_and_route_article
from app.services.pubmed.client import PubMedClient


def parse_pmid_list(text: str) -> list[str]:
    parts = re.split(r"[\s,;]+", text.strip())
    pmids: list[str] = []
    for p in parts:
        p = p.strip()
        if re.fullmatch(r"\d{1,12}", p):
            pmids.append(p)
    # preserve order, unique
    seen: set[str] = set()
    out: list[str] = []
    for p in pmids:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def parse_articles_csv(content: str) -> list[dict[str, Any]]:
    """CSV columns: pmid (required), title, abstract, journal, doi, pub_date (YYYY-MM-DD)."""
    reader = csv.DictReader(io.StringIO(content))
    if not reader.fieldnames:
        raise ValueError("CSV has no header row")
    fields = {f.lower().strip(): f for f in reader.fieldnames}
    if "pmid" not in fields:
        raise ValueError("CSV must include a 'pmid' column")
    rows: list[dict[str, Any]] = []
    for raw in reader:
        pmid = (raw.get(fields["pmid"]) or "").strip()
        if not pmid:
            continue
        row: dict[str, Any] = {"pmid": pmid}
        for key in ("title", "abstract", "journal", "doi", "pub_date"):
            if key in fields:
                row[key] = (raw.get(fields[key]) or "").strip() or None
        rows.append(row)
    return rows


async def import_pmids_from_pubmed(
    db: Session,
    *,
    product_id: int,
    pmids: list[str],
    actor: str,
) -> dict[str, Any]:
    product = db.get(Product, product_id)
    if not product:
        raise ValueError("Product not found")
    names = product_name_list(product)
    existing = {
        a.pmid: a
        for a in db.scalars(select(Article).where(Article.pmid.in_(pmids))).all()
    } if pmids else {}
    new_pmids = [p for p in pmids if p not in existing]
    rehit = len(pmids) - len(new_pmids)

    created_ids: list[int] = []
    async with PubMedClient() as client:
        fetched = await client.efetch(new_pmids)
    for dto in fetched:
        art = Article(
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
        db.add(art)
        db.flush()
        await score_and_route_article(db, art, product, names)
        created_ids.append(art.id)

    log_event(
        db,
        actor=actor,
        action="import_pmids_pubmed",
        entity_type="product",
        entity_id=product_id,
        payload={
            "requested": len(pmids),
            "new": len(created_ids),
            "already_known": rehit,
            "fetched": len(fetched),
        },
    )
    db.commit()
    return {
        "requested": len(pmids),
        "created": len(created_ids),
        "already_known": rehit,
        "article_ids": created_ids,
    }


async def import_csv_rows(
    db: Session,
    *,
    product_id: int,
    rows: list[dict[str, Any]],
    actor: str,
    fetch_missing_from_pubmed: bool = True,
) -> dict[str, Any]:
    product = db.get(Product, product_id)
    if not product:
        raise ValueError("Product not found")
    names = product_name_list(product)

    # Rows with only pmid and no title → batch EFetch
    need_fetch = [
        r["pmid"]
        for r in rows
        if not r.get("title") and re.fullmatch(r"\d{1,12}", str(r["pmid"]))
    ]
    fetched_map: dict[str, Any] = {}
    if fetch_missing_from_pubmed and need_fetch:
        async with PubMedClient() as client:
            for dto in await client.efetch(need_fetch):
                fetched_map[dto.pmid] = dto

    created = 0
    updated = 0
    skipped = 0
    article_ids: list[int] = []

    for r in rows:
        pmid = str(r["pmid"]).strip()
        existing = db.scalars(select(Article).where(Article.pmid == pmid)).first()
        if existing:
            skipped += 1
            article_ids.append(existing.id)
            continue

        dto = fetched_map.get(pmid)
        title = r.get("title") or (dto.title if dto else f"(Imported) PMID {pmid}")
        abstract = r.get("abstract") or (dto.abstract if dto else None)
        journal = r.get("journal") or (dto.journal if dto else None)
        doi = r.get("doi") or (dto.doi if dto else None)
        pub_date = None
        if r.get("pub_date"):
            try:
                pub_date = date.fromisoformat(str(r["pub_date"])[:10])
            except ValueError:
                pub_date = None
        if not pub_date and dto:
            pub_date = dto.pub_date

        art = Article(
            product_id=product.id,
            pmid=pmid,
            doi=doi,
            title=title,
            abstract=abstract,
            journal=journal,
            authors=dto.authors if dto else [],
            pub_date=pub_date,
            mesh_terms=dto.mesh_terms if dto else [],
            publication_types=dto.publication_types if dto else ["Imported"],
            pubmed_url=dto.pubmed_url
            if dto
            else (f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid.isdigit() else None),
            content_hash=dto.content_hash if dto else None,
            status=ArticleStatus.INGESTED,
        )
        db.add(art)
        db.flush()
        await score_and_route_article(db, art, product, names)
        created += 1
        article_ids.append(art.id)

    log_event(
        db,
        actor=actor,
        action="import_csv",
        entity_type="product",
        entity_id=product_id,
        payload={"created": created, "skipped": skipped, "rows": len(rows)},
    )
    db.commit()
    return {
        "rows": len(rows),
        "created": created,
        "skipped_existing": skipped,
        "updated": updated,
        "article_ids": article_ids,
    }
