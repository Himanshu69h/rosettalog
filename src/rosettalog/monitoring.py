from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from jsonschema import validate

from rosettalog.learning import ParserLearner, ReviewList, YamlEmitter
from rosettalog.parsing import ParserRegistry
from rosettalog.verification import transition_parser


@dataclass(frozen=True, slots=True)
class MonitorReport:
    source_file: str
    parser_name: str
    records_seen: int
    matched_records: int
    unmatched_records: int
    parser_error_records: int
    coverage: float
    mean_confidence: float
    drift: bool
    drift_reasons: tuple[str, ...]
    candidate_parser: str | None
    report_file: str

    def as_dict(self) -> dict[str, object]:
        return {
            "source_file": self.source_file,
            "parser_name": self.parser_name,
            "records_seen": self.records_seen,
            "matched_records": self.matched_records,
            "unmatched_records": self.unmatched_records,
            "parser_error_records": self.parser_error_records,
            "coverage": self.coverage,
            "mean_confidence": self.mean_confidence,
            "drift": self.drift,
            "drift_reasons": list(self.drift_reasons),
            "candidate_parser": self.candidate_parser,
            "report_file": self.report_file,
        }


def monitor_file(
    input_file: Path,
    parser_name: str,
    parser_dir: Path,
    parser_schema_path: Path,
    synonyms_path: Path,
    *,
    output_dir: Path = Path("monitor_reports"),
    draft_dir: Path = Path("draft_parsers"),
    review_list_path: Path = Path("review_queue.jsonl"),
    min_coverage: float = 0.9,
    min_mean_confidence: float = 0.5,
) -> MonitorReport:
    if not 0.0 <= min_coverage <= 1.0:
        raise ValueError("min_coverage must be between 0 and 1")
    if not 0.0 <= min_mean_confidence <= 1.0:
        raise ValueError("min_mean_confidence must be between 0 and 1")
    if input_file.stat().st_size > 50 * 1024 * 1024:
        raise ValueError("monitor input exceeds 50 MiB")
    raw_records = input_file.read_bytes().splitlines()
    if not raw_records:
        raise ValueError("monitor input contains no records")
    if len(raw_records) > 1_000_000:
        raise ValueError("monitor input exceeds 1000000 records")
    if any(len(raw) > 65_536 for raw in raw_records):
        raise ValueError("monitor input contains a record exceeding 64 KiB")
    try:
        records = [raw.decode("utf-8") for raw in raw_records]
    except UnicodeDecodeError as error:
        raise ValueError(f"monitor input is not valid UTF-8: {error}") from error

    schema = json.loads(parser_schema_path.read_text(encoding="utf-8"))
    parser_path, definition = _find_parser(parser_name, parser_dir, schema)
    if definition["state"] not in {"verified", "active"}:
        raise ValueError("monitoring requires a verified or active parser")
    registry = ParserRegistry(parser_dir, parser_schema_path)
    matched: list[str] = []
    confidence_sum = 0.0
    unmatched: list[str] = []
    parser_error_records = 0
    for record in records:
        try:
            parsed = registry.parse(record)
        except (ValueError, TypeError):
            parsed = None
            parser_error_records += 1
        if parsed is not None and parsed.parser_name == parser_name:
            matched.append(record)
            confidence_sum += parsed.confidence
        else:
            unmatched.append(record)
    coverage = len(matched) / len(records)
    mean_confidence = confidence_sum / len(matched) if matched else 0.0
    reasons: list[str] = []
    if coverage < min_coverage:
        reasons.append("coverage_below_threshold")
    if matched and mean_confidence < min_mean_confidence:
        reasons.append("mean_confidence_below_threshold")
    if parser_error_records:
        reasons.append("parser_errors_present")
    drift = bool(reasons)

    candidate_parser: str | None = None
    report_digest = hashlib.sha256(b"\n".join(raw_records)).hexdigest()[:16]
    safe_name = re.sub(r"[^A-Za-z0-9_-]", "_", parser_name)[:40] or "parser"
    if not safe_name[0].isalpha():
        safe_name = f"parser_{safe_name}"
    report_path = output_dir / f"{safe_name}-{report_digest}-monitor.json"
    train_records = [record for record in unmatched if record][:10_000] if drift else []
    if train_records:
        candidate_parser = f"{safe_name}_relearn_{report_digest[:8]}"
        learner = ParserLearner(
            synonyms_path,
            parser_schema_path,
            review_list=ReviewList(review_list_path),
        )
        learned = learner.learn(
            train_records,
            name=candidate_parser,
            source_format=definition["source_format"],
            created_from=str(input_file),
        )
        candidate_path = draft_dir / f"{candidate_parser}.yaml"
        if candidate_path.exists():
            existing = yaml.safe_load(candidate_path.read_text(encoding="utf-8"))
            if existing != learned.definition:
                raise FileExistsError(candidate_path)
        else:
            YamlEmitter(parser_schema_path).emit(learned.definition, candidate_path.parent)

    report = MonitorReport(
        source_file=str(input_file),
        parser_name=parser_name,
        records_seen=len(records),
        matched_records=len(matched),
        unmatched_records=len(unmatched),
        parser_error_records=parser_error_records,
        coverage=coverage,
        mean_confidence=mean_confidence,
        drift=drift,
        drift_reasons=tuple(reasons),
        candidate_parser=candidate_parser,
        report_file=str(report_path),
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report.as_dict(), sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    if drift and definition["state"] == "active":
        transition_parser(parser_path, "drifting", parser_schema_path)
    return report


def _find_parser(
    parser_name: str, parser_dir: Path, schema: dict[str, Any]
) -> tuple[Path, dict[str, Any]]:
    for path in sorted(parser_dir.glob("*.yaml")):
        definition = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(definition, dict):
            raise ValueError(f"parser definition must be a mapping: {path}")
        validate(instance=definition, schema=schema)
        if definition["name"] == parser_name:
            return path, definition
    raise ValueError(f"parser not found: {parser_name}")
