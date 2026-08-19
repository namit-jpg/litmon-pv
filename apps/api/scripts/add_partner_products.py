"""Add the partner's requested monitored products.

Four of the six are absent from RxNorm — it is a United States vocabulary, and
sodium fusidate is not US-approved while Ascazin, Lyfaquin and Zincovit are
Indian brands. They are still monitorable: a search string is free text. This
script creates them directly so the set is reproducible on a fresh database
rather than living only in one laptop's SQLite file.

Every query is built on the active substance with the brand kept as an alias,
because the literature names the molecule and rarely the brand.

    python scripts/add_partner_products.py            # create what is missing
    python scripts/add_partner_products.py --dry-run  # show what would change

Two caveats are deliberately recorded in the notes below rather than hidden:
Ascazin and Zincovit are multi-ingredient supplements whose exact composition
the partner has not supplied, so their queries are broad and will retrieve
loosely related nutrition literature until tightened; and Lyfaquin is assumed to
be centhaquine citrate, which needs confirming.
"""

from __future__ import annotations

import argparse
import sys

from sqlalchemy import func, select

from app.core.database import SessionLocal
from app.models.entities import Product, SearchString
from app.services.audit import log_event
from app.services.drug_catalog import get_or_create_ingredients

SAFETY_TERMS = (
    'adverse OR toxicity OR safety OR "case report" OR "adverse drug reaction" '
    "OR interaction OR pregnancy OR overdose OR hypersensitivity"
)

PRODUCTS: list[dict] = [
    {
        "name": "Sodium fusidate",
        "inn": "fusidic acid",
        "brands": ["Fucidin"],
        "synonyms": ["fusidic acid", "sodium fusidate", "fusidate"],
        "query": (
            '("sodium fusidate" OR "fusidic acid" OR fusidate) '
            f"AND ({SAFETY_TERMS})"
        ),
        "note": "Not in RxNorm — not US-approved. Well covered in the literature.",
    },
    {
        "name": "Ativan",
        "inn": "lorazepam",
        "brands": ["Ativan"],
        "synonyms": ["lorazepam"],
        "query": f"(lorazepam OR Ativan) AND ({SAFETY_TERMS})",
        "note": "In RxNorm as a brand; queried on the substance.",
    },
    {
        "name": "Lyfaquin",
        "inn": "centhaquine citrate",
        "brands": ["Lyfaquin"],
        "synonyms": ["centhaquine", "centhaquin", "PMZ-2010"],
        "query": (
            '(centhaquine OR centhaquin OR "PMZ-2010" OR Lyfaquin) '
            f"AND ({SAFETY_TERMS})"
        ),
        "note": "ASSUMED to be centhaquine citrate injection — confirm with the partner.",
    },
    {
        "name": "Zincovit",
        "inn": "multivitamin with zinc and trace minerals",
        "brands": ["Zincovit"],
        "synonyms": ["multivitamin", "zinc supplement"],
        "query": (
            '(Zincovit OR ((multivitamin OR "vitamin supplement") AND zinc)) '
            f"AND ({SAFETY_TERMS})"
        ),
        "note": "Composition not supplied — query is broad and will need tightening.",
    },
    {
        "name": "Ascazin",
        "inn": "zinc with ascorbic acid",
        "brands": ["Ascazin"],
        "synonyms": ["zinc ascorbate", "zinc and vitamin C"],
        "query": (
            '(Ascazin OR (zinc AND ("ascorbic acid" OR "vitamin C"))) '
            f"AND ({SAFETY_TERMS})"
        ),
        "note": "Composition not supplied — query is broad and will need tightening.",
    },
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="report what would be created without writing",
    )
    args = parser.parse_args()

    db = SessionLocal()
    created: list[str] = []
    skipped: list[str] = []
    try:
        for spec in PRODUCTS:
            existing = db.scalars(
                select(Product).where(
                    func.lower(Product.name) == spec["name"].lower()
                )
            ).first()
            if existing:
                skipped.append(spec["name"])
                continue
            if args.dry_run:
                created.append(spec["name"])
                continue

            product = Product(
                name=spec["name"],
                inn=spec["inn"],
                brands=spec["brands"],
                synonyms=spec["synonyms"],
                is_active=True,
            )
            # Without an API tag the reviewer's substance column is empty and
            # activesubstancename is missing from the E2B export, so tag from
            # the INN — there is no RxNorm concept to derive it from.
            product.active_ingredients = get_or_create_ingredients(db, [spec["inn"]])
            db.add(product)
            db.flush()
            db.add(
                SearchString(
                    product_id=product.id,
                    version=1,
                    query_text=spec["query"],
                    is_active=True,
                    approved_by="script:add_partner_products",
                    notes=spec["note"],
                )
            )
            log_event(
                db,
                actor="script:add_partner_products",
                action="product_created",
                entity_type="product",
                entity_id=str(product.id),
                payload={
                    "name": product.name,
                    "inn": product.inn,
                    "rxcui": None,
                    "query_text": spec["query"],
                    "note": spec["note"],
                },
            )
            created.append(spec["name"])

        if not args.dry_run:
            db.commit()
    finally:
        db.close()

    verb = "would create" if args.dry_run else "created"
    print(f"{verb}: {', '.join(created) if created else 'nothing'}")
    if skipped:
        print(f"already present: {', '.join(skipped)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
