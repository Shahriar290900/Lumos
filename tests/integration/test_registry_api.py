"""
Registry service and API integration tests.

Covers the acceptance criteria for LUMOS-004A end to end: migration from an
empty database, a seed that matches the audited evidence, availability served
over HTTP, and — the point of the goal — a request for an unavailable subject
refused before anything downstream runs.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import psycopg
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

from services.curriculum.registry import (  # noqa: E402
    CurriculumRegistry,
    OfferingNotFound,
    OfferingUnavailable,
)


# ─────────────────────────────────────────────────────────────────────────────
# Migration
# ─────────────────────────────────────────────────────────────────────────────

def test_migration_from_empty_database_and_back(empty_database_url):
    """
    0001 in isolation: up → schema exists; down → schema gone; up → back again.

    Applied with `--to` so this stays a test of the registry migration alone.
    Later migrations get their own reversal tests; asserting on the union here
    would turn a precise test into one that has to be edited every time a
    migration is added.
    """
    REGISTRY = "0001_curriculum_registry"
    env = {**os.environ, "DATABASE_URL": empty_database_url}
    migrate = [sys.executable, str(REPO_ROOT / "packages/db/migrate.py")]

    EXPECTED_TABLES = {
        "curricula", "syllabus_versions", "subjects", "levels",
        "subject_offerings", "source_documents", "corpus_snapshots",
    }
    EXPECTED_VIEWS = {"curriculum_availability"}

    def relations() -> tuple[set[str], set[str]]:
        """(base tables, views) in public, excluding migration bookkeeping."""
        with psycopg.connect(empty_database_url) as c, c.cursor() as cur:
            cur.execute(
                "SELECT table_name, table_type FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_name <> 'schema_migrations'")
            rows = cur.fetchall()
        return ({n for n, t in rows if t == "BASE TABLE"},
                {n for n, t in rows if t == "VIEW"})

    assert relations() == (set(), set())

    subprocess.run(migrate + ["up", "--to", REGISTRY], env=env, check=True,
                   capture_output=True, text=True)
    assert relations() == (EXPECTED_TABLES, EXPECTED_VIEWS)

    with psycopg.connect(empty_database_url) as c, c.cursor() as cur:
        cur.execute("SELECT count(*) FROM curriculum_availability")
        assert cur.fetchone()[0] == 0          # schema present, no data

    subprocess.run(migrate + ["down", "--to", "0000"], env=env, check=True,
                   capture_output=True, text=True)
    assert relations() == (set(), set())       # reversible, leaves nothing behind

    subprocess.run(migrate + ["up", "--to", REGISTRY], env=env, check=True,
                   capture_output=True, text=True)
    assert relations() == (EXPECTED_TABLES, EXPECTED_VIEWS)   # re-appliable


def test_seed_is_idempotent(database_url):
    """Re-seeding updates rows rather than duplicating them."""
    def counts() -> tuple[int, int, int]:
        with psycopg.connect(database_url) as c, c.cursor() as cur:
            cur.execute("SELECT count(*) FROM subject_offerings")
            offerings = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM source_documents")
            docs = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM curricula")
            return offerings, docs, cur.fetchone()[0]

    before = counts()
    env = {**os.environ, "DATABASE_URL": database_url}
    cmd = [sys.executable, str(REPO_ROOT / "packages/db/seed/curriculum_seed.py"),
           "--audit", str(REPO_ROOT / "evidence/curriculum_audit_local.json")]
    catalog = REPO_ROOT / "evidence/source_catalog.json"
    if catalog.exists():
        cmd += ["--catalog", str(catalog)]
    subprocess.run(cmd, env=env, check=True, capture_output=True, text=True)

    offerings, docs, curricula = counts()
    assert (offerings, docs, curricula)[:1] == before[:1]
    assert docs == before[1]
    assert curricula == before[2]


# ─────────────────────────────────────────────────────────────────────────────
# Seed matches the audited evidence
# ─────────────────────────────────────────────────────────────────────────────

def test_seeded_counts_match_the_corpus_auditor(registry):
    """
    The registry's audited counts must equal the auditor's output.

    This is the guard against ADR-008 repeating itself: a hand-maintained figure
    drifting away from the data it claims to describe.
    """
    audit = json.loads(
        (REPO_ROOT / "evidence/curriculum_audit_local.json").read_text(encoding="utf-8"))
    by_subject = {k: v["records"] for k, v in audit["subjects"].items()}

    counts = registry.audited_record_counts()
    assert counts["nctb/ict/ssc"] == by_subject["ICT"]
    assert counts["nctb/english/ssc"] == by_subject["English"]
    assert counts["edexcel-ial/physics/a2"] == by_subject["Physics"]
    assert sum(counts.values()) == audit["total_records"]


def test_no_offering_is_available_yet(registry):
    """
    Nothing has been ingested, so nothing may be queried. If this test starts
    failing, either a corpus really was indexed and evaluated, or the rule broke.
    """
    assert registry.available_offerings() == []


def test_every_visible_unavailable_offering_explains_itself(registry):
    for o in registry.list_offerings():
        if not o.is_available:
            assert o.display_note_en, f"{o.slug} is unavailable with no English note"
            assert o.blocked_reasons, f"{o.slug} is unavailable with no reasons"


def test_empty_subjects_are_known_but_unavailable(registry):
    """Known-but-unavailable, so the UI can explain rather than omit."""
    for slug in ("nctb/chemistry/ssc", "nctb/biology/ssc",
                 "nctb/mathematics/ssc", "nctb/bangla/ssc"):
        o = registry.get_by_slug(slug)
        assert o.is_available is False
        assert o.publication_status == "planned"
        assert o.source_document_count == 0
        assert o.indexed_chunk_count == 0


def test_as_physics_offering_has_the_full_source_hierarchy(registry):
    """The demo corpus: papers, mark schemes, examiner reports and a textbook."""
    o = registry.get_by_slug("edexcel-ial/physics/international-as")
    docs = registry.source_documents(o.offering_id, include_private=True)
    types = {d["document_type"] for d in docs}
    assert {"past_paper", "mark_scheme", "examiner_report", "textbook"} <= types

    papers = {d["paper_code"] for d in docs if d["paper_code"]}
    assert papers == {"WPH11", "WPH12", "WPH13"}, "AS scope is units 1-3 only"

    official = [d for d in docs if d["source_priority"] == 1]
    assert len(official) == 9, "3 units x (paper, mark scheme, examiner report)"
    assert all(d["is_private"] for d in docs), "licensed sources must be marked private"


def test_a2_offering_holds_units_4_to_6_and_is_not_in_scope(registry):
    o = registry.get_by_slug("edexcel-ial/physics/a2")
    assert o.publication_status == "planned"
    docs = registry.source_documents(o.offering_id, include_private=True)
    papers = {d["paper_code"] for d in docs if d["paper_code"]}
    assert papers == {"WPH14", "WPH15", "WPH16"}


def test_private_sources_are_hidden_from_public_reads(registry):
    """A student-facing read must not enumerate licensed filenames."""
    o = registry.get_by_slug("edexcel-ial/physics/international-as")
    public = registry.source_documents(o.offering_id)
    assert public == [], "every Edexcel source is private and must not surface publicly"


def test_source_documents_are_ordered_most_authoritative_first(registry):
    o = registry.get_by_slug("edexcel-ial/physics/international-as")
    priorities = [d["source_priority"]
                  for d in registry.source_documents(o.offering_id, include_private=True)]
    assert priorities == sorted(priorities)


def test_ingestion_route_is_recorded_per_document(registry):
    """
    Route is per document, not per corpus: two examiner reports from the same
    session differ, so a single corpus-wide setting would be wrong.
    """
    o = registry.get_by_slug("edexcel-ial/physics/international-as")
    docs = registry.source_documents(o.offering_id, include_private=True)
    routes = {d["ingestion_route"] for d in docs}
    assert "ocr_required" in routes
    assert "text" in routes
    textbook = next(d for d in docs if d["document_type"] == "textbook")
    assert textbook["ingestion_route"] == "ocr_required"
    assert textbook["page_count"] == 225


# ─────────────────────────────────────────────────────────────────────────────
# The gate
# ─────────────────────────────────────────────────────────────────────────────

def test_require_available_raises_for_an_unavailable_offering(registry):
    with pytest.raises(OfferingUnavailable) as exc:
        registry.require_available(curriculum="NCTB", subject="BANGLA", level="SSC")
    assert "no_indexed_chunks" in exc.value.reasons
    assert exc.value.display_note_en


def test_require_available_raises_for_an_unknown_offering(registry):
    with pytest.raises(OfferingNotFound):
        registry.require_available(curriculum="NCTB", subject="ASTROLOGY", level="SSC")


def test_resolve_is_case_insensitive(registry):
    a = registry.resolve(curriculum="nctb", subject="ict", level="ssc")
    b = registry.resolve(curriculum="NCTB", subject="ICT", level="SSC")
    assert a.offering_id == b.offering_id


def test_ambiguous_resolution_is_refused_rather_than_guessed(registry, conn):
    """
    Two syllabus versions of the same subject and level must not resolve to
    whichever row the planner happened to return first.
    """
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM curricula WHERE code = 'NCTB'")
        cid = cur.fetchone()[0]
        cur.execute("SELECT id FROM subjects WHERE curriculum_id = %s AND code = 'ICT'", (cid,))
        sid = cur.fetchone()[0]
        cur.execute("SELECT id FROM levels WHERE curriculum_id = %s AND code = 'SSC'", (cid,))
        lid = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO syllabus_versions (curriculum_id, code, name) "
            "VALUES (%s, 'NCTB_SSC_2026', 'Revised') RETURNING id", (cid,))
        svid = cur.fetchone()[0]
        cur.execute(
            """
            INSERT INTO subject_offerings
                (curriculum_id, subject_id, level_id, syllabus_version_id, slug,
                 languages, publication_status, display_note_en)
            VALUES (%s, %s, %s, %s, 'nctb/ict/ssc-2026', ARRAY['bn'], 'planned', 'note')
            """, (cid, sid, lid, svid))

    with pytest.raises(OfferingNotFound, match="specify a syllabus version"):
        registry.resolve(curriculum="NCTB", subject="ICT", level="SSC")

    picked = registry.resolve(curriculum="NCTB", subject="ICT", level="SSC",
                              syllabus_version="NCTB_SSC_2026")
    assert picked.slug == "nctb/ict/ssc-2026"


# ─────────────────────────────────────────────────────────────────────────────
# HTTP
# ─────────────────────────────────────────────────────────────────────────────

def test_health_reports_the_database(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["database"] == "ok"
    assert body["available_offerings"] == 0


def test_curriculum_listing_returns_availability_and_notes(client):
    r = client.get("/curriculum")
    assert r.status_code == 200
    body = r.json()
    assert body["counts"]["total"] == 9
    assert body["counts"]["available"] == 0

    by_slug = {o["slug"]: o for o in body["offerings"]}
    assert "nctb/bangla/ssc" in by_slug
    bangla = by_slug["nctb/bangla/ssc"]
    assert bangla["is_available"] is False
    assert bangla["display_note_en"]
    assert bangla["display_note_bn"]
    assert "no_indexed_chunks" in bangla["blocked_reasons"]


def test_listing_never_leaks_licence_terms(client):
    body = client.get("/curriculum").json()
    for offering in body["offerings"]:
        assert "licence_status" not in offering


def test_available_only_filter(client):
    body = client.get("/curriculum", params={"available_only": True}).json()
    assert body["offerings"] == []


def test_offering_detail_includes_snapshots_with_provenance(client):
    r = client.get("/curriculum/NCTB/ICT/SSC")
    assert r.status_code == 200
    body = r.json()
    assert body["slug"] == "nctb/ict/ssc"
    snapshots = body["corpus_snapshots"]
    assert snapshots and snapshots[0]["record_count"] == 120
    assert snapshots[0]["method"] == "scripts/audit_corpus.py"
    assert snapshots[0]["evidence_ref"] == "evidence/curriculum_audit_local.json"


def test_offering_detail_404s_for_an_unknown_subject(client):
    assert client.get("/curriculum/NCTB/ASTROLOGY/SSC").status_code == 404


def test_tutor_refuses_an_unavailable_subject_before_retrieval(client):
    """The বাংলা case, over HTTP. 409 with reasons — never an answer."""
    r = client.post("/tutor/ask", json={
        "query": "বাংলা ব্যাকরণে কারক কী?",
        "curriculum": "NCTB", "subject": "BANGLA", "level": "SSC", "language": "bn",
    })
    assert r.status_code == 409
    detail = r.json()["detail"]
    assert detail["error"] == "subject_unavailable"
    assert detail["slug"] == "nctb/bangla/ssc"
    assert "no_indexed_chunks" in detail["blocked_reasons"]
    assert detail["message_bn"]
    # A refusal must not carry anything resembling a tutoring response.
    assert set(r.json()) == {"detail"}
    assert "answer" not in detail and "sources" not in detail


def test_tutor_refuses_every_seeded_offering_while_nothing_is_indexed(client):
    offerings = client.get("/curriculum").json()["offerings"]
    assert offerings
    for o in offerings:
        r = client.post("/tutor/ask", json={
            "query": "test",
            "curriculum": o["curriculum_code"],
            "subject": o["subject_code"],
            "level": o["level_code"],
        })
        assert r.status_code == 409, f"{o['slug']} returned {r.status_code}, expected 409"
        assert r.json()["detail"]["error"] == "subject_unavailable"


def test_tutor_404s_for_an_unknown_subject(client):
    r = client.post("/tutor/ask", json={
        "query": "test", "curriculum": "NCTB", "subject": "ASTROLOGY", "level": "SSC"})
    assert r.status_code == 404
    assert r.json()["detail"]["error"] == "unknown_offering"


def test_tutor_rejects_a_malformed_request(client):
    assert client.post("/tutor/ask", json={"query": "", "curriculum": "NCTB",
                                           "subject": "ICT", "level": "SSC"}).status_code == 422


def test_the_slug_the_listing_publishes_resolves_at_the_tutor_route(client):
    """
    Every offering must be reachable using the identifiers `/curriculum` prints.

    Found by driving the running API. `GET /curriculum` publishes the slug
    `edexcel-ial/physics/international-as`, but the stored codes are
    `EDEXCEL_IAL` / `INTERNATIONAL_AS`, and the resolver folded case without
    folding the separator. Posting the published segments back returned 404
    `unknown_offering` — the API telling a client that the one offering in demo
    scope does not exist, immediately after listing it.

    A 404 that contradicts the listing endpoint is a worse failure than a strict
    match is a benefit, so the resolver now treats `-` and `_` as one separator.
    """
    offerings = client.get("/curriculum").json()["offerings"]
    assert offerings

    for o in offerings:
        r = client.post("/tutor/ask", json={"query": "test", "slug": o["slug"]})
        assert r.status_code != 404, (
            f"slug {o['slug']!r} is published by /curriculum but does not "
            f"resolve at /tutor/ask")
        # Nothing is indexed, so the correct answer is 'unavailable', never an answer.
        assert r.status_code == 409
        assert r.json()["detail"]["slug"] == o["slug"]


def test_identifier_matching_folds_case_and_separator_together(client):
    """The same offering, named four ways a real client might name it."""
    forms = [
        ("edexcel-ial", "physics", "international-as"),   # as /curriculum prints it
        ("EDEXCEL_IAL", "PHYSICS", "INTERNATIONAL_AS"),   # as the registry stores it
        ("edexcel_ial", "physics", "international_as"),   # lowercase, underscores
        ("Edexcel-IAL", "Physics", "International_AS"),   # mixed, as a human types it
    ]
    slugs = set()
    for curriculum, subject, level in forms:
        r = client.post("/tutor/ask", json={
            "query": "test", "curriculum": curriculum,
            "subject": subject, "level": level})
        assert r.status_code == 409, f"{curriculum}/{subject}/{level} → {r.status_code}"
        slugs.add(r.json()["detail"]["slug"])

    assert slugs == {"edexcel-ial/physics/international-as"}, (
        f"the four spellings resolved to {slugs}, not to one offering")


def test_widening_the_match_did_not_make_unknown_subjects_resolve(client):
    """Folding separators must not turn a real 404 into a false match."""
    for curriculum, subject, level in [
        ("nctb", "astrology", "ssc"),
        ("nctb-fake", "ict", "ssc"),
        ("edexcel-ial", "physics", "international-gcse"),
    ]:
        r = client.post("/tutor/ask", json={
            "query": "test", "curriculum": curriculum,
            "subject": subject, "level": level})
        assert r.status_code == 404, f"{curriculum}/{subject}/{level} should not resolve"
        assert r.json()["detail"]["error"] == "unknown_offering"
