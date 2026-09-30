from __future__ import annotations

import html
import json
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import re2  # type: ignore[import-untyped]
import yaml
from jsonschema import validate

from rosettalog.parsing import ParserRegistry

_STATE_TRANSITIONS = {
    "draft": {"verified"},
    "verified": {"active"},
    "active": {"drifting"},
    "drifting": {"active", "superseded"},
    "superseded": set(),
}


@dataclass(frozen=True, slots=True)
class VerificationCase:
    raw: str
    expected_template_id: str | None
    required_fields: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class VerificationReport:
    parser_name: str
    parser_version: int
    cases_checked: int
    positive_cases: int
    covered_cases: int
    coverage: float
    overmerged_cases: int
    missing_required_fields: int
    ambiguous_cases: int
    roundtrip_failures: int
    regex_safe: bool
    errors: tuple[str, ...]
    case_results: tuple[dict[str, object], ...]

    @property
    def valid(self) -> bool:
        return (
            self.regex_safe
            and self.covered_cases == self.positive_cases
            and self.overmerged_cases == 0
            and self.missing_required_fields == 0
            and self.ambiguous_cases == 0
            and self.roundtrip_failures == 0
            and not self.errors
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "parser_name": self.parser_name,
            "parser_version": self.parser_version,
            "valid": self.valid,
            "cases_checked": self.cases_checked,
            "positive_cases": self.positive_cases,
            "covered_cases": self.covered_cases,
            "coverage": self.coverage,
            "overmerged_cases": self.overmerged_cases,
            "missing_required_fields": self.missing_required_fields,
            "ambiguous_cases": self.ambiguous_cases,
            "roundtrip_failures": self.roundtrip_failures,
            "regex_safe": self.regex_safe,
            "errors": list(self.errors),
            "case_results": list(self.case_results),
        }


class ParserVerifier:
    def __init__(self, parser_schema_path: Path) -> None:
        self.schema_path = parser_schema_path
        self.schema = json.loads(parser_schema_path.read_text(encoding="utf-8"))

    def verify(self, parser_path: Path, cases_path: Path) -> VerificationReport:
        definition = yaml.safe_load(parser_path.read_text(encoding="utf-8"))
        if not isinstance(definition, dict):
            raise ValueError("parser definition must be a YAML mapping")
        validate(instance=definition, schema=self.schema)
        if definition["state"] != "draft":
            raise ValueError("only draft parsers can be verified")

        cases = self._read_cases(cases_path, definition["templates"])
        compiled: list[tuple[dict[str, Any], Any]] = []
        regex_errors: list[str] = []
        for template in definition["templates"]:
            try:
                compiled.append((template, re2.compile(template["regex"])))
            except (re2.error, TypeError) as error:
                regex_errors.append(f"{template['id']}: {error}")

        if regex_errors:
            return VerificationReport(
                parser_name=definition["name"],
                parser_version=definition["version"],
                cases_checked=len(cases),
                positive_cases=sum(case.expected_template_id is not None for case in cases),
                covered_cases=0,
                coverage=0.0,
                overmerged_cases=0,
                missing_required_fields=0,
                ambiguous_cases=0,
                roundtrip_failures=0,
                regex_safe=False,
                errors=tuple(regex_errors),
                case_results=(),
            )

        verified_definition = dict(definition)
        verified_definition["state"] = "verified"
        with tempfile.TemporaryDirectory(prefix="rosettalog-verify-") as temporary_dir:
            candidate_path = Path(temporary_dir) / parser_path.name
            candidate_path.write_text(
                yaml.safe_dump(verified_definition, sort_keys=False), encoding="utf-8"
            )
            registry = ParserRegistry(Path(temporary_dir), self.schema_path)
            case_results: list[dict[str, object]] = []
            covered_cases = 0
            overmerged_cases = 0
            missing_required_fields = 0
            ambiguous_cases = 0
            roundtrip_failures = 0
            case_errors: list[str] = []
            for line_no, case in enumerate(cases, start=1):
                text = case.raw.rstrip("\r\n")
                match_count = sum(pattern.search(text) is not None for _, pattern in compiled)
                parse_error: str | None = None
                try:
                    parsed = registry.parse(case.raw)
                except ValueError as error:
                    parsed = None
                    parse_error = str(error)
                    case_errors.append(f"case line {line_no}: {error}")
                actual_template = parsed.template_id if parsed is not None else None
                if case.expected_template_id is not None and (
                    actual_template == case.expected_template_id
                ):
                    covered_cases += 1
                if (
                    actual_template is not None
                    and actual_template != case.expected_template_id
                ):
                    overmerged_cases += 1
                if match_count > 1:
                    ambiguous_cases += 1
                if parsed is not None and parsed.raw != case.raw:
                    roundtrip_failures += 1
                missing = [
                    field_name
                    for field_name in case.required_fields
                    if parsed is None
                    or not self._has_field(
                        parsed.fields,
                        self._field_path(definition["templates"], actual_template, field_name),
                    )
                ]
                missing_required_fields += len(missing)
                case_results.append(
                    {
                        "line": line_no,
                        "expected_template_id": case.expected_template_id,
                        "actual_template_id": actual_template,
                        "regex_matches": match_count,
                        "missing_required_fields": missing,
                        "roundtrip_ok": parsed.raw == case.raw if parsed is not None else None,
                        "error": parse_error,
                    }
                )

        positive_cases = sum(case.expected_template_id is not None for case in cases)
        coverage = covered_cases / positive_cases if positive_cases else 0.0
        return VerificationReport(
            parser_name=definition["name"],
            parser_version=definition["version"],
            cases_checked=len(cases),
            positive_cases=positive_cases,
            covered_cases=covered_cases,
            coverage=coverage,
            overmerged_cases=overmerged_cases,
            missing_required_fields=missing_required_fields,
            ambiguous_cases=ambiguous_cases,
            roundtrip_failures=roundtrip_failures,
            regex_safe=True,
            errors=tuple(case_errors),
            case_results=tuple(case_results),
        )

    @staticmethod
    def write_reports(report: VerificationReport, output_dir: Path) -> tuple[Path, Path]:
        output_dir.mkdir(parents=True, exist_ok=True)
        safe_name = re.sub(r"[^A-Za-z0-9_-]", "_", report.parser_name)[:64]
        stem = f"{safe_name}-v{report.parser_version}-verification"
        json_path = output_dir / f"{stem}.json"
        html_path = output_dir / f"{stem}.html"
        payload = json.dumps(report.as_dict(), indent=2, sort_keys=True)
        title = html.escape(f"Verification: {report.parser_name} v{report.parser_version}")
        html_body = (
            "<!doctype html><html><head><meta charset=\"utf-8\">"
            f"<title>{title}</title></head><body><h1>{title}</h1>"
            f"<pre>{html.escape(payload)}</pre></body></html>"
        )
        ParserVerifier._write_atomic(json_path, payload + "\n")
        ParserVerifier._write_atomic(html_path, html_body + "\n")
        return json_path, html_path

    @staticmethod
    def _read_cases(path: Path, templates: list[dict[str, Any]]) -> list[VerificationCase]:
        if path.stat().st_size > 50 * 1024 * 1024:
            raise ValueError("verification cases file exceeds 50 MiB")
        template_fields = {
            template["id"]: {field["name"] for field in template["fields"]}
            for template in templates
        }
        cases: list[VerificationCase] = []
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            if len(line.encode("utf-8")) > 131_072:
                raise ValueError(f"case line {line_no} exceeds 128 KiB")
            try:
                item = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(f"invalid case JSON on line {line_no}: {error}") from error
            if not isinstance(item, dict) or not isinstance(item.get("raw"), str):
                raise ValueError(f"case line {line_no} must contain a string 'raw'")
            if len(item["raw"].encode("utf-8")) > 65_536:
                raise ValueError(f"raw record on case line {line_no} exceeds 64 KiB")
            if "expected_template_id" not in item:
                raise ValueError(f"case line {line_no} must label expected_template_id")
            expected = item.get("expected_template_id")
            if expected is not None and (
                not isinstance(expected, str) or expected not in template_fields
            ):
                raise ValueError(f"case line {line_no} references an unknown template")
            required = item.get("required_fields", [])
            if (
                not isinstance(required, list)
                or not all(isinstance(field, str) for field in required)
            ):
                raise ValueError(f"case line {line_no} has invalid required_fields")
            allowed_fields = template_fields.get(expected, set())
            if any(field not in allowed_fields for field in required):
                raise ValueError(f"case line {line_no} requires an unknown parser field")
            cases.append(
                VerificationCase(
                    raw=item["raw"],
                    expected_template_id=expected,
                    required_fields=tuple(required),
                )
            )
            if len(cases) > 100_000:
                raise ValueError("verification cases file exceeds 100000 records")
        if not cases:
            raise ValueError("verification cases file contains no cases")
        return cases

    @staticmethod
    def _field_path(
        templates: list[dict[str, Any]], template_id: str | None, field_name: str
    ) -> str:
        for template in templates:
            if template["id"] == template_id:
                for field in template["fields"]:
                    if field["name"] == field_name:
                        path = field["ocsf_path"]
                        if isinstance(path, str):
                            return path
        return ""

    @staticmethod
    def _has_field(event: dict[str, object], path: str) -> bool:
        current: object = event
        for part in path.split("."):
            if not isinstance(current, dict) or part not in current:
                return False
            current = current[part]
        return current is not None and current != ""

    @staticmethod
    def _write_atomic(path: Path, contents: str) -> None:
        temporary_path: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                newline="\n",
                dir=path.parent,
                suffix=".tmp",
                delete=False,
            ) as temporary:
                temporary_path = temporary.name
                temporary.write(contents)
                temporary.flush()
            Path(temporary_path).replace(path)
        finally:
            if temporary_path is not None:
                Path(temporary_path).unlink(missing_ok=True)


def transition_parser(
    parser_path: Path,
    target_state: str,
    parser_schema_path: Path,
    *,
    verify_report_ref: str | None = None,
) -> None:
    definition = yaml.safe_load(parser_path.read_text(encoding="utf-8"))
    if not isinstance(definition, dict):
        raise ValueError("parser definition must be a YAML mapping")
    schema = json.loads(parser_schema_path.read_text(encoding="utf-8"))
    validate(instance=definition, schema=schema)
    current_state = definition.get("state")
    if not isinstance(current_state, str):
        raise ValueError("parser state must be a string")
    allowed = _STATE_TRANSITIONS.get(current_state)
    if allowed is None or target_state not in allowed:
        raise ValueError(f"parser cannot transition from {current_state!r} to {target_state!r}")
    if target_state == "verified":
        if not verify_report_ref:
            raise ValueError("verified parsers require a verification report reference")
        definition["verify_report_ref"] = verify_report_ref
    elif target_state == "active":
        report_ref = definition.get("verify_report_ref")
        if not isinstance(report_ref, str) or not report_ref:
            raise ValueError("only parsers with a verification report can be activated")
        report_path = Path(report_ref)
        if not report_path.is_file():
            raise ValueError(f"verification report does not exist: {report_path}")
        report = json.loads(report_path.read_text(encoding="utf-8"))
        if (
            not isinstance(report, dict)
            or report.get("valid") is not True
            or report.get("parser_name") != definition.get("name")
            or report.get("parser_version") != definition.get("version")
        ):
            raise ValueError("verification report does not validate this parser version")
    elif verify_report_ref is not None:
        raise ValueError("verification report references apply only when verifying")
    definition["state"] = target_state
    validate(instance=definition, schema=schema)
    ParserVerifier._write_atomic(parser_path, yaml.safe_dump(definition, sort_keys=False))
