"""active pharmaceutical ingredient (API) tags

Revision ID: 3c8e1a5f7b92
Revises: 2a4c7b9d5e11
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "3c8e1a5f7b92"
down_revision: Union[str, None] = "2a4c7b9d5e11"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Guarded like the other pilot revisions so a database that create_all
    # already touched can still upgrade in place.
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())

    if "active_ingredients" not in tables:
        op.create_table(
            "active_ingredients",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(255), nullable=False, unique=True),
            sa.Column("inn", sa.String(255), nullable=True),
            sa.Column("atc_code", sa.String(32), nullable=True),
            sa.Column("unii", sa.String(32), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
        )
        op.create_index("ix_active_ingredients_name", "active_ingredients", ["name"])
        op.create_index("ix_active_ingredients_inn", "active_ingredients", ["inn"])

    if "product_active_ingredients" not in tables:
        op.create_table(
            "product_active_ingredients",
            sa.Column(
                "product_id",
                sa.Integer(),
                sa.ForeignKey("products.id", ondelete="CASCADE"),
                primary_key=True,
            ),
            sa.Column(
                "active_ingredient_id",
                sa.Integer(),
                sa.ForeignKey("active_ingredients.id", ondelete="CASCADE"),
                primary_key=True,
            ),
        )

    _backfill()


def _backfill() -> None:
    """Seed API tags from the existing single-value Product.inn column.

    Product.inn is kept as a denormalised display field; the tag table
    becomes the source of truth for regulatory export.
    """
    op.execute(
        sa.text(
            "INSERT INTO active_ingredients (name, inn, atc_code, is_active) "
            "SELECT DISTINCT LOWER(TRIM(p.inn)), LOWER(TRIM(p.inn)), p.atc_code, 1 "
            "FROM products p "
            "WHERE p.inn IS NOT NULL AND TRIM(p.inn) <> '' "
            "  AND LOWER(TRIM(p.inn)) NOT IN (SELECT name FROM active_ingredients)"
        )
    )
    op.execute(
        sa.text(
            "INSERT INTO product_active_ingredients (product_id, active_ingredient_id) "
            "SELECT p.id, ai.id FROM products p "
            "JOIN active_ingredients ai ON ai.name = LOWER(TRIM(p.inn)) "
            "WHERE p.inn IS NOT NULL AND TRIM(p.inn) <> '' "
            "  AND NOT EXISTS ("
            "     SELECT 1 FROM product_active_ingredients x "
            "     WHERE x.product_id = p.id AND x.active_ingredient_id = ai.id)"
        )
    )


def downgrade() -> None:
    op.drop_table("product_active_ingredients")
    op.drop_index("ix_active_ingredients_inn", table_name="active_ingredients")
    op.drop_index("ix_active_ingredients_name", table_name="active_ingredients")
    op.drop_table("active_ingredients")
