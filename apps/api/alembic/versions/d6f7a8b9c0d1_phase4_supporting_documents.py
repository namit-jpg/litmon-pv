"""phase 4 supporting document references

Revision ID: d6f7a8b9c0d1
Revises: c4e5f6a7b8c9
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "d6f7a8b9c0d1"
down_revision: Union[str, None] = "c4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    columns = {
        column["name"]
        for column in sa.inspect(op.get_bind()).get_columns("review_decisions")
    }
    if "supporting_documents" not in columns:
        with op.batch_alter_table("review_decisions") as batch:
            batch.add_column(sa.Column("supporting_documents", sa.JSON(), nullable=True))


def downgrade() -> None:
    columns = {
        column["name"]
        for column in sa.inspect(op.get_bind()).get_columns("review_decisions")
    }
    if "supporting_documents" in columns:
        with op.batch_alter_table("review_decisions") as batch:
            batch.drop_column("supporting_documents")
