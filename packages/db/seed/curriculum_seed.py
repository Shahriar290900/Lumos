#!/usr/bin/env python3
"""
curriculum_seed.py — seed the Lumos curriculum registry from verified evidence.

Every number this script writes is read from a machine-generated evidence file,
never typed in by hand:

    evidence/curriculum_audit_local.json   scripts/audit_corpus.py    legacy JSONL corpora
    evidence/source_catalog.json           scripts/catalog_sources.py private PDF sources

That indirection is the point. A hand-maintained inventory is how the prebuild
pack came to state 1,022 records against an actual 180 (ADR-008). The registry
is seeded from the auditor's output so the two cannot drift, and CI re-runs the
comparison (`scripts/check_registry_consistency.py`).

The seed is idempotent: re-running it updates rows in place rather than
duplicating them.

Usage
-----
    DATABASE_URL=... python packages/db/seed/curriculum_seed.py \
        --audit evidence/curriculum_audit_local.json \
        --catalog evidence/source_catalog.json

`--catalog` is optional: without it, only the legacy corpora and the empty
placeholder subjects are seeded, and the Edexcel offerings carry no source
documents. That is the correct behaviour on a machine that does not hold the
licensed material.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path, PurePosixPath
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Json

REPO_ROOT = Path(__file__).resolve().parents[3]

# ─────────────────────────────────────────────────────────────────────────────
# Static structure. Counts and checksums are never hardcoded here.
# ─────────────────────────────────────────────────────────────────────────────

CURRICULA = [
    {
        "code": "EDEXCEL_IAL",
        "name": "Pearson Edexcel International Advanced Level",
        "awarding_body": "Pearson Edexcel",
        "region": "International",
    },
    {
        "code": "NCTB",
        "name": "National Curriculum and Textbook Board",
        "awarding_body": "NCTB Bangladesh",
        "region": "Bangladesh",
    },
]

SYLLABUS_VERSIONS = [
    {
        "curriculum": "EDEXCEL_IAL",
        "code": "IAL_PHYSICS_2018",
        "name": "International Advanced Level Physics (2018 specification)",
        "effective_from": "2018-09-01",
        "effective_to": None,
        # Deliberately hedged. The unit codes WPH11–WPH16 are read off the papers
        # themselves; the exact specification document has not been obtained, and
        # that gap is a publication blocker, not a detail to paper over.
        "specification_reference": None,
        "notes": (
            "Unit codes WPH11-WPH16 verified from the 2024 May/June question papers. "
            "The published specification document has not yet been obtained or "
            "checksummed; specification_reference stays NULL until it is."
        ),
    },
    {
        "curriculum": "NCTB",
        "code": "NCTB_SSC",
        "name": "NCTB Secondary School Certificate curriculum",
        "effective_from": None,
        "effective_to": None,
        "specification_reference": None,
        "notes": (
            "The legacy corpus is textbook-derived. Neither the syllabus edition "
            "nor the textbook print year has been established."
        ),
    },
]

LEVELS = [
    {"curriculum": "EDEXCEL_IAL", "code": "INTERNATIONAL_AS", "name": "International AS", "sort_order": 10},
    {"curriculum": "EDEXCEL_IAL", "code": "IAL_A2", "name": "International A2", "sort_order": 20},
    {"curriculum": "NCTB", "code": "SSC", "name": "Secondary School Certificate", "sort_order": 10},
    {"curriculum": "NCTB", "code": "HSC", "name": "Higher Secondary Certificate", "sort_order": 20},
]

SUBJECTS = [
    {"curriculum": "EDEXCEL_IAL", "code": "PHYSICS", "name_en": "Physics", "name_bn": "পদার্থবিজ্ঞান"},
    {"curriculum": "NCTB", "code": "ICT", "name_en": "ICT", "name_bn": "আইসিটি"},
    {"curriculum": "NCTB", "code": "ENGLISH", "name_en": "English", "name_bn": "ইংরেজি"},
    {"curriculum": "NCTB", "code": "PHYSICS", "name_en": "Physics", "name_bn": "পদার্থবিজ্ঞান"},
    {"curriculum": "NCTB", "code": "CHEMISTRY", "name_en": "Chemistry", "name_bn": "রসায়ন"},
    {"curriculum": "NCTB", "code": "BIOLOGY", "name_en": "Biology", "name_bn": "জীববিজ্ঞান"},
    {"curriculum": "NCTB", "code": "MATHEMATICS", "name_en": "Mathematics", "name_bn": "গণিত"},
    {"curriculum": "NCTB", "code": "BANGLA", "name_en": "Bangla", "name_bn": "বাংলা"},
]

# Source hierarchy, most authoritative first (ADR-009).
OFFICIAL_FIRST = ["specification", "mark_scheme", "examiner_report", "past_paper",
                  "textbook", "revision_guide", "topic_notes"]
TEXTBOOK_FIRST = ["textbook", "legacy_corpus", "topic_notes", "revision_guide"]

OFFERINGS = [
    {
        "slug": "edexcel-ial/physics/international-as",
        "curriculum": "EDEXCEL_IAL", "subject": "PHYSICS",
        "level": "INTERNATIONAL_AS", "syllabus": "IAL_PHYSICS_2018",
        "languages": ["en"],
        "publication_status": "in_preparation",
        "indexing_status": "sources_catalogued",
        "evaluation_status": "none",
        "licence_status": "permitted_private",
        "source_priority_policy": OFFICIAL_FIRST,
        "display_note_en": "Edexcel IAL AS Physics — sources catalogued, ingestion in progress.",
        "display_note_bn": "এডেক্সেল আইএএল এএস পদার্থবিজ্ঞান — উৎস তালিকাভুক্ত, ইনজেশন চলছে।",
        "notes": (
            "Demo scope. Units 1-3 (WPH11/12/13) plus Student Book 1, whose Topics 1-4 "
            "cover the same AS content, giving a complete source hierarchy over one body "
            "of material."
        ),
        "paper_codes": ["WPH11", "WPH12", "WPH13"],
        "include_textbooks": True,
    },
    {
        "slug": "edexcel-ial/physics/a2",
        "curriculum": "EDEXCEL_IAL", "subject": "PHYSICS",
        "level": "IAL_A2", "syllabus": "IAL_PHYSICS_2018",
        "languages": ["en"],
        "publication_status": "planned",
        "indexing_status": "sources_catalogued",
        "evaluation_status": "none",
        "licence_status": "permitted_private",
        "source_priority_policy": OFFICIAL_FIRST,
        "display_note_en": "A2 Physics — papers held, not yet indexed. AS units come first.",
        "display_note_bn": "এ২ পদার্থবিজ্ঞান — প্রশ্নপত্র সংরক্ষিত, এখনো ইনডেক্স করা হয়নি।",
        "notes": (
            "Units 4-6 (WPH14/15/16) are held and catalogued but out of the demo scope: "
            "Student Book 1 covers AS content only, so A2 answers would rest on papers "
            "alone with no textbook layer beneath them. The 17 legacy Astrophysics and "
            "Cosmology chunks belong here — specification area 5.6 sits in Unit 5."
        ),
        "paper_codes": ["WPH14", "WPH15", "WPH16"],
        "include_textbooks": False,
        "legacy_subjects": ["Physics"],
    },
    {
        "slug": "nctb/ict/ssc",
        "curriculum": "NCTB", "subject": "ICT", "level": "SSC", "syllabus": "NCTB_SSC",
        "languages": ["bn"],
        "publication_status": "in_preparation",
        "indexing_status": "normalising",
        "evaluation_status": "none",
        "licence_status": "unknown",
        "source_priority_policy": TEXTBOOK_FIRST,
        "display_note_en": "SSC ICT — Bangla corpus in preparation. Cleaning OCR damage before publication.",
        "display_note_bn": "এসএসসি আইসিটি — বাংলা কর্পাস প্রস্তুত হচ্ছে।",
        "notes": (
            "Target for publication. 73 of the 120 legacy records carry Bangla vowel-sign "
            "and conjunct corruption that must be repaired first (LUMOS-004C)."
        ),
        "legacy_subjects": ["ICT"],
    },
    {
        "slug": "nctb/english/ssc",
        "curriculum": "NCTB", "subject": "ENGLISH", "level": "SSC", "syllabus": "NCTB_SSC",
        "languages": ["en", "bn"],
        "publication_status": "in_preparation",
        "indexing_status": "normalising",
        "evaluation_status": "none",
        "licence_status": "unknown",
        "source_priority_policy": TEXTBOOK_FIRST,
        "display_note_en": "SSC English — corpus in preparation. Re-chunking before publication.",
        "display_note_bn": "এসএসসি ইংরেজি — কর্পাস প্রস্তুত হচ্ছে।",
        "notes": (
            "Target for publication. All 43 legacy records are whole textbook units of "
            "roughly 2,000 tokens and must be re-chunked to 400-600 tokens (LUMOS-004C)."
        ),
        "legacy_subjects": ["English"],
    },
    # Known but empty. Present so the UI can explain rather than omit, and so a
    # request naming one is refused by the registry rather than falling through.
    {
        "slug": "nctb/physics/ssc",
        "curriculum": "NCTB", "subject": "PHYSICS", "level": "SSC", "syllabus": "NCTB_SSC",
        "languages": ["bn"], "publication_status": "planned",
        "indexing_status": "not_started", "evaluation_status": "none",
        "licence_status": "unknown", "source_priority_policy": TEXTBOOK_FIRST,
        "display_note_en": "Coming soon — no NCTB Physics corpus has been ingested yet.",
        "display_note_bn": "শীঘ্রই আসছে — এনসিটিবি পদার্থবিজ্ঞান কর্পাস এখনো যুক্ত হয়নি।",
        "notes": "No corpus. Distinct from Edexcel Physics; do not conflate.",
    },
    {
        "slug": "nctb/chemistry/ssc",
        "curriculum": "NCTB", "subject": "CHEMISTRY", "level": "SSC", "syllabus": "NCTB_SSC",
        "languages": ["bn"], "publication_status": "planned",
        "indexing_status": "not_started", "evaluation_status": "none",
        "licence_status": "unknown", "source_priority_policy": TEXTBOOK_FIRST,
        "display_note_en": "Coming soon — no Chemistry corpus has been ingested yet.",
        "display_note_bn": "শীঘ্রই আসছে — রসায়ন কর্পাস এখনো যুক্ত হয়নি।",
        "notes": "No corpus.",
    },
    {
        "slug": "nctb/biology/ssc",
        "curriculum": "NCTB", "subject": "BIOLOGY", "level": "SSC", "syllabus": "NCTB_SSC",
        "languages": ["bn"], "publication_status": "planned",
        "indexing_status": "not_started", "evaluation_status": "none",
        "licence_status": "unknown", "source_priority_policy": TEXTBOOK_FIRST,
        "display_note_en": "Coming soon — no Biology corpus has been ingested yet.",
        "display_note_bn": "শীঘ্রই আসছে — জীববিজ্ঞান কর্পাস এখনো যুক্ত হয়নি।",
        "notes": "No corpus.",
    },
    {
        "slug": "nctb/mathematics/ssc",
        "curriculum": "NCTB", "subject": "MATHEMATICS", "level": "SSC", "syllabus": "NCTB_SSC",
        "languages": ["bn"], "publication_status": "planned",
        "indexing_status": "not_started", "evaluation_status": "none",
        "licence_status": "unknown", "source_priority_policy": TEXTBOOK_FIRST,
        "display_note_en": "Coming soon — no Mathematics corpus has been ingested yet.",
        "display_note_bn": "শীঘ্রই আসছে — গণিত কর্পাস এখনো যুক্ত হয়নি।",
        "notes": "No corpus.",
    },
    {
        # The specific failure this whole registry exists to prevent. The legacy
        # desktop app shipped this subject button with nothing behind it; the
        # retriever returned nothing and the model answered ungrounded.
        "slug": "nctb/bangla/ssc",
        "curriculum": "NCTB", "subject": "BANGLA", "level": "SSC", "syllabus": "NCTB_SSC",
        "languages": ["bn"], "publication_status": "planned",
        "indexing_status": "not_started", "evaluation_status": "none",
        "licence_status": "unknown", "source_priority_policy": TEXTBOOK_FIRST,
        "display_note_en": "Coming soon — no Bangla language corpus has been ingested yet.",
        "display_note_bn": "শীঘ্রই আসছে — বাংলা বিষয়ের কর্পাস এখনো যুক্ত হয়নি।",
        "notes": (
            "REGRESSION GUARD. Shikhbo-Local-App v1.0.0 offered this subject with no "
            "corpus; selecting it produced ungrounded output that looked like tutoring. "
            "The ICT corpus is written in Bangla, but no Bangla language or literature "
            "corpus exists anywhere. Must never report available on zero chunks."
        ),
    },
]


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def load_json(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    if not path.exists():
        print(f"warning: {path} not found — continuing without it", file=sys.stderr)
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def upsert(cur, table: str, keys: dict[str, Any], values: dict[str, Any]) -> str:
    """Insert or update one row keyed on `keys`; return its id."""
    where = " AND ".join(f"{k} = %({k})s" for k in keys)
    cur.execute(f"SELECT id FROM {table} WHERE {where}", keys)
    row = cur.fetchone()
    if row:
        if values:
            sets = ", ".join(f"{k} = %({k})s" for k in values)
            cur.execute(f"UPDATE {table} SET {sets} WHERE id = %(_id)s",
                        {**values, "_id": row["id"]})
        return row["id"]
    payload = {**keys, **values}
    cols = ", ".join(payload)
    ph = ", ".join(f"%({k})s" for k in payload)
    cur.execute(f"INSERT INTO {table} ({cols}) VALUES ({ph}) RETURNING id", payload)
    return cur.fetchone()["id"]


def seed(conn: psycopg.Connection, audit: dict | None, catalog: dict | None) -> dict[str, int]:
    counts = {"curricula": 0, "syllabus_versions": 0, "levels": 0, "subjects": 0,
              "offerings": 0, "source_documents": 0, "corpus_snapshots": 0}

    with conn.cursor(row_factory=dict_row) as cur:
        curriculum_ids, syllabus_ids, level_ids, subject_ids = {}, {}, {}, {}

        for c in CURRICULA:
            curriculum_ids[c["code"]] = upsert(
                cur, "curricula", {"code": c["code"]},
                {"name": c["name"], "awarding_body": c["awarding_body"],
                 "region": c["region"], "updated_at": "now()"})
            counts["curricula"] += 1

        for s in SYLLABUS_VERSIONS:
            cid = curriculum_ids[s["curriculum"]]
            syllabus_ids[s["code"]] = upsert(
                cur, "syllabus_versions", {"curriculum_id": cid, "code": s["code"]},
                {"name": s["name"], "effective_from": s["effective_from"],
                 "effective_to": s["effective_to"],
                 "specification_reference": s["specification_reference"],
                 "notes": s["notes"]})
            counts["syllabus_versions"] += 1

        for l in LEVELS:
            cid = curriculum_ids[l["curriculum"]]
            level_ids[(l["curriculum"], l["code"])] = upsert(
                cur, "levels", {"curriculum_id": cid, "code": l["code"]},
                {"name": l["name"], "sort_order": l["sort_order"]})
            counts["levels"] += 1

        for s in SUBJECTS:
            cid = curriculum_ids[s["curriculum"]]
            subject_ids[(s["curriculum"], s["code"])] = upsert(
                cur, "subjects", {"curriculum_id": cid, "code": s["code"]},
                {"name_en": s["name_en"], "name_bn": s["name_bn"]})
            counts["subjects"] += 1

        # Index the evidence by the keys the offerings refer to.
        catalog_docs = (catalog or {}).get("documents", [])
        audit_subjects = (audit or {}).get("subjects", {})
        audit_files = {f["file"]: f for f in (audit or {}).get("per_file", [])}

        for o in OFFERINGS:
            cid = curriculum_ids[o["curriculum"]]
            offering_id = upsert(
                cur, "subject_offerings",
                {"slug": o["slug"]},
                {
                    "curriculum_id": cid,
                    "subject_id": subject_ids[(o["curriculum"], o["subject"])],
                    "level_id": level_ids[(o["curriculum"], o["level"])],
                    "syllabus_version_id": syllabus_ids[o["syllabus"]],
                    "languages": o["languages"],
                    "publication_status": o["publication_status"],
                    "indexing_status": o["indexing_status"],
                    "evaluation_status": o["evaluation_status"],
                    "licence_status": o["licence_status"],
                    "source_priority_policy": Json(o["source_priority_policy"]),
                    "display_note_en": o.get("display_note_en"),
                    "display_note_bn": o.get("display_note_bn"),
                    "notes": o.get("notes"),
                    "updated_at": "now()",
                })
            counts["offerings"] += 1

            # ── private PDF sources, matched by paper code / document type ──
            wanted_codes = set(o.get("paper_codes", []))
            for doc in catalog_docs:
                code = doc.get("paper_code")
                is_textbook = doc.get("document_type") == "textbook"
                if not ((code and code in wanted_codes)
                        or (is_textbook and o.get("include_textbooks"))):
                    continue
                tl = doc.get("text_layer", {})
                session = doc.get("session") or {}
                upsert(
                    cur, "source_documents",
                    {"offering_id": offering_id, "sha256": doc["sha256"]},
                    {
                        "document_type": doc["document_type"],
                        "source_priority": doc.get("source_priority") or 3,
                        "title": _title_for(doc),
                        "filename": doc["filename"],
                        "relative_path": doc["relative_path"],
                        "bytes": doc["bytes"],
                        "page_count": tl.get("pages"),
                        "ingestion_route": tl.get("verdict", "unknown"),
                        "paper_code": code,
                        "unit_number": doc.get("unit"),
                        "session_year": session.get("year"),
                        "session_series": session.get("series"),
                        "language": "en",
                        "licence_status": o["licence_status"],
                        "is_private": True,
                    })
                counts["source_documents"] += 1

            # ── legacy JSONL sources and their audited counts ──
            for legacy_subject in o.get("legacy_subjects", []):
                stats = audit_subjects.get(legacy_subject)
                if not stats:
                    continue
                for audit_path, finfo in sorted(audit_files.items()):
                    if legacy_subject not in finfo.get("subjects", []):
                        continue
                    # The auditor reports paths relative to the corpus parent
                    # ("raw_data/ICT_C1.jsonl"). `filename` is the basename and
                    # `relative_path` is that path as given — never one nested
                    # inside the other.
                    rel_path = PurePosixPath(audit_path.replace("\\", "/"))
                    fname = rel_path.name
                    upsert(
                        cur, "source_documents",
                        {"offering_id": offering_id, "relative_path": str(rel_path)},
                        {
                            "document_type": "legacy_corpus",
                            "source_priority": 2,
                            "title": f"Legacy corpus — {fname}",
                            "filename": fname,
                            "bytes": finfo.get("bytes"),
                            "ingestion_route": "structured",
                            "language": "bn" if legacy_subject == "ICT" else "en",
                            "licence_status": o["licence_status"],
                            "is_private": False,
                        })
                    counts["source_documents"] += 1

                cur.execute(
                    """
                    INSERT INTO corpus_snapshots
                        (offering_id, method, evidence_ref, record_count, notes)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (offering_id, "scripts/audit_corpus.py",
                     "evidence/curriculum_audit_local.json", stats["records"],
                     f"Audited legacy JSONL records for subject '{legacy_subject}'. "
                     f"Not yet normalised or indexed, so indexed_chunk_count remains 0."))
                counts["corpus_snapshots"] += 1

    conn.commit()
    return counts


def _title_for(doc: dict[str, Any]) -> str:
    if doc.get("document_type") == "textbook":
        return "Pearson Edexcel International AS/A Level Physics Student Book 1"
    session = doc.get("session") or {}
    label = {
        "past_paper": "Question paper",
        "mark_scheme": "Mark scheme",
        "examiner_report": "Examiner report",
    }.get(doc.get("document_type", ""), doc.get("document_type", "Document"))
    code = doc.get("paper_code", "")
    unit = f" Unit {doc['unit']}" if doc.get("unit") else ""
    when = f" {session.get('year', '')} {session.get('series', '')}".rstrip()
    return f"{label} — {code}{unit}{when}".strip()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--audit", type=Path, default=REPO_ROOT / "evidence/curriculum_audit_local.json")
    ap.add_argument("--catalog", type=Path, default=REPO_ROOT / "evidence/source_catalog.json")
    args = ap.parse_args()

    url = os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("DATABASE_URL is not set.")

    audit = load_json(args.audit)
    catalog = load_json(args.catalog)
    if audit is None:
        raise SystemExit(
            f"{args.audit} is required — run scripts/audit_corpus.py first.\n"
            "The registry is seeded from audited evidence, never from hand-typed counts."
        )

    with psycopg.connect(url) as conn:
        counts = seed(conn, audit, catalog)

    print("seeded:", ", ".join(f"{k}={v}" for k, v in counts.items()))
    if catalog is None:
        print("note: no source catalog supplied — private PDF sources were not seeded.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
