from __future__ import annotations

from importlib import import_module
from typing import Any

try:
    fastapi_module = import_module("fastapi")
except ImportError:  # pragma: no cover - optional dependency for base installs.
    app: Any = None
else:
    fastapi_type = getattr(fastapi_module, "FastAPI")
    app = fastapi_type(title="RosettaLog API", version="0.1.0")


def health() -> dict[str, str]:
    """Health endpoint for container checks and service monitoring."""
    return {"status": "ok"}


def list_parsers() -> list[str]:
    """STUB: connect parser listing when the Gate 4 API is implemented."""
    return []


if app is not None:
    app.get("/health")(health)
    app.get("/parsers")(list_parsers)
