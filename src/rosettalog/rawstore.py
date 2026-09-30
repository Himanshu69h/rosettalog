from __future__ import annotations

import hashlib
import json
import os
import threading
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import BinaryIO, TextIO

import zstandard


class RawStoreError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class RawRecordRef:
    sequence: int
    frame_offset: int
    compressed_size: int
    raw_size: int
    sha256: str
    source_id: str
    source_file: str
    byte_offset: int
    line_no: int


@dataclass(frozen=True, slots=True)
class StoreVerification:
    valid: bool
    records_checked: int
    errors: tuple[str, ...]


class RawStore:
    def __init__(
        self,
        root: Path,
        *,
        max_record_bytes: int = 65_536,
        sync_every: int = 1,
    ) -> None:
        if sync_every < 1:
            raise ValueError("sync_every must be positive")
        self.root = root
        self.data_path = root / "records.zst"
        self.index_path = root / "index.jsonl"
        self.max_record_bytes = max_record_bytes
        self.sync_every = sync_every
        self._lock = threading.Lock()
        self._compressor = zstandard.ZstdCompressor(level=3)
        self._decompressor = zstandard.ZstdDecompressor()
        self._data_stream: BinaryIO | None = None
        self._index_stream: TextIO | None = None
        self.root.mkdir(parents=True, exist_ok=True)
        self._sequence = self._indexed_record_count()

    def append(
        self,
        raw: bytes,
        *,
        source_id: str,
        source_file: str,
        byte_offset: int,
        line_no: int,
    ) -> RawRecordRef:
        if len(raw) > self.max_record_bytes:
            raise RawStoreError(f"record exceeds the {self.max_record_bytes}-byte limit")
        if byte_offset < 0 or line_no < 1:
            raise RawStoreError("source position must have a non-negative offset and positive line")
        compressed = self._compressor.compress(raw)
        with self._lock:
            if self.sync_every == 1:
                frame_offset = self.data_path.stat().st_size if self.data_path.exists() else 0
            else:
                self._open_batch_streams()
                assert self._data_stream is not None
                assert self._index_stream is not None
                frame_offset = self._data_stream.tell()
            ref = RawRecordRef(
                sequence=self._sequence,
                frame_offset=frame_offset,
                compressed_size=len(compressed),
                raw_size=len(raw),
                sha256=hashlib.sha256(raw).hexdigest(),
                source_id=source_id,
                source_file=source_file,
                byte_offset=byte_offset,
                line_no=line_no,
            )
            if self.sync_every == 1:
                with self.data_path.open("ab") as data_file:
                    data_file.write(compressed)
                    data_file.flush()
                    os.fsync(data_file.fileno())
                with self.index_path.open("a", encoding="utf-8", newline="\n") as index_file:
                    index_file.write(
                        json.dumps(asdict(ref), sort_keys=True, separators=(",", ":"))
                    )
                    index_file.write("\n")
                    index_file.flush()
                    os.fsync(index_file.fileno())
            else:
                assert self._data_stream is not None
                assert self._index_stream is not None
                self._data_stream.write(compressed)
                self._index_stream.write(
                    json.dumps(asdict(ref), sort_keys=True, separators=(",", ":"))
                )
                self._index_stream.write("\n")
            self._sequence += 1
            if self.sync_every > 1 and self._sequence % self.sync_every == 0:
                self._sync_locked()
            return ref

    def sync(self) -> None:
        with self._lock:
            self._sync_locked()

    def close(self) -> None:
        with self._lock:
            self._sync_locked()
            for stream in (self._data_stream, self._index_stream):
                if stream is not None:
                    stream.close()
            self._data_stream = None
            self._index_stream = None

    def _open_batch_streams(self) -> None:
        if self._data_stream is None:
            self._data_stream = self.data_path.open("ab")
        if self._index_stream is None:
            self._index_stream = self.index_path.open("a", encoding="utf-8", newline="\n")

    def _sync_locked(self) -> None:
        streams = (
            (self._data_stream, self.data_path),
            (self._index_stream, self.index_path),
        )
        for stream, path in streams:
            if stream is not None:
                stream.flush()
                os.fsync(stream.fileno())
            elif path.exists():
                with path.open("ab") as output:
                    os.fsync(output.fileno())

    def read(self, ref: RawRecordRef) -> bytes:
        try:
            with self.data_path.open("rb") as data_file:
                data_file.seek(ref.frame_offset)
                compressed = data_file.read(ref.compressed_size)
            if len(compressed) != ref.compressed_size:
                raise RawStoreError("compressed frame is truncated")
            raw = self._decompressor.decompress(compressed, max_output_size=self.max_record_bytes)
        except (OSError, zstandard.ZstdError) as error:
            raise RawStoreError(f"cannot read raw record {ref.sequence}: {error}") from error
        if len(raw) != ref.raw_size:
            raise RawStoreError(f"raw record {ref.sequence} has an unexpected size")
        if hashlib.sha256(raw).hexdigest() != ref.sha256:
            raise RawStoreError(f"raw record {ref.sequence} failed SHA-256 verification")
        return raw

    def records(self) -> list[RawRecordRef]:
        refs: list[RawRecordRef] = []
        if not self.index_path.exists():
            return refs
        with self.index_path.open("r", encoding="utf-8") as index_file:
            for line_no, line in enumerate(index_file, start=1):
                try:
                    item = json.loads(line)
                    refs.append(RawRecordRef(**item))
                except (json.JSONDecodeError, TypeError, ValueError) as error:
                    raise RawStoreError(
                        f"invalid rawstore index line {line_no}: {error}"
                    ) from error
        return refs

    def verify(self) -> StoreVerification:
        errors: list[str] = []
        checked = 0
        expected_offset = 0
        try:
            refs = self.records()
        except RawStoreError as error:
            return StoreVerification(False, checked, (str(error),))

        for expected_sequence, ref in enumerate(refs):
            if ref.sequence != expected_sequence:
                errors.append(f"index sequence {ref.sequence} is not {expected_sequence}")
            if ref.frame_offset != expected_offset:
                errors.append(f"record {ref.sequence} frame offset is not contiguous")
            if ref.raw_size > self.max_record_bytes:
                errors.append(f"record {ref.sequence} exceeds the configured raw size limit")
            try:
                self.read(ref)
            except RawStoreError as error:
                errors.append(str(error))
            checked += 1
            expected_offset = ref.frame_offset + ref.compressed_size

        actual_size = self.data_path.stat().st_size if self.data_path.exists() else 0
        if actual_size != expected_offset:
            errors.append("raw data file contains unindexed or missing bytes")
        return StoreVerification(not errors, checked, tuple(errors))

    def _indexed_record_count(self) -> int:
        if not self.index_path.exists():
            return 0
        with self.index_path.open("rb") as index_file:
            return sum(1 for _ in index_file)