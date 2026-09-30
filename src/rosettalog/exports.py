from __future__ import annotations

import base64
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Literal

from jsonschema import FormatChecker, validate

ExportFormat = Literal["ndjson", "cef", "syslog"]


def export_events(
    event_file: Path,
    output_file: Path,
    envelope_schema_path: Path,
    export_format: ExportFormat,
) -> int:
    if event_file.stat().st_size > 1024 * 1024 * 1024:
        raise ValueError("event ledger exceeds 1 GiB")
    schema = json.loads(envelope_schema_path.read_text(encoding="utf-8"))
    output_file.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: str | None = None
    exported = 0
    try:
        with event_file.open("r", encoding="utf-8") as source:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                newline="\n",
                dir=output_file.parent,
                suffix=".tmp",
                delete=False,
            ) as target:
                temporary_path = target.name
                for line_no, line in enumerate(source, start=1):
                    if len(line.encode("utf-8")) > 1_048_576:
                        raise ValueError(f"event ledger line {line_no} exceeds 1 MiB")
                    if not line.strip():
                        continue
                    try:
                        envelope = json.loads(line)
                    except json.JSONDecodeError as error:
                        raise ValueError(f"invalid event ledger JSON on line {line_no}") from error
                    if not isinstance(envelope, dict):
                        raise ValueError(f"event ledger line {line_no} must be an object")
                    validate(
                        instance=envelope,
                        schema=schema,
                        format_checker=FormatChecker(),
                    )
                    target.write(_format_event(envelope, export_format))
                    target.write("\n")
                    exported += 1
                target.flush()
                os.fsync(target.fileno())
        Path(temporary_path).replace(output_file)
    finally:
        if temporary_path is not None:
            Path(temporary_path).unlink(missing_ok=True)
    return exported


def _format_event(envelope: dict[str, Any], export_format: ExportFormat) -> str:
    if export_format == "ndjson":
        return json.dumps(envelope, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    canonical_envelope = json.dumps(
        envelope, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    encoded_envelope = base64.b64encode(canonical_envelope).decode("ascii")
    event = envelope["event"]
    if export_format == "syslog":
        timestamp = event.get("time") or envelope["ingest_time"]
        message = json.dumps(
            {
                "event_id": envelope["event_id"],
                "raw_sha256": envelope["raw_sha256"],
                "envelope_base64": encoded_envelope,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return f"<134>1 {timestamp} rosettalog rosettalog - - {message}"

    source = event.get("src_endpoint", {})
    destination = event.get("dst_endpoint", {})
    source = source if isinstance(source, dict) else {}
    destination = destination if isinstance(destination, dict) else {}
    signature_id = str(event.get("class_uid") or 0)
    name = str(event.get("class_name") or "Event")
    severity = _cef_severity(event.get("severity"))
    header = "|".join(
        _cef_header(value)
        for value in ("CEF:0", "RosettaLog", "Event", "1.0", signature_id, name, severity)
    )
    extension_fields = [
        ("externalId", envelope["event_id"]),
        ("rt", event.get("time", "")),
        ("act", event.get("action", "")),
        ("src", source.get("ip", "")),
        ("dst", destination.get("ip", "")),
        ("cs1Label", "RosettaLogEnvelopeBase64"),
        ("cs1", encoded_envelope),
    ]
    if source.get("port") is not None:
        extension_fields.append(("spt", source["port"]))
    if destination.get("port") is not None:
        extension_fields.append(("dpt", destination["port"]))
    extension = " ".join(
        f"{key}={_cef_extension(value)}" for key, value in extension_fields if value != ""
    )
    return f"{header}|{extension}"


def _cef_header(value: object) -> str:
    return str(value).replace("\\", "\\\\").replace("|", "\\|").replace("\r", " ").replace(
        "\n", " "
    )


def _cef_extension(value: object) -> str:
    text = str(value)
    return (
        text.replace("\\", "\\\\")
        .replace("=", "\\=")
        .replace("\r", "\\r")
        .replace("\n", "\\n")
    )


def _cef_severity(value: object) -> str:
    if isinstance(value, int) and not isinstance(value, bool):
        return str(min(max(value, 0), 10))
    if isinstance(value, str):
        severity = value.casefold()
        if severity in {"critical", "fatal", "emergency"}:
            return "10"
        if severity in {"high", "error"}:
            return "8"
        if severity in {"medium", "warning"}:
            return "5"
        if severity in {"low", "informational", "info"}:
            return "2"
    return "5"
