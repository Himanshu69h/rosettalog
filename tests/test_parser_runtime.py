from __future__ import annotations

from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from rosettalog.parsing import ParserRegistry

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def registry() -> ParserRegistry:
    return ParserRegistry(ROOT / "parsers", ROOT / "schemas" / "parser.schema.json")


@pytest.mark.parametrize(
    ("filename", "parser_name", "expected_action"),
    [
        ("asa.log", "asa_syslog", "Deny"),
        ("fortigate.log", "fortigate_kv", "deny"),
        ("cef.log", "cef_generic", "Deny"),
        ("json.log", "json_generic", "deny"),
    ],
)
def test_known_formats_parse_and_preserve_raw(
    registry: ParserRegistry, filename: str, parser_name: str, expected_action: str
) -> None:
    raw = (ROOT / "samples" / "known" / filename).read_text(encoding="utf-8").splitlines()[0]

    result = registry.parse(raw)

    assert result is not None
    assert result.parser_name == parser_name
    assert result.raw == raw
    assert result.fields["event"]["action"] == expected_action  # type: ignore[index]


def test_unmapped_captures_are_retained(registry: ParserRegistry) -> None:
    raw = (ROOT / "samples" / "known" / "asa.log").read_text(encoding="utf-8").splitlines()[0]

    result = registry.parse(raw)

    assert result is not None
    assert result.unmapped["host"] == "fw01"
    assert result.unmapped["proto"] == "tcp"
    assert result.unmapped["src_port"] == "443"


def test_parser_converts_fields_using_yaml_types(registry: ParserRegistry) -> None:
    raw = (ROOT / "samples" / "known" / "cef.log").read_text(encoding="utf-8").splitlines()[0]

    result = registry.parse(raw)

    assert result is not None
    assert result.fields["event"]["severity"] == "5"  # type: ignore[index]


def test_unknown_or_malformed_records_do_not_match(registry: ParserRegistry) -> None:
    assert registry.parse("not a supported log record") is None
    assert registry.parse('{"action":') is None


def test_json_non_object_is_not_accepted(registry: ParserRegistry) -> None:
    assert registry.parse('["not", "an", "event"]') is None


@settings(max_examples=50, deadline=None)
@given(st.text(max_size=2048))
def test_parser_handles_arbitrary_hostile_text(raw: str) -> None:
    registry = ParserRegistry(ROOT / "parsers", ROOT / "schemas" / "parser.schema.json")

    result = registry.parse(raw)

    assert result is None or result.raw == raw