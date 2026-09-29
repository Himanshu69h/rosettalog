from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class AppConfig:
    """Project-wide configuration for the Gate 0 baseline."""

    project_name: str = "RosettaLog"
    raw_store_root: Path = field(default_factory=lambda: Path("raw_store"))
    parquet_root: Path = field(default_factory=lambda: Path("parquet"))
    max_line_bytes: int = 65_536
    max_file_bytes: int = 50 * 1024 * 1024
    allow_network: bool = False
    default_timezone: str = "UTC"
    unmapped_key: str = "unmapped"
