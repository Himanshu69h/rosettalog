"""Seeded sample-log generator for Gate 0 and later gates.

This script produces reproducible, synthetic perimeter-device log samples.
The generated data is clearly labeled as synthetic and is meant for tests,
validation, and benchmarking work.
"""

from __future__ import annotations

import random
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


def main() -> None:
    random.seed(SEED)
    root = Path(__file__).resolve().parent
    for name, generator in {
        'asa.log': _build_asa_lines,
        'fortigate.log': _build_fortigate_lines,
        'cef.log': _build_cef_lines,
    }.items():
        output = root / 'known' / name
        output.write_text('\n'.join(generator()) + '\n', encoding='utf-8')

    print(f"Wrote synthetic samples to {root / 'known'}")


if __name__ == '__main__':
    main()
