# ADR-001: Technology Stack and Toolchain Selection

**Status:** Accepted  
**Date:** 2026-11-03  
**Deciders:** Principal Product Architect, Core Engineering Team  
**Blueprint Reference:** Blueprint v4.0 — Project-wide non-negotiable rules; Prompts 1, 2  

---

## 1. Context and Problem Statement
TypeVector Arena requires a robust, reproducible, and performant technical stack capable of delivering both an educational typing practice curriculum and high-integrity, real-time ranked competitive typing events. The platform needs strict deterministic execution, sub-millisecond input sequence verification, low overhead, and straightforward local development without excessive operational complexity.

## 2. Decision Drivers
- Strict alignment with Blueprint v4.0 mandated boundaries.
- Zero tolerance for framework-induced hydration mismatches, client-side state vulnerabilities, or uncontrolled DOM re-renders during high-frequency typing.
- Server-authoritative input validation and scoring with high developer velocity.
- Rapid, reproducible dependency resolution across both frontend and backend tooling.
- Single command local bootstrapper (`pnpm dev`) for local multi-service orchestration.

## 3. Considered Options
1. **Mandated Blueprint Stack:**
   - Frontend: Semantic HTML5, CSS3, modern Vanilla JavaScript ES modules (Vite for static asset bundling/dev serving only).
   - Backend: Python 3.12+ with FastAPI, Pydantic v2, SQLAlchemy 2.x (async), and Alembic.
   - Persistence & Cache: PostgreSQL (authoritative) + Redis (ephemeral coordination/fanout).
   - Async Workers: Celery with Redis broker and PostgreSQL transactional outbox.
   - Orchestration & Tooling: `pnpm` (workspace orchestration) + `uv` (deterministic Python package management).
2. **SPA / Full-Stack JS Framework (e.g., Next.js / React + Node.js / Express):**
   - Violates blueprint non-goals; adds virtual DOM overhead, complex SSR/client state synchronizations, and heavy framework dependencies.
3. **Microservices with Polyglot Services & Event Bus (e.g., Go/Rust microservices + Kafka):**
   - Violates blueprint non-goals; introduces distributed transaction overhead, network split-brain risks, and operational burdens premature for this phase.

## 4. Decision Outcome
**Chosen Option:** Mandated Blueprint Stack (Vanilla JS + FastAPI + PostgreSQL + Redis + Celery + pnpm + uv).

### Justification:
- **FastAPI + Pydantic v2:** Offers clean OpenAPI contract generation, asynchronous I/O capabilities for WebSockets, and strict schema validation.
- **Vanilla ES Modules & CSS:** Guarantees zero runtime overhead, direct DOM manipulation for critical typing surfaces, and total predictability of layout shifts.
- **uv + pnpm:** `uv` provides orders-of-magnitude faster, strictly locked Python environment resolution compared to pip/poetry, while `pnpm` provides efficient workspace orchestration.

## 5. Consequences and Trade-offs
### Positive Consequences
- Predictable performance: Zero framework rendering lag or garbage collection spikes during 120+ WPM typing bursts.
- Clean architectural surface: Clear separation between static browser assets and Python domain logic.
- Lightning-fast CI and local environment setup using `uv sync` and `pnpm install`.
- Strong, validated contract interfaces via auto-generated OpenAPI artifacts.

### Negative Consequences / Accepted Trade-offs
- Vanilla JS requires handcrafted DOM helpers and page controllers rather than reactive component libraries.
- Developers must manually manage multi-page routing, state lifecycles, and component cleanup.
- Python asyncio requires disciplined avoidance of blocking calls in async route and WebSocket handlers.

## 6. Compliance, Security, and Privacy Implications
- Eliminates npm package supply chain vulnerabilities typical of massive frontend dependency trees.
- Python backend allows strict centralization of authentication, session management, CSRF, and authorization.
- Secrets are isolated to backend `.env` and runtime environments; no secrets leak into frontend bundles.

## 7. Validation Strategy
- Baseline CI check runs `pnpm lint`, `uv run pytest`, and static typing validation.
- Healthcheck endpoints (`/healthz`, `/readyz`) verify connectivity of all primary services.
- Golden vector tests verify that score formulas and input protocols compute identically across platforms.

