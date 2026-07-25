"""Create tables and seed pilot users + product."""

from __future__ import annotations

from sqlalchemy import select

from app.core.database import Base, SessionLocal, engine
from app.core.security import hash_password
from app.models import Product, SearchString, User
from app.models.entities import Role
from app.services.audit import log_event


def bootstrap() -> None:
    Base.metadata.create_all(bind=engine)
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

        product = db.scalars(
            select(Product).where(Product.name == "DrugX (Pilot)")
        ).first()
        if not product:
            product = Product(
                name="DrugX (Pilot)",
                inn="drugxanib",
                brands=["DrugX", "Drug-X"],
                synonyms=["DrugX", "drugxanib", "DX-101"],
                atc_code="C08CA99",
                is_active=True,
            )
            db.add(product)
            db.flush()
            ss = SearchString(
                product_id=product.id,
                version=1,
                query_text='("DrugX" OR drugxanib OR "DX-101") AND (adverse OR safety OR toxicity OR "case report")',
                is_active=True,
                approved_by="pvlead@litmon.local",
                notes="Pilot search string — align with manual process before parallel run",
            )
            db.add(ss)

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
        print("  Product: DrugX (Pilot) with PubMed search string v1")
    finally:
        db.close()


if __name__ == "__main__":
    bootstrap()
