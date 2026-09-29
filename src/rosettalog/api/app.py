from __future__ import annotations

from typing import Any

try:
    from fastapi import FastAPI  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - optional dependency for Gate 0 base install.
    FastAPI = None

if FastAPI is not None:
    app: Any = FastAPI(title="RosettaLog API", version="0.1.0")
else:
    app = None


def health() -> dict[str, str]:
    """Health endpoint for container checks and service monitoring."""
    return {"status": "ok"}


def list_parsers() -> list[str]:
    """Return a list of parser names. Gate 0 is intentionally minimal."""
    return []


if app is not None:
    app.get("/health")(health)
    app.get("/parsers")(list_parsers)
