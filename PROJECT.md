# Lumos — Project Definition

## Identity
**Name:** Lumos
**Description:** AI educational assistant for Bangladeshi students
**Tagline:** Lights the way to knowledge.

## Purpose
Lumos is a curriculum-grounded, personalised educational assistant. Its differentiator is not generic chat; it is evidence-linked tutoring constrained by a student's declared curriculum, subject, level and syllabus version, in Bangla and English.

## Legacy implementations
- Cloud / multimodal reference: `https://github.com/Shahriar290900/shikhbo-ai`
- Local-first reference: `https://github.com/Shahriar290900/Shikhbo-Local-App`

Lumos is a controlled migration from these, not a rename. See `MIGRATION_MAP.md`.

## Capabilities (intended)
1. Curriculum-grounded tutoring with source attribution
2. Past-paper learning support *(gated on corpus acquisition — BLOCK-001)*
3. Adaptive practice
4. Student progress tracking
5. Teacher resource preparation
6. Bangla and English interaction
7. Voice and image/document input as infrastructure permits
8. A cinematic 3D homepage that never blocks learning

## Constraints
- Source attribution is mandatory for substantive grounded answers, and every citation must resolve to a chunk that was actually retrieved.
- Curriculum isolation is enforced before semantic retrieval, at the SQL boundary.
- Insufficient evidence produces an explicit limitation, never an invented citation.
- Subject availability comes from the curriculum registry. A UI card is not availability.
- Student data is minimised and protected; most users are minors.
- Model providers are replaceable; none is reachable from the browser.
- Core learning works when optional external services are down.
- Performance targets low-end Android devices and slow networks.

## Current verified scope
**180 curriculum records**: SSC English 43, SSC ICT 120, Edexcel IAL Physics spec 5.6 17. Partial, uncleaned, and not yet production-ready. `CURRICULUM_INVENTORY.md` is authoritative.
