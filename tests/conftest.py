"""
Shared test fixtures.

Every test runs against a real PostgreSQL database created for the session and
dropped afterwards. There is no mock database and no SQLite substitute: the
availability rule lives in a SQL view and enum/CHECK constraints do real work,
so testing against anything else would test a different system.

Set `TEST_DATABASE_URL` (or `DATABASE_URL`) to a server the test user may create
databases on. The whole suite runs with `AI_PROVIDER=mock` and needs no model
credential of any kind.
"""

from __future__ import annotations

import os
import subprocess
import sys
import uuid
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import psycopg
import pytest
from psycopg.rows import dict_row

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

MIGRATE = REPO_ROOT / "packages/db/migrate.py"
SEED = REPO_ROOT / "packages/db/seed/curriculum_seed.py"
AUDIT_EVIDENCE = REPO_ROOT / "evidence/curriculum_audit_local.json"
CATALOG_EVIDENCE = REPO_ROOT / "evidence/source_catalog.json"


def _admin_url() -> str:
    url = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL / DATABASE_URL not set — cannot run database tests")
    return url


def _with_database(url: str, dbname: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, f"/{dbname}", parts.query, parts.fragment))


@pytest.fixture(scope="session")
def database_url() -> str:
    """A throwaway database with the schema applied and the registry seeded."""
    admin = _admin_url()
    name = f"lumos_test_{uuid.uuid4().hex[:10]}"

    with psycopg.connect(_with_database(admin, "postgres"), autocommit=True) as conn:
        conn.execute(f'CREATE DATABASE "{name}"')

    url = _with_database(admin, name)
    env = {**os.environ, "DATABASE_URL": url, "AI_PROVIDER": "mock"}

    subprocess.run([sys.executable, str(MIGRATE), "up"], env=env, check=True,
                   capture_output=True, text=True)
    cmd = [sys.executable, str(SEED), "--audit", str(AUDIT_EVIDENCE)]
    if CATALOG_EVIDENCE.exists():
        cmd += ["--catalog", str(CATALOG_EVIDENCE)]
    subprocess.run(cmd, env=env, check=True, capture_output=True, text=True)

    yield url

    with psycopg.connect(_with_database(admin, "postgres"), autocommit=True) as conn:
        conn.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s", (name,))
        conn.execute(f'DROP DATABASE IF EXISTS "{name}"')


@pytest.fixture
def empty_database_url() -> str:
    """
    A database with nothing in it, for migration tests.

    Function-scoped on purpose: two migration tests sharing one database would
    each start from whatever the other left behind, and "migration from empty"
    would stop meaning anything.
    """
    admin = _admin_url()
    name = f"lumos_empty_{uuid.uuid4().hex[:10]}"
    with psycopg.connect(_with_database(admin, "postgres"), autocommit=True) as conn:
        conn.execute(f'CREATE DATABASE "{name}"')
    yield _with_database(admin, name)
    with psycopg.connect(_with_database(admin, "postgres"), autocommit=True) as conn:
        conn.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s", (name,))
        conn.execute(f'DROP DATABASE IF EXISTS "{name}"')


@pytest.fixture
def conn(database_url: str):
    """A connection that rolls back everything the test did."""
    with psycopg.connect(database_url) as c:
        c.autocommit = False
        yield c
        c.rollback()


@pytest.fixture
def dict_conn(database_url: str):
    with psycopg.connect(database_url, row_factory=dict_row) as c:
        c.autocommit = False
        yield c
        c.rollback()


@pytest.fixture
def registry(conn):
    from services.curriculum.registry import CurriculumRegistry
    return CurriculumRegistry(conn)


@pytest.fixture
def client(database_url: str, monkeypatch):
    from fastapi.testclient import TestClient
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("AI_PROVIDER", "mock")
    from apps.api.main import app
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


@pytest.fixture
def sandbox(conn):
    """
    A throwaway curriculum offering with one source document, for chunk tests.

    Built inside the test transaction and rolled back afterwards, so chunk tests
    never touch the seeded registry or each other.
    """
    import uuid as _uuid

    tag = _uuid.uuid4().hex[:8]
    doc_sha = _uuid.uuid4().hex + _uuid.uuid4().hex   # 64 hex characters
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO curricula (code, name) VALUES (%s, %s) RETURNING id",
            (f"SBX_{tag.upper()}", f"Sandbox {tag}"))
        curriculum_id = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO subjects (curriculum_id, code, name_en) "
            "VALUES (%s, 'SBX_SUBJECT', 'Sandbox subject') RETURNING id",
            (curriculum_id,))
        subject_id = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO levels (curriculum_id, code, name) "
            "VALUES (%s, 'SBX_LEVEL', 'Sandbox level') RETURNING id",
            (curriculum_id,))
        level_id = cur.fetchone()[0]
        cur.execute(
            """
            INSERT INTO subject_offerings
                (curriculum_id, subject_id, level_id, slug, languages,
                 publication_status, display_note_en)
            VALUES (%s, %s, %s, %s, ARRAY['en'], 'planned', 'sandbox')
            RETURNING id
            """,
            (curriculum_id, subject_id, level_id, f"sandbox/{tag}"))
        offering_id = cur.fetchone()[0]
        cur.execute(
            """
            INSERT INTO source_documents
                (offering_id, document_type, source_priority, title, filename,
                 sha256, page_count, ingestion_route, paper_code, unit_number,
                 session_year, session_series, language, is_private)
            VALUES (%s, 'past_paper', 1, 'Sandbox paper', 'sandbox.pdf',
                    %s, 12, 'text', 'SBX01', 1, 2024, 'May June', 'en', true)
            RETURNING id
            """,
            (offering_id, doc_sha))
        document_id = cur.fetchone()[0]

    return {
        "tag": tag,
        "offering_id": str(offering_id),
        "document_id": str(document_id),
        "document_sha256": doc_sha,
        "slug": f"sandbox/{tag}",
    }
