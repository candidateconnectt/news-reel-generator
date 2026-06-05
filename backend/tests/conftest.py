"""Pytest config: ensure the app package is importable from the backend/ dir."""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Add backend/ to sys.path so `from app...` works under pytest.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Set test defaults BEFORE any app module imports settings.
os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("MAKE_COM_CALLBACK_SECRET", "")
os.environ.setdefault("MAKE_COM_WEBHOOK_URL", "")
