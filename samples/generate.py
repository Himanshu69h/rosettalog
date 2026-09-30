"""Seeded sample-log generator for Gate 0 and later gates.

This script produces reproducible, synthetic perimeter-device log samples.
The generated data is clearly labeled as synthetic and is meant for tests,
validation, and benchmarking work.
"""

from __future__ import annotations

import argparse
import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

SEED = 2026


def _build_asa_lines() -> list[str]:
    lines = [
        (
            'Sep 29 08:15:00 fw01 %ASA-4-106023: Deny tcp src 10.0.0.5/443 '
            'dst 203.0.113.4/443 by access-group "OUTSIDE_IN"'
        ),
        (
            'Sep 29 08:15:05 fw01 %ASA-4-106023: Deny tcp src 10.0.0.7/80 '
            'dst 203.0.113.10/80 by access-group "OUTSIDE_IN"'
        ),
        (
            'Sep 29 08:16:00 fw01 %ASA-4-106023: Allow tcp src 10.0.0.12/443 '
            'dst 198.51.100.8/443 by access-group "INTERNAL"'
        ),
    ]
    return lines


def _build_fortigate_lines() -> list[str]:
    return [
        (
            'date=2026-09-29 time=08:15:00 log_id=000000001 action=deny '
            'srcip=10.0.0.5 dstip=203.0.113.4 proto=tcp srcport=443 dstport=443'
        ),
        (
            'date=2026-09-29 time=08:15:05 log_id=000000001 action=accept '
            'srcip=10.0.0.8 dstip=198.51.100.15 proto=udp srcport=53 dstport=53'
        ),
    ]


def _build_cef_lines() -> list[str]:
    return [
        (
            'CEF:0|Cisco|ASA|9.12|106023|Deny|5|src=10.0.0.5 dst=203.0.113.4 '
            'proto=tcp spt=443 dpt=443 msg=Access denied'
        ),
        (
            'CEF:0|Fortinet|FortiGate|7.0|000000001|Accept|3|src=10.0.0.7 '
            'dst=198.51.100.11 proto=udp spt=53 dpt=53 msg=Allowed flow'
        ),
    ]


def _build_json_lines(randomizer: random.Random) -> list[str]:
    first_ip = f"10.0.0.{randomizer.randint(1, 254)}"
    second_ip = f"203.0.113.{randomizer.randint(1, 254)}"
    return [
        json.dumps(
            {
                "time": "2026-09-29T08:15:00Z",
                "src_ip": first_ip,
                "dst_ip": second_ip,
                "action": "deny",
                "protocol": "tcp",
            },
            sort_keys=True,
            separators=(",", ":"),
        ),
        json.dumps(
            {
                "time": "2026-09-29T08:15:05Z",
                "src_ip": "10.0.0.8",
                "dst_ip": "198.51.100.15",
                "action": "accept",
                "protocol": "udp",
            },
            sort_keys=True,
            separators=(",", ":"),
        ),
    ]


def generate_samples(output_dir: Path | None = None, *, seed: int = SEED) -> list[Path]:
    root = output_dir or Path(__file__).resolve().parent / "known"
    root.mkdir(parents=True, exist_ok=True)
    randomizer = random.Random(seed)
    generated: list[Path] = []
    for name, generator in {
        'asa.log': _build_asa_lines,
        'fortigate.log': _build_fortigate_lines,
        'cef.log': _build_cef_lines,
        'json.log': lambda: _build_json_lines(randomizer),
    }.items():
        output = root / name
        output.write_text('\n'.join(generator()) + '\n', encoding='utf-8')
        generated.append(output)
    return generated


def generate_benchmark_samples(
    output_dir: Path | None = None,
    *,
    records_per_format: int = 100_000,
    seed: int = SEED,
) -> list[Path]:
    if not 1 <= records_per_format <= 1_000_000:
        raise ValueError("records_per_format must be between 1 and 1000000")
    root = output_dir or Path(__file__).resolve().parent / "benchmark"
    root.mkdir(parents=True, exist_ok=True)
    randomizer = random.Random(seed)
    generated: list[Path] = []
    start_time = datetime(2026, 9, 29, tzinfo=timezone.utc)

    def address(index: int, *, public: bool = False) -> str:
        third = (index // 254) % 256
        fourth = index % 254 + 1
        if public:
            return f"198.51.{third}.{fourth}"
        second = (index // (254 * 256)) % 256
        return f"10.{second}.{third}.{fourth}"

    writers = {
        "asa.log": lambda index: (
            f"{(start_time + timedelta(seconds=index)).strftime('%b %d %H:%M:%S')} "
            f"fw01 %ASA-4-106023: {('Deny' if index % 2 == 0 else 'Allow')} "
            f"{('tcp' if index % 2 == 0 else 'udp')} src {address(index)}/"
            f"{randomizer.randint(1, 65535)} "
            f"dst {address(index, public=True)}/{randomizer.randint(1, 65535)} "
            'by access-group "BENCHMARK"'
        ),
        "fortigate.log": lambda index: (
            f"date={(start_time + timedelta(seconds=index)).strftime('%Y-%m-%d')} "
            f"time={(start_time + timedelta(seconds=index)).strftime('%H:%M:%S')} "
            f"log_id=000000001 action={('deny' if index % 2 == 0 else 'accept')} "
            f"srcip={address(index)} dstip={address(index, public=True)} "
            f"proto={('tcp' if index % 2 == 0 else 'udp')} "
            f"srcport={randomizer.randint(1, 65535)} dstport={randomizer.randint(1, 65535)}"
        ),
        "cef.log": lambda index: (
            f"CEF:0|Cisco|ASA|9.12|106023|{('Deny' if index % 2 == 0 else 'Accept')}|5|"
            f"src={address(index)} dst={address(index, public=True)} "
            f"proto={('tcp' if index % 2 == 0 else 'udp')} "
            f"spt={randomizer.randint(1, 65535)} dpt={randomizer.randint(1, 65535)} "
            f"msg=synthetic-{index}"
        ),
        "json.log": lambda index: json.dumps(
            {
                "time": (start_time + timedelta(seconds=index)).isoformat().replace("+00:00", "Z"),
                "src_ip": address(index),
                "dst_ip": address(index, public=True),
                "action": "deny" if index % 2 == 0 else "accept",
                "protocol": "tcp" if index % 2 == 0 else "udp",
            },
            sort_keys=True,
            separators=(",", ":"),
        ),
    }
    for name, make_record in writers.items():
        output = root / name
        with output.open("w", encoding="utf-8", newline="\n") as stream:
            for index in range(records_per_format):
                stream.write(make_record(index))
                stream.write("\n")
        generated.append(output)
    return generated


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate deterministic synthetic log samples.")
    parser.add_argument(
        "--output-dir", type=Path, default=Path(__file__).resolve().parent / "benchmark"
    )
    parser.add_argument("--records-per-format", type=int, default=100_000)
    parser.add_argument("--seed", type=int, default=SEED)
    arguments = parser.parse_args()
    paths = generate_benchmark_samples(
        arguments.output_dir,
        records_per_format=arguments.records_per_format,
        seed=arguments.seed,
    )
    print(f"Wrote {arguments.records_per_format} records per format to {arguments.output_dir}")
    for path in paths:
        print(path)


if __name__ == '__main__':
    main()
