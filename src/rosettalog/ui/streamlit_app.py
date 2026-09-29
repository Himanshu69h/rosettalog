from __future__ import annotations

try:
    import streamlit as st  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - optional dependency for Gate 0 base install.
    st = None

if st is not None:
    st.title("RosettaLog")
    st.caption("Gate 0 baseline stub: schema, docs, and project skeleton only.")
    st.write("Later gates will add Learn, Verify, Run, and Monitor views.")

__all__ = ["st"]
