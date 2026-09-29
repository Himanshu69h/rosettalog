from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import threading
from pathlib import Path
from typing import Any, cast

import duckdb
import pyarrow as pa
import pyarrow.parquet as parquet

_PARQUET_SCHEMA = pa.schema(
    [
        ("event_id", pa.string()),
        ("ingest_time", pa.string()),
        ("source_id", pa.string()),
        ("source_file", pa.string()),
        ("byte_offset", pa.int64()),
        ("line_no", pa.int64()),
        ("raw", pa.string()),
        ("raw_sha256", pa.string()),
        ("parser_name", pa.string()),
        ("parser_version", pa.int64()),
        ("parser_confidence", pa.float64()),
        ("event_time", pa.string()),
        ("class_uid", pa.int64()),
        ("class_name", pa.string()),
        ("activity_id", pa.int64()),
        ("action", pa.string()),
        ("src_ip", pa.string()),
        ("dst_ip", pa.string()),
        ("protocol", pa.string()),
        ("event_json", pa.string()),
        ("unmapped_json", pa.string()),
        ("flags_json", pa.string()),
    ]
)


class ParquetSink:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def write_events(self, events: list[dict[str, Any]]) -> Path | None:
        if not events:
            return None
        rows = [self._row(event) for event in events]
        canonical = json.dumps(rows, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        target = self.root / f"part-{digest}.parquet"
        with self._lock:
            if target.exists():
                return target
            table = pa.Table.from_pylist(rows, schema=_PARQUET_SCHEMA)
            temporary_path: str | None = None
            try:
                with tempfile.NamedTemporaryFile(
                    dir=self.root, suffix=".tmp", delete=False
                ) as temp:
                    temporary_path = temp.name
                parquet.write_table(table, temporary_path, compression="zstd")
                with open(temporary_path, "r+b") as written:
                    os.fsync(written.fileno())
                os.replace(temporary_path, target)
            finally:
                if temporary_path is not None and os.path.exists(temporary_path):
                    os.unlink(temporary_path)
        return target

    @staticmethod
    def _row(envelope: dict[str, Any]) -> dict[str, object]:
        event = envelope.get("event", {})
        source = envelope.get("source", {})
        parser = envelope.get("parser", {})
        if (
            not isinstance(event, dict)
            or not isinstance(source, dict)
            or not isinstance(parser, dict)
        ):
            raise ValueError("event envelope contains invalid nested fields")
        src_endpoint = event.get("src_endpoint", {})
        dst_endpoint = event.get("dst_endpoint", {})
        network = event.get("network", {})
        src_ip = src_endpoint.get("ip") if isinstance(src_endpoint, dict) else None
        dst_ip = dst_endpoint.get("ip") if isinstance(dst_endpoint, dict) else None
        protocol = network.get("protocol") if isinstance(network, dict) else None
        def encode(value: object) -> str:
            return json.dumps(value, sort_keys=True, separators=(",", ":"))

        return {
            "event_id": envelope["event_id"],
            "ingest_time": envelope["ingest_time"],
            "source_id": source["id"],
            "source_file": source["file"],
            "byte_offset": source["byte_offset"],
            "line_no": source["line_no"],
            "raw": envelope["raw"],
            "raw_sha256": envelope["raw_sha256"],
            "parser_name": parser["name"],
            "parser_version": parser["version"],
            "parser_confidence": parser["confidence"],
            "event_time": event.get("time"),
            "class_uid": event.get("class_uid"),
            "class_name": event.get("class_name"),
            "activity_id": event.get("activity_id"),
            "action": event.get("action"),
            "src_ip": src_ip,
            "dst_ip": dst_ip,
            "protocol": protocol,
            "event_json": encode(event),
            "unmapped_json": encode(envelope.get("unmapped", {})),
            "flags_json": encode(envelope.get("flags", {})),
        }


def query_events(parquet_root: Path, sql: str) -> list[dict[str, Any]]:
    if not re.match(r"\s*select\b", sql, flags=re.IGNORECASE) or ";" in sql:
        raise ValueError(
            "query must be one read-only SELECT statement without a trailing semicolon"
        )
    files = sorted(parquet_root.glob("part-*.parquet"))
    if not files:
        return []
    table = parquet.read_table([str(path) for path in files])
    connection = duckdb.connect(
        database=":memory:", config={"enable_external_access": "false"}
    )
    try:
        connection.register("events", table)
        result = connection.execute(sql).to_arrow_table()
        return cast(list[dict[str, Any]], result.to_pylist())
    finally:
        connection.close()