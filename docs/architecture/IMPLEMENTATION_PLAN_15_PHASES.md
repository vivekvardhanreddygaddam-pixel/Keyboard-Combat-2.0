# TypeVector Arena — 15-Phase Dependency-Aware Implementation Plan

**Document Version:** 1.0.0  
**Date:** 2026-11-03  
**Status:** Approved Master Engineering Plan  
**Author:** Principal Product Architect & Technical Lead  
**Governing Rule:** Sequential execution discipline. Do not proceed to subsequent phases or start parallel implementation until the current phase exit criteria are fully satisfied and evidenced.

---

## 1. Plan Overview & Architectural Phasing Strategy

The 15 phases of TypeVector Arena correspond directly to the 15 prompts of the Master Prompt Pack. The architecture follows a strict bottom-up dependency progression:
```
Foundation & Tooling (Phases 1-2)
       │
       ▼
Frontend Shells & Backend Core (Phases 3-4)
       │
       ▼
Identity, Tenant Isolation & Registration (Phase 5)
       │
       ├──► Practice & Educational Progression (Phases 6-7)
       │
       └──► Ranked Competition Engine (Phases 8-10)
                 │
                 ▼
       Organizer Command Center & Async Operations (Phases 11-12)
                 │
                 ▼
       Cross-Cutting Hardening, Verification & Release (Phases 13-15)
```

---

## 2. Phase-by-Phase Specification

### Phase 1: Product Discovery, Architecture Decisions, and Execution Plan
- **Primary Focus:** Blueprint audit, repository inspection, domain boundaries, ADR establishment, risk analysis, handoff documentation.
- **Prerequisites:** Blueprint source and prompt pack access.
- **Key Deliverables:**
  - Complete project context and domain architecture documents.
  - Initial 5 foundational ADRs + ADR template.
  - All 5 agent handoff documents (`PROJECT_CONTEXT.md`, `IMPLEMENTATION_STATUS.md`, `DECISIONS.md`, `NEXT_STEPS.md`, `KNOWN_LIMITATIONS.md`).
  - Requirements Traceability Matrix initialized with all requirements marked `NOT STARTED`.
- **Exit Criteria:** All 5 handoff files exist and agree; complete blueprint recorded; zero feature implementation started.
- **Execution Mode:** **Strictly Sequential (Cannot Overlap).**

### Phase 2: Monorepo, Tooling, Local Infrastructure, and CI Foundation
- **Primary Focus:** Workspace orchestration via `pnpm`, Python environment and lockfile via `uv`, Docker Compose for local PostgreSQL and Redis, CI pipeline.
- **Prerequisites:** Phase 1 complete.
- **Key Deliverables:**
  - Root `package.json`, `pnpm-workspace.yaml`, `pyproject.toml`, `uv.lock`.
  - Local `infra/local/docker-compose.yml` with health checks.
  - Unified developer bootstrapper (`pnpm dev`).
  - GitHub Actions CI workflow for lint, format, typecheck, and unit test runner.
  - Minimal FastAPI skeleton health endpoints (`/healthz`, `/readyz`).
- **Exit Criteria:** `pnpm dev` boots clean stack; `uv sync` and `pnpm install` succeed; CI checks run clean; no fake data.
- **Execution Mode:** **Strictly Sequential (Cannot Overlap).**

### Phase 3: Brand, Design System, Public Site, and Multi-page Frontend Shell
- **Primary Focus:** CSS custom property design tokens, semantic components, multi-page layout shells, public route navigation, vanilla JS controllers.
- **Prerequisites:** Phase 2 complete.
- **Key Deliverables:**
  - Global CSS tokens (`--tv-*`) and BEM component system.
  - Public routes: `/`, `/events`, `/organizations/{slug}`, `/events/{slug}`, `/leaderboards/{id}`, `/results/{id}/{v}`, `/help`, `/about`.
  - Shared layout with skip links, responsive navigation, accessible landmarks, and honest empty/unavailable states.
- **Exit Criteria:** All public routes load; responsive across mobile and desktop; zero framework runtime; zero dead buttons.
- **Overlap Potential:** *Could conceptually overlap with Phase 4 if multiple engineers were present, but executed sequentially in this agent harness to maintain context integrity.*

### Phase 4: Backend Foundation, Domain Modules, Database Schema, and Migrations
- **Primary Focus:** Modular monolith structure, SQLAlchemy 2.x async base, initial PostgreSQL schema, Alembic migrations, OpenAPI conventions.
- **Prerequisites:** Phase 2 complete.
- **Key Deliverables:**
  - 16 domain packages established under `apps/api/src/typevector/domains/`.
  - Initial normalized schema covering users, events, registrations, rounds, attempts, and audit.
  - Composite foreign keys enforcing cross-event isolation.
  - Clean Alembic migration history with forward and backward safety checks.
- **Exit Criteria:** Migrations apply cleanly against real PostgreSQL; domain boundaries enforced; OpenAPI documentation generated.
- **Execution Mode:** **Strictly Sequential (Precursor to all backend logic).**

### Phase 5: Authentication, Verified Identity, Organizations, Authorization, and Registration
- **Primary Focus:** Secure cookie sessions, Argon2id passwords, tenant isolation, identity claims vs verified identity, race-safe atomic event registration.
- **Prerequisites:** Phases 3 and 4 complete.
- **Key Deliverables:**
  - Auth APIs and server-side session management.
  - Organization multi-tenancy and RBAC permission evaluator.
  - Atomic event registration with `SELECT ... FOR UPDATE` capacity lock.
  - Participant registration UI connected to real backend APIs.
- **Exit Criteria:** Registration race tests pass with zero overbooking; cross-tenant access returns 403 Forbidden; auth lifecycle complete.
- **Execution Mode:** **Sequential.**

### Phase 6: Practice Typing Engine, Modes, Saved Sessions, and Mistake Review
- **Primary Focus:** Client-side vanilla JS typing surface, IME handling, server persistence, deterministic diff alignment, mistake categorization.
- **Prerequisites:** Phase 5 complete.
- **Key Deliverables:**
  - 8 core practice modes (words, punctuation, paragraphs, numbers, code, sprint, accuracy, endurance).
  - High-performance typing controller with zero layout shift and no animation lag.
  - Server-side calculation of gross/net WPM, accuracy, and error types.
  - Interactive mistake review page with character-level alignment.
- **Exit Criteria:** Practice attempts save durably to PostgreSQL; review diff is deterministic; clear Local vs Saved state indicators.
- **Overlap Potential:** *Independent of Ranked Engine (Phases 8-10); could overlap with Phase 8 in a multi-team setting, but kept sequential here.*

### Phase 7: Skill Tracks, Level Progression, Assessment, and Adaptive Practice
- **Primary Focus:** Independent curriculum tracks, multi-attempt qualification logic, transparent level criteria, evidence-backed recommendations.
- **Prerequisites:** Phase 6 complete.
- **Key Deliverables:**
  - Curriculum domain models: `SkillTrack`, `TrackLevel`, `LevelCriteria`.
  - Multi-attempt aggregation engine (prevents single lucky attempt advancement).
  - Adaptive recommendation service citing explicit weakness evidence.
  - UI progress dashboard with transparent qualification explanations.
- **Exit Criteria:** Independent progression per track; level criteria versioned; unapproved thresholds marked as Draft.
- **Execution Mode:** **Sequential.**

### Phase 8: Ranked Attempt Core, Immutable Challenges, WebSocket Protocol, Durable Input ACK
- **Primary Focus:** High-throughput `arena-ws-v1` protocol, monotonic sequences, writer-generation fencing, single-transaction batch commit, ACK-after-commit.
- **Prerequisites:** Phase 5 complete.
- **Key Deliverables:**
  - WebSocket handler admitting constrained typing operations (`insert`, `backspace`).
  - Atomic transaction: batch log + text projection update + outbox event.
  - Idempotent replay handling for identical sequence + digest.
  - Client pending queue with Saved-through-sequence visual indicators.
- **Exit Criteria:** ACK dispatched only after DB commit; stale writer rejected; duplicate batch replay is idempotent; zero client-side score authority.
- **Execution Mode:** **Strictly Sequential (Core competition engine).**

### Phase 9: Event Lifecycle, Check-in, Round Orchestration, Pause/Void Policy, and Realtime Fanout
- **Primary Focus:** Event state machine (Draft -> Published -> Live -> Completed -> Results), synchronized server countdowns, global pause, Redis pub/sub.
- **Prerequisites:** Phase 8 complete.
- **Key Deliverables:**
  - Transition table enforcement with optimistic locking.
  - Check-in window and lobby management.
  - Synchronized server deadline admission.
  - Transactional outbox to Redis pub/sub bridge for spectator updates.
  - Event-wide pause/void/restart action controllers.
- **Exit Criteria:** Illegal lifecycle transitions rejected; server controls all deadlines; spectator updates decoupled from input ACKs.
- **Execution Mode:** **Sequential.**

### Phase 10: Canonicalization, Official Scoring, Result Aggregation, Review, Appeals, Publication
- **Primary Focus:** Pinned Unicode canonicalization, deterministic `arena-score-v1` formula, round aggregation, human integrity review, appeals, immutable results.
- **Prerequisites:** Phase 9 complete.
- **Key Deliverables:**
  - Pinned NFC and Unicode extended grapheme cluster segmentation.
  - Fixed-point integer scoring formula with <=699 / >=700 completion gating.
  - Golden test vectors verifying reproducible score computation.
  - Restricted integrity review queue with dual-approval workflow.
  - Immutable result publication tables (`published_result_versions`).
- **Exit Criteria:** Golden vectors pass identically; replay produces identical results; amendments create new immutable versions; unapproved formulas gated from prize events.
- **Execution Mode:** **Sequential.**

### Phase 11: Organizer Command Center and Operational Workflows
- **Primary Focus:** Dense, high-efficiency organizer UI (`/command/*`), event wizard, live operations dashboard, judging queue, audit viewer.
- **Prerequisites:** Phases 5, 9, 10 complete.
- **Key Deliverables:**
  - 14 organizer routes built with vanilla JS and CSS design system.
  - Live operations dashboard displaying real connection, latency, and outbox metrics.
  - Gated event-wide pause/void controls with mandatory reason and confirmation.
  - Audit trail viewer with search, filtering, and PII redaction.
- **Exit Criteria:** All organizer actions permission-checked on backend; zero fake metrics; high-impact actions audited and confirmed.
- **Execution Mode:** **Sequential.**

### Phase 12: Redis/Celery Integration, Notifications, Outbox Delivery, Exports, Retention
- **Primary Focus:** Background job workers, outbox event processor, transactional notifications, CSV/JSON report exports, automated data retention.
- **Prerequisites:** Phases 10, 11 complete.
- **Key Deliverables:**
  - Celery application with Redis broker and JSON serialization.
  - Outbox poller worker delivering PostgreSQL outbox events to Redis.
  - Export service with CSV formula injection protection (`=` -> `'=`).
  - Data retention sweep jobs for inactive sessions and aged logs.
- **Exit Criteria:** Duplicate task delivery is safe/idempotent; Redis loss does not corrupt PostgreSQL; exports expire and are access-controlled.
- **Execution Mode:** **Sequential.**

### Phase 13: Security, Privacy, Accessibility, and Product-Truth Hardening
- **Primary Focus:** OWASP ASVS control register, IDOR audits, tenant boundary verification, keyboard/screen-reader accessibility, claim truthfulness audit.
- **Prerequisites:** All previous feature phases complete.
- **Key Deliverables:**
  - Completed OWASP ASVS control checklist with pass/fail evidence.
  - Security hardening of WebSocket origins, cookies, CSRF, and SQL queries.
  - Accessibility audit (WCAG 2.1 AA targets, keyboard navigation, contrast, zoom).
  - Removal of unsubstantiated product claims across documentation and UI.
- **Exit Criteria:** Zero unresolved critical/high security findings; keyboard-only flows verified; truthfulness audit clean.
- **Execution Mode:** **Sequential.**

### Phase 14: Comprehensive Integration, Concurrency, Load, Resilience, and Regression Testing
- **Primary Focus:** End-to-end user journeys, chaos/failure injection, concurrency load testing, baseline performance measurement.
- **Prerequisites:** Phase 13 complete.
- **Key Deliverables:**
  - Automated test suite covering unit, property, golden vector, and integration suites.
  - Race condition tests: registration capacity, competing WebSocket writers.
  - Failure injection tests: DB disconnect, Redis kill, worker restart during active rounds.
  - Measured baseline latency reports (ACK p50/p95/p99) on documented hardware.
- **Exit Criteria:** All automated suites pass; critical race invariants verified; baseline performance documented without fake claims.
- **Execution Mode:** **Sequential.**

### Phase 15: Deployment, Observability, Backup/Restore, Runbooks, and Release Decision
- **Primary Focus:** Hardened container assets, environment configurations, backup/restore verification with tombstone replay, operational runbooks, final GO/NO-GO gate.
- **Prerequisites:** Phase 14 complete.
- **Key Deliverables:**
  - Non-root, multi-stage `Dockerfile` and production Compose/deploy assets.
  - Structured logging, metrics, and incident runbooks.
  - Verified backup-and-restore rehearsal documentation.
  - Formal Release Decision evaluation against all blueprint release gates.
- **Exit Criteria:** Staging rehearsal complete or limitations documented; all 10 release gates evaluated with concrete evidence; formal GO / CONDITIONAL GO / NO-GO recommendation delivered.
- **Execution Mode:** **Final Release Gate.**

---

## 3. Safe Overlap vs Strict Sequential Dependency Matrix

```
Phase 01: Architecture & Execution Plan ──► [CANNOT OVERLAP]
Phase 02: Monorepo, Tooling & CI ────────► [CANNOT OVERLAP]
Phase 03: Frontend Shells & Brand ───────► (Could overlap with Phase 04 in large teams)
Phase 04: Backend Foundation & DB ───────► (Requires Phase 02; precursor to all backend)
Phase 05: Identity, Tenant & Reg ────────► [CANNOT OVERLAP - Depends on 03 & 04]
Phase 06: Practice Engine ───────────────► (Can safely proceed in parallel with Phase 08)
Phase 07: Curriculum Progression ────────► [Depends on Phase 06]
Phase 08: Ranked WebSocket Input Core ───► [Depends on Phase 05; precursor to 09]
Phase 09: Event Lifecycle & Fanout ──────► [Depends on Phase 08]
Phase 10: Scoring, Review & Publication ─► [Depends on Phase 09]
Phase 11: Organizer Command Center ──────► [Depends on Phases 05, 09, 10]
Phase 12: Async Workers, Exports, Outbox ► [Depends on Phases 10, 11]
Phase 13: Hardening & Truthfulness ──────► [CANNOT OVERLAP - Global audit]
Phase 14: Comprehensive Verification ───► [CANNOT OVERLAP - Verification of all code]
Phase 15: Deployment & Release Decision ─► [FINAL GATE - Evaluates all gates]
```

