from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("sample_generator", ROOT / "samples" / "generate.py")
assert SPEC is not None and SPEC.loader is not None
sample_generator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sample_generator)


def test_generator_writes_all_formats_reproducibly(tmp_path: Path) -> None:
    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"

    first_paths = sample_generator.generate_samples(first_dir, seed=1234)
    sample_generator.generate_samples(second_dir, seed=1234)

    assert {path.name for path in first_paths} == {
        "asa.log",
        "fortigate.log",
        "cef.log",
        "json.log",
    }
    for path in first_paths:
        assert path.read_bytes() == (second_dir / path.name).read_bytes()


def test_benchmark_generator_writes_requested_rows_reproducibly(tmp_path: Path) -> None:
    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"

    first_paths = sample_generator.generate_benchmark_samples(
        first_dir, records_per_format=20, seed=1234
    )
    sample_generator.generate_benchmark_samples(
        second_dir, records_per_format=20, seed=1234
    )

    assert len(first_paths) == 4
    for path in first_paths:
        lines = path.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 20
        assert path.read_bytes() == (second_dir / path.name).read_bytes()