# TypeVector Arena — Architecture Decisions Log (DECISIONS.md)

**Last Updated:** 2026-11-05 (Updated in Phase 13 Hardening Pass)  
**Status:** Maintained across all 15 phases  
**Lead Architect:** Principal Product Architect & Technical Lead  

This document tracks all formal Architecture Decision Records (ADRs) established for TypeVector Arena. Detailed records are located in `docs/decisions/`.

---

## Architecture Decision Records Index

| ADR ID | Title | Date | Status | Summary & Core Impact |
| :--- | :--- | :--- | :--- | :--- |
| [ADR-000](../decisions/ADR-000-template.md) | Architecture Decision Record Template | 2026-11-03 | Accepted | Standard structure for evaluating options, recording rationale, consequences, and validation. |
| [ADR-001](../decisions/ADR-001-technology-stack.md) | Technology Stack and Toolchain Selection | 2026-11-03 | Accepted | Mandates Vanilla HTML5/CSS3/JS, Python/FastAPI, PostgreSQL, Redis, Celery, pnpm, and uv. Rejects heavy JS frameworks and premature microservices. |
| [ADR-002](../decisions/ADR-002-modular-monolith.md) | Modular Monolith Architecture Pattern | 2026-11-03 | Accepted | Adopts a modular monolith with 16 distinct domain packages, strict DAG dependency rules, and atomic database transaction ownership. Rejects microservices. |
| [ADR-003](../decisions/ADR-003-vanilla-multi-page-frontend.md) | Vanilla Multi-Page Frontend Architecture | 2026-11-03 | Accepted | Implements discrete multi-page shells (`apps/web`) using vanilla ES modules and custom CSS design tokens. Guarantees zero framework render overhead during typing. |
| [ADR-004](../decisions/ADR-004-postgresql-authoritative-store.md) | PostgreSQL as Exclusive Authority | 2026-11-03 | Accepted | PostgreSQL is the sole system of record. Every ranked input batch, score, registration, and published result commits to PostgreSQL before client acknowledgment. |
| [ADR-005](../decisions/ADR-005-redis-ephemeral-non-authoritative.md) | Redis Role as Ephemeral Broker & Fanout | 2026-11-03 | Accepted | Restricts Redis to ephemeral pub/sub fanout, spectator cache, and Celery brokering via Transactional Outbox. Redis failure never loses persistent business state. |
| [ADR-006](../decisions/ADR-006-schema-conventions-and-composite-invariants.md) | Schema Conventions & Composite Invariants | 2026-11-04 | Accepted | Establishes strict PostgreSQL naming conventions, composite foreign keys preventing cross-event corruption, and safe Alembic migration workflows. |
| [ADR-007](../decisions/ADR-007-session-auth-csrf-and-verified-identity.md) | Server-Side Sessions, CSRF Defense & Verified Identity | 2026-11-04 | Accepted | Implements Argon2id hashing, 256-bit hashed server sessions, HttpOnly cookies, HMAC-SHA256 CSRF protection, 3-tier identity model, and pessimistic capacity locking. |
| [ADR-008](../decisions/ADR-008-practice-engine-alignment-and-metrics.md) | Practice Engine Alignment, Metrics & UI Architecture | 2026-11-04 | Accepted | Implements deterministic sequence alignment, explainable WPM/accuracy metrics, 9 initial practice modes, layout-shift protected typing surface, and server-side diff evaluation. |
| [ADR-009](../decisions/ADR-009-curriculum-skill-tracks-and-progression.md) | Skill Tracks, Multi-Attempt Qualification & Progression | 2026-11-04 | Accepted | Establishes 7 independent skill tracks, 6-tier level model, multi-attempt qualification rules, draft criteria versioning, and evidence-backed adaptive recommendations. |
| [ADR-010](../decisions/ADR-010-ranked-input-protocol-and-fencing.md) | Server-Authoritative Ranked WebSocket Protocol and Writer Fencing | 2026-11-04 | Accepted | Implements `arena-ws-v1`, monotonic sequence admission, idempotent replay, writer-generation fencing, incremental text projection, and post-commit durable ACKs. |
| [ADR-011](../decisions/ADR-011-event-lifecycle-fairness-and-round-orchestration.md) | Event Lifecycle State Machine, Check-in Windows, Round Orchestration, and Uniform Pause Fairness | 2026-11-04 | Accepted | Establishes authoritative lifecycle state transitions, optimistic locking, frozen ruleset immutability, check-in window gating, automated no-show sweeps, server clock sampling (&le;5ms), and uniform pause/resume fairness extensions. |
| [ADR-012](../decisions/ADR-012-official-scoring-integrity-review-and-immutable-results.md) | Official Scoring Engine, Deterministic Replay, Integrity Review Dual-Approval, and Immutable Published Results | 2026-11-04 | Accepted | Implements pinned Unicode canonicalization (extended graphemes & code scalars; zero byte counting), fixed-point `arena-score-v1` with completion gating (&le;699 incomplete, &ge;700 complete), prize event approval gate, frozen multi-round aggregation with voided denominator exclusion, dual-approval reviewer separation for disqualifications, independent appellate adjudication, immutable result versions with signed hashes, and strict zero-PII public standings. |
| [ADR-013](../decisions/ADR-013-organizer-command-center-and-operational-workflows.md) | Organizer Command Center, Tenant Scoping, Operational Truthfulness, and Export Security | 2026-11-05 | Accepted | Establishes strictly scoped organizer command center, draft-only ruleset/round/prompt mutability, transparent operational metrics with authentic probes (None latency when dormant), CSV formula injection defense (CWE-1236), read-only results preview, and structured audit logs with secret redaction. |
| [ADR-014](../decisions/ADR-014-celery-transactional-outbox-and-background-integrations.md) | Celery Background Processing, Transactional Outbox, Notifications, Safe Exports, and Retention Policies | 2026-11-05 | Accepted | Implements Celery 5.4 background processing with strict JSON serialization (CWE-502), PostgreSQL transactional outbox worker claiming (`SKIP LOCKED`), idempotent dispatch, provider-abstracted notifications with truth-in-advertising (unconfigured providers), sanitized CSV/JSON exports (CWE-1236), reviewed retention policies protecting permanent competition records, and single-instance Celery Beat scheduler with Redis distributed locking. |
| [ADR-015](../decisions/ADR-015-security-privacy-accessibility-and-product-truth-hardening.md) | Cross-Project Security, Privacy, Accessibility, and Product-Truth Hardening | 2026-11-05 | Accepted | Eliminates public PII harvesting via `PublicUserRead`, closes IDOR vectors on results preview, scoring reconciliation, and case review, enforces dual-approval reviewer and judge separation, introduces GDPR Art. 16/17 rectification and deactivation with session family revocation, enforces under-18 consent gate, hardens spectator WebSocket with origin checks and payload caps, fixes modal dialog keyboard traps and focus order, and qualifies all product claims. |
| [ADR-016](../decisions/ADR-016-comprehensive-integration-concurrency-and-reliability-verification.md) | Comprehensive Integration, Concurrency, and Reliability Verification | 2026-11-05 | Accepted | Validates 7 end-to-end user journeys, capacity boundary concurrency locks, competing lifecycle optimistic locks, split-brain writer fencing (`4409`), post-commit durable ACKs, idempotent replay deduplication, outbox Redis outage resilience, and local micro-benchmarks establishing sub-0.1ms p95 algorithmic execution. |
| [ADR-017](../decisions/ADR-017-production-deployment-packaging-observability-and-release-gating.md) | Production Deployment Packaging, Operational Observability, and Release Gating | 2026-11-05 | Accepted | Establishes provider-neutral multi-stage container images, non-root `appuser` (UID 10001), Nginx/Caddy reverse proxies with 300s WebSocket timeouts, database connection pool bounds, automated tamper-evident backup/restore tooling, Prometheus/Alertmanager observability, and formal audit of all 10 Blueprint Gates with CONDITIONAL GO verdict. |




---

## Guidelines for Adding ADRs
1. Copy the structure from `docs/decisions/ADR-000-template.md`.
2. Assign the next sequential ID (`ADR-006`, etc.).
3. Document context, considered alternatives, chosen solution, positive/negative consequences, security/privacy impact, and validation strategy.
4. Update this index with a concise summary and link.
5. High-impact policy choices (e.g., scoring formulas, qualification criteria, data retention schedules) must be accompanied by an ADR before graduation from draft to production status.

