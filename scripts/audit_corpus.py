#!/usr/bin/env python3
"""
audit_corpus.py — Lumos legacy-corpus audit and verification tool.

Reproduces every corpus number quoted in RECONNAISSANCE_REPORT.md,
CURRICULUM_INVENTORY.md, COVERAGE_MATRIX.md and CHUNKED_DATA_AUDIT.md.

It is deliberately dependency-free (stdlib only) so an external evaluator can
run it against a fresh clone of the legacy repositories and confirm the figures
without installing anything.

Usage
-----
    # audit one directory of JSONL files
    python scripts/audit_corpus.py /path/to/Shikhbo-Local-App/raw_data

    # audit several roots and cross-check for duplication between them
    python scripts/audit_corpus.py \
        /path/to/Shikhbo-Local-App/raw_data \
        /path/to/shikhbo-ai \
        --output evidence/curriculum_audit.json

Exit codes
----------
    0  audit completed (findings are reported, not treated as failures)
    2  no JSONL files found under any supplied root
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

# Fields the legacy corpora are expected to share. Absence is reported, not fatal.
COMMON_FIELDS = {
    "chunk_id", "class", "subject", "chapter_no", "page_no",
    "topic", "prerequisite", "keywords", "token_count", "content",
}

# Fields the canonical Lumos schema requires that legacy records never carry.
# See docs/CHUNK_SCHEMA.md. Reported as a migration gap.
CANONICAL_GAP_FIELDS = [
    "curriculum", "curriculum_version", "language", "document_type",
    "source_id", "source_priority", "provenance_hash",
    "question_number", "sub_question", "marks",
    "parent_question_id", "depends_on", "ingestion_version",
]

BANGLA_RE = re.compile(r"[ঀ-৿]")

# Known OCR/extraction artefact signatures observed in the legacy corpus.
# Each entry is (label, compiled pattern).
ARTEFACT_PATTERNS = [
    ("bangla_duplicated_vowel_sign", re.compile(r"যয|োো|িি")),
    ("bullet_ocr_as_letter_e", re.compile(r"(?:^|\n)\s*e\s+[A-Z]")),
    ("stray_control_chars", re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")),
    ("repeated_whitespace_run", re.compile(r" {4,}")),
    ("broken_word_split", re.compile(r"\b\w+-\s+\w+\b")),
]


def _iter_records(path: Path):
    """Yield (line_number, record_or_None, error_or_None) for a JSONL file."""
    with path.open(encoding="utf-8", errors="replace") as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                yield lineno, json.loads(line), None
            except Exception as exc:  # noqa: BLE001 - report, don't crash
                yield lineno, None, str(exc)


def _content_of(rec: dict) -> str:
    for key in ("content", "text", "answer"):
        val = rec.get(key)
        if isinstance(val, str):
            return val
    return ""


def audit_roots(roots: list[Path]) -> dict[str, Any]:
    files: list[tuple[Path, Path]] = []  # (root, file)
    for root in roots:
        if root.is_file() and root.suffix == ".jsonl":
            files.append((root.parent, root))
        else:
            files.extend((root, f) for f in sorted(root.glob("*.jsonl")))

    if not files:
        return {}

    per_file: list[dict[str, Any]] = []
    by_subject: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "files": set(), "records": 0, "classes": set(), "chapters": set(),
            "token_counts": [], "content_chars": [], "bangla_records": 0,
            "missing_common_fields": Counter(),
        }
    )
    content_hashes: dict[str, list[str]] = defaultdict(list)
    chunk_ids: Counter = Counter()
    errors: list[dict[str, Any]] = []
    artefact_hits: Counter = Counter()
    artefact_examples: dict[str, str] = {}
    canonical_gaps: Counter = Counter()
    total = 0

    for root, fp in files:
        rel = str(fp.relative_to(root.parent if root.is_dir() else root))
        f_records = 0
        f_subjects: set[str] = set()
        f_chars = 0
        for lineno, rec, err in _iter_records(fp):
            if err is not None:
                errors.append({"file": rel, "line": lineno, "error": err})
                continue
            if not isinstance(rec, dict):
                errors.append({"file": rel, "line": lineno, "error": "record is not an object"})
                continue

            total += 1
            f_records += 1
            subject = str(rec.get("subject", "UNKNOWN"))
            f_subjects.add(subject)
            entry = by_subject[subject]
            entry["files"].add(rel)
            entry["records"] += 1
            if rec.get("class") is not None:
                entry["classes"].add(str(rec["class"]))
            if rec.get("chapter_no") is not None:
                entry["chapters"].add(str(rec["chapter_no"]))
            if isinstance(rec.get("token_count"), (int, float)):
                entry["token_counts"].append(rec["token_count"])
            for key in COMMON_FIELDS:
                if key not in rec:
                    entry["missing_common_fields"][key] += 1
            for key in CANONICAL_GAP_FIELDS:
                if key not in rec:
                    canonical_gaps[key] += 1

            cid = rec.get("chunk_id")
            if cid is not None:
                chunk_ids[str(cid)] += 1

            content = _content_of(rec)
            f_chars += len(content)
            entry["content_chars"].append(len(content))
            if BANGLA_RE.search(content):
                entry["bangla_records"] += 1

            digest = hashlib.sha256(content.strip().lower().encode("utf-8")).hexdigest()
            content_hashes[digest].append(f"{rel}#{cid or lineno}")

            for label, pattern in ARTEFACT_PATTERNS:
                if pattern.search(content):
                    artefact_hits[label] += 1
                    artefact_examples.setdefault(label, f"{rel}#{cid or lineno}")

        per_file.append({
            "file": rel,
            "bytes": fp.stat().st_size,
            "records": f_records,
            "content_chars": f_chars,
            "subjects": sorted(f_subjects),
        })

    duplicate_content = {
        h: locs for h, locs in content_hashes.items() if len(locs) > 1
    }
    duplicate_ids = {cid: n for cid, n in chunk_ids.items() if n > 1}

    subjects_out: dict[str, Any] = {}
    for subject, c in sorted(by_subject.items()):
        toks = c["token_counts"]
        chars = c["content_chars"]
        subjects_out[subject] = {
            "files": len(c["files"]),
            "records": c["records"],
            "classes": sorted(c["classes"]),
            "chapters": sorted(c["chapters"], key=lambda s: (len(s), s)),
            "records_containing_bangla": c["bangla_records"],
            "declared_token_count": {
                "min": min(toks) if toks else None,
                "median": statistics.median(toks) if toks else None,
                "max": max(toks) if toks else None,
            },
            "content_chars": {
                "min": min(chars) if chars else None,
                "median": statistics.median(chars) if chars else None,
                "max": max(chars) if chars else None,
            },
            "missing_common_fields": dict(c["missing_common_fields"]),
        }

    return {
        "roots": [str(r) for r in roots],
        "jsonl_files": len(files),
        "total_records": total,
        "unique_content_blocks": len(content_hashes),
        "records_sharing_content_with_another_record": sum(
            len(v) for v in duplicate_content.values()
        ),
        "duplicate_content_groups": len(duplicate_content),
        "duplicate_chunk_ids": duplicate_ids,
        "parse_errors": errors,
        "subjects": subjects_out,
        "per_file": per_file,
        "ocr_artefact_hits": {
            label: {"records": n, "example": artefact_examples.get(label)}
            for label, n in sorted(artefact_hits.items(), key=lambda kv: -kv[1])
        },
        "canonical_schema_gaps": {
            "explanation": (
                "Number of legacy records missing each field required by the "
                "canonical Lumos chunk schema (docs/CHUNK_SCHEMA.md)."
            ),
            "missing_counts": dict(canonical_gaps),
            "total_records": total,
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("roots", nargs="+", type=Path, help="Directories (or .jsonl files) to audit")
    ap.add_argument("--output", type=Path, default=None, help="Write the full JSON report here")
    ap.add_argument("--quiet", action="store_true", help="Print the summary only, not the full JSON")
    args = ap.parse_args()

    result = audit_roots(args.roots)
    if not result:
        print("No JSONL files found under: " + ", ".join(str(r) for r in args.roots), file=sys.stderr)
        return 2

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=" * 68)
    print(f"JSONL files            : {result['jsonl_files']}")
    print(f"Total records          : {result['total_records']}")
    print(f"Unique content blocks  : {result['unique_content_blocks']}")
    print(f"Duplicate content grps : {result['duplicate_content_groups']}")
    print(f"Duplicate chunk_ids    : {len(result['duplicate_chunk_ids'])}")
    print(f"Parse errors           : {len(result['parse_errors'])}")
    print("-" * 68)
    for subject, s in result["subjects"].items():
        print(
            f"{subject:<10} files={s['files']:<3} records={s['records']:<5} "
            f"classes={','.join(s['classes']):<10} "
            f"content_chars(med)={s['content_chars']['median']}"
        )
    print("-" * 68)
    for label, info in result["ocr_artefact_hits"].items():
        print(f"artefact {label:<32} records={info['records']}")
    print("=" * 68)

    if not args.quiet:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.output:
        print(f"\nFull report written to {args.output}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
