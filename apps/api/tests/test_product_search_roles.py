"""Role boundaries for Product Search and the ops-only surfaces.

Hiding a nav link is not access control — these assert the API itself.
"""

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.api.deps import get_current_user
from app.core.database import Base, get_db
from app.main import app
from app.models import User
from app.models.entities import Role

engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
Base.metadata.create_all(engine)
TestingSession = sessionmaker(bind=engine)


def _db_override():
    db = TestingSession()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = _db_override


def _as(role: Role, email: str):
    """Run requests as a user with the given role."""
    db = TestingSession()
    user = db.query(User).filter(User.email == email).first()
    if not user:
        user = User(
            email=email,
            full_name=email,
            hashed_password="x",
            role=role,
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    db.close()
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


REVIEWER = (Role.REVIEWER, "r@t.local")
PV_LEAD = (Role.PV_LEAD, "l@t.local")


def test_reviewer_cannot_create_or_delete_products():
    c = _as(*REVIEWER)
    assert c.post("/api/products", json={"name": "Nope"}).status_code == 403
    assert c.delete("/api/products/1").status_code == 403


def test_pv_lead_can_create_product_and_gets_a_search_string():
    c = _as(*PV_LEAD)
    r = c.post("/api/products", json={"name": "Roletest", "inn": "roletest"})
    assert r.status_code == 201, r.text
    pid = r.json()["id"]

    strings = c.get(f"/api/search-strings?product_id={pid}").json()
    assert len(strings) == 1
    q = strings[0]["query_text"]
    assert "Roletest" in q and "adverse" in q
    assert strings[0]["is_active"] is True


def test_duplicate_product_name_is_rejected():
    c = _as(*PV_LEAD)
    c.post("/api/products", json={"name": "Dupetest"})
    assert c.post("/api/products", json={"name": "dupetest"}).status_code == 409


def test_reviewer_can_search_and_schedule():
    """Reviewers run searches — that is the point of the Product Search tab."""
    lead = _as(*PV_LEAD)
    pid = lead.post("/api/products", json={"name": "Schedtest"}).json()["id"]

    c = _as(*REVIEWER)
    r = c.post(
        "/api/search-schedules",
        json={
            "product_ids": [pid],
            "frequency": "weekly",
            "end_date": "2099-01-01",
        },
    )
    assert r.status_code == 201, r.text
    assert r.json()[0]["frequency"] == "weekly"
    assert c.get("/api/search-schedules").status_code == 200


def test_schedule_end_date_cannot_be_in_the_past():
    lead = _as(*PV_LEAD)
    pid = lead.post("/api/products", json={"name": "Pasttest"}).json()["id"]
    r = lead.post(
        "/api/search-schedules",
        json={
            "product_ids": [pid],
            "frequency": "daily",
            "end_date": "2020-01-01",
        },
    )
    assert r.status_code == 400


def test_new_schedule_supersedes_the_previous_one():
    """Two active schedules for one product would double-hit NCBI."""
    c = _as(*PV_LEAD)
    pid = c.post("/api/products", json={"name": "Supersede"}).json()["id"]
    body = {"product_ids": [pid], "frequency": "daily", "end_date": "2099-01-01"}
    first = c.post("/api/search-schedules", json=body).json()[0]
    c.post("/api/search-schedules", json={**body, "frequency": "weekly"})

    active = [
        s
        for s in c.get("/api/search-schedules").json()
        if s["product_id"] == pid and s["is_active"]
    ]
    assert len(active) == 1
    assert active[0]["frequency"] == "weekly"
    assert active[0]["id"] != first["id"]


def test_reviewer_is_blocked_from_ops_surfaces():
    """These back the Ops/Audit/Admin tabs now hidden from reviewers."""
    c = _as(*REVIEWER)
    assert c.get("/api/audit").status_code == 403
    assert c.get("/api/jobs").status_code == 403
    assert c.get("/api/ops/metrics").status_code == 403
    assert c.post("/api/drugs/sync").status_code == 403


def test_reviewer_keeps_access_to_their_own_work():
    """Tightening ops access must not break the reviewer queue."""
    c = _as(*REVIEWER)
    assert c.get("/api/articles").status_code == 200
    assert c.get("/api/products").status_code == 200
    assert c.get("/api/sla/overdue").status_code == 200
    assert c.get("/api/drugs/search?q=test").status_code == 200
