from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from rosettalog.api.app import ApiSettings, create_app

ROOT = Path(__file__).resolve().parents[1]


def _settings(tmp_path: Path, *, max_upload_bytes: int = 1_000_000) -> ApiSettings:
    return ApiSettings(
        data_dir=tmp_path / "data",
        parser_dir=ROOT / "parsers",
        parser_schema_path=ROOT / "schemas" / "parser.schema.json",
        envelope_schema_path=ROOT / "schemas" / "envelope.schema.json",
        max_upload_bytes=max_upload_bytes,
    )


def _request(
    application: FastAPI,
    method: str,
    path: str,
    **kwargs: object,
):
    async def send_request():
        async with AsyncClient(
            transport=ASGITransport(app=application),
            base_url="http://test",
        ) as client:
            return await client.request(method, path, **kwargs)

    return asyncio.run(send_request())


def test_api_health_parser_list_ingestion_and_events(tmp_path: Path) -> None:
    application = create_app(_settings(tmp_path))
    assert _request(application, "GET", "/health").json() == {"status": "ok"}
    parsers = _request(application, "GET", "/parsers")
    assert parsers.status_code == 200
    assert len(parsers.json()) == 4

    log_bytes = (ROOT / "samples" / "known" / "json.log").read_bytes()
    result = _request(
        application,
        "POST",
        "/ingest",
        content=log_bytes,
        headers={
            "Content-Type": "application/octet-stream",
            "X-Filename": "..\\private\\events.json",
        },
    )
    assert result.status_code == 200, result.text
    assert result.json()["events_written"] == 2
    events = _request(application, "GET", "/events")
    assert events.status_code == 200
    assert len(events.json()) == 2


def test_api_upload_limits_and_content_type_are_enforced(tmp_path: Path) -> None:
    application = create_app(_settings(tmp_path, max_upload_bytes=8))
    too_large = _request(
        application,
        "POST",
        "/ingest",
        content=b"0123456789",
        headers={"Content-Type": "application/octet-stream"},
    )
    wrong_type = _request(
        application,
        "POST",
        "/ingest",
        content=b"x",
        headers={"Content-Type": "application/json"},
    )

    assert too_large.status_code == 413
    assert wrong_type.status_code == 415
    assert list((tmp_path / "data" / "incoming").glob("*")) == []

    async def chunked_body():
        yield b"12345"
        yield b"67890"

    streamed_client = create_app(_settings(tmp_path / "streamed", max_upload_bytes=8))
    streamed = _request(
        streamed_client,
        "POST",
        "/ingest",
        content=chunked_body(),
        headers={"Content-Type": "application/octet-stream"},
    )
    assert streamed.status_code == 413
    assert list((tmp_path / "streamed" / "data" / "incoming").glob("*")) == []


def test_api_event_limit_is_bounded(tmp_path: Path) -> None:
    result = _request(create_app(_settings(tmp_path)), "GET", "/events?limit=1001")

    assert result.status_code == 422
