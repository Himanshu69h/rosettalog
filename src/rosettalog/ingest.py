from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from jsonschema import FormatChecker, validate

from rosettalog.models import Envelope
from rosettalog.parsing import ParsedLine, ParserRegistry
from rosettalog.rawstore import RawRecordRef, RawStore

CLASS_UIDS = {
    "Authentication": 3002,
    "Detection Finding": 2004,
    "Network Activity": 4001,
}


@dataclass(frozen=True, slots=True)
class QuarantineRecord:
    reason_code: str
    detail: str
    source_id: str
    source_file: str
    byte_offset: int
    line_no: int
    raw_refs: tuple[RawRecordRef, ...]


@dataclass(frozen=True, slots=True)
class IngestReport:
    source_id: str
    records_seen: int
    events: tuple[dict[str, Any], ...]
    quarantined: tuple[QuarantineRecord, ...]


class Ingestor:
    def __init__(
        self,
        raw_store: RawStore,
        parser_registry: ParserRegistry,
        *,
        envelope_schema_path: Path,
        max_line_bytes: int = 65_536,
        default_timezone: str = "UTC",
    ) -> None:
        self.raw_store = raw_store
        self.parser_registry = parser_registry
        self.max_line_bytes = max_line_bytes
        self.default_timezone = default_timezone
        self.envelope_schema = json.loads(envelope_schema_path.read_text(encoding="utf-8"))
        self.event_path = raw_store.root / "events.jsonl"
        self.quarantine_path = raw_store.root / "quarantine.jsonl"

    def ingest_file(
        self, path: Path, *, ingest_time: datetime | None = None
    ) -> IngestReport:
        resolved_path = path.resolve()
        source_id = hashlib.sha256(str(resolved_path).encode("utf-8")).hexdigest()[:16]
        source_file = str(path)
        timestamp = ingest_time or datetime.now(timezone.utc)
        if timestamp.tzinfo is None:
            raise ValueError("ingest_time must be timezone-aware")
        timestamp = timestamp.astimezone(timezone.utc)
        events: list[dict[str, Any]] = []
        quarantined: list[QuarantineRecord] = []
        records_seen = 0

        with path.open("rb") as source:
            byte_offset = 0
            line_no = 1
            while raw := source.readline(self.max_line_bytes + 1):
                record_offset = byte_offset
                byte_offset += len(raw)
                records_seen += 1
                if len(raw) > self.max_line_bytes:
                    refs = [
                        self.raw_store.append(
                            raw[index : index + self.max_line_bytes],
                            source_id=source_id,
                            source_file=source_file,
                            byte_offset=record_offset + index,
                            line_no=line_no,
                        )
                        for index in range(0, len(raw), self.max_line_bytes)
                    ]
                    while not raw.endswith(b"\n"):
                        raw = source.readline(self.max_line_bytes)
                        if not raw:
                            break
                        refs.append(
                            self.raw_store.append(
                                raw,
                                source_id=source_id,
                                source_file=source_file,
                                byte_offset=byte_offset,
                                line_no=line_no,
                            )
                        )
                        byte_offset += len(raw)
                    quarantine = QuarantineRecord(
                        "line_too_large",
                        f"record exceeds {self.max_line_bytes} bytes",
                        source_id,
                        source_file,
                        record_offset,
                        line_no,
                        tuple(refs),
                    )
                    quarantined.append(quarantine)
                    self._append_jsonl(self.quarantine_path, asdict(quarantine))
                    line_no += 1
                    continue

                ref = self.raw_store.append(
                    raw,
                    source_id=source_id,
                    source_file=source_file,
                    byte_offset=record_offset,
                    line_no=line_no,
                )
                try:
                    raw_text = raw.decode("utf-8")
                except UnicodeDecodeError as error:
                    quarantine = self._quarantine(
                        "invalid_utf8", str(error), ref, source_id, source_file
                    )
                    quarantined.append(quarantine)
                    line_no += 1
                    continue

                try:
                    parsed = self.parser_registry.parse(raw_text)
                except (ValueError, TypeError) as error:
                    quarantine = self._quarantine(
                        "parser_error", str(error), ref, source_id, source_file
                    )
                    quarantined.append(quarantine)
                    line_no += 1
                    continue
                if parsed is None:
                    quarantine = self._quarantine(
                        "no_parser_match",
                        "no parser template matched the record",
                        ref,
                        source_id,
                        source_file,
                    )
                    quarantined.append(quarantine)
                    line_no += 1
                    continue

                try:
                    envelope = self._make_envelope(
                        parsed,
                        raw_text,
                        ref,
                        source_id,
                        source_file,
                        timestamp,
                    )
                    validate(
                        instance=envelope,
                        schema=self.envelope_schema,
                        format_checker=FormatChecker(),
                    )
                    Envelope.model_validate(envelope)
                except (ValueError, TypeError, KeyError, OverflowError) as error:
                    quarantine = self._quarantine(
                        "invalid_envelope", str(error), ref, source_id, source_file
                    )
                    quarantined.append(quarantine)
                    line_no += 1
                    continue

                events.append(envelope)
                self._append_jsonl(self.event_path, envelope)
                line_no += 1

        return IngestReport(source_id, records_seen, tuple(events), tuple(quarantined))

    def _make_envelope(
        self,
        parsed: ParsedLine,
        raw: str,
        ref: RawRecordRef,
        source_id: str,
        source_file: str,
        ingest_time: datetime,
    ) -> dict[str, Any]:
        event = parsed.fields.get("event", {})
        if not isinstance(event, dict):
            raise ValueError("mapped event fields must be an object")
        class_uid = CLASS_UIDS.get(parsed.event_class)
        if class_uid is None:
            raise ValueError(f"unknown OCSF event class: {parsed.event_class}")
        event["class_uid"] = class_uid
        event["activity_id"] = 0
        event["class_name"] = parsed.event_class
        action = event.get("action", parsed.activity)
        event["action"] = action.casefold() if isinstance(action, str) else parsed.activity
        event_time, tz_assumed, time_source = self._event_time(parsed, ingest_time)
        event["time"] = event_time.isoformat(timespec="seconds").replace("+00:00", "Z")
        if time_source != "event":
            event["time_source"] = time_source
        event_id = hashlib.sha256(
            f"{source_id}:{ref.byte_offset}:{ref.sha256}".encode("utf-8")
        ).hexdigest()
        return {
            "event_id": event_id,
            "ingest_time": ingest_time.isoformat(timespec="seconds").replace("+00:00", "Z"),
            "source": {
                "id": source_id,
                "file": source_file,
                "byte_offset": ref.byte_offset,
                "line_no": ref.line_no,
            },
            "raw": raw,
            "raw_sha256": ref.sha256,
            "parser": {
                "name": parsed.parser_name,
                "version": parsed.parser_version,
                "confidence": parsed.confidence,
            },
            "event": event,
            "unmapped": parsed.unmapped,
            "flags": {
                "duplicate_of": None,
                "duplicate_count": 0,
                "tz_assumed": tz_assumed,
                "masked": True,
            },
        }

    def _event_time(self, parsed: ParsedLine, ingest_time: datetime) -> tuple[datetime, bool, str]:
        unmapped = parsed.unmapped
        raw_time = unmapped.get("time")
        if isinstance(raw_time, str):
            try:
                parsed_time = datetime.fromisoformat(raw_time.replace("Z", "+00:00"))
            except ValueError:
                parsed_time = None
            if parsed_time is not None:
                if parsed_time.tzinfo is None:
                    return (
                        parsed_time.replace(tzinfo=ZoneInfo(self.default_timezone)),
                        True,
                        "event",
                    )
                return parsed_time.astimezone(timezone.utc), False, "event"

        date_value = unmapped.get("date")
        clock_value = unmapped.get("time")
        if isinstance(date_value, str) and isinstance(clock_value, str):
            parsed_time = datetime.strptime(f"{date_value} {clock_value}", "%Y-%m-%d %H:%M:%S")
            return parsed_time.replace(tzinfo=ZoneInfo(self.default_timezone)), True, "event"

        syslog_time = unmapped.get("ts")
        if isinstance(syslog_time, str):
            parsed_time = datetime.strptime(syslog_time, "%b %d %H:%M:%S")
            parsed_time = parsed_time.replace(year=ingest_time.year)
            return parsed_time.replace(tzinfo=ZoneInfo(self.default_timezone)), True, "event"

        return ingest_time, True, "ingest_fallback"

    def _quarantine(
        self,
        reason_code: str,
        detail: str,
        ref: RawRecordRef,
        source_id: str,
        source_file: str,
    ) -> QuarantineRecord:
        record = QuarantineRecord(
            reason_code,
            detail,
            source_id,
            source_file,
            ref.byte_offset,
            ref.line_no,
            (ref,),
        )
        self._append_jsonl(self.quarantine_path, asdict(record))
        return record

    @staticmethod
    def _append_jsonl(path: Path, value: object) -> None:
        with path.open("a", encoding="utf-8", newline="\n") as output:
            output.write(json.dumps(value, sort_keys=True, separators=(",", ":"), default=asdict))
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())