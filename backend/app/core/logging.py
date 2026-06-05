"""Centralized logging setup. Forces UTF-8 on stdout so Unicode log
characters (like the -> arrow) don't crash on Windows cp1252 consoles.
"""
from __future__ import annotations

import logging
import sys


def setup_logging(level: str = "INFO") -> None:
    # Force UTF-8 on stdout/stderr if possible. On Windows with cp1252
    # default, Unicode characters in log messages raise UnicodeEncodeError.
    for stream in (sys.stdout, sys.stderr):
        enc = getattr(stream, "encoding", None)
        if enc and enc.lower().replace("-", "") != "utf8":
            try:
                stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
            except Exception:  # noqa: BLE001
                pass

    # Basic root logger setup
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
    )

    # Explicitly configure the "app" logger to print to stdout so it isn't
    # swallowed/ignored by Uvicorn's custom log configurations.
    app_logger = logging.getLogger("app")
    app_logger.setLevel(level)
    
    # If app_logger has no handlers, attach a console handler
    if not app_logger.handlers:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s", "%Y-%m-%d %H:%M:%S")
        )
        app_logger.addHandler(console_handler)
        app_logger.propagate = False

