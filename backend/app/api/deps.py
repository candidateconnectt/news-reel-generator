"""Shared FastAPI dependencies."""
from app.database import get_db  # re-export for routes

__all__ = ["get_db"]
