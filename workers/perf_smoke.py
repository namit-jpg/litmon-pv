"""Performance smoke: score/route N synthetic articles.

Usage (from apps/api with venv + PYTHONPATH):
  python ../../workers/perf_smoke.py --n 500
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1] / "apps" / "api"
sys.path.insert(0, str(API_ROOT))

from sqlalchemy import select  # noqa: E402

from app.core.database import Base, SessionLocal, engine  # noqa: E402
from app.models import Product  # noqa: E402
from app.models.entities import Article, ArticleStatus  # noqa: E402
from app.services.pipeline import product_name_list, score_and_route_article  # noqa: E402


async def run(n: int, keep: bool) -> None:
    import app.models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        product = db.scalars(select(Product).where(Product.is_active.is_(True))).first()
        if not product:
            print("No active product — run bootstrap first")
            return
        names = product_name_list(product)
        t0 = time.perf_counter()
        latencies: list[float] = []
        for i in range(n):
            art = Article(
                product_id=product.id,
                pmid=f"perf{int(time.time())}{i:05d}"[:20],
                title=f"Perf smoke abstract {i} DrugX adverse event case report",
                abstract=(
                    f"We report patient {i} with rash after DrugX. "
                    "Authors describe the adverse reaction."
                    if i % 5 != 0
                    else f"Unrelated physiology paper number {i} with no drug mention."
                ),
                journal="Perf Journal",
                authors=["Smoke Test"],
                status=ArticleStatus.INGESTED,
            )
            db.add(art)
            db.flush()
            s = time.perf_counter()
            await score_and_route_article(db, art, product, names)
            latencies.append((time.perf_counter() - s) * 1000)
            if (i + 1) % 50 == 0:
                db.commit()
                print(f"  … {i + 1}/{n}")
        db.commit()
        total = time.perf_counter() - t0
        avg = sum(latencies) / len(latencies) if latencies else 0
        p95 = sorted(latencies)[int(0.95 * (len(latencies) - 1))] if latencies else 0
        print("--- perf smoke results ---")
        print(f"articles: {n}")
        print(f"wall_seconds: {total:.2f}")
        print(f"throughput_per_sec: {n / total:.1f}")
        print(f"score_avg_ms: {avg:.1f}")
        print(f"score_p95_ms: {p95:.1f}")
        if not keep:
            from sqlalchemy import delete

            from app.models import (
                ArticleAppearance,
                ReviewDecision,
                ScreeningResult,
                TriageAssignment,
            )

            perf_ids = [
                a.id
                for a in db.scalars(select(Article).where(Article.pmid.like("perf%"))).all()
            ]
            if perf_ids:
                # Order respects FKs: triage refs screening
                db.execute(
                    delete(TriageAssignment).where(
                        TriageAssignment.article_id.in_(perf_ids)
                    )
                )
                db.execute(
                    delete(ScreeningResult).where(ScreeningResult.article_id.in_(perf_ids))
                )
                db.execute(
                    delete(ArticleAppearance).where(
                        ArticleAppearance.article_id.in_(perf_ids)
                    )
                )
                db.execute(
                    delete(ReviewDecision).where(ReviewDecision.article_id.in_(perf_ids))
                )
                db.execute(delete(Article).where(Article.id.in_(perf_ids)))
                db.commit()
            print("cleaned perf articles (use --keep to retain)")
    finally:
        db.close()


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--n", type=int, default=200)
    p.add_argument("--keep", action="store_true")
    args = p.parse_args()
    asyncio.run(run(args.n, args.keep))
