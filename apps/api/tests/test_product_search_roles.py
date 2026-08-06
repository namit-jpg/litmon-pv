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


def test_ingredient_product_is_tagged_with_its_substance():
    """A product with no API tags empties the reviewer's substance column and
    drops activesubstancename from the E2B export."""
    c = _as(*PV_LEAD)
    r = c.post(
        "/api/products",
        json={"name": "simvastatin", "rxcui": "36567", "tty": "IN"},
    )
    assert r.status_code == 201, r.text
    tags = [t["name"] for t in r.json()["active_ingredients"]]
    assert tags == ["simvastatin"]


def test_combination_product_is_tagged_with_every_substance():
    """The whole point of many-to-many API tags is combination products."""
    c = _as(*PV_LEAD)
    r = c.post(
        "/api/products",
        json={"name": "amoxicillin / clavulanate", "rxcui": "19711", "tty": "MIN"},
    )
    assert r.status_code == 201, r.text
    tags = sorted(t["name"] for t in r.json()["active_ingredients"])
    assert tags == ["amoxicillin", "clavulanate"]


def test_same_substance_across_products_reuses_one_tag():
    """Otherwise querying by substance would miss half the products."""
    c = _as(*PV_LEAD)
    a = c.post("/api/products", json={"name": "ibuprofen", "tty": "IN"}).json()
    b = c.post(
        "/api/products", json={"name": "ibuprofen / famotidine", "tty": "MIN"}
    ).json()
    ids_a = {t["id"] for t in a["active_ingredients"]}
    ids_b = {t["id"] for t in b["active_ingredients"]}
    assert ids_a and ids_a < ids_b, "ibuprofen tag should be shared, not duplicated"


def test_reactivated_product_regains_its_substance_tags():
    """Re-adding a removed product must not bring it back untagged."""
    c = _as(*PV_LEAD)
    body = {"name": "reactivateme", "tty": "IN"}
    first = c.post("/api/products", json=body).json()
    assert [t["name"] for t in first["active_ingredients"]] == ["reactivateme"]

    c.delete(f"/api/products/{first['id']}")
    again = c.post("/api/products", json=body)
    assert again.status_code == 201, again.text
    assert again.json()["id"] == first["id"], "should reuse the row, not duplicate"
    assert [t["name"] for t in again.json()["active_ingredients"]] == ["reactivateme"]


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
