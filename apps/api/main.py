"""
apps.api.main — Lumos API.

At this goal the API exposes the curriculum registry and one guarded stub of the
tutor route. The stub is here on purpose: LUMOS-004A's acceptance criterion is
that an unavailable subject is refused *before retrieval*, and the only way to
demonstrate that is to have the route that would retrieve.

It returns 501 once the gate passes, because retrieval does not exist yet
(LUMOS-008). It never returns an answer, mock or otherwise — a route that
fabricates a tutoring response to look finished is exactly the failure this
project is built to avoid.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any, Iterator

import psycopg
from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, model_validator

from pathlib import Path

from services.curriculum.registry import (
    CurriculumRegistry,
    OfferingNotFound,
    OfferingUnavailable,
    offerings_to_public_dicts,
)

app = FastAPI(
    title="Lumos API",
    version="0.1.0",
    description=(
        "Curriculum-grounded tutoring for Bangladeshi students. "
        "Subject availability is served from the curriculum registry; a subject "
        "the registry does not mark available cannot be queried."
    ),
)


# ─────────────────────────────────────────────────────────────────────────────
# Database
# ─────────────────────────────────────────────────────────────────────────────

@contextmanager
def _connection() -> Iterator[psycopg.Connection]:
    url = os.environ.get("DATABASE_URL")
    if not url:
        # Fail closed and say so plainly (ADR-012). Never guess a connection.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="DATABASE_URL is not configured",
        )
    with psycopg.connect(url) as conn:
        yield conn


def get_registry() -> Iterator[CurriculumRegistry]:
    with _connection() as conn:
        yield CurriculumRegistry(conn)


# ─────────────────────────────────────────────────────────────────────────────
# Schemas
# ─────────────────────────────────────────────────────────────────────────────

class TutorRequest(BaseModel):
    """
    Name an offering either by its slug or by its code triple.

    Both exist because the registry has two identifier systems and `GET
    /curriculum` publishes the first. The slug `edexcel-ial/physics/a2` carries
    level `a2`, while the stored level code is `IAL_A2`; no normalisation rule
    bridges that, because the slug is a separate identity rather than a
    lower-cased view of the codes.

    Accepting only the triple meant a client that read `/curriculum` and posted
    the segments it published got 404 `unknown_offering` — the API denying the
    existence of an offering it had just listed. Slug is therefore the preferred
    input, and the triple is kept because it is what the seed and the tests
    already speak.
    """

    query: str = Field(min_length=1, max_length=4000)
    slug: str | None = Field(default=None, max_length=128)
    curriculum: str | None = Field(default=None, max_length=32)
    subject: str | None = Field(default=None, max_length=32)
    level: str | None = Field(default=None, max_length=32)
    syllabus_version: str | None = Field(default=None, max_length=64)
    language: str = Field(default="en", pattern="^[a-z]{2}$")

    @model_validator(mode="after")
    def _needs_one_identifier(self) -> "TutorRequest":
        if self.slug:
            return self
        missing = [f for f in ("curriculum", "subject", "level") if not getattr(self, f)]
        if missing:
            raise ValueError(
                "name the offering either by 'slug' (as GET /curriculum returns it) "
                f"or by curriculum + subject + level; missing: {', '.join(missing)}")
        return self


# ─────────────────────────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/health")
def health() -> dict[str, Any]:
    """
    Liveness plus a truthful readiness breakdown.

    Reports which subsystems are actually up rather than a single green light,
    so a half-loaded service cannot look healthy.
    """
    out: dict[str, Any] = {"status": "ok", "version": app.version}
    url = os.environ.get("DATABASE_URL")
    if not url:
        out["database"] = "not_configured"
        out["status"] = "degraded"
        return out
    try:
        with psycopg.connect(url, connect_timeout=5) as conn, conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM curriculum_availability WHERE is_available")
            out["database"] = "ok"
            out["available_offerings"] = cur.fetchone()[0]
    except Exception as exc:  # noqa: BLE001 - report, do not crash the probe
        out["database"] = "unreachable"
        out["database_error"] = f"{type(exc).__name__}"
        out["status"] = "degraded"

    # The model boundary reports itself, including whether answers would be
    # mocked. A client that cannot tell a real answer from a mock one is exactly
    # the failure this project exists to avoid, so it is surfaced here rather
    # than left for someone to infer from configuration.
    try:
        from services.models import CapabilityUnavailable, ModelGateway
        gateway = ModelGateway.from_env()
        out["model_provider"] = gateway.provider_name
        out["chat_model"] = gateway.config.chat_model

        # Report whether generation *works*, not which provider is configured.
        #
        # Naming the provider was the first version and it lied: with
        # AI_PROVIDER=huggingface the endpoint reported "generation: live" while
        # every request failed, because no provider serves gemma4:e4b. A status
        # field that says a subsystem is up when it is down is worse than no
        # status field, and this project exists to not do that.
        if gateway.is_mock:
            out["generation"] = "mock"
            out["generation_note"] = (
                "Deterministic mock. Retrieval and citations are real; the "
                "explanation is not a tutoring answer.")
            out["status"] = "degraded"
        else:
            try:
                gateway.generate("ping", max_tokens=1)
                out["generation"] = "live"
            except CapabilityUnavailable as exc:
                out["generation"] = "unavailable"
                out["generation_note"] = str(exc)[:220]
                out["status"] = "degraded"
            except Exception as exc:  # noqa: BLE001
                out["generation"] = "error"
                out["generation_note"] = f"{type(exc).__name__}"
                out["status"] = "degraded"
    except Exception as exc:  # noqa: BLE001
        out["model_provider"] = "misconfigured"
        out["model_error"] = f"{type(exc).__name__}: {exc}"[:200]
        out["status"] = "degraded"
    return out


@app.get("/curriculum")
def list_curriculum(
    available_only: bool = Query(
        default=False,
        description="Return only offerings a student may actually query.",
    ),
    registry: CurriculumRegistry = Depends(get_registry),
) -> dict[str, Any]:
    """
    The subject list.

    This is the front end's only source of availability. Offerings that are not
    available are still returned — with `is_available: false`, `blocked_reasons`,
    and the registry's own `display_note_en` / `display_note_bn` — so the UI can
    render an honest "coming soon" or "in preparation" state instead of either
    hiding the roadmap or implying a subject works.
    """
    offerings = registry.available_offerings() if available_only else registry.list_offerings()
    return {
        "offerings": offerings_to_public_dicts(offerings),
        "counts": {
            "total": len(offerings),
            "available": sum(1 for o in offerings if o.is_available),
        },
    }


@app.get("/curriculum/{curriculum_code}/{subject_code}/{level_code}")
def get_offering(
    curriculum_code: str,
    subject_code: str,
    level_code: str,
    syllabus_version: str | None = Query(default=None),
    registry: CurriculumRegistry = Depends(get_registry),
) -> dict[str, Any]:
    """One offering, with its non-private source documents and audited counts."""
    try:
        offering = registry.resolve(
            curriculum=curriculum_code, subject=subject_code,
            level=level_code, syllabus_version=syllabus_version,
        )
    except OfferingNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))

    payload = offerings_to_public_dicts([offering])[0]
    payload["source_documents"] = registry.source_documents(offering.offering_id)
    payload["corpus_snapshots"] = registry.corpus_snapshots(offering.offering_id)
    return payload


@app.post("/tutor/ask")
def tutor_ask(
    req: TutorRequest,
    registry: CurriculumRegistry = Depends(get_registry),
) -> JSONResponse:
    """
    The coverage gate, in the position that matters.

    The registry check runs first. Nothing downstream — no retrieval, no
    embedding, no model call — happens for an offering the registry has not
    marked available.
    """
    try:
        offering = registry.require_available(
            slug=req.slug,
            curriculum=req.curriculum, subject=req.subject,
            level=req.level, syllabus_version=req.syllabus_version,
        )
    except OfferingNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "unknown_offering", "message": str(exc)},
        )
    except OfferingUnavailable as exc:
        # 409, not 403: the request is well-formed and the caller is permitted —
        # the corpus simply is not ready. The body carries the reasons and the
        # student-facing copy so the client never has to invent an explanation.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "subject_unavailable",
                "slug": exc.slug,
                "publication_status": exc.publication_status,
                "blocked_reasons": list(exc.reasons),
                "message_en": exc.display_note_en
                or "This subject is not available yet.",
                "message_bn": exc.display_note_bn,
            },
        )

    # Gate passed. Retrieve, ground, and validate every citation.
    #
    # The order matters and is the whole design: availability first (nothing
    # downstream runs for an offering the registry has not cleared), retrieval
    # second, generation last, and citation validation after that. An answer
    # whose citations do not resolve to this turn's context is not shown as
    # grounded (ADR-010).
    from services.models import ModelGateway
    from services.rag.retrieval import HybridRetriever
    from services.rag.tutor import Tutor

    gateway = ModelGateway.from_env()
    with _connection() as conn:
        tutor = Tutor(HybridRetriever(conn, gateway), gateway)
        answer = tutor.ask(req.query, offering_id=offering.offering_id)

    payload = answer.as_dict()
    payload["offering"] = {
        "slug": offering.slug,
        "subject": offering.subject_name_en,
        "level": offering.level_name,
    }
    return JSONResponse(status_code=200, content=payload)


# ─────────────────────────────────────────────────────────────────────────────
# The interface
# ─────────────────────────────────────────────────────────────────────────────
#
# Served by the API rather than a separate front end, deliberately. A Hugging
# Face Space is one container, and splitting the interface out would mean a
# second deployment and a CORS boundary for no benefit at this stage. The page
# is static: it reads /health and /curriculum and posts to /tutor/ask, so it
# cannot show a subject as available unless the registry says so (ADR-011).

_STATIC = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=_STATIC), name="static")


@app.get("/offerings/{offering_slug:path}/documents")
def list_documents(offering_slug: str,
                   registry: CurriculumRegistry = Depends(get_registry)) -> dict[str, Any]:
    """
    Documents this offering may show a student (ADR-026).

    Often an empty list, and that is a correct answer. Only the exam papers are
    servable; the textbook grounds answers and is never shown.
    """
    from services.delivery.documents import servable_documents
    with _connection() as conn:
        docs = servable_documents(conn, offering_slug)
    return {"offering": offering_slug,
            "documents": [d.as_dict() for d in docs],
            "count": len(docs)}


@app.get("/documents/{document_id}/url")
def document_url(document_id: str) -> dict[str, Any]:
    """
    A short-lived URL for one PDF, if the registry permits it.

    Presigned rather than public: a leaked presigned link expires, and a public
    bucket URL cannot be withdrawn once shared.
    """
    from services.delivery.documents import (
        DeliveryUnavailable, DocumentNotServable, presigned_url,
    )
    try:
        with _connection() as conn:
            url, document = presigned_url(conn, document_id)
    except DocumentNotServable as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail={"error": "not_servable", "message": str(exc)})
    except DeliveryUnavailable as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail={"error": "delivery_unconfigured", "message": str(exc)})
    return {"url": url, "expires_in": 900, **document.as_dict()}


@app.get("/", include_in_schema=False)
def home() -> FileResponse:
    return FileResponse(_STATIC / "index.html")
