"""Backfill what migration 8f3a2c6d1b40 leaves behind on a populated database.

That migration was written against an empty database, so three of its steps do
nothing when rows already exist. Each failure is silent at migration time and
surfaces later as a 500 on ordinary reads:

1. ``status`` — the remap table is keyed on enum *values* (``routed``) while
   SQLAlchemy stores enum *names* (``ROUTED``), so every UPDATE matched nothing
   and pre-split rows keep statuses the new enum cannot load.
2. ``priority`` — added with ``server_default="p3"``, the value rather than the
   name, so existing rows get a spelling the enum rejects.
3. ``markets`` / ``channels`` — added nullable with no backfill, but the
   matching response models require lists, so serialising any pre-existing
   product or alert fails.

Safe to re-run: each step only touches rows that are still wrong.

    python scripts/repair_phase1_backfill.py --yes
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import inspect, text  # noqa: E402

from app.core.database import engine  # noqa: E402
from app.models.entities import ArticleStatus, Classification, Priority  # noqa: E402

# Old status name -> (new status name, inferred classification name or None).
# Mirrors _STATUS_MAP in the migration, keyed the way the column is written.
STATUS_MAP: dict[str, tuple[str, str | None]] = {
    "INGESTED": ("NEW_ALERT", None),
    "SCORED": ("NEW_ALERT", None),
    "ROUTED": ("AWAITING_REVIEW", "POTENTIALLY_RELEVANT"),
    "UNDER_REVIEW": ("UNDER_ASSESSMENT", "REQUIRES_HUMAN_REVIEW"),
    "AUTO_CLEAR": ("ARCHIVED", "IRRELEVANT"),
    "DISPOSITION_NOT_CASE": ("ARCHIVED", "IRRELEVANT"),
    "DISPOSITION_VALID_ICSR": ("APPROVED_FOR_SUBMISSION", "ADVERSE_EVENT_RELATED"),
}


def _plan(conn) -> dict[str, int]:
    """Count what is still wrong, without changing anything."""
    valid_status = {e.name for e in ArticleStatus}
    valid_priority = {e.name for e in Priority}
    cols = {c["name"] for c in inspect(engine).get_columns("articles")}

    plan: dict[str, int] = {}

    stale_status = [
        (s, n)
        for s, n in conn.execute(
            text("SELECT status, COUNT(*) FROM articles GROUP BY status")
        ).all()
        if s not in valid_status
    ]
    plan["status"] = sum(n for _, n in stale_status)
    plan["_status_detail"] = stale_status  # type: ignore[assignment]

    if "priority" in cols:
        plan["priority"] = sum(
            n
            for p, n in conn.execute(
                text("SELECT priority, COUNT(*) FROM articles GROUP BY priority")
            ).all()
            if p is not None and p not in valid_priority
        )
    else:
        plan["priority"] = 0

    # Every JSON list column added without a backfill fails response validation
    # the same way, so check them together rather than one bug at a time.
    for table, column in (("products", "markets"), ("alerts", "channels")):
        plan[f"{table}.{column}"] = (
            conn.execute(
                text(f"SELECT COUNT(*) FROM {table} WHERE {column} IS NULL")
            ).scalar_one()
            or 0
        )
    return plan


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--yes", action="store_true", help="apply (else dry run)")
    args = parser.parse_args()

    valid_status = {e.name for e in ArticleStatus}
    valid_class = {e.name for e in Classification}
    for old, (new, cls) in STATUS_MAP.items():
        assert new in valid_status, f"{new} is not an ArticleStatus"
        assert cls is None or cls in valid_class, f"{cls} is not a Classification"

    with engine.connect() as conn:
        plan = _plan(conn)

    detail = plan.pop("_status_detail", [])
    if not any(plan.values()):
        print("Nothing to repair — the database is already consistent.")
        return 0

    print("To repair:")
    for status, n in sorted(detail):
        target = STATUS_MAP.get(status)
        arrow = target[0] if target else "NO MAPPING — left as-is"
        print(f"  articles.status    {status:<24} {n:>4} -> {arrow}")
    if plan["priority"]:
        print(f"  articles.priority  lower-case value    {plan['priority']:>4} -> upper-case name")
    for key in ("products.markets", "alerts.channels"):
        if plan.get(key):
            print(f"  {key:<18} NULL                {plan[key]:>4} -> []")

    unmapped = [s for s, _ in detail if s not in STATUS_MAP]
    if unmapped:
        print(f"\nNo mapping for {unmapped}; those rows stay unreadable.")

    if not args.yes:
        print("\nDry run. Re-run with --yes to apply.")
        return 0

    with engine.begin() as conn:
        for old, (new, cls) in STATUS_MAP.items():
            conn.execute(
                text(
                    "UPDATE articles SET status = :new, "
                    "ai_classification = COALESCE(ai_classification, :cls) "
                    "WHERE status = :old"
                ).bindparams(new=new, cls=cls, old=old)
            )
        # Rewrite each enum value to its name rather than assuming one default,
        # so a row already triaged to P1 is not flattened back to P3.
        for member in Priority:
            conn.execute(
                text(
                    "UPDATE articles SET priority = :name WHERE priority = :value"
                ).bindparams(name=member.name, value=member.value)
            )
        for table, column in (("products", "markets"), ("alerts", "channels")):
            conn.execute(
                text(f"UPDATE {table} SET {column} = '[]' WHERE {column} IS NULL")
            )

    with engine.connect() as conn:
        after = _plan(conn)
    after.pop("_status_detail", None)
    print("\nRepaired. Remaining problems:", after if any(after.values()) else "none")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
