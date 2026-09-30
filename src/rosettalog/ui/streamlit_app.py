from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

import streamlit as st

_API_URL = os.environ.get("ROSETTALOG_API_URL", "http://api:8000").rstrip("/")


def _api_request(path: str, *, data: bytes | None = None, filename: str = "") -> Any:
    headers = {"Accept": "application/json"}
    url = f"{_API_URL}{path}"
    if data is not None:
        headers["Content-Type"] = "application/octet-stream"
        safe_filename = filename.replace("\\", "/").rsplit("/", 1)[-1]
        headers["X-Filename"] = (
            safe_filename if re.fullmatch(r"[A-Za-z0-9._-]{1,128}", safe_filename) else "upload.log"
        )
    request = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> None:
    st.set_page_config(page_title="RosettaLog", layout="wide")
    st.title("RosettaLog")
    st.caption("Offline perimeter-log ingestion, parser review, and event visibility.")

    try:
        health = _api_request("/health")
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
        st.error(f"RosettaLog API is unavailable: {error}")
        st.stop()
    st.success(f"API status: {health.get('status', 'unknown')}")

    ingest_tab, parsers_tab, events_tab = st.tabs(["Ingest", "Parsers", "Events"])
    with ingest_tab:
        uploaded = st.file_uploader("Select a UTF-8 log file", type=["log", "txt", "json"])
        if uploaded is not None and st.button("Ingest file", type="primary"):
            try:
                result = _api_request(
                    "/ingest",
                    data=uploaded.getvalue(),
                    filename=uploaded.name,
                )
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
                st.error(f"Ingestion request failed: {error}")
            else:
                st.json(result)

    with parsers_tab:
        if st.button("Refresh parser list"):
            try:
                parser_rows = _api_request("/parsers")
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
                st.error(f"Could not load parsers: {error}")
            else:
                st.dataframe(parser_rows, use_container_width=True)

    with events_tab:
        event_limit = st.number_input(
            "Maximum recent events", min_value=1, max_value=1000, value=100
        )
        if st.button("Refresh events"):
            query = urllib.parse.urlencode({"limit": int(event_limit)})
            try:
                event_rows = _api_request(f"/events?{query}")
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
                st.error(f"Could not load events: {error}")
            else:
                st.dataframe(event_rows, use_container_width=True)


if __name__ == "__main__":
    main()
