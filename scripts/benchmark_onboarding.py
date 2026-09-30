from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "samples" / "unseen" / "northstar.log"
PARSER_SCHEMA = ROOT / "schemas" / "parser.schema.json"
SYNONYMS = ROOT / "schemas" / "synonyms.yaml"


def run() -> dict[str, Any]:
    records = [
        line.strip()
        for line in INPUT.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    with tempfile.TemporaryDirectory(prefix="rosettalog-onboarding-") as temporary_dir:
        output = Path(temporary_dir)
        drafts = output / "drafts"
        review_list = output / "review.jsonl"
        reports = output / "reports"
        start = time.perf_counter()
        learn = subprocess.run(
            [
                sys.executable,
                "-m",
                "rosettalog",
                "learn",
                str(INPUT),
                "northstar_candidate",
                "--output",
                str(drafts),
                "--review-list",
                str(review_list),
                "--parser-schema",
                str(PARSER_SCHEMA),
                "--synonyms",
                str(SYNONYMS),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        learn_result = json.loads(learn.stdout)
        parser_path = Path(learn_result["parser_file"])
        definition = yaml.safe_load(parser_path.read_text(encoding="utf-8"))
        template_id = definition["templates"][0]["id"]
        required = [field["name"] for field in definition["templates"][0]["fields"]]
        cases_path = output / "cases.jsonl"
        cases = [
            {
                "raw": record,
                "expected_template_id": template_id,
                "required_fields": required,
            }
            for record in records
        ]
        cases.append(
            {
                "raw": "not a Northstar event",
                "expected_template_id": None,
                "required_fields": [],
            }
        )
        cases_path.write_text(
            "".join(json.dumps(case, sort_keys=True) + "\n" for case in cases),
            encoding="utf-8",
        )
        verify = subprocess.run(
            [
                sys.executable,
                "-m",
                "rosettalog",
                "verify",
                str(parser_path),
                str(cases_path),
                "--parser-schema",
                str(PARSER_SCHEMA),
                "--report-dir",
                str(reports),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        if verify.returncode != 0:
            raise RuntimeError(verify.stdout + verify.stderr)
        elapsed = time.perf_counter() - start
        verify_result = json.loads(verify.stdout)
        return {
            "format": "unseen Northstar key/value",
            "records_learned": len(records),
            "verification_cases": len(cases),
            "valid": verify_result["valid"],
            "elapsed_seconds_learn_plus_verify": elapsed,
        }


def main() -> None:
    print(json.dumps(run(), sort_keys=True))


if __name__ == "__main__":
    main()
