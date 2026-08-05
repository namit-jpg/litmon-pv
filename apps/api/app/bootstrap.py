"""Create tables and seed the pilot user accounts.

Deliberately does NOT create products, search strings or articles. Monitored
products are added through the Product Search screen against the live NLM
RxNorm catalogue, so every product in the system is real, operator-chosen data
with an audit trail — not a fixture.
"""

from __future__ import annotations

from sqlalchemy import select

from app.core.database import SessionLocal, engine
from app.core.migrate import run_migrations
from app.core.security import hash_password
from app.models import User
from app.models.entities import Role
from app.services.audit import log_event

# Pilot accounts. These exist so the application is reachable on a fresh
# database; everything else is created by operators through the UI.
PILOT_USERS = [
    ("reviewer@litmon.local", "Reviewer One", "reviewer123", Role.REVIEWER),
    ("pvlead@litmon.local", "PV Lead", "pvlead123", Role.PV_LEAD),
    ("admin@litmon.local", "Admin User", "admin123", Role.ADMIN),
    ("senior@litmon.local", "Senior Reviewer", "senior123", Role.SENIOR_REVIEWER),
]


def bootstrap() -> None:
    # Go through Alembic rather than create_all: create_all adds missing
    # tables but never adds columns to existing ones, which is what left
    # pilot databases half-upgraded and silently broken.
    run_migrations(engine)
    db = SessionLocal()
    try:
        created = []
        for email, name, password, role in PILOT_USERS:
            if not db.scalars(select(User).where(User.email == email)).first():
                db.add(
                    User(
                        email=email,
                        full_name=name,
                        hashed_password=hash_password(password),
                        role=role,
                    )
                )
                created.append(email)

        log_event(
            db,
            actor="system",
            action="bootstrap",
            entity_type="system",
            entity_id="0",
            payload={"message": "Database initialized", "users_created": created},
        )
        db.commit()

        print("Bootstrap complete.")
        if created:
            print(f"  Created {len(created)} user account(s).")
        else:
            print("  User accounts already present.")
        for email, _name, password, role in PILOT_USERS:
            print(f"    {email} / {password}  ({role.value})")
        print()
        print("  No products are seeded. Add them under Product Search;")
        print("  run the drug-catalogue sync first if it is empty.")
    finally:
        db.close()


if __name__ == "__main__":
    bootstrap()
