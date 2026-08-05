"""pilot Omni-style presence and capacity

Revision ID: 2a4c7b9d5e11
Revises: 0b7d2d38a1f4
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "2a4c7b9d5e11"
down_revision: Union[str, None] = "0b7d2d38a1f4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Guarded like the previous revision: a pilot database that ``create_all``
    # already touched may hold some of these objects.
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            "DO $$ BEGIN "
            "CREATE TYPE presencestatus AS ENUM ('OFFLINE', 'AVAILABLE', 'BUSY'); "
            "EXCEPTION WHEN duplicate_object THEN NULL; END $$"
        )

    existing = {c["name"] for c in sa.inspect(bind).get_columns("users")}
    if "presence_status" in existing and "capacity_limit" in existing:
        return

    with op.batch_alter_table("users") as batch_op:
        if "presence_status" not in existing:
            batch_op.add_column(
                sa.Column(
                    "presence_status",
                    sa.Enum("OFFLINE", "AVAILABLE", "BUSY", name="presencestatus"),
                    nullable=False,
                    server_default="AVAILABLE",
                )
            )
        if "capacity_limit" not in existing:
            batch_op.add_column(
                sa.Column(
                    "capacity_limit", sa.Integer(), nullable=False, server_default="20"
                )
            )
        if "presence_status" not in existing:
            batch_op.create_index("ix_users_presence_status", ["presence_status"])


def downgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_index("ix_users_presence_status")
        batch_op.drop_column("capacity_limit")
        batch_op.drop_column("presence_status")
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP TYPE presencestatus")
