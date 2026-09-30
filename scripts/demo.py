from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]


def _generate_samples(output_dir: Path) -> list[Path]:
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from samples.generate import generate_samples

    return generate_samples(output_dir)


def _run_cli(*arguments: str) -> str:
    command = [sys.executable, "-m", "rosettalog", *arguments]
    print("$ " + " ".join(command))
    result = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    if result.stdout:
        print(result.stdout.rstrip())
    if result.returncode != 0:
        raise RuntimeError(
            f"command failed ({result.returncode}): {' '.join(arguments)}\n{result.stderr}"
        )
    return result.stdout


def _step(number: int, description: str) -> None:
    print(f"\n[{number}/7] {description}")


def run_demo(output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=False)
    generated_dir = output_dir / "generated"
    generated_dir.mkdir()

    _step(1, "Generate deterministic synthetic samples")
    generated_samples = _generate_samples(generated_dir)
    for sample in generated_samples:
        print(sample)

    _step(2, "Learn an untrusted parser candidate and add it to review")
    drafts = output_dir / "draft_parsers"
    review_list = output_dir / "review_queue.jsonl"
    learn_summary = json.loads(
        _run_cli(
            "learn",
            str(generated_dir / "fortigate.log"),
            "demo_fortigate",
            "--output",
            str(drafts),
            "--review-list",
            str(review_list),
        )
    )
    parser_path = Path(learn_summary["parser_file"])
    definition: dict[str, Any] = yaml.safe_load(parser_path.read_text(encoding="utf-8"))
    templates = definition["templates"]
    if len(templates) != 1:
        raise RuntimeError("generated FortiGate sample should produce one candidate template")

    _step(3, "Verify the labeled candidate and activate only after success")
    verification_cases = output_dir / "verification_cases.jsonl"
    template = templates[0]
    required_fields = [field["name"] for field in template["fields"]]
    records = (generated_dir / "fortigate.log").read_text(encoding="utf-8").splitlines()
    verification_cases.write_text(
        "".join(
            json.dumps(
                {
                    "raw": record,
                    "expected_template_id": template["id"],
                    "required_fields": required_fields,
                },
                sort_keys=True,
            )
            + "\n"
            for record in records
        ),
        encoding="utf-8",
    )
    reports = output_dir / "verification_reports"
    _run_cli(
        "verify",
        str(parser_path),
        str(verification_cases),
        "--report-dir",
        str(reports),
    )
    _run_cli("activate", str(parser_path))

    _step(4, "Run the active learned parser and write raw, event, and Parquet stores")
    parser_dir = output_dir / "active_parsers"
    parser_dir.mkdir()
    for source_parser in (ROOT / "parsers").glob("*.yaml"):
        shutil.copy2(source_parser, parser_dir / source_parser.name)
    shutil.copy2(parser_path, parser_dir / parser_path.name)
    raw_store = output_dir / "raw_store"
    parquet_root = output_dir / "parquet"
    _run_cli(
        "run",
        str(generated_dir / "fortigate.log"),
        "--raw-store",
        str(raw_store),
        "--parquet",
        str(parquet_root),
        "--parsers",
        str(parser_dir),
    )
    event_ledger = raw_store / "events.jsonl"
    events = [json.loads(line) for line in event_ledger.read_text(encoding="utf-8").splitlines()]
    if not events or any(event["parser"]["name"] != "demo_fortigate" for event in events):
        raise RuntimeError("ingestion did not use the activated learned parser")

    _step(5, "Trace one event to its raw bytes and verify the complete store")
    _run_cli("trace", events[0]["event_id"], "--raw-store", str(raw_store))
    _run_cli("verify-store", str(raw_store))

    _step(6, "Query normalized events and export all supported envelope formats")
    _run_cli(
        "query",
        "SELECT count(*) AS event_count FROM events",
        "--parquet",
        str(parquet_root),
    )
    for output_format in ("ndjson", "cef", "syslog"):
        _run_cli(
            "export",
            str(event_ledger),
            str(output_dir / f"events.{output_format}"),
            "--format",
            output_format,
        )

    _step(7, "Detect drift and create a separate draft re-learn proposal")
    unseen = output_dir / "unseen.log"
    unseen.write_text(
        "new_vendor=unexpected action=block srcip=192.0.2.4 vendor_code=9\n",
        encoding="utf-8",
    )
    monitor_summary = json.loads(
        _run_cli(
            "monitor",
            str(unseen),
            "demo_fortigate",
            "--parsers",
            str(parser_dir),
            "--output",
            str(output_dir / "monitor_reports"),
            "--drafts",
            str(output_dir / "draft_parsers"),
            "--review-list",
            str(review_list),
        )
    )
    if not monitor_summary["drift"] or not monitor_summary["candidate_parser"]:
        raise RuntimeError("unseen record did not produce a drift re-learn proposal")
    print(f"\nDemo complete. Artifacts: {output_dir}")
    return output_dir


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the seven-step RosettaLog demo.")
    parser.add_argument(
        "--output",
        type=Path,
        help="new, empty output directory; defaults to a unique temporary-directory child",
    )
    arguments = parser.parse_args()
    output_dir = arguments.output or (
        Path(tempfile.gettempdir()) / f"rosettalog-demo-{uuid.uuid4().hex[:8]}"
    )
    run_demo(output_dir.resolve())


if __name__ == "__main__":
    main()
