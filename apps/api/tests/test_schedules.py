from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.core.database import Base
from app.models import Alert, Product, ScheduleFrequency, SearchSchedule, SearchString, User
from app.models.entities import Role
from app.services.schedules import (
    advance_past,
    compute_next_run,
    default_lookback_days,
    due_schedules,
    is_expired,
    run_schedule,
)


def session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _schedule(db, **over):
    product = Product(name=over.pop("product_name", "warfarin"), brands=[], synonyms=[])
    db.add(product)
    db.flush()
    db.add(
        SearchString(
            product_id=product.id, version=1, query_text="test", is_active=True
        )
    )
    defaults = dict(
        product_id=product.id,
        frequency=ScheduleFrequency.DAILY,
        end_date=date.today() + timedelta(days=30),
        lookback_days=2,
        max_fetch=30,
        is_active=True,
        next_run_at=datetime.now(timezone.utc),
    )
    defaults.update(over)
    s = SearchSchedule(**defaults)
    db.add(s)
    db.flush()
    return s


UTC = timezone.utc


def test_daily_and_weekly_advance():
    start = datetime(2026, 3, 10, 9, 0, tzinfo=UTC)
    assert compute_next_run(start, ScheduleFrequency.DAILY) == datetime(
        2026, 3, 11, 9, 0, tzinfo=UTC
    )
    assert compute_next_run(start, ScheduleFrequency.WEEKLY) == datetime(
        2026, 3, 17, 9, 0, tzinfo=UTC
    )


def test_monthly_advance_is_calendar_aware():
    assert compute_next_run(
        datetime(2026, 1, 15, 8, 0, tzinfo=UTC), ScheduleFrequency.MONTHLY
    ) == datetime(2026, 2, 15, 8, 0, tzinfo=UTC)
    # December must roll the year over, not produce month 13.
    assert compute_next_run(
        datetime(2026, 12, 5, 8, 0, tzinfo=UTC), ScheduleFrequency.MONTHLY
    ) == datetime(2027, 1, 5, 8, 0, tzinfo=UTC)


def test_monthly_clamps_to_short_month():
    """31 Jan + 1 month is end of Feb, never 3 March."""
    assert compute_next_run(
        datetime(2026, 1, 31, 8, 0, tzinfo=UTC), ScheduleFrequency.MONTHLY
    ) == datetime(2026, 2, 28, 8, 0, tzinfo=UTC)
    # 2028 is a leap year.
    assert compute_next_run(
        datetime(2028, 1, 31, 8, 0, tzinfo=UTC), ScheduleFrequency.MONTHLY
    ) == datetime(2028, 2, 29, 8, 0, tzinfo=UTC)


def test_advance_past_does_not_fire_a_backlog():
    """After a week of downtime a daily schedule resumes once, not 7 times."""
    stale = datetime(2026, 3, 1, 9, 0, tzinfo=UTC)
    now = datetime(2026, 3, 8, 10, 0, tzinfo=UTC)
    nxt = advance_past(stale, ScheduleFrequency.DAILY, now)
    assert nxt > now
    # Exactly one interval past now, not a queue of missed runs.
    assert nxt - now < timedelta(days=1)


def test_advance_past_always_returns_future():
    now = datetime(2026, 3, 8, 10, 0, tzinfo=UTC)
    for freq in ScheduleFrequency:
        assert advance_past(now, freq, now) > now


def test_expiry_is_inclusive_of_end_date():
    db = session()
    today = date.today()
    s = _schedule(db, end_date=today)
    assert not is_expired(s, today)  # last day still runs
    assert is_expired(s, today + timedelta(days=1))


def test_due_schedules_respects_time_and_active_flag():
    db = session()
    now = datetime.now(timezone.utc)
    past = _schedule(db, next_run_at=now - timedelta(minutes=5), product_name="A")
    _schedule(db, next_run_at=now + timedelta(hours=1), product_name="B")
    paused = _schedule(
        db,
        next_run_at=now - timedelta(hours=1),
        is_active=False,
        product_name="C",
    )
    due = due_schedules(db, now)
    ids = {s.id for s in due}
    assert past.id in ids
    assert paused.id not in ids
    assert len(due) == 1


def test_lookback_covers_the_interval():
    """Each run must look back at least as far as it waited, or it drops articles."""
    assert default_lookback_days(ScheduleFrequency.DAILY) >= 1
    assert default_lookback_days(ScheduleFrequency.WEEKLY) >= 7
    assert default_lookback_days(ScheduleFrequency.MONTHLY) >= 31


def test_missing_active_search_string_creates_in_app_failure_alert():
    db = session()
    reviewer = User(
        email="schedule-owner@example.com",
        full_name="Schedule Owner",
        hashed_password="unused",
        role=Role.REVIEWER,
    )
    product = Product(
        name="Unconfigured Product",
        brands=[],
        synonyms=[],
        primary_reviewer_id=None,
    )
    db.add_all([reviewer, product])
    db.flush()
    product.primary_reviewer_id = reviewer.id
    schedule = SearchSchedule(
        product_id=product.id,
        frequency=ScheduleFrequency.DAILY,
        end_date=date.today() + timedelta(days=7),
        lookback_days=2,
        max_fetch=10,
        is_active=True,
        next_run_at=datetime.now(timezone.utc),
    )
    db.add(schedule)
    db.flush()

    result = __import__("asyncio").run(run_schedule(db, schedule))

    assert result["status"] == "no_active_search_string"
    alert = db.scalar(select(Alert).where(Alert.alert_type == "search_failed"))
    assert alert is not None
    assert alert.user_id == reviewer.id
    assert alert.channels == ["in_app"]
