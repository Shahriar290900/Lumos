#!/usr/bin/env python3
"""
catalog_sources.py — catalogue private curriculum source documents for the
Lumos curriculum registry.

Walks a directory of licensed source PDFs and emits a metadata-only manifest:
checksum, size, page count, document type, paper code, unit, session, and — the
part that decides the ingestion route — whether the PDF has a usable text layer
or requires OCR.

**It never emits document content.** The manifest is safe to commit; the PDFs it
describes are not, and must stay outside version control (see .githooks/pre-commit).

Expected layout, matching private_source_materials/:

    <root>/
      <Curriculum Subject>/
        textbooks/
          *.pdf
        <YYYY Month Month>/            e.g. "2024 May June"
          Question-paper/*.pdf
          Mark-scheme/*.pdf
          Examiner-report/*.pdf

Usage
-----
    python scripts/catalog_sources.py "<path>/private_source_materials" \
        --output evidence/source_catalog.json

Text-layer verdicts
-------------------
    text          extractable text layer; parse directly
    ocr_required  no usable text layer (scanned pages, or embedded fonts with
                  no ToUnicode map that decode to (cid:N) garbage)
    mixed         some pages extract, some do not
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Pearson Edexcel IAL Physics unit codes.
UNIT_CODES = {
    "wph11": {"unit": 1, "qualification": "International AS", "title": "Mechanics and Materials"},
    "wph12": {"unit": 2, "qualification": "International AS", "title": "Waves and Electricity"},
    "wph13": {"unit": 3, "qualification": "International AS", "title": "Practical Skills in Physics I"},
    "wph14": {"unit": 4, "qualification": "IAL A2", "title": "Further Mechanics, Fields and Particles"},
    "wph15": {"unit": 5, "qualification": "IAL A2", "title": "Thermodynamics, Radiation, Oscillations and Cosmology"},
    "wph16": {"unit": 6, "qualification": "IAL A2", "title": "Practical Skills in Physics II"},
}

# Directory name → (document_type, source_priority)
# Priority follows ADR-009: 1 = official/authoritative, 2 = core textbook,
# 3 = supplementary. Lower number wins when context is contested.
DIR_TYPES = {
    "question-paper": ("past_paper", 1),
    "mark-scheme": ("mark_scheme", 1),
    "examiner-report": ("examiner_report", 1),
    "specification": ("specification", 1),
    "textbooks": ("textbook", 2),
    "revision-guide": ("revision_guide", 3),
    "topic-notes": ("topic_notes", 3),
}

FILE_TYPE_HINTS = {"que": "past_paper", "rms": "mark_scheme", "pef": "examiner_report"}

CID_RE = re.compile(r"\(cid:\d+\)")
SESSION_RE = re.compile(r"^(\d{4})\s+(.+)$")


def sha256_of(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while block := fh.read(chunk):
            h.update(block)
    return h.hexdigest()


def probe_text_layer(path: Path, sample: int = 8) -> dict[str, Any]:
    """Sample pages and decide whether the PDF can be parsed or needs OCR."""
    try:
        import pdfplumber
    except ImportError:
        return {"verdict": "unknown", "reason": "pdfplumber not installed"}

    try:
        with pdfplumber.open(str(path)) as doc:
            n = len(doc.pages)
            if n == 0:
                return {"pages": 0, "verdict": "unknown", "reason": "no pages"}
            step = max(1, n // sample)
            idxs = list(range(0, n, step))[:sample]
            good = bad = empty = 0
            for i in idxs:
                text = (doc.pages[i].extract_text() or "").strip()
                if not text:
                    empty += 1
                    continue
                cid_chars = sum(len(m.group(0)) for m in CID_RE.finditer(text))
                if len(text) < 40 or cid_chars > len(text) * 0.2:
                    bad += 1
                else:
                    good += 1
    except Exception as exc:  # noqa: BLE001 - a broken PDF is a finding, not a crash
        return {"verdict": "unknown", "reason": f"{type(exc).__name__}: {exc}"}

    sampled = len(idxs)
    if good == sampled:
        verdict, reason = "text", "all sampled pages yielded text"
    elif good == 0 and bad > 0:
        verdict, reason = "ocr_required", "sampled pages decode to (cid:N) glyphs — font has no ToUnicode map"
    elif good == 0:
        verdict, reason = "ocr_required", "sampled pages contain no text layer (scanned images)"
    else:
        verdict, reason = "mixed", f"{good}/{sampled} sampled pages yielded text"

    return {
        "pages": n,
        "sampled_pages": sampled,
        "pages_with_text": good,
        "pages_garbled": bad,
        "pages_empty": empty,
        "verdict": verdict,
        "reason": reason,
    }


def classify(path: Path, root: Path) -> dict[str, Any]:
    rel = path.relative_to(root)
    parts = [p.lower() for p in rel.parts]

    doc_type, priority = None, None
    for part in parts:
        if part in DIR_TYPES:
            doc_type, priority = DIR_TYPES[part]
            break

    stem = path.stem.lower()
    if doc_type is None:
        for hint, t in FILE_TYPE_HINTS.items():
            if f"-{hint}-" in stem or stem.endswith(f"-{hint}"):
                doc_type = t
                priority = 1
                break

    unit_info: dict[str, Any] = {}
    for code, info in UNIT_CODES.items():
        if code in stem:
            unit_info = {"paper_code": code.upper(), **info}
            break

    session = None
    for part in rel.parts:
        m = SESSION_RE.match(part)
        if m:
            session = {"year": int(m.group(1)), "series": m.group(2).strip()}
            break

    subject_dir = rel.parts[0] if len(rel.parts) > 1 else None

    return {
        "relative_path": str(rel),
        "subject_folder": subject_dir,
        "document_type": doc_type or "unknown",
        "source_priority": priority,
        "session": session,
        **unit_info,
    }


def catalog(root: Path) -> dict[str, Any]:
    pdfs = sorted(p for p in root.rglob("*.pdf") if p.is_file())
    entries = []
    for p in pdfs:
        meta = classify(p, root)
        meta.update(
            {
                "filename": p.name,
                "bytes": p.stat().st_size,
                "sha256": sha256_of(p),
                "text_layer": probe_text_layer(p),
            }
        )
        entries.append(meta)

    by_type: dict[str, int] = {}
    by_route: dict[str, int] = {}
    for e in entries:
        by_type[e["document_type"]] = by_type.get(e["document_type"], 0) + 1
        v = e["text_layer"].get("verdict", "unknown")
        by_route[v] = by_route.get(v, 0) + 1

    digests = [e["sha256"] for e in entries]
    dupes = {d: [e["relative_path"] for e in entries if e["sha256"] == d]
             for d in digests if digests.count(d) > 1}

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "root": str(root),
        "note": (
            "Metadata only. No document content appears in this file. The PDFs "
            "described here are licensed material and must never be committed."
        ),
        "document_count": len(entries),
        "total_bytes": sum(e["bytes"] for e in entries),
        "by_document_type": by_type,
        "by_ingestion_route": by_route,
        "duplicate_checksums": dupes,
        "documents": entries,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("root", type=Path)
    ap.add_argument("--output", type=Path, default=None)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    if not args.root.is_dir():
        print(f"not a directory: {args.root}", file=sys.stderr)
        return 2

    result = catalog(args.root)
    if not result["documents"]:
        print(f"no PDFs found under {args.root}", file=sys.stderr)
        return 2

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=" * 78)
    print(f"documents: {result['document_count']}   "
          f"total: {result['total_bytes'] / 1024 / 1024:.1f} MB")
    print(f"by type:   {result['by_document_type']}")
    print(f"by route:  {result['by_ingestion_route']}")
    if result["duplicate_checksums"]:
        print(f"DUPLICATES: {result['duplicate_checksums']}")
    print("-" * 78)
    for e in result["documents"]:
        tl = e["text_layer"]
        code = e.get("paper_code", "—")
        print(f"{e['filename']:<32} {e['document_type']:<16} {code:<7} "
              f"p={tl.get('pages', '?'):<4} {tl.get('verdict', '?'):<13} "
              f"{e['sha256'][:12]}")
    print("=" * 78)

    if not args.quiet:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.output:
        print(f"\nmanifest written to {args.output}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
