from __future__ import annotations

import json
from dataclasses import dataclass
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
    def __init__(self, parser_dir: Path, schema_path: Path) -> None:
        self._definitions: list[dict[str, Any]] = []
        self._patterns: list[list[Any]] = []
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        for path in sorted(parser_dir.glob("*.yaml")):
            definition = yaml.safe_load(path.read_text(encoding="utf-8"))
            if not isinstance(definition, dict):
                raise ValueError(f"Parser definition must be a mapping: {path}")
            validate(instance=definition, schema=schema)
            patterns = [compile_pattern(template["regex"]) for template in definition["templates"]]
            self._definitions.append(definition)
            self._patterns.append(patterns)

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