from __future__ import annotations

import json
import re
import shlex
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from ipaddress import IPv4Address
from pathlib import Path
from typing import Any

import yaml
from drain3 import TemplateMiner
from drain3.template_miner_config import TemplateMinerConfig
from jsonschema import validate


@dataclass(frozen=True, slots=True)
class FieldInference:
    name: str
    field_type: str
    ocsf_path: str | None
    confidence: float
    examples: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ParserLearningResult:
    definition: dict[str, Any]
    inferred_fields: tuple[FieldInference, ...]
    review_item: dict[str, Any]
    cluster_count: int
    records_used: int


class SynonymMapper:
    def __init__(self, synonyms_path: Path) -> None:
        document = yaml.safe_load(synonyms_path.read_text(encoding="utf-8"))
        self._paths: dict[str, str] = {}
        for entry in document["sources"]:
            target = self._event_path(entry["src"])
            for name in [entry["src"], *entry["aliases"]]:
                self._paths[self._normalize(name)] = target

    def map_name(self, name: str) -> str | None:
        return self._paths.get(self._normalize(name))

    @staticmethod
    def _normalize(name: str) -> str:
        return re.sub(r"[^a-z0-9]", "", name.casefold())

    @staticmethod
    def _event_path(path: str) -> str:
        return path if path.startswith("event.") else f"event.{path}"


class ReviewList:
    def __init__(self, path: Path) -> None:
        self.path = path

    def append(self, item: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8", newline="\n") as output:
            output.write(json.dumps(item, sort_keys=True, separators=(",", ":")))
            output.write("\n")
            output.flush()

    def items(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        with self.path.open("r", encoding="utf-8") as source:
            return [json.loads(line) for line in source if line.strip()]


class YamlEmitter:
    def __init__(self, parser_schema_path: Path) -> None:
        self.schema = json.loads(parser_schema_path.read_text(encoding="utf-8"))

    def emit(self, definition: dict[str, Any], output_dir: Path) -> Path:
        if definition.get("state") != "draft":
            raise ValueError("learned parser definitions must remain in draft state")
        validate(instance=definition, schema=self.schema)
        name = str(definition["name"])
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,63}", name):
            raise ValueError(
                "parser name must contain only letters, digits, underscores, or hyphens"
            )
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / f"{name}.yaml"
        if path.exists():
            raise FileExistsError(path)
        path.write_text(yaml.safe_dump(definition, sort_keys=False), encoding="utf-8")
        return path


class ParserLearner:
    def __init__(
        self,
        synonyms_path: Path,
        parser_schema_path: Path,
        *,
        review_list: ReviewList | None = None,
        max_records: int = 10_000,
        max_line_bytes: int = 65_536,
    ) -> None:
        self.mapper = SynonymMapper(synonyms_path)
        self.parser_schema = json.loads(parser_schema_path.read_text(encoding="utf-8"))
        self.review_list = review_list
        self.max_records = max_records
        self.max_line_bytes = max_line_bytes

    def learn(
        self,
        records: list[str],
        *,
        name: str,
        source_format: str = "key_value",
        created_from: str = "",
    ) -> ParserLearningResult:
        if not records or len(records) > self.max_records:
            raise ValueError(f"records must contain between 1 and {self.max_records} lines")
        if any(
            not record or len(record.encode("utf-8")) > self.max_line_bytes
            for record in records
        ):
            raise ValueError(f"records must be non-empty and at most {self.max_line_bytes} bytes")

        key_values = [self._key_values(record) for record in records]
        all_key_values = all(pairs for pairs in key_values)
        config = TemplateMinerConfig()
        config.drain_extra_delimiters = ["="] if all_key_values else []
        config.drain_sim_th = 0.6
        config.drain_max_clusters = 1_000
        miner = TemplateMiner(config=config)
        results = [miner.add_log_message(record) for record in records]

        if all_key_values:
            definition, inferred = self._key_value_definition(
                records, key_values, results, name, source_format, created_from
            )
        else:
            definition, inferred = self._generic_definition(
                records, results, name, source_format, created_from
            )
        validate(instance=definition, schema=self.parser_schema)
        review_item = {
            "parser_name": name,
            "state": "draft",
            "source_format": source_format,
            "created_from": created_from,
            "records_used": len(records),
            "cluster_count": len(miner.drain.clusters),
            "mapped_fields": [field.name for field in inferred if field.ocsf_path],
            "unmapped_fields": [field.name for field in inferred if not field.ocsf_path],
        }
        if self.review_list is not None:
            self.review_list.append(review_item)
        return ParserLearningResult(
            definition=definition,
            inferred_fields=tuple(inferred),
            review_item=review_item,
            cluster_count=len(miner.drain.clusters),
            records_used=len(records),
        )

    def leave_one_format_out_accuracy(
        self, formats: dict[str, dict[str, str]]
    ) -> tuple[int, int]:
        correct = 0
        total = 0
        for held_out, fields in formats.items():
            training: dict[str, Counter[str]] = defaultdict(Counter)
            for format_name, examples in formats.items():
                if format_name == held_out:
                    continue
                for field_name, path in examples.items():
                    training[field_name][path] += 1
            for field_name, expected_path in fields.items():
                candidates = training.get(field_name, Counter())
                if candidates:
                    predicted_path, count = candidates.most_common(1)[0]
                    if len(candidates) > 1 and list(candidates.values()).count(count) > 1:
                        predicted_path = ""
                else:
                    predicted_path = self.mapper.map_name(field_name) or ""
                correct += predicted_path == expected_path
                total += 1
        return correct, total

    def _key_value_definition(
        self,
        records: list[str],
        key_values: list[list[tuple[str, str]]],
        results: list[dict[str, Any]],
        name: str,
        source_format: str,
        created_from: str,
    ) -> tuple[dict[str, Any], list[FieldInference]]:
        groups: dict[tuple[int, tuple[str, ...]], list[list[tuple[str, str]]]] = defaultdict(list)
        for pairs, result in zip(key_values, results, strict=True):
            signature = tuple(key for key, _ in pairs)
            groups[(result["cluster_id"], signature)].append(pairs)

        templates: list[dict[str, Any]] = []
        inferences: list[FieldInference] = []
        mapped_paths: set[str] = set()
        for template_index, ((cluster_id, signature), samples) in enumerate(
            groups.items(), start=1
        ):
            names = self._group_names(signature)
            field_values = {
                key: [pairs[index][1] for pairs in samples]
                for index, key in enumerate(signature)
            }
            fields: list[dict[str, Any]] = []
            for key, field_name in zip(signature, names, strict=True):
                target = self.mapper.map_name(key)
                inferred = self._infer_field(field_name, field_values[key], target)
                inferences.append(inferred)
                if target is not None:
                    mapped_paths.add(target)
                    fields.append(
                        {
                            "name": field_name,
                            "type": inferred.field_type,
                            "ocsf_path": target,
                            "confidence": inferred.confidence,
                        }
                    )
            expression = self._key_value_pattern(signature, names)
            templates.append(
                {
                    "id": f"drain_{cluster_id:04d}_{template_index:02d}",
                    "regex": expression,
                    "fields": fields,
                    "event_class": self._event_class(mapped_paths),
                    "activity": "record",
                }
            )

        definition = self._definition(
            name, source_format, created_from, templates, signature=next(iter(groups))[1]
        )
        return definition, inferences

    def _generic_definition(
        self,
        records: list[str],
        results: list[dict[str, Any]],
        name: str,
        source_format: str,
        created_from: str,
    ) -> tuple[dict[str, Any], list[FieldInference]]:
        groups: dict[int, list[str]] = defaultdict(list)
        templates_by_cluster: dict[int, str] = {}
        for record, result in zip(records, results, strict=True):
            cluster_id = result["cluster_id"]
            groups[cluster_id].append(record)
            templates_by_cluster[cluster_id] = result["template_mined"]
        templates: list[dict[str, Any]] = []
        inferences: list[FieldInference] = []
        mapped_paths: set[str] = set()
        for template_index, (cluster_id, samples) in enumerate(groups.items(), start=1):
            expression, names, captures = self._generic_pattern(
                templates_by_cluster[cluster_id], samples
            )
            fields: list[dict[str, Any]] = []
            for name_index, field_name in enumerate(names):
                values = [match.get(field_name, "") for match in captures]
                inferred = self._infer_field(field_name, values, None)
                inferences.append(inferred)
            templates.append(
                {
                    "id": f"drain_{cluster_id:04d}_{template_index:02d}",
                    "regex": expression,
                    "fields": fields,
                    "event_class": self._event_class(mapped_paths),
                    "activity": "record",
                }
            )
        definition = self._definition(
            name, source_format, created_from, templates, signature=()
        )
        return definition, inferences

    def _infer_field(
        self, name: str, examples: list[str], target: str | None
    ) -> FieldInference:
        if not examples:
            return FieldInference(name, "free_text", target, 0.0, ())
        types = [self._value_type(example) for example in examples]
        counts = Counter(types)
        inferred_type, most_common = counts.most_common(1)[0]
        if target in {"event.action", "event.protocol_name"} and len(set(examples)) <= 8:
            inferred_type = "enum"
            most_common = len(examples)
        confidence = most_common / len(examples)
        return FieldInference(name, inferred_type, target, confidence, tuple(examples[:5]))

    @staticmethod
    def _value_type(value: str) -> str:
        try:
            IPv4Address(value)
            return "ipv4"
        except ValueError:
            pass
        if re.fullmatch(r"[+-]?\d+", value):
            return "int"
        for date_format in (None, "%Y-%m-%d", "%H:%M:%S"):
            try:
                if date_format is None:
                    datetime.fromisoformat(value.replace("Z", "+00:00"))
                else:
                    datetime.strptime(value, date_format)
                return "timestamp"
            except ValueError:
                continue
        return "free_text"

    def _definition(
        self,
        name: str,
        source_format: str,
        created_from: str,
        templates: list[dict[str, Any]],
        *,
        signature: tuple[str, ...],
    ) -> dict[str, Any]:
        first_key = signature[0] if signature else None
        definition = {
            "name": name,
            "version": 1,
            "state": "draft",
            "source_format": source_format,
            "envelope": {
                "header_regex": rf"^\s*{re.escape(first_key)}=" if first_key else None,
                "timestamp_format": "%Y-%m-%dT%H:%M:%SZ",
                "tz": "UTC",
            },
            "templates": templates,
            "unmapped_policy": "retain",
            "created_from": created_from,
            "verify_report_ref": None,
        }
        return definition

    @staticmethod
    def _key_values(record: str) -> list[tuple[str, str]]:
        try:
            tokens = shlex.split(record)
        except ValueError:
            return []
        pairs: list[tuple[str, str]] = []
        for token in tokens:
            key, separator, value = token.partition("=")
            if not separator or not key or not value:
                return []
            pairs.append((key, value))
        return pairs

    @staticmethod
    def _group_names(keys: tuple[str, ...]) -> list[str]:
        names: list[str] = []
        used: set[str] = set()
        for index, key in enumerate(keys, start=1):
            base = re.sub(r"[^A-Za-z0-9_]", "_", key)
            if not base or base[0].isdigit():
                base = f"field_{base}"
            candidate = base
            suffix = 2
            while candidate in used:
                candidate = f"{base}_{suffix}"
                suffix += 1
            used.add(candidate)
            names.append(candidate or f"field_{index}")
        return names

    @staticmethod
    def _key_value_pattern(keys: tuple[str, ...], names: list[str]) -> str:
        parts = ["^"]
        for index, (key, name) in enumerate(zip(keys, names, strict=True)):
            parts.append(re.escape(key))
            parts.append("=(?P<" + name + ">.+?)")
            if index + 1 < len(keys):
                parts.append(r"\s+")
        parts.append("$")
        return "".join(parts)

    @staticmethod
    def _generic_pattern(
        template: str, samples: list[str]
    ) -> tuple[str, list[str], list[dict[str, str]]]:
        names: list[str] = []
        tokens = template.split()
        pieces: list[str] = ["^"]
        for token_index, token in enumerate(tokens):
            if token_index:
                pieces.append(r"\s+")
            position = 0
            for marker in re.finditer(r"<[^>]+>|\*", token):
                pieces.append(re.escape(token[position : marker.start()]))
                name = f"field_{len(names) + 1}"
                names.append(name)
                pieces.append(f"(?P<{name}>\\S+)")
                position = marker.end()
            pieces.append(re.escape(token[position:]))
        pieces.append("$")
        expression = "".join(pieces)
        compiled = re.compile(expression)
        captures = [
            match.groupdict()
            for sample in samples
            if (match := compiled.match(sample)) is not None
        ]
        return expression, names, captures

    @staticmethod
    def _event_class(mapped_paths: set[str]) -> str:
        if any(
            path.startswith(("event.src_endpoint", "event.dst_endpoint", "event.network"))
            for path in mapped_paths
        ):
            return "Network Activity"
        return "Detection Finding"