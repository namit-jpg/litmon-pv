"""phase 2 regulatory submission records

Revision ID: c4e5f6a7b8c9
Revises: 8f3a2c6d1b40
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "c4e5f6a7b8c9"
down_revision: Union[str, None] = "8f3a2c6d1b40"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if "regulatory_records" in set(sa.inspect(op.get_bind()).get_table_names()):
        return
    op.create_table(
        "regulatory_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "article_id",
            sa.Integer(),
            sa.ForeignKey("articles.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("latest_export_id", sa.Integer(), sa.ForeignKey("export_packages.id")),
        sa.Column("decision", sa.String(32), nullable=False, server_default="pending_decision"),
        sa.Column("decision_reason", sa.Text(), nullable=True),
        sa.Column("gateway", sa.String(255), nullable=True),
        sa.Column("submission_reference", sa.String(255), nullable=True),
        sa.Column("acknowledgement", sa.Text(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_regulatory_records_article_id", "regulatory_records", ["article_id"])
    op.create_index("ix_regulatory_records_decision", "regulatory_records", ["decision"])


def downgrade() -> None:
    op.drop_index("ix_regulatory_records_decision", table_name="regulatory_records")
    op.drop_index("ix_regulatory_records_article_id", table_name="regulatory_records")
    op.drop_table("regulatory_records")
