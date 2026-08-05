"""Schema bootstrap via Alembic (with create_all fallback for pilot laptops)."""

from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy import inspect

logger = logging.getLogger("litmon.migrate")

_API_DIR = Path(__file__).resolve().parents[2]

_BASELINE_REVISION = "7611f1d89eaa"


def _create_all(engine) -> None:
    from app.core.database import Base
    import app.models  # noqa: F401

    Base.metadata.create_all(bind=engine)


def _missing_columns(engine) -> dict[str, list[str]]:
    """Columns the ORM expects but the database does not have.

    ``create_all`` adds missing *tables* but never adds *columns* to existing
    ones, so a database it "repaired" can still be unusable. This is the check
    that turns that silent breakage into a visible error.
    """
    from app.core.database import Base
    import app.models  # noqa: F401

    inspector = inspect(engine)
    existing = set(inspector.get_table_names())
    missing: dict[str, list[str]] = {}
    for table in Base.metadata.sorted_tables:
        if table.name not in existing:
            continue
        actual = {c["name"] for c in inspector.get_columns(table.name)}
        gap = [c.name for c in table.columns if c.name not in actual]
        if gap:
            missing[table.name] = gap
    return missing


def _drop_stale_batch_tables(engine) -> None:
    """Remove ``_alembic_tmp_*`` residue left by an interrupted batch migration.

    SQLite batch operations rebuild a table via a temp copy. If a migration
    dies midway the temp table survives and blocks every later attempt with
    "table _alembic_tmp_x already exists".
    """
    from sqlalchemy import text

    inspector = inspect(engine)
    stale = [t for t in inspector.get_table_names() if t.startswith("_alembic_tmp_")]
    if not stale:
        return
    with engine.begin() as conn:
        for name in stale:
            logger.warning("Dropping stale batch-migration table %s", name)
            conn.execute(text(f'DROP TABLE IF EXISTS "{name}"'))


def run_migrations(engine) -> str:
    """Apply Alembic migrations to head for ``engine``.

    If the database already has application tables but no ``alembic_version``
    row (legacy ``create_all`` DBs), stamp to the baseline and upgrade from
    there. Falls back to ``create_all`` if Alembic is unavailable — but never
    stamps a revision it did not actually apply.
    """
    try:
        from alembic import command
        from alembic.config import Config
    except ImportError:
        logger.warning("Alembic not installed; using create_all")
        _create_all(engine)
        return "create_all"

    ini = _API_DIR / "alembic.ini"
    if not ini.exists():
        logger.warning("alembic.ini not found; using create_all")
        _create_all(engine)
        return "create_all"

    cfg = Config(str(ini))
    # Ensure script location resolves when cwd is not apps/api
    cfg.set_main_option("script_location", str(_API_DIR / "alembic"))
    cfg.set_main_option("sqlalchemy.url", str(engine.url))
    # env.py reads this first, so migrations hit the engine we were handed
    # rather than whatever the ambient settings point at.
    cfg.attributes["db_url"] = str(engine.url)

    try:
        _drop_stale_batch_tables(engine)
        inspector = inspect(engine)
        tables = set(inspector.get_table_names())
        if tables and "alembic_version" not in tables:
            # Pre-Alembic pilot DBs match the original generated baseline.
            # Stamp that baseline, then apply every newer pilot migration.
            logger.info(
                "Existing tables without alembic_version — stamping baseline and upgrading (%d tables)",
                len(tables),
            )
            command.stamp(cfg, _BASELINE_REVISION)
            command.upgrade(cfg, "head")
            outcome = "stamp_baseline_upgrade_head"
        else:
            command.upgrade(cfg, "head")
            outcome = "upgrade_head"
    except Exception as exc:
        # Deliberately do NOT stamp head here. Stamping a revision whose DDL
        # did not run marks a broken schema as fully migrated, so every later
        # boot reports success while the columns are still missing.
        logger.error("Alembic migration failed: %s", exc)
        _create_all(engine)
        outcome = f"create_all_fallback:{type(exc).__name__}"

    gap = _missing_columns(engine)
    if gap:
        detail = "; ".join(f"{t}: {', '.join(cols)}" for t, cols in sorted(gap.items()))
        raise RuntimeError(
            "Database schema is incomplete after migration "
            f"({outcome}). Missing columns -> {detail}. "
            "The database predates these columns and could not be upgraded in "
            "place. Back up the file, then recreate it with "
            "`python -m app.bootstrap`, or apply the migrations manually."
        )
    return outcome
