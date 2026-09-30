from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from rosettalog.learning import ParserLearner, ReviewList, SynonymMapper, YamlEmitter
from rosettalog.parsing import ParserRegistry
from rosettalog.regex import compile_pattern

ROOT = Path(__file__).resolve().parents[1]


def _learner(review_path: Path | None = None) -> ParserLearner:
    review_list = ReviewList(review_path) if review_path is not None else None
    return ParserLearner(
        ROOT / "schemas" / "synonyms.yaml",
        ROOT / "schemas" / "parser.schema.json",
        review_list=review_list,
    )


def test_drain3_learning_infers_key_types_and_emits_valid_draft(tmp_path: Path) -> None:
    records = (ROOT / "samples" / "known" / "fortigate.log").read_text(
        encoding="utf-8"
    ).splitlines()
    review_path = tmp_path / "review" / "queue.jsonl"
    result = _learner(review_path).learn(
        records,
        name="learned_fortigate",
        created_from="samples/known/fortigate.log",
    )

    inferred = {field.name: field for field in result.inferred_fields}
    assert result.cluster_count == 1
    assert result.definition["state"] == "draft"
    assert inferred["srcip"].field_type == "ipv4"
    assert inferred["srcport"].field_type == "int"
    assert inferred["action"].field_type == "enum"
    assert inferred["date"].field_type == "timestamp"
    assert inferred["srcip"].ocsf_path == "event.src_endpoint.ip"

    output = YamlEmitter(ROOT / "schemas" / "parser.schema.json").emit(
        result.definition, tmp_path / "drafts"
    )
    emitted = yaml.safe_load(output.read_text(encoding="utf-8"))
    assert emitted == result.definition
    assert compile_pattern(emitted["templates"][0]["regex"]).search(records[0])
    assert ReviewList(review_path).items() == [result.review_item]

    registry = ParserRegistry(tmp_path / "drafts", ROOT / "schemas" / "parser.schema.json")
    assert registry.parse(records[0]) is None


def test_drain3_generic_template_infers_parameter_type() -> None:
    records = ["LINK UP 10.0.0.1 from edge", "LINK UP 10.0.0.2 from edge"]

    result = _learner().learn(
        records,
        name="learned_link",
        source_format="syslog",
        created_from="synthetic",
    )

    assert result.cluster_count == 1
    assert result.definition["state"] == "draft"
    assert result.inferred_fields[0].field_type == "ipv4"


def test_leave_one_format_out_reports_real_mapping_accuracy() -> None:
    formats: dict[str, dict[str, str]] = {}
    for path in sorted((ROOT / "parsers").glob("*.yaml")):
        definition = yaml.safe_load(path.read_text(encoding="utf-8"))
        formats[definition["name"]] = {
            field["name"]: field["ocsf_path"]
            for template in definition["templates"]
            for field in template["fields"]
        }
    learner = _learner()

    correct, total = learner.leave_one_format_out_accuracy(formats)
    print(f"Leave-one-format-out mapping accuracy: {correct} of {total} correct")

    assert total > 0
    assert correct == total


def test_mapper_uses_normalized_synonyms() -> None:
    mapper = SynonymMapper(ROOT / "schemas" / "synonyms.yaml")

    assert mapper.map_name("src_ip") == "event.src_endpoint.ip"
    assert mapper.map_name("Action_Name") == "event.action"
    assert mapper.map_name("severity_id") == "event.severity"


def test_emitter_refuses_non_draft_parser(tmp_path: Path) -> None:
    records = (ROOT / "samples" / "known" / "fortigate.log").read_text(
        encoding="utf-8"
    ).splitlines()
    definition = _learner().learn(records, name="candidate").definition
    definition["state"] = "active"

    with pytest.raises(ValueError, match="draft"):
        YamlEmitter(ROOT / "schemas" / "parser.schema.json").emit(
            definition, tmp_path / "drafts"
        )