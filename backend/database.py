"""
Database configuration and session management

Uses SQLAlchemy for ORM and connection pooling.
"""

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Database URL from environment
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:password@localhost:5432/clarity")

# Create engine with connection pooling
engine = create_engine(
    DATABASE_URL,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,  # Verify connections before using
    echo=os.getenv("DEBUG", "false").lower() == "true"
)

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for models
Base = declarative_base()


def get_db() -> Session:
    """
    Dependency to get database session.

    Usage in FastAPI:
        @app.get("/api/items")
        async def list_items(db: Session = Depends(get_db)):
            items = db.query(Item).all()
            return items
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _reconcile_missing_columns(engine):
    """
    Additively bring EXISTING tables up to the models: `ADD COLUMN` for any model
    column that the live table is missing. NEVER drops or alters a column — so
    data is always preserved.

    This closes the one gap that breaks generated apps on a redeploy: each app has
    a PERSISTENT per-app schema, and `create_all` only creates missing *tables* —
    it never ALTERs an existing one. So when an edit adds a field to a model whose
    table already exists, the live table keeps its old shape and the app fails with
    `column ... does not exist`. Here we diff the model against the live table and
    add only what's missing.

    Safety: strictly additive (only `ADD COLUMN`), idempotent (we skip columns the
    table already has), and the column is added NULLABLE even if the model marks it
    NOT NULL — a NOT NULL column can't be added to a table with existing rows
    without a backfill, and we must never fail or rewrite data. The ORM still
    enforces the model's constraints on new writes. Best-effort per column.
    """
    from sqlalchemy import inspect, text

    insp = inspect(engine)
    existing = set(insp.get_table_names())
    for table in Base.metadata.sorted_tables:
        if table.name not in existing:
            continue  # create_all() (already run) creates missing tables in full
        live_cols = {c["name"] for c in insp.get_columns(table.name)}
        for col in table.columns:
            if col.name in live_cols:
                continue
            try:
                coltype = col.type.compile(dialect=engine.dialect)
            except Exception as e:  # exotic/custom type — skip, don't crash boot
                print(f"  ⚠️  skip {table.name}.{col.name}: can't render type ({e})")
                continue
            ddl = f'ALTER TABLE "{table.name}" ADD COLUMN "{col.name}" {coltype}'
            if col.server_default is not None:
                try:
                    arg = col.server_default.arg
                    ddl += f" DEFAULT {arg.text if hasattr(arg, 'text') else arg}"
                except Exception:
                    pass  # Python-side default → ORM applies it on insert; fine
            try:
                with engine.begin() as conn:
                    conn.execute(text(ddl))
                print(f"  ➕ added column {table.name}.{col.name}")
            except Exception as e:
                print(f"  ⚠️  could not add {table.name}.{col.name}: {e}")


def init_db():
    """
    Bring the database schema up to the models on startup — additively, never
    destructively (data is always preserved). Three layers, each fail-open so a
    hiccup never blocks boot:

      1. Alembic (`upgrade head` / `stamp head`) — the proper migration history
         for the template tables and any committed migrations.
      2. `create_all` — additively creates any model TABLE not yet present (the
         app's domain tables that aren't in a migration). It only ever CREATEs
         missing tables; it never ALTERs an existing one.
      3. `_reconcile_missing_columns` — `ADD COLUMN` for any model column missing
         on an already-created table (the drift `create_all` can't fix). Strictly
         additive.

    Together these guarantee the live schema always GAINS what the models need
    (tables + columns) across redeploys, while never dropping or rewriting data.
    """
    from backend import models  # noqa: F401  (register models on Base.metadata)
    import os

    # 1. Alembic migration history (template tables + any committed migrations).
    try:
        from alembic.config import Config
        from alembic import command
        from sqlalchemy import inspect

        cfg = Config(os.path.join(os.path.dirname(__file__), "alembic.ini"))
        insp = inspect(engine)
        has_alembic = insp.has_table("alembic_version")
        has_legacy_tables = insp.has_table("tasks")

        if has_legacy_tables and not has_alembic:
            command.stamp(cfg, "head")  # adopt an existing (create_all) schema
            print("✅ Database schema adopted into Alembic (stamped head)")
        else:
            command.upgrade(cfg, "head")
            print("✅ Database migrated to head")
    except Exception as e:  # never block boot — create_all below still runs
        print(f"⚠️  Alembic step skipped ({e})")

    # 2. Additively create any model table not yet present (idempotent; never
    #    alters existing tables).
    try:
        Base.metadata.create_all(bind=engine)
    except Exception as e:
        print(f"⚠️  create_all skipped ({e})")

    # 3. Additively add any model column missing on an existing table.
    try:
        _reconcile_missing_columns(engine)
    except Exception as e:
        print(f"⚠️  column reconcile skipped ({e})")

    print("✅ Database schema reconciled to models (additive, data-preserving)")


def seed_example_tasks():
    """
    Populate the example "Tasks" app with a few sample rows on first run so the
    template's widget (and dashboard) show real, varied content out of the box —
    this is what makes the small/medium/large widget sizes visibly different.

    Idempotent: only seeds when the tasks table is completely empty. Seeds for
    the local identity ("dev-user" — what backend/security.py:require_user returns
    in local dev, when no Claritty edge is present to stamp a real user), so the
    template's data shows out of the box when you run it locally.

    This is template/example data only — generated apps overwrite the models and
    this layer with their own, so it never leaks into a real app.
    """
    from backend import models

    db = SessionLocal()
    try:
        if db.query(models.Task).count() > 0:
            return  # already has data — don't duplicate

        DEMO_USER = "dev-user"
        # (title, priority, suggested_action, done) — mixed so open_count,
        # top_priority, and done_today are all non-zero.
        samples = [
            ("Fix the failing checkout webhook", "urgent",
             "Replay the last failed event and check the signature.", False),
            ("Reply to the partnership email", "high",
             "Draft a short yes and propose three times.", False),
            ("Review the Q3 roadmap draft", "high",
             "Skim for scope creep, flag the top two risks.", False),
            ("Prep slides for the demo", "medium",
             "Reuse last month's deck, swap in new metrics.", False),
            ("Refill coffee beans", "low",
             "Order the usual two bags.", False),
            ("Book dentist appointment", "medium",
             "Call before noon, they close early today.", False),
            ("Submit expense report", "medium", None, True),
            ("Merge the docs PR", "low", None, True),
        ]

        for title, priority, action, done in samples:
            db.add(models.Task(
                user_id=DEMO_USER,
                title=title,
                priority=priority,
                suggested_action=action,
                done=done,
            ))
        db.commit()
        print(f"✅ Seeded {len(samples)} example tasks for '{DEMO_USER}'")
    except Exception as e:  # never block startup on seed failure
        db.rollback()
        print(f"⚠️  Failed to seed example tasks: {e}")
    finally:
        db.close()
