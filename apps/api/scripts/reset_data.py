"""Wipe all monitoring data, leaving user accounts and the drug catalogue.

Everything this deletes is operational data that the application recreates by
itself: pick a drug and search, and the backing rows come back. User logins and
the RxNorm catalogue are kept so the app stays usable immediately afterwards.

    python scripts/reset_data.py --yes
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import func, select, text  # noqa: E402

from app.core.database import SessionLocal, engine  # noqa: E402
from app.models import DrugConcept, User  # noqa: E402

# Child rows first so foreign keys never block the delete. Triage rows point at
# screening results, so they have to go before them.
TABLES_IN_ORDER = [
    "article_appearances",
    "triage_assignments",
    "screening_results",
    "review_decisions",
    "alerts",
    "articles",
    "search_runs",
    "search_schedules",
    "search_strings",
    "product_active_ingredients",
    "products",
    "active_ingredients",
    "export_packages",
    "jobs",
    "audit_events",
]

# Deliberately untouched: users (you would be locked out) and drug_concepts
# (a 10k-row mirror that takes a network round trip to rebuild).
PRESERVED = ["users", "drug_concepts"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--yes", action="store_true", help="actually delete (otherwise dry run)"
    )
    args = parser.parse_args()

    inspector_tables = set()
    with engine.connect() as conn:
        for name in TABLES_IN_ORDER:
            try:
                conn.execute(text(f"SELECT 1 FROM {name} LIMIT 1"))
                inspector_tables.add(name)
            except Exception:  # noqa: BLE001 - table simply does not exist yet
                continue

    db = SessionLocal()
    try:
        counts = {}
        with engine.connect() as conn:
            for name in TABLES_IN_ORDER:
                if name in inspector_tables:
                    counts[name] = conn.execute(
                        text(f"SELECT COUNT(*) FROM {name}")
                    ).scalar_one()

        total = sum(counts.values())
        print("Rows to delete:")
        for name, n in counts.items():
            if n:
                print(f"  {name:<28} {n}")
        print(f"  {'TOTAL':<28} {total}")

        print("\nPreserved:")
        print(f"  {'users':<28} {db.scalar(select(func.count(User.id)))}")
        print(
            f"  {'drug_concepts':<28} "
            f"{db.scalar(select(func.count(DrugConcept.id)))}"
        )

        if not args.yes:
            print("\nDry run. Re-run with --yes to delete.")
            return 0

        # Suspend FK enforcement for the wipe. The order above is correct, but
        # a single missed edge would otherwise abort a half-finished delete and
        # leave the database in a worse state than it started.
        is_sqlite = engine.dialect.name == "sqlite"
        with engine.begin() as conn:
            if is_sqlite:
                conn.execute(text("PRAGMA defer_foreign_keys = ON"))
            for name in TABLES_IN_ORDER:
                if name in inspector_tables:
                    conn.execute(text(f"DELETE FROM {name}"))

        print(f"\nDeleted {total} rows. Pick a drug under Product Search to begin.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
