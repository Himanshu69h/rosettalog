from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import datetime
from ipaddress import IPv4Address
from pathlib import Path
from typing import Any

import yaml
from jsonschema import validate

from rosettalog.regex import compile_pattern


@dataclass(frozen=True, slots=True)
class ParsedLine:
    parser_name: str
    parser_version: int
    template_id: str
    confidence: float
    raw: str
    fields: dict[str, object]
    unmapped: dict[str, object]
    event_class: str
    activity: str


class ParserRegistry:
    _CSV_FIELDS: dict[str, tuple[str, str]] = {
        "time": ("event.time", "timestamp"),
        "timestamp": ("event.time", "timestamp"),
        "event_time": ("event.time", "timestamp"),
        "datetime": ("event.time", "timestamp"),
        "src": ("event.src_endpoint.ip", "ipv4"),
        "srcip": ("event.src_endpoint.ip", "ipv4"),
        "src_ip": ("event.src_endpoint.ip", "ipv4"),
        "source_ip": ("event.src_endpoint.ip", "ipv4"),
        "source_address": ("event.src_endpoint.ip", "ipv4"),
        "dst": ("event.dst_endpoint.ip", "ipv4"),
        "dstip": ("event.dst_endpoint.ip", "ipv4"),
        "dst_ip": ("event.dst_endpoint.ip", "ipv4"),
        "destination_ip": ("event.dst_endpoint.ip", "ipv4"),
        "destination_address": ("event.dst_endpoint.ip", "ipv4"),
        "sport": ("event.src_endpoint.port", "int"),
        "srcport": ("event.src_endpoint.port", "int"),
        "src_port": ("event.src_endpoint.port", "int"),
        "dport": ("event.dst_endpoint.port", "int"),
        "dstport": ("event.dst_endpoint.port", "int"),
        "dst_port": ("event.dst_endpoint.port", "int"),
        "proto": ("event.protocol_name", "free_text"),
        "protocol": ("event.protocol_name", "free_text"),
        "protocol_name": ("event.protocol_name", "free_text"),
        "action": ("event.action", "free_text"),
        "result": ("event.action", "free_text"),
        "msg": ("event.message", "free_text"),
        "message": ("event.message", "free_text"),
        "description": ("event.message", "free_text"),
        "severity": ("event.severity", "free_text"),
        "username": ("event.user_name", "free_text"),
        "user": ("event.user_name", "free_text"),
        "user_name": ("event.user_name", "free_text"),
    }

    def __init__(self, parser_dir: Path, schema_path: Path) -> None:
        self._definitions: list[dict[str, Any]] = []
        self._patterns: list[list[Any]] = []
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        for path in sorted(parser_dir.glob("*.yaml")):
            definition = yaml.safe_load(path.read_text(encoding="utf-8"))
            if not isinstance(definition, dict):
                raise ValueError(f"Parser definition must be a mapping: {path}")
            validate(instance=definition, schema=schema)
            if definition["state"] not in {"verified", "active"}:
                continue
            patterns = [compile_pattern(template["regex"]) for template in definition["templates"]]
            self._definitions.append(definition)
            self._patterns.append(patterns)

    @property
    def parser_count(self) -> int:
        return len(self._definitions)

    def parse(self, raw: str) -> ParsedLine | None:
        record = raw.rstrip("\r\n")
        for definition, patterns in zip(self._definitions, self._patterns, strict=True):
            source_format = definition["source_format"]
            values: dict[str, object]
            if source_format == "json":
                try:
                    parsed_json = json.loads(record)
                except json.JSONDecodeError:
                    continue
                if not isinstance(parsed_json, dict):
                    continue
                values = parsed_json
            else:
                values = {}

            for template, pattern in zip(definition["templates"], patterns, strict=True):
                match = pattern.search(record)
                if source_format == "json":
                    if match is None:
                        continue
                elif match is None:
                    continue
                else:
                    values = {
                        key: value for key, value in match.groupdict().items() if value is not None
                    }

                mapped: dict[str, object] = {}
                mapped_names: set[str] = set()
                confidence = 1.0
                for field in template["fields"]:
                    field_name = field["name"]
                    if field_name not in values:
                        continue
                    value = self._convert_value(field["type"], values[field_name])
                    self._set_path(mapped, field["ocsf_path"], value)
                    mapped_names.add(field_name)
                    confidence = min(confidence, float(field["confidence"]))

                unmapped = {
                    key: value
                    for key, value in values.items()
                    if key not in mapped_names and isinstance(key, str)
                }
                return ParsedLine(
                    parser_name=definition["name"],
                    parser_version=definition["version"],
                    template_id=template["id"],
                    confidence=confidence,
                    raw=raw,
                    fields=mapped,
                    unmapped=unmapped,
                    event_class=template["event_class"],
                    activity=template["activity"],
                )
        return None

    @classmethod
    def detect_csv_header(cls, raw: str) -> list[str] | None:
        try:
            headers = next(csv.reader([raw], strict=True))
        except (csv.Error, StopIteration):
            return None
        normalized = [
            header.strip().casefold().replace("-", "_").replace(" ", "_")
            for header in headers
        ]
        if len(normalized) < 2 or any(not header for header in normalized):
            return None
        if len(set(normalized)) != len(normalized):
            return None
        if sum(header in cls._CSV_FIELDS for header in normalized) < 2:
            return None
        return normalized

    @classmethod
    def parse_csv(cls, raw: str, headers: list[str]) -> ParsedLine | None:
        try:
            values = next(csv.reader([raw], strict=True))
        except (csv.Error, StopIteration):
            return None
        if len(values) != len(headers):
            return None

        event: dict[str, object] = {}
        unmapped: dict[str, object] = {}
        confidence = 0.9
        for name, value in zip(headers, values, strict=True):
            field = cls._CSV_FIELDS.get(name)
            if field is None:
                unmapped[name] = value
                continue
            path, field_type = field
            if value:
                converted = cls._convert_value(field_type, value)
                cls._set_path(event, path.removeprefix("event."), converted)
            confidence = min(confidence, 0.9)

        return ParsedLine(
            parser_name="csv_header",
            parser_version=1,
            template_id="csv_header",
            confidence=confidence,
            raw=raw,
            fields={"event": event},
            unmapped=unmapped,
            event_class="Network Activity",
            activity="record",
        )

    @staticmethod
    def _convert_value(field_type: str, value: object) -> object:
        if field_type == "ipv4":
            if not isinstance(value, str):
                raise ValueError("IPv4 fields must be strings")
            return str(IPv4Address(value))
        if field_type == "int":
            if isinstance(value, bool) or not isinstance(value, (int, str)):
                raise ValueError("integer fields must be strings or integers")
            return int(value)
        if field_type == "timestamp":
            if not isinstance(value, str):
                raise ValueError("timestamp fields must be strings")
            try:
                datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                try:
                    datetime.strptime(value, "%H:%M:%S")
                except ValueError as error:
                    raise ValueError(f"invalid timestamp value: {value}") from error
            return value
        if field_type in {"enum", "free_text"}:
            if not isinstance(value, str):
                raise ValueError(f"{field_type} fields must be strings")
            return value
        raise ValueError(f"unsupported parser field type: {field_type}")

    @staticmethod
    def _set_path(target: dict[str, object], path: str, value: object) -> None:
        parts = path.split(".")
        current = target
        for part in parts[:-1]:
            child = current.get(part)
            if not isinstance(child, dict):
                child = {}
                current[part] = child
            current = child
        current[parts[-1]] = value