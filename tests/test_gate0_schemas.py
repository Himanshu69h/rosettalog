from __future__ import annotations

import json
import socket
from pathlib import Path

import pytest
import yaml
from jsonschema import validate

ROOT = Path(__file__).resolve().parents[1]
SCHEMAS_DIR = ROOT / "schemas"


def _load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_envelope_schema_validates_minimal_event() -> None:
    schema = _load_json(SCHEMAS_DIR / "envelope.schema.json")
    event = {
        "event_id": "01J9KQ31KBZFH5K8D7V7JYV6N6",
        "ingest_time": "2026-09-29T08:15:00Z",
        "source": {
            "id": "fw01",
            "file": "fw01.log",
            "byte_offset": 42,
            "line_no": 7,
        },
        "raw": "Sep 29 08:15:00 fw01 %ASA-4-106023: Deny tcp src 10.0.0.5/443 dst 203.0.113.4/443",
        "raw_sha256": "".join("ab" for _ in range(32)),
        "parser": {"name": "asa_syslog", "version": 1, "confidence": 0.97},
        "event": {
            "time": "2026-09-29T08:15:00Z",
            "class_name": "Network Activity",
            "action": "deny",
            "src_endpoint": {"ip": "10.0.0.5", "port": 443},
            "dst_endpoint": {"ip": "203.0.113.4", "port": 443},
        },
        "unmapped": {"vendor_field": "OUTSIDE_IN"},
        "flags": {"duplicate_of": None, "duplicate_count": 0, "tz_assumed": False, "masked": True},
    }
    validate(instance=event, schema=schema)


def test_parser_schema_validates_yaml() -> None:
    schema = _load_json(SCHEMAS_DIR / "parser.schema.json")
    parser_doc = yaml.safe_load((ROOT / "parsers" / "asa_syslog.yaml").read_text(encoding="utf-8"))
    validate(instance=parser_doc, schema=schema)


def test_ocsf_subset_definition_is_present() -> None:
    subset = _load_json(SCHEMAS_DIR / "ocsf_subset.json")
    assert subset["classes"]
    assert "Network Activity" in subset["classes"]
    assert "Authentication" in subset["classes"]
    assert "Detection Finding" in subset["classes"]


def test_no_socket_connect_attempts(monkeypatch: pytest.MonkeyPatch) -> None:
    called = {"value": False}

    def _fail(*args: object, **kwargs: object) -> None:
        called["value"] = True
        raise AssertionError("A socket connection was attempted unexpectedly.")

    monkeypatch.setattr(socket.socket, "connect", _fail)
    assert called["value"] is False
