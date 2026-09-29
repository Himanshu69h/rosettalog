from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pytest

from rosettalog.analytics import ParquetSink, query_events
from rosettalog.ingest import Ingestor
from rosettalog.parsing import ParserRegistry
from rosettalog.rawstore import RawStore

ROOT = Path(__file__).resolve().parents[1]


def test_parquet_sink_and_duckdb_read_only_query(tmp_path: Path) -> None:
    raw_store = RawStore(tmp_path / "raw")
    registry = ParserRegistry(ROOT / "parsers", ROOT / "schemas" / "parser.schema.json")
    ingestor = Ingestor(
        raw_store,
        registry,
        envelope_schema_path=ROOT / "schemas" / "envelope.schema.json",
    )
    report = ingestor.ingest_file(
        ROOT / "samples" / "known" / "json.log",
        ingest_time=datetime(2026, 9, 29, 12, tzinfo=timezone.utc),
    )
    sink = ParquetSink(tmp_path / "parquet")

    first_path = sink.write_events(list(report.events))
    second_path = sink.write_events(list(report.events))
    result = query_events(tmp_path / "parquet", "SELECT event_id, action FROM events")

    assert first_path == second_path
    assert len(list((tmp_path / "parquet").glob("part-*.parquet"))) == 1
    assert result[0]["event_id"] == report.events[0]["event_id"]
    assert result[0]["action"] == "deny"


@pytest.mark.parametrize("sql", ["DELETE FROM events", "SELECT 1; SELECT 2"])
def test_query_rejects_mutating_or_multiple_statements(tmp_path: Path, sql: str) -> None:
    with pytest.raises(ValueError):
        query_events(tmp_path, sql)


def test_query_disables_external_file_access(tmp_path: Path) -> None:
    raw_store = RawStore(tmp_path / "raw")
    registry = ParserRegistry(ROOT / "parsers", ROOT / "schemas" / "parser.schema.json")
    ingestor = Ingestor(
        raw_store,
        registry,
        envelope_schema_path=ROOT / "schemas" / "envelope.schema.json",
    )
    report = ingestor.ingest_file(
        ROOT / "samples" / "known" / "json.log",
        ingest_time=datetime(2026, 9, 29, 12, tzinfo=timezone.utc),
    )
    ParquetSink(tmp_path / "parquet").write_events(list(report.events))

    with pytest.raises(duckdb.Error):
        query_events(tmp_path / "parquet", "SELECT * FROM read_csv_auto('secrets.csv')")