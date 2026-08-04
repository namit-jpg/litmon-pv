from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Article, Product, User
from app.models.entities import ArticleStatus, PresenceStatus, Role


CLOSED_STATUSES = (
    ArticleStatus.AUTO_CLEAR,
    ArticleStatus.DISPOSITION_NOT_CASE,
    ArticleStatus.DISPOSITION_VALID_ICSR,
)


def active_work_count(db: Session, user_id: int) -> int:
    return (
        db.scalar(
            select(func.count())
            .select_from(Article)
            .where(
                Article.assignee_id == user_id,
                Article.status.notin_(CLOSED_STATUSES),
            )
        )
        or 0
    )


def is_routable(db: Session, user: User) -> bool:
    return (
        user.is_active
        and user.presence_status == PresenceStatus.AVAILABLE
        and active_work_count(db, user.id) < (user.capacity_limit or 20)
    )


def route_article(
    db: Session,
    *,
    product: Product,
    article: Article,
) -> tuple[User | None, str]:
    """Route a review item like a small Service Cloud Omni queue.

    Product primary reviewer is preferred. If unavailable or at capacity, the
    least-loaded available PV user receives the item. If nobody is routable,
    the item remains in its triage queue as unassigned.
    """
    if product.primary_reviewer_id:
        primary = db.get(User, product.primary_reviewer_id)
        if primary and is_routable(db, primary):
            return primary, "primary_reviewer"

    candidates = list(
        db.scalars(
            select(User).where(
                User.is_active.is_(True),
                User.presence_status == PresenceStatus.AVAILABLE,
                User.role.in_([Role.REVIEWER, Role.SENIOR_REVIEWER, Role.PV_LEAD]),
            )
        ).all()
    )
    candidates = [u for u in candidates if is_routable(db, u)]
    if candidates:
        candidates.sort(key=lambda u: (active_work_count(db, u.id), u.id))
        return candidates[0], "least_loaded_available"
    return None, "no_available_capacity"
