from __future__ import annotations

import json
import os
import re
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from fastapi import FastAPI, HTTPException, Request
from jsonschema import validate

from rosettalog.analytics import ParquetSink, query_events
from rosettalog.ingest import Ingestor
from rosettalog.parsing import ParserRegistry
from rosettalog.rawstore import RawStore


@dataclass(frozen=True, slots=True)
class ApiSettings:
    data_dir: Path
    parser_dir: Path
    parser_schema_path: Path
    envelope_schema_path: Path
    max_upload_bytes: int = 50 * 1024 * 1024
    max_line_bytes: int = 65_536

    def __post_init__(self) -> None:
        if not 1 <= self.max_upload_bytes <= 50 * 1024 * 1024:
            raise ValueError("max_upload_bytes must be between 1 and 50 MiB")
        if not 1 <= self.max_line_bytes <= 65_536:
            raise ValueError("max_line_bytes must be between 1 and 64 KiB")

    @classmethod
    def from_env(cls) -> ApiSettings:
        return cls(
            data_dir=Path(os.environ.get("ROSETTALOG_DATA_DIR", "data")),
            parser_dir=Path(os.environ.get("ROSETTALOG_PARSER_DIR", "parsers")),
            parser_schema_path=Path(
                os.environ.get("ROSETTALOG_PARSER_SCHEMA", "schemas/parser.schema.json")
            ),
            envelope_schema_path=Path(
                os.environ.get("ROSETTALOG_ENVELOPE_SCHEMA", "schemas/envelope.schema.json")
            ),
        )


def create_app(settings: ApiSettings | None = None) -> FastAPI:
    config = settings or ApiSettings.from_env()
    application = FastAPI(title="RosettaLog API", version="0.1.0")
    application.state.ingest_lock = threading.Lock()

    @application.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @application.get("/parsers")
    async def list_parsers() -> list[dict[str, object]]:
        schema = json.loads(config.parser_schema_path.read_text(encoding="utf-8"))
        result: list[dict[str, object]] = []
        for path in sorted(config.parser_dir.glob("*.yaml")):
            definition = yaml.safe_load(path.read_text(encoding="utf-8"))
            if not isinstance(definition, dict):
                raise ValueError(f"parser definition must be a mapping: {path}")
            validate(instance=definition, schema=schema)
            result.append(
                {
                    "name": definition["name"],
                    "version": definition["version"],
                    "state": definition["state"],
                    "source_format": definition["source_format"],
                }
            )
        return result

    @application.post("/ingest")
    async def ingest(request: Request) -> dict[str, object]:
        content_length = request.headers.get("content-length")
        if content_length is not None:
            try:
                if int(content_length) > config.max_upload_bytes:
                    raise HTTPException(
                        status_code=413,
                        detail=f"upload exceeds {config.max_upload_bytes} bytes",
                    )
            except ValueError as error:
                raise HTTPException(status_code=400, detail="invalid content-length") from error
        content_type = request.headers.get("content-type", "")
        if content_type not in {"application/octet-stream", "text/plain"}:
            raise HTTPException(
                status_code=415,
                detail="content-type must be application/octet-stream or text/plain",
            )
        incoming = config.data_dir / "incoming"
        incoming.mkdir(parents=True, exist_ok=True)
        requested_name = request.headers.get("x-filename", "upload.log").replace("\\", "/")
        requested_name = Path(requested_name).name
        if not re.fullmatch(r"[A-Za-z0-9._-]{1,128}", requested_name):
            requested_name = "upload.log"
        upload_path = incoming / f"{uuid.uuid4().hex}-{requested_name}"
        total_bytes = 0
        try:
            with upload_path.open("wb") as destination:
                async for chunk in request.stream():
                    total_bytes += len(chunk)
                    if total_bytes > config.max_upload_bytes:
                        raise HTTPException(
                            status_code=413,
                            detail=f"upload exceeds {config.max_upload_bytes} bytes",
                        )
                    destination.write(chunk)
        except HTTPException:
            upload_path.unlink(missing_ok=True)
            raise
        except OSError:
            upload_path.unlink(missing_ok=True)
            raise
        if total_bytes == 0:
            upload_path.unlink(missing_ok=True)
            raise HTTPException(status_code=400, detail="upload is empty")

        store = RawStore(config.data_dir / "raw_store", max_record_bytes=config.max_line_bytes)
        registry = ParserRegistry(config.parser_dir, config.parser_schema_path)
        ingestor = Ingestor(
            store,
            registry,
            envelope_schema_path=config.envelope_schema_path,
            max_line_bytes=config.max_line_bytes,
        )
        with application.state.ingest_lock:
            report = ingestor.ingest_file(upload_path)
            parquet_path = ParquetSink(config.data_dir / "parquet").write_events(
                list(report.events)
            )
        return {
            "source_id": report.source_id,
            "records_seen": report.records_seen,
            "events_written": len(report.events),
            "quarantined": len(report.quarantined),
            "parquet_file": str(parquet_path) if parquet_path is not None else None,
            "upload_file": upload_path.name,
        }

    @application.get("/events")
    async def list_events(limit: int = 100) -> list[dict[str, Any]]:
        if not 1 <= limit <= 1000:
            raise HTTPException(status_code=422, detail="limit must be between 1 and 1000")
        sql = (
            "SELECT event_id, ingest_time, source_file, parser_name, parser_version, "
            f"event_json, raw_sha256 FROM events ORDER BY ingest_time DESC LIMIT {limit}"
        )
        return query_events(config.data_dir / "parquet", sql)

    return application


app = create_app()
