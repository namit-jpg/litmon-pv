"""Weekly (or on-demand) PubMed search runner for pilot cadence.

Usage (from apps/api with PYTHONPATH set):
  python ../../workers/scheduled_search.py
  python ../../workers/scheduled_search.py --days 7 --max-fetch 50

Schedule via Windows Task Scheduler or cron to meet EU GVP weekly literature cadence.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import date, timedelta
from pathlib import Path

# Ensure apps/api is on path
API_ROOT = Path(__file__).resolve().parents[1] / "apps" / "api"
sys.path.insert(0, str(API_ROOT))

from sqlalchemy import select  # noqa: E402

from app.core.database import SessionLocal  # noqa: E402
from app.models import SearchString  # noqa: E402
from app.services.pipeline import run_search  # noqa: E402


async def main(days: int, max_fetch: int) -> None:
    db = SessionLocal()
    try:
        active = list(
            db.scalars(
                select(SearchString).where(SearchString.is_active.is_(True))
            ).all()
        )
        if not active:
            print("No active search strings.")
            return
        date_to = date.today()
        date_from = date_to - timedelta(days=days)
        for ss in active:
            print(f"Running search_string id={ss.id} v{ss.version} …")
            try:
                run = await run_search(
                    db,
                    ss.id,
                    date_from=date_from,
                    date_to=date_to,
                    triggered_by="scheduler",
                    max_fetch=max_fetch,
                )
                print(
                    f"  run #{run.id} status={run.status.value} "
                    f"hits={run.hit_count} new={run.new_article_count}"
                )
            except Exception as exc:
                print(f"  FAILED: {exc}")
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="LitMon-PV scheduled PubMed search")
    parser.add_argument("--days", type=int, default=7, help="Lookback window in days")
    parser.add_argument(
        "--max-fetch", type=int, default=50, help="Max new PMIDs to fetch/score"
    )
    args = parser.parse_args()
    asyncio.run(main(args.days, args.max_fetch))
