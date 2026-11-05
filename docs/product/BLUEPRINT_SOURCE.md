# TypeVector Arena — Blueprint Source of Truth Record

**Document Version:** 1.0.0  
**Date:** 2026-11-03  
**Status:** Recorded & Verified  
**Author:** Principal Product Architect & Technical Lead  

---

## 1. Blueprint Location & Provenance

In accordance with Phase 1 tasks and repository discovery procedures:

- **Expected Target Path:** `docs/product/blueprint-v4.md`
- **Current Workspace State:** `e:\keyboard` was initialized as an empty directory with no existing files or pre-existing commits.
- **Source Blueprint Discovered:** `C:\Users\vivek\Downloads\typevector-arena-antigravity-prompts.md`
- **Blueprint Version:** TypeVector Arena Final Production Engineering Blueprint v4.0

### Discovery Evidence & Scope
1. A disk-wide search across local storage volumes (`C:\`, `D:\`, `E:\`) confirmed that no standalone `docs/product/blueprint-v4.md` existed prior to this phase.
2. The complete 15-phase specification was located at `C:\Users\vivek\Downloads\typevector-arena-antigravity-prompts.md` (75,249 bytes, modified 2026-11-03 22:20:27).
3. This specification directly encapsulates the functional, data, operational, and architectural directives of Blueprint v4.0 across all 15 implementation phases.
4. If a separate extended narrative document for Blueprint v4.0 is supplied by the Product Owner at a later date, it should be placed at `docs/product/blueprint-v4.md`. In the interim, this repository uses the explicit requirements, constraints, and protocol specifications derived directly from `C:\Users\vivek\Downloads\typevector-arena-antigravity-prompts.md`.

---

## 2. Core Preserved Blueprint Decisions

The following foundational decisions from Blueprint v4.0 are binding across all implementation phases:

1. **Frontend Architecture:**
   - Multi-page experience built with semantic HTML5, modern CSS3, and vanilla JavaScript ES modules.
   - Explicitly no frontend component frameworks (No React, Next.js, Vue, Angular, Svelte).
   - Vite is permitted strictly as development and static-asset build tooling, never as a component runtime.
   - Resilient keyboard input handling with zero animation overhead during active typing.

2. **Backend Architecture:**
   - Modular monolith implemented in Python with FastAPI.
   - Strict domain package encapsulation, single direction dependency flow, and explicit transaction ownership.
   - No premature microservices, Kafka, or Kubernetes.

3. **Data & Storage Authority:**
   - **PostgreSQL** is the sole authoritative system of record for all persistent data: identity, organizations, registrations, event rules, immutable prompts, accepted ranked input batches, score calculations, review cases, and published official results.
   - **Redis** is strictly non-authoritative: utilized solely for ephemeral coordination, outbox message distribution fanout, and pub/sub spectator cache snapshots. Redis failure must never result in corruption or loss of authoritative domain state.

4. **Async & Background Execution:**
   - **Celery** with transactional outbox event consumption for asynchronous processing (report generation, audit archiving, email/notification dispatch, and data retention sweeps).
   - Task idempotency and failure recovery without DB compromise.

5. **Toolchain & Package Management:**
   - `pnpm` for frontend/workspace orchestration and scripts.
   - `uv` for deterministic, locked Python virtual environment and dependency resolution.

6. **Engine Separation & Status Semantics:**
   - Separate practice typing engine and ranked tournament input engine with independent configuration, canonicalization profiles, and metrics.
   - Explicit, honest status semantics across UI and APIs: `Local`, `Pending`, `Saved`, `Provisional`, `Official`, `Unavailable`.
   - Never trust the client browser for scores, timestamps, admission eligibility, or rank calculations.

