from __future__ import annotations

from pydantic import BaseModel, Field


class SourceRef(BaseModel):
    id: str
    file: str
    byte_offset: int
    line_no: int


class ParserRef(BaseModel):
    name: str
    version: int
    confidence: float = Field(ge=0.0, le=1.0)


class EventFlags(BaseModel):
    duplicate_of: str | None = None
    duplicate_count: int = 0
    tz_assumed: bool = False
    masked: bool = True


class Envelope(BaseModel):
    event_id: str
    ingest_time: str
    source: SourceRef
    raw: str
    raw_sha256: str
    parser: ParserRef
    event: dict[str, object]
    unmapped: dict[str, object]
    flags: EventFlags
