from __future__ import annotations

from importlib import import_module
from typing import Any

try:
    st: Any = import_module("streamlit")
except ImportError:  # pragma: no cover - optional dependency for base installs.
    st = None

if st is not None:
    st.title("RosettaLog")
    st.caption("STUB: Gate 4 will provide the RosettaLog workflow UI.")
    st.write("Later gates will add Learn, Verify, Run, and Monitor views.")

__all__ = ["st"]
