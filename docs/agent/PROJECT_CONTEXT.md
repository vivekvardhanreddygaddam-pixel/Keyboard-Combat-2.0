# TypeVector Arena — Project Context (PROJECT_CONTEXT.md)

**Document Version:** 1.14.0  
**Current Phase:** Phase 15 of 15 (Deployment, Observability, Backup/Restore, and Release Decision Complete)  
**Last Updated:** 2026-11-05  
**Lead Architect:** Principal Product Architect & Technical Lead  


---

## 1. Product Summary & Mission

**TypeVector Arena** is an independent, high-integrity typing practice and competitive tournament platform. It delivers:
1. An **educational practice engine & curriculum** supporting independent skill tracks, multi-attempt progression levels, real-time typing diagnostics, and deterministic mistake review.
2. A **server-authoritative ranked tournament arena** providing synchronized round orchestration, millisecond-accurate input admission via WebSockets, writer-generation fencing, idempotent replay, and tamper-proof score calculations.
3. An **Organizer Command Center** for real-time competition management, roster readiness, audit inspection, fair incident handling (pause/void), and immutable result publication.

The platform is designed for institutions, universities, corporate events, and competitive communities who demand absolute fairness, transparent rules, and verifiable results.

---

## 2. Core Architectural Decisions (Summary of ADRs)

- **Frontend:** Semantic HTML5, CSS3, modern Vanilla JavaScript ES modules. Strictly NO frontend frameworks (React, Vue, Svelte, Angular, Next.js). Minimal asset bundling/dev serving via Vite.
- **Backend:** Modular monolith built in Python with FastAPI, Pydantic v2, and SQLAlchemy 2.x async.
- **Data Authority:** **PostgreSQL** is the sole authoritative system of record for all persistent state. Every ranked batch, score, registration, and published result must commit to PostgreSQL before acknowledgment.
- **Coordination & Fanout:** **Redis** is strictly non-authoritative: utilized solely for ephemeral pub/sub broadcast, spectator cache snapshots, and Celery task brokering.
- **Background Tasks:** **Celery** with PostgreSQL Transactional Outbox pattern for asynchronous delivery (exports, notifications, retention sweeps).
- **Authentication & Security (ADR-007):** Argon2id password hashing, 256-bit server-side sessions with SHA-256 database lookup, HttpOnly/SameSite=Lax/Secure cookies, HMAC-SHA256 CSRF protection on all mutating requests, 3-tier identity model (`User`, unverified `IdentityClaim`, audited verified claim), and pessimistic `SELECT ... FOR UPDATE` locking on event capacity.
- **Practice Engine & Sequence Alignment (ADR-008):** Independent practice typing engine decoupled from ranked arena WebSocket pipeline. Hybrid deterministic sequence alignment (Needleman-Wunsch DP), explainable Gross/Net WPM, layout-shift protected character tokens, and server-side mistake diff review.
- **Curriculum, Tracks & Progression (ADR-009):** 7 independent skill tracks, 6 progressive level tiers (42 levels total), non-certification disclaimer distinguishing learning milestones, multi-attempt qualification rules (2-5 passes), versioned criteria (`2026.1-draft`) marked as draft awaiting product approval, and statistical safeguards for adaptive practice recommendations ($N \ge 3$).
- **Ranked Attempt Core & Input Fencing (ADR-010):** `arena-ws-v1` server-authoritative WebSocket protocol, monotonic sequence admission ($S=W+1$), writer-generation fencing with active socket eviction (code 4409), idempotent replay with identical digest, prompt withholding prior to active round start, single-transaction atomic projection updates, and durable ACKs post-PostgreSQL commit.
- **Event Lifecycle, Check-in & Round Orchestration (ADR-011):** Authoritative state machine (`DRAFT` &rarr; `ARCHIVED`), optimistic locking (`version`), check-in window gating, automated no-show sweeps on `LIVE`, server clock sampling (&le;5ms uncertainty), uniform pause/resume fairness extensions across all rounds & attempts, draft fairness policy (`DRAFT_AWAITING_TOURNAMENT_APPROVAL`, max 2 pauses, max 600s), outbox dispatcher with resilient Redis pub/sub, and 1 Hz throttled spectator leaderboard stream.
- **Official Scoring, Integrity Dual-Approval & Immutable Results (ADR-012):** Pinned Unicode canonicalization (extended graphemes & code scalars; zero raw byte counting), fixed-point `arena-score-v1` with completion gating (&le;699 incomplete, &ge;700 complete), prize event policy gate (`ruleset_approval_status == 'approved'`), frozen multi-round aggregation with voided denominator exclusion, dual-approval reviewer separation for disqualifications, independent appellate adjudication, immutable result versions with signed hashes, and strict zero-PII public standings.
- **Organizer Command Center, Telemetry & Export Security (ADR-013):** Vanilla JS organizer SPA (`command-center.js`), strictly scoped tenant RBAC, draft-only ruleset and prompt mutability, genuine operational telemetry with authentic health probes (None latency when dormant), CWE-1236 CSV formula injection defense (`sanitize_csv_value`), read-only results preview, and searchable audit logging with recursive secret masking.
- **Celery Background Processing, Outbox & Safe Integrations (ADR-014):** Celery 5.4 application with JSON-only serialization (CWE-502), PostgreSQL transactional outbox worker claiming (`SKIP LOCKED`) and backoff retries, provider-abstracted notification pipeline with truth in unconfigured states (`ProviderNotConfiguredError`), async export jobs with sanitization and 7-day physical cleanup, reviewed retention policies protecting permanent competition records, and single-instance Celery Beat scheduler with Redis distributed lock.
- **Security, Privacy, Accessibility & Product-Truth Hardening (ADR-015):** Eliminates public PII harvesting via `PublicUserRead`, closes IDOR vectors on results preview, scoring reconciliation, and case review, enforces dual-approval reviewer and judge separation, introduces GDPR Art. 16/17 rectification and deactivation with session family revocation, enforces under-18 consent gate, hardens spectator WebSocket with origin checks and payload caps, fixes modal dialog keyboard traps and focus order, and qualifies all product claims.
- **Integration, Concurrency & Reliability Verification (ADR-016):** Validates 7 critical user journeys, capacity boundary concurrency locks, competing lifecycle optimistic locks, split-brain writer fencing (`4409`), post-commit durable ACKs, idempotent replay deduplication, outbox Redis outage resilience, and local micro-benchmarks establishing sub-0.1ms p95 algorithmic execution.
- **Production Packaging, Observability & Release Gating (ADR-017):** Establishes provider-neutral multi-stage container images, non-root `appuser` (UID 10001), Nginx/Caddy reverse proxies with 300s WebSocket timeouts, database connection pool bounds, automated tamper-evident backup/restore tooling, Prometheus/Alertmanager observability, and formal audit of all 10 Blueprint Gates with CONDITIONAL GO verdict.
- **Workspace Tooling:** `pnpm` for workspace scripts and frontend dependencies; `uv` for fast, deterministic Python virtual environments and locked dependencies.


---

## 3. Strict Project Constraints & Non-Goals

1. **No Frontend Frameworks:** No React, Next.js, Vue, Angular, Svelte, or runtime virtual DOMs.
2. **No Microservices:** Maintain a single modular monolith repository with strict domain encapsulation.
3. **No Heavy Infrastructure:** No Kafka, Kubernetes, or service meshes.
4. **No AI Proctoring / Automated Disqualification:** Integrity signals are flags for human review; no automated disqualification based on webcam, focus loss, or opaque heuristics.
5. **No Client Score Authority:** The browser is NEVER trusted for score calculations, timer cutoffs, admission eligibility, or rank order.
6. **No Deceptive Polish:** Zero fake metrics, fake participants, simulated actions, or nonfunctional dead buttons.

---

## 4. Key Repository Paths

| Path | Purpose |
| :--- | :--- |
| `docs/product/BLUEPRINT_SOURCE.md` | Verification record of the v4.0 blueprint source (`C:\Users\vivek\Downloads\typevector-arena-antigravity-prompts.md`). |
| `docs/product/REQUIREMENTS_TRACEABILITY.md` | Master Requirements Traceability Matrix (RTM) mapping requirements to tests and gates. |
| `docs/agent/PROJECT_CONTEXT.md` | This document: high-level architecture, boundaries, and product summary. |
| `docs/agent/IMPLEMENTATION_STATUS.md` | Phase-by-phase execution tracker with test outcomes and blocker logs. |
| `docs/agent/DECISIONS.md` | Master ADR index linking to detailed decision records. |
| `docs/agent/NEXT_STEPS.md` | Actionable checklist for the immediate next phase (Phase 15). |
| `docs/agent/KNOWN_LIMITATIONS.md` | Register of intentionally unsupported features, unverified claims, and release blockers. |
| `docs/security/OWASP_ASVS_AND_WEBSOCKET_SECURITY_REGISTER.md` | Risk-selected Level 2 control register and WebSocket protocol checklist. |
| `docs/testing/WORKLOAD_MODEL_AND_CAPACITY_TARGETS.md` | Workload models, math formulations, reconnect jitter, and candidate SLO proposals. |
| `docs/testing/INTEGRATION_AND_RELIABILITY_REPORT.md` | 13-point verification matrix, failure injection results, and local benchmark findings. |
| `docs/architecture/DOMAIN_BOUNDARIES.md` | Detailed 16-domain boundary matrix and DAG dependency rules. |
| `docs/architecture/RISK_ANALYSIS_AND_OPEN_DECISIONS.md` | Deep risk analysis, concurrency mitigations, and decisions awaiting PO approval. |
| `docs/architecture/ENGINEERING_STANDARDS.md` | Coding standards, naming conventions, migration rules, and Definition of Done. |
| `docs/architecture/DIRECTORY_LAYOUT.md` | Documented monorepo folder layout. |
| `docs/architecture/TASTEGATE_CRITIQUE_REPORT.md` | Visual design critique, token verification, and accessibility audit for Phase 3. |

---

## 5. Domain Boundary Index

The system contains 16 distinct domain modules:
1. `identity` — User accounts, sessions, Argon2id auth, verification claims.
2. `organizations` — Multi-tenant organization boundaries and role management.
3. `events` — Event definition, versioned rule sets, lifecycle state machine.
4. `registrations` — Event roster, eligibility checks, atomic capacity reservations.
5. `rounds` — Round setup, challenge prompts, prompt versioning.
6. `practice` — Independent practice typing surface, sessions, error diffs.
7. `curriculum` — Skill tracks, level criteria, multi-attempt qualification.
8. `ranked_input` — High-throughput WebSocket ingestion, sequence fencing, ACKs.
9. `scoring` — Deterministic metric calculation, canonicalization, vectors.
10. `results` — Result aggregation, immutable published versions, amendments.
11. `integrity_review` — Review flags, human judging rationale, participant appeals.
12. `broadcast` — Ephemeral fanout, WebSocket subscriptions, spectator feed.
13. `notifications` — Transactional email, system alerts, deliverability tracking.
14. `exports` — Async report generation (CSV/JSON), formula injection guard.
15. `audit` — Append-only privileged action log, tenant compliance.
16. `operations` — Platform health checks, DB pool metrics, Redis latency.
