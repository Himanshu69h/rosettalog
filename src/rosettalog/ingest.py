from __future__ import annotations

import hashlib
import ipaddress
import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TextIO
from zoneinfo import ZoneInfo

from jsonschema import FormatChecker
from jsonschema.validators import validator_for

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
        mask_ips: bool = False,
        ipv4_prefix_length: int = 24,
        ipv6_prefix_length: int = 64,
        hash_usernames: bool = False,
        username_hash_salt: str = "",
        sync_event_ledger: bool = True,
    ) -> None:
        if not 0 <= ipv4_prefix_length <= 32:
            raise ValueError("ipv4_prefix_length must be between 0 and 32")
        if not 0 <= ipv6_prefix_length <= 128:
            raise ValueError("ipv6_prefix_length must be between 0 and 128")
        if hash_usernames and not username_hash_salt:
            raise ValueError("username_hash_salt is required when username hashing is enabled")
        self.raw_store = raw_store
        self.parser_registry = parser_registry
        self.max_line_bytes = max_line_bytes
        self.default_timezone = default_timezone
        self.mask_ips = mask_ips
        self.ipv4_prefix_length = ipv4_prefix_length
        self.ipv6_prefix_length = ipv6_prefix_length
        self.hash_usernames = hash_usernames
        self.username_hash_salt = username_hash_salt
        self.sync_event_ledger = sync_event_ledger
        self.envelope_schema = json.loads(envelope_schema_path.read_text(encoding="utf-8"))
        validator_type = validator_for(self.envelope_schema)
        validator_type.check_schema(self.envelope_schema)
        self.envelope_validator = validator_type(
            self.envelope_schema,
            format_checker=FormatChecker(),
        )
        self.event_path = raw_store.root / "events.jsonl"
        self.quarantine_path = raw_store.root / "quarantine.jsonl"
        self._event_streams: dict[Path, TextIO] = {}

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
        seen_events: dict[str, tuple[str, int]] = {}
        csv_headers: list[str] | None = None
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
                    if parsed is None and csv_headers is not None:
                        parsed = self.parser_registry.parse_csv(raw_text, csv_headers)
                    elif parsed is None and line_no == 1:
                        csv_headers = self.parser_registry.detect_csv_header(raw_text)
                        if csv_headers is not None:
                            line_no += 1
                            continue
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
                    masked = self._mask_normalized(envelope)
                    envelope["flags"]["masked"] = masked
                    duplicate_key = json.dumps(
                        envelope["event"], sort_keys=True, separators=(",", ":")
                    )
                    previous = seen_events.get(duplicate_key)
                    if previous is None:
                        duplicate_count = 0
                    else:
                        first_event_id, duplicate_count = previous
                        duplicate_count += 1
                        envelope["flags"]["duplicate_of"] = first_event_id
                        envelope["flags"]["duplicate_count"] = duplicate_count
                    self.envelope_validator.validate(envelope)
                    Envelope.model_validate(envelope)
                    if previous is None:
                        seen_events[duplicate_key] = (envelope["event_id"], 0)
                    else:
                        seen_events[duplicate_key] = (previous[0], duplicate_count)
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

        if not self.sync_event_ledger:
            self.sync_event_ledgers()
        return IngestReport(source_id, records_seen, tuple(events), tuple(quarantined))

    def sync_event_ledgers(self) -> None:
        for output in self._event_streams.values():
            output.flush()
            os.fsync(output.fileno())
            output.close()
        self._event_streams.clear()

    def _mask_normalized(self, envelope: dict[str, Any]) -> bool:
        masked = False

        def transform(value: object, key: str = "") -> object:
            nonlocal masked
            if isinstance(value, dict):
                return {
                    item_key: transform(item, item_key.casefold())
                    for item_key, item in value.items()
                }
            if isinstance(value, list):
                return [transform(item, key) for item in value]
            if not isinstance(value, str):
                return value
            if self.mask_ips and (key.endswith("ip") or key.endswith("_ip")):
                try:
                    address = ipaddress.ip_address(value)
                except ValueError:
                    return value
                prefix = (
                    self.ipv4_prefix_length if address.version == 4 else self.ipv6_prefix_length
                )
                masked_value = str(
                    ipaddress.ip_network(f"{address}/{prefix}", strict=False).network_address
                )
                masked = masked or masked_value != value
                return masked_value
            username_field = key in {"user", "username", "user_name", "src_user", "dst_user"}
            if self.hash_usernames and username_field:
                digest = hashlib.sha256(
                    f"{self.username_hash_salt}:{value}".encode("utf-8")
                ).hexdigest()
                masked = True
                return f"sha256:{digest}"
            return value

        envelope["event"] = transform(envelope["event"])
        envelope["unmapped"] = transform(envelope["unmapped"])
        return masked

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
                "masked": False,
            },
        }

    def _event_time(self, parsed: ParsedLine, ingest_time: datetime) -> tuple[datetime, bool, str]:
        unmapped = parsed.unmapped
        date_value = unmapped.get("date")
        raw_time = unmapped.get("time")
        if isinstance(raw_time, str):
            try:
                parsed_time = datetime.fromisoformat(raw_time.replace("Z", "+00:00"))
            except ValueError:
                parsed_time = None
            if parsed_time is not None:
                return self._normalize_event_time(parsed_time)

        clock_value = unmapped.get("time")
        if isinstance(date_value, str) and isinstance(clock_value, str):
            try:
                parsed_time = datetime.strptime(
                    f"{date_value} {clock_value}", "%Y-%m-%d %H:%M:%S"
                )
            except ValueError:
                parsed_time = None
            if parsed_time is not None:
                return self._normalize_event_time(parsed_time)

        syslog_time = unmapped.get("ts")
        if isinstance(syslog_time, str):
            try:
                parsed_time = datetime.strptime(syslog_time, "%b %d %H:%M:%S")
                parsed_time = parsed_time.replace(year=ingest_time.year)
            except ValueError:
                parsed_time = None
            if parsed_time is not None:
                return self._normalize_event_time(parsed_time)

        mapped_event = parsed.fields.get("event", {})
        mapped_time = mapped_event.get("time") if isinstance(mapped_event, dict) else None
        if isinstance(mapped_time, str):
            try:
                parsed_time = datetime.fromisoformat(mapped_time.replace("Z", "+00:00"))
            except ValueError:
                parsed_time = None
            if parsed_time is not None:
                return self._normalize_event_time(parsed_time)
            if isinstance(date_value, str):
                try:
                    parsed_time = datetime.strptime(
                        f"{date_value} {mapped_time}", "%Y-%m-%d %H:%M:%S"
                    )
                except ValueError:
                    parsed_time = None
                if parsed_time is not None:
                    return self._normalize_event_time(parsed_time)
            try:
                parsed_clock = datetime.strptime(mapped_time, "%H:%M:%S")
            except ValueError:
                parsed_clock = None
            if parsed_clock is not None:
                try:
                    event_date = (
                        datetime.strptime(date_value, "%Y-%m-%d").date()
                        if isinstance(date_value, str)
                        else ingest_time.date()
                    )
                except ValueError:
                    event_date = ingest_time.date()
                combined = datetime.combine(event_date, parsed_clock.time())
                return self._normalize_event_time(combined)
            try:
                parsed_date = datetime.strptime(mapped_time, "%Y-%m-%d")
            except ValueError:
                parsed_date = None
            if parsed_date is not None:
                return self._normalize_event_time(parsed_date)

        return ingest_time, True, "ingest_fallback"

    def _normalize_event_time(
        self, event_time: datetime
    ) -> tuple[datetime, bool, str]:
        tz_assumed = event_time.tzinfo is None
        if tz_assumed:
            event_time = event_time.replace(tzinfo=ZoneInfo(self.default_timezone))
        return event_time.astimezone(timezone.utc), tz_assumed, "event"

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

    def _append_jsonl(self, path: Path, value: object) -> None:
        if self.sync_event_ledger:
            with path.open("a", encoding="utf-8", newline="\n") as durable_output:
                durable_output.write(
                    json.dumps(value, sort_keys=True, separators=(",", ":"), default=asdict)
                )
                durable_output.write("\n")
                durable_output.flush()
                os.fsync(durable_output.fileno())
            return

        output = self._event_streams.get(path)
        if output is None:
            output = path.open("a", encoding="utf-8", newline="\n")
            self._event_streams[path] = output
        output.write(json.dumps(value, sort_keys=True, separators=(",", ":"), default=asdict))
        output.write("\n")