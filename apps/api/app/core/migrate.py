"""Schema bootstrap via Alembic (with create_all fallback for pilot laptops)."""

from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy import inspect, text

logger = logging.getLogger("litmon.migrate")

_API_DIR = Path(__file__).resolve().parents[2]


def run_migrations(engine) -> str:
    """Apply Alembic migrations to head.

    If the database already has application tables but no ``alembic_version``
    row (legacy ``create_all`` DBs), stamp to head without re-running DDL.
    Falls back to ``create_all`` if Alembic is unavailable or fails.
    """
    try:
        from alembic import command
        from alembic.config import Config
    except ImportError:
        logger.warning("Alembic not installed; using create_all")
        from app.core.database import Base
        import app.models  # noqa: F401

        Base.metadata.create_all(bind=engine)
        return "create_all"

    ini = _API_DIR / "alembic.ini"
    if not ini.exists():
        from app.core.database import Base
        import app.models  # noqa: F401

        Base.metadata.create_all(bind=engine)
        return "create_all"

    cfg = Config(str(ini))
    # Ensure script location resolves when cwd is not apps/api
    cfg.set_main_option("script_location", str(_API_DIR / "alembic"))
    cfg.set_main_option("sqlalchemy.url", str(engine.url))

    try:
        inspector = inspect(engine)
        tables = set(inspector.get_table_names())
        if tables and "alembic_version" not in tables:
            # Pre-Alembic pilot DBs match the original generated baseline.
            # Stamp that baseline, then apply every newer pilot migration.
            logger.info(
                "Existing tables without alembic_version — stamping baseline and upgrading (%d tables)",
                len(tables),
            )
            command.stamp(cfg, "7611f1d89eaa")
            command.upgrade(cfg, "head")
            return "stamp_baseline_upgrade_head"

        command.upgrade(cfg, "head")
        return "upgrade_head"
    except Exception as exc:
        logger.warning("Alembic migration failed (%s); falling back to create_all", exc)
        from app.core.database import Base
        import app.models  # noqa: F401

        Base.metadata.create_all(bind=engine)
        # Best-effort stamp so next boot uses Alembic
        try:
            command.stamp(cfg, "head")
        except Exception:
            pass
        return f"create_all_fallback:{type(exc).__name__}"
