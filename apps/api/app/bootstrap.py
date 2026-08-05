"""Create tables and seed pilot users + four-product pilot configuration."""

from __future__ import annotations

from sqlalchemy import select

from app.core.database import SessionLocal, engine
from app.core.migrate import run_migrations
from app.core.security import hash_password
from app.models import Product, SearchString, User
from app.models.entities import Role
from app.services.audit import log_event


def bootstrap() -> None:
    # Go through Alembic rather than create_all: create_all adds missing
    # tables but never adds columns to existing ones, which is what left
    # pilot databases half-upgraded and silently broken.
    run_migrations(engine)
    db = SessionLocal()
    try:
        users = [
            ("reviewer@litmon.local", "Reviewer One", "reviewer123", Role.REVIEWER),
            ("pvlead@litmon.local", "PV Lead", "pvlead123", Role.PV_LEAD),
            ("admin@litmon.local", "Admin User", "admin123", Role.ADMIN),
            (
                "senior@litmon.local",
                "Senior Reviewer",
                "senior123",
                Role.SENIOR_REVIEWER,
            ),
        ]
        for email, name, password, role in users:
            if not db.scalars(select(User).where(User.email == email)).first():
                db.add(
                    User(
                        email=email,
                        full_name=name,
                        hashed_password=hash_password(password),
                        role=role,
                    )
                )

        db.flush()
        default_reviewer = db.scalars(
            select(User).where(User.email == "reviewer@litmon.local")
        ).first()

        pilot_products = [
            {
                "name": "Ibuprofen",
                "inn": "ibuprofen",
                "brands": ["Advil", "Motrin", "Nurofen", "Brufen"],
                "synonyms": [
                    "ibuprofen",
                    "2-(4-isobutylphenyl)propionic acid",
                    "isobutylphenylpropionic acid",
                ],
                "query": '(ibuprofen OR Advil OR Motrin OR Nurofen OR Brufen) AND (adverse OR toxicity OR safety OR "case report" OR interaction OR pregnancy OR overdose)',
            },
            {
                "name": "Metformin",
                "inn": "metformin",
                "brands": ["Glucophage", "Fortamet", "Riomet"],
                "synonyms": ["metformin", "metformin hydrochloride", "dimethylbiguanide"],
                "query": '(metformin OR Glucophage OR Fortamet OR Riomet) AND (adverse OR toxicity OR safety OR "case report" OR lactic acidosis OR interaction OR pregnancy)',
            },
            {
                "name": "Amoxicillin",
                "inn": "amoxicillin",
                "brands": ["Amoxil", "Moxatag", "Trimox"],
                "synonyms": ["amoxicillin", "amoxycillin", "amoxicillin trihydrate"],
                "query": '(amoxicillin OR Amoxil OR Moxatag OR Trimox) AND (adverse OR allergy OR anaphylaxis OR toxicity OR safety OR "case report" OR interaction OR pregnancy)',
            },
            {
                "name": "Atorvastatin",
                "inn": "atorvastatin",
                "brands": ["Lipitor", "Sortis", "Torvast"],
                "synonyms": ["atorvastatin", "atorvastatin calcium", "statin"],
                "query": '(atorvastatin OR Lipitor OR Sortis OR Torvast) AND (adverse OR myopathy OR rhabdomyolysis OR toxicity OR safety OR "case report" OR interaction OR pregnancy)',
            },
        ]

        legacy = db.scalars(select(Product).where(Product.name == "DrugX (Pilot)")).first()
        if legacy:
            legacy.is_active = False

        for cfg in pilot_products:
            product = db.scalars(
                select(Product).where(Product.name == cfg["name"])
            ).first()
            if not product:
                product = Product(
                    name=cfg["name"],
                    inn=cfg["inn"],
                    brands=cfg["brands"],
                    synonyms=cfg["synonyms"],
                    is_active=True,
                )
                db.add(product)
                db.flush()
            else:
                product.is_active = True
                product.inn = cfg["inn"]
                product.brands = cfg["brands"]
                product.synonyms = cfg["synonyms"]
            if default_reviewer:
                product.primary_reviewer_id = default_reviewer.id
            active_string = db.scalars(
                select(SearchString).where(
                    SearchString.product_id == product.id,
                    SearchString.is_active.is_(True),
                )
            ).first()
            if not active_string:
                db.add(
                    SearchString(
                        product_id=product.id,
                        version=1,
                        query_text=cfg["query"],
                        is_active=True,
                        approved_by="pvlead@litmon.local",
                        notes="Pilot safety-monitoring query; validate against partner-approved search strategy",
                    )
                )

        log_event(
            db,
            actor="system",
            action="bootstrap",
            entity_type="system",
            entity_id="0",
            payload={"message": "Database initialized"},
        )
        db.commit()
        print("Bootstrap complete.")
        print("  Users: reviewer@litmon.local / reviewer123")
        print("         pvlead@litmon.local / pvlead123")
        print("         admin@litmon.local / admin123")
        print("  Products: Ibuprofen, Metformin, Amoxicillin, Atorvastatin")
    finally:
        db.close()


if __name__ == "__main__":
    bootstrap()
