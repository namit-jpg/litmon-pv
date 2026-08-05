"""drug concept catalogue and recurring search schedules

Revision ID: 5d2f9c4a8e73
Revises: 3c8e1a5f7b92
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "5d2f9c4a8e73"
down_revision: Union[str, None] = "3c8e1a5f7b92"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Guarded like the other pilot revisions so a database that create_all
    # already touched can still upgrade in place.
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())

    if "drug_concepts" not in tables:
        op.create_table(
            "drug_concepts",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("rxcui", sa.String(32), nullable=False, unique=True),
            sa.Column("name", sa.String(512), nullable=False),
            sa.Column("name_lower", sa.String(512), nullable=False),
            sa.Column("tty", sa.String(8), nullable=False),
            sa.Column(
                "synced_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
        )
        op.create_index("ix_drug_concepts_rxcui", "drug_concepts", ["rxcui"])
        op.create_index("ix_drug_concepts_name", "drug_concepts", ["name"])
        op.create_index("ix_drug_concepts_name_lower", "drug_concepts", ["name_lower"])
        op.create_index("ix_drug_concepts_tty", "drug_concepts", ["tty"])

    if "search_schedules" not in tables:
        op.create_table(
            "search_schedules",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "product_id",
                sa.Integer(),
                sa.ForeignKey("products.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "frequency",
                sa.Enum("DAILY", "WEEKLY", "MONTHLY", name="schedulefrequency"),
                nullable=False,
            ),
            sa.Column("end_date", sa.Date(), nullable=False),
            sa.Column(
                "lookback_days", sa.Integer(), nullable=False, server_default="7"
            ),
            sa.Column("max_fetch", sa.Integer(), nullable=False, server_default="30"),
            sa.Column(
                "is_active", sa.Boolean(), nullable=False, server_default=sa.true()
            ),
            sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_status", sa.String(32), nullable=True),
            sa.Column("last_error", sa.Text(), nullable=True),
            sa.Column("run_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_by", sa.String(255), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
        )
        op.create_index(
            "ix_search_schedules_product_id", "search_schedules", ["product_id"]
        )
        op.create_index(
            "ix_search_schedules_is_active", "search_schedules", ["is_active"]
        )
        # The runner polls on this column, so keep it indexed.
        op.create_index(
            "ix_search_schedules_next_run_at", "search_schedules", ["next_run_at"]
        )


def downgrade() -> None:
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())
    if "search_schedules" in tables:
        op.drop_table("search_schedules")
    if "drug_concepts" in tables:
        op.drop_table("drug_concepts")
