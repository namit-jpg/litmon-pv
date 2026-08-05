"""pilot assignment signal alerts

Revision ID: 0b7d2d38a1f4
Revises: 7611f1d89eaa
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0b7d2d38a1f4"
down_revision: Union[str, None] = "7611f1d89eaa"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns(bind, table: str) -> set:
    return {c["name"] for c in sa.inspect(bind).get_columns(table)}


def _backfill() -> None:
    """Preserve a useful demo immediately after upgrade.

    The bootstrap user is the pilot default; Admin can change each product
    assignment in the UI. Both statements are ``WHERE ... IS NULL`` guarded so
    re-running them is a no-op.
    """
    op.execute(
        sa.text(
            "UPDATE products SET primary_reviewer_id = "
            "(SELECT id FROM users WHERE email = 'reviewer@litmon.local' LIMIT 1) "
            "WHERE primary_reviewer_id IS NULL"
        )
    )
    op.execute(
        sa.text(
            "UPDATE articles SET assignee_id = "
            "(SELECT primary_reviewer_id FROM products WHERE products.id = articles.product_id) "
            "WHERE assignee_id IS NULL AND status NOT IN "
            "('AUTO_CLEAR', 'DISPOSITION_NOT_CASE', 'DISPOSITION_VALID_ICSR')"
        )
    )


def upgrade() -> None:
    # Pilot laptops may already have parts of this schema: bootstrap used to
    # call ``create_all``, which adds new *tables* (alerts) but never adds new
    # *columns*. Every step below is therefore guarded so such a hybrid
    # database can still upgrade instead of dying on "already exists".
    bind = op.get_bind()

    if bind.dialect.name == "postgresql":
        op.execute("ALTER TYPE decisionaction ADD VALUE IF NOT EXISTS 'MARK_POTENTIAL_SIGNAL'")
        op.execute("ALTER TYPE decisionaction ADD VALUE IF NOT EXISTS 'CONFIRM_SIGNAL'")
        op.execute("ALTER TYPE decisionaction ADD VALUE IF NOT EXISTS 'REJECT_SIGNAL'")

    article_uniques = {
        u["name"] for u in sa.inspect(bind).get_unique_constraints("articles")
    }
    if "uq_articles_product_pmid" not in article_uniques:
        with op.batch_alter_table("articles") as batch_op:
            if "uq_articles_pmid" in article_uniques:
                batch_op.drop_constraint("uq_articles_pmid", type_="unique")
            batch_op.create_unique_constraint(
                "uq_articles_product_pmid", ["product_id", "pmid"]
            )

    if "primary_reviewer_id" not in _columns(bind, "products"):
        with op.batch_alter_table("products") as batch_op:
            batch_op.add_column(
                sa.Column("primary_reviewer_id", sa.Integer(), nullable=True)
            )
            batch_op.create_foreign_key(
                "fk_products_primary_reviewer", "users", ["primary_reviewer_id"], ["id"]
            )
            batch_op.create_index(
                "ix_products_primary_reviewer_id", ["primary_reviewer_id"]
            )

    if "signal_status" not in _columns(bind, "articles"):
        with op.batch_alter_table("articles") as batch_op:
            batch_op.add_column(
                sa.Column(
                    "signal_status",
                    sa.Enum(
                        "NOT_ASSESSED",
                        "POTENTIAL",
                        "CONFIRMED",
                        "REJECTED",
                        name="signalstatus",
                    ),
                    nullable=False,
                    server_default="NOT_ASSESSED",
                )
            )
            batch_op.create_index("ix_articles_signal_status", ["signal_status"])

    if "alerts" in sa.inspect(bind).get_table_names():
        _backfill()
        return

    op.create_table(
        "alerts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("article_id", sa.Integer(), sa.ForeignKey("articles.id"), nullable=True),
        sa.Column("alert_type", sa.String(64), nullable=False),
        sa.Column("priority", sa.String(16), nullable=False, server_default="normal"),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("dedupe_key", sa.String(255), nullable=True, unique=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_alerts_user_id", "alerts", ["user_id"])
    op.create_index("ix_alerts_article_id", "alerts", ["article_id"])
    op.create_index("ix_alerts_alert_type", "alerts", ["alert_type"])
    op.create_index("ix_alerts_priority", "alerts", ["priority"])
    op.create_index("ix_alerts_read_at", "alerts", ["read_at"])
    op.create_index("ix_alerts_created_at", "alerts", ["created_at"])

    _backfill()


def downgrade() -> None:
    op.drop_table("alerts")
    with op.batch_alter_table("articles") as batch_op:
        batch_op.drop_index("ix_articles_signal_status")
        batch_op.drop_column("signal_status")
        batch_op.drop_constraint("uq_articles_product_pmid", type_="unique")
        batch_op.create_unique_constraint("uq_articles_pmid", ["pmid"])
    with op.batch_alter_table("products") as batch_op:
        batch_op.drop_index("ix_products_primary_reviewer_id")
        batch_op.drop_constraint("fk_products_primary_reviewer", type_="foreignkey")
        batch_op.drop_column("primary_reviewer_id")
