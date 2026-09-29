from __future__ import annotations

import re
import warnings
from typing import Any

try:
    import re2  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - optional dependency for Gate 0 base install.
    warnings.warn(
        "google-re2 is not installed; falling back to the stdlib re module. "
        "Use a strict pattern-safety lint pass before production regex changes.",
        RuntimeWarning,
        stacklevel=2,
    )
    re2 = re


def compile_pattern(pattern: str, *, flags: int = 0) -> Any:
    """Compile a regex pattern using re2 when available, else the stdlib fallback."""
    return re2.compile(pattern, flags)
