from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from rosettalog.rawstore import RawStore, RawStoreError


def test_rawstore_appends_and_reads_exact_bytes(tmp_path: Path) -> None:
    store = RawStore(tmp_path / "raw")
    first = b"record one\r\n\x00"
    second = b"record two\n"

    first_ref = store.append(
        first, source_id="source", source_file="input.log", byte_offset=0, line_no=1
    )
    second_ref = store.append(
        second, source_id="source", source_file="input.log", byte_offset=len(first), line_no=2
    )

    assert store.read(first_ref) == first
    assert store.read(second_ref) == second
    assert second_ref.frame_offset == first_ref.frame_offset + first_ref.compressed_size
    assert store.verify().valid
    assert len(store.records()) == 2


@settings(max_examples=30, deadline=None)
@given(st.binary(max_size=4096))
def test_rawstore_round_trips_arbitrary_bytes(raw: bytes) -> None:
    with tempfile.TemporaryDirectory() as directory:
        store = RawStore(Path(directory) / "raw")
        ref = store.append(
            raw, source_id="fuzz", source_file="fuzz.bin", byte_offset=0, line_no=1
        )

        assert store.read(ref) == raw
        assert store.verify().valid


def test_rawstore_detects_frame_corruption(tmp_path: Path) -> None:
    store = RawStore(tmp_path / "raw")
    ref = store.append(
        b"integrity check", source_id="source", source_file="x", byte_offset=0, line_no=1
    )
    data = bytearray(store.data_path.read_bytes())
    data[ref.frame_offset + ref.compressed_size // 2] ^= 0xFF
    store.data_path.write_bytes(data)

    result = store.verify()

    assert not result.valid
    assert result.errors
    with pytest.raises(RawStoreError):
        store.read(ref)


def test_rawstore_rejects_oversized_records(tmp_path: Path) -> None:
    store = RawStore(tmp_path / "raw", max_record_bytes=4)

    with pytest.raises(RawStoreError, match="exceeds"):
        store.append(b"12345", source_id="source", source_file="x", byte_offset=0, line_no=1)