"""SQLAlchemy engine, session factory, and FastAPI dependency."""
from __future__ import annotations

import re
from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from app.config import settings

_db_url = settings.database_url.strip() if settings.database_url else ""

# If no DATABASE_URL set, try to build Supavisor session-mode URI from config.
# Supavisor is IPv4-only (required when db.X.supabase.co doesn't resolve).
if not _db_url and settings.supabase_url and settings.supabase_database_password:
    # Extract project ref from supabase_url (e.g. "wflrdsjagynptracwaxe" from URL)
    ref_match = re.search(r"://([^.]+)\.supabase", settings.supabase_url)
    ref = ref_match.group(1) if ref_match else ""
    # Strip trailing quote from password if present
    password = settings.supabase_database_password.rstrip("'").strip()
    # Build Supavisor session-mode URI (port 5432, persistent backend)
    _db_url = f"postgresql+psycopg2://postgres.{ref}:{password}@aws-1-ap-northeast-2.pooler.supabase.com:6543/postgres"

if not _db_url:
    raise RuntimeError(
        "DATABASE_URL is not set in .env and could not be built from Supabase config. "
        "Set DATABASE_URL to your Supavisor session-mode URI from the Supabase dashboard."
    )

engine = create_engine(_db_url, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, future=True)
Base = declarative_base()


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
