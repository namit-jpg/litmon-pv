"""split classification from workflow status; signal tags, sources, extraction

The load-bearing change of the partner-feedback rebuild. ``ArticleStatus`` used
to mix where an article sits in the workflow with what it turned out to be, so
"potential safety signal" and "under review" were mutually exclusive when they
should be orthogonal. This splits them three ways: status (workflow),
classification (what it is) and signal tags (multi-select assessment).

Revision ID: 8f3a2c6d1b40
Revises: 5d2f9c4a8e73
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "8f3a2c6d1b40"
down_revision: Union[str, None] = "5d2f9c4a8e73"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Old ArticleStatus -> (new status, inferred classification).
#
# Only the members that described an *outcome* move. ``deferred``,
# ``second_review`` and ``qc_sample`` are genuinely about where an article
# sits, so they survive unchanged and are absent from this map.
#
# ``disposition_not_case`` becomes archived/irrelevant: it was terminal and the
# article was found not to be a case. ``auto_clear`` also archives, but as
# ``irrelevant`` rather than ``invalid`` — it was cleared by threshold, not by
# failure. Nothing maps to the new ``exception`` status; no old status meant
# "processing failed", which is exactly the gap the partner asked us to close.
_STATUS_MAP = {
    "ingested": ("new_alert", None),
    "scored": ("new_alert", None),
    "routed": ("awaiting_review", "potentially_relevant"),
    "under_review": ("under_assessment", "requires_human_review"),
    "auto_clear": ("archived", "irrelevant"),
    "disposition_not_case": ("archived", "irrelevant"),
    "disposition_valid_icsr": ("approved_for_submission", "adverse_event_related"),
}

_SOURCES = [
    ("PubMed", "bibliographic", "NLM / NCBI", "public", "E-utilities ESearch + EFetch", "Title, abstract, MeSH", True),
    ("PubMed Central (PMC)", "full_text", "NLM / NCBI", "public", "E-utilities, OA subset", "Full text where OA", False),
    ("Embase", "bibliographic", "Elsevier", "subscription", None, None, False),
]


def upgrade() -> None:
    # Guarded like the other pilot revisions so a database that create_all
    # already touched can still upgrade in place.
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    def cols(table: str) -> set[str]:
        return {c["name"] for c in inspector.get_columns(table)} if table in tables else set()

    if "literature_sources" not in tables:
        op.create_table(
            "literature_sources",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(128), nullable=False, unique=True),
            sa.Column("kind", sa.String(64), nullable=False, server_default="bibliographic"),
            sa.Column("provider", sa.String(128), nullable=True),
            sa.Column("access_model", sa.String(64), nullable=False, server_default="public"),
            sa.Column("retrieval", sa.String(255), nullable=True),
            sa.Column("coverage", sa.String(255), nullable=True),
            sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
        )

    if "article_signal_tags" not in tables:
        op.create_table(
            "article_signal_tags",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "article_id",
                sa.Integer(),
                sa.ForeignKey("articles.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("tag", sa.String(32), nullable=False),
            sa.Column("is_ai_proposed", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("set_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.UniqueConstraint("article_id", "tag", name="uq_article_signal_tags"),
        )
        op.create_index("ix_article_signal_tags_article_id", "article_signal_tags", ["article_id"])
        op.create_index("ix_article_signal_tags_tag", "article_signal_tags", ["tag"])

    article_cols = cols("articles")
    with op.batch_alter_table("articles") as batch:
        if "ai_classification" not in article_cols:
            batch.add_column(sa.Column("ai_classification", sa.String(32), nullable=True))
        if "human_classification" not in article_cols:
            batch.add_column(sa.Column("human_classification", sa.String(32), nullable=True))
        if "priority" not in article_cols:
            # The default is the enum *name*, matching how SQLAlchemy persists
            # this column. Seeding the value ("p3") instead makes every existing
            # row unreadable the moment the ORM tries to load it.
            batch.add_column(
                sa.Column("priority", sa.String(8), nullable=False, server_default="P3")
            )
        if "exception_cause" not in article_cols:
            batch.add_column(sa.Column("exception_cause", sa.String(32), nullable=True))
        if "literature_source_id" not in article_cols:
            # Batch mode rebuilds the table, so the constraint needs an explicit
            # name — SQLite has no autogenerated one to carry over.
            batch.add_column(
                sa.Column(
                    "literature_source_id",
                    sa.Integer(),
                    sa.ForeignKey(
                        "literature_sources.id",
                        name="fk_articles_literature_source_id",
                    ),
                    nullable=True,
                )
            )

    product_cols = cols("products")
    with op.batch_alter_table("products") as batch:
        if "mah" not in product_cols:
            batch.add_column(sa.Column("mah", sa.String(255), nullable=True))
        if "markets" not in product_cols:
            batch.add_column(sa.Column("markets", sa.JSON(), nullable=True))
            # ProductOut.markets is a required list, so products that predate
            # this column fail response validation until they hold an array.
            op.execute(sa.text("UPDATE products SET markets = '[]' WHERE markets IS NULL"))

    screening_cols = cols("screening_results")
    extraction = [
        ("indication", sa.String(512)),
        ("dosage", sa.String(512)),
        ("outcome", sa.String(255)),
        ("seriousness", sa.String(128)),
        ("country_of_occurrence", sa.String(128)),
        ("reporter_type", sa.String(128)),
        ("concomitant_medication", sa.Text()),
        ("relevance_reason", sa.Text()),
    ]
    with op.batch_alter_table("screening_results") as batch:
        for name, type_ in extraction:
            if name not in screening_cols:
                batch.add_column(sa.Column(name, type_, nullable=True))
        if "article_excerpts" not in screening_cols:
            batch.add_column(sa.Column("article_excerpts", sa.JSON(), nullable=True))
        if "confidence" not in screening_cols:
            batch.add_column(sa.Column("confidence", sa.Float(), nullable=True))
        if "processed_at" not in screening_cols:
            batch.add_column(
                sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True)
            )

    if "channels" not in cols("alerts"):
        with op.batch_alter_table("alerts") as batch:
            batch.add_column(sa.Column("channels", sa.JSON(), nullable=True))
        # AlertOut.channels is a required list, so alerts raised before this
        # column existed break the inbox until they hold an array.
        op.execute(sa.text("UPDATE alerts SET channels = '[]' WHERE channels IS NULL"))

    _seed_sources()
    _remap_statuses()


def _seed_sources() -> None:
    for name, kind, provider, access, retrieval, coverage, enabled in _SOURCES:
        op.execute(
            sa.text(
                "INSERT INTO literature_sources "
                "(name, kind, provider, access_model, retrieval, coverage, is_enabled) "
                "SELECT :name, :kind, :provider, :access, :retrieval, :coverage, :enabled "
                "WHERE NOT EXISTS (SELECT 1 FROM literature_sources WHERE name = :name)"
            ).bindparams(
                name=name,
                kind=kind,
                provider=provider,
                access=access,
                retrieval=retrieval,
                coverage=coverage,
                enabled=enabled,
            )
        )
    # Everything ingested so far came from PubMed, which is the only source the
    # pipeline has ever queried.
    op.execute(
        sa.text(
            "UPDATE articles SET literature_source_id = "
            "(SELECT id FROM literature_sources WHERE name = 'PubMed') "
            "WHERE literature_source_id IS NULL"
        )
    )


def _remap_statuses() -> None:
    """Rewrite old combined statuses onto the status/classification split.

    The map above is written in enum values, but SQLAlchemy persists enum
    *names*, so the column holds ``ROUTED`` rather than ``routed``. Matching on
    the value alone updates nothing and leaves populated databases carrying
    statuses the new enum cannot load, so compare against both spellings.
    """
    for old, (new_status, classification) in _STATUS_MAP.items():
        op.execute(
            sa.text(
                "UPDATE articles SET status = :new_status_name, "
                "ai_classification = COALESCE(ai_classification, :classification_name) "
                "WHERE status IN (:old, :old_name)"
            ).bindparams(
                new_status_name=new_status.upper(),
                classification_name=(
                    classification.upper() if classification else None
                ),
                old=old,
                old_name=old.upper(),
            )
        )

    # signal_status is retained as the coarse rollup the queue already sorts on;
    # mirror it into the new tag table so both surfaces agree from day one.
    for signal_status, tag in (
        ("potential_signal", "potential_signal"),
        ("confirmed_signal", "confirmed_signal"),
    ):
        op.execute(
            sa.text(
                "INSERT INTO article_signal_tags (article_id, tag, is_ai_proposed) "
                "SELECT a.id, :tag, 0 FROM articles a WHERE a.signal_status = :ss "
                "AND NOT EXISTS (SELECT 1 FROM article_signal_tags t "
                "                WHERE t.article_id = a.id AND t.tag = :tag)"
            ).bindparams(tag=tag, ss=signal_status)
        )


def downgrade() -> None:
    # Lossy by nature: archived collapses auto_clear and disposition_not_case,
    # and the new exception status has no pre-split equivalent at all.
    inverse = {
        "new_alert": "ingested",
        "awaiting_review": "routed",
        "under_assessment": "under_review",
        "exception": "deferred",
        "approved_for_submission": "disposition_valid_icsr",
        "not_for_submission": "disposition_not_case",
        "submitted": "disposition_valid_icsr",
        "archived": "auto_clear",
    }
    # Same name-vs-value mismatch as the upgrade: match either spelling and
    # write back the stored form, or a rollback strands every row.
    for new_status, old in inverse.items():
        op.execute(
            sa.text(
                "UPDATE articles SET status = :old_name "
                "WHERE status IN (:new_status, :new_status_name)"
            ).bindparams(
                old_name=old.upper(),
                new_status=new_status,
                new_status_name=new_status.upper(),
            )
        )

    with op.batch_alter_table("alerts") as batch:
        batch.drop_column("channels")
    with op.batch_alter_table("screening_results") as batch:
        for name in (
            "indication",
            "dosage",
            "outcome",
            "seriousness",
            "country_of_occurrence",
            "reporter_type",
            "concomitant_medication",
            "relevance_reason",
            "article_excerpts",
            "confidence",
            "processed_at",
        ):
            batch.drop_column(name)
    with op.batch_alter_table("products") as batch:
        batch.drop_column("markets")
        batch.drop_column("mah")
    with op.batch_alter_table("articles") as batch:
        batch.drop_column("literature_source_id")
        batch.drop_column("exception_cause")
        batch.drop_column("priority")
        batch.drop_column("human_classification")
        batch.drop_column("ai_classification")

    op.drop_table("article_signal_tags")
    op.drop_table("literature_sources")
