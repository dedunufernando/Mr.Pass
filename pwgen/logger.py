"""Structured logging setup."""
from __future__ import annotations
import logging


def setup_logging(debug: bool = False, log_file: str | None = None) -> None:
    level = logging.DEBUG if debug else logging.INFO
    handlers: list[logging.Handler] = []

    try:
        from rich.logging import RichHandler
        handlers.append(RichHandler(rich_tracebacks=True, show_path=False))
    except ImportError:
        handlers.append(logging.StreamHandler())

    if log_file:
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))

    logging.basicConfig(level=level, handlers=handlers, force=True)
