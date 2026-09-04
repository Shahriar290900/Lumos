"""
services.ingestion — turning sources into canonical chunks.

    canonical.py       the canonical chunk model, deterministic identity, idempotent writing
    legacy_adapter.py  legacy JSONL -> canonical chunks, preserving original identity
    past_paper.py      exam papers -> one chunk per complete main question

Every adapter produces `CanonicalChunk` objects and writes them through
`ChunkWriter`. Adding a source type means adding an adapter, never changing the
model.
"""

from .canonical import (
    CHUNK_KEY_VERSION,
    INGESTION_VERSION,
    LUMOS_CHUNK_NAMESPACE,
    CanonicalChunk,
    ChunkWriter,
    WriteResult,
    make_chunk_id,
    make_chunk_key,
    record_run,
)

__all__ = [
    "CHUNK_KEY_VERSION",
    "INGESTION_VERSION",
    "LUMOS_CHUNK_NAMESPACE",
    "CanonicalChunk",
    "ChunkWriter",
    "WriteResult",
    "make_chunk_id",
    "make_chunk_key",
    "record_run",
]
