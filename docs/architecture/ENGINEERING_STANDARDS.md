# TypeVector Arena — Engineering Standards, Conventions & Definition of Done

**Document Version:** 1.0.0  
**Date:** 2026-11-03  
**Status:** Canonical Engineering Standards  
**Author:** Principal Product Architect & Technical Lead  

---

## 1. Code Conventions & Language Standards

### 1.1. Python (Backend: `apps/api/`, `workers/`)
- **Version:** Python 3.12+ (strictly managed via `uv`).
- **Style Guide:** Strict adherence to PEP 8, formatted and linted via `ruff`.
- **Type Safety:** 100% type annotation coverage on all functions, classes, and service methods. Verified with `mypy --strict`.
- **Asynchronous I/O:**
  - Route handlers and WebSocket admission controllers must be `async def`.
  - Never execute blocking I/O (synchronous file access, `time.sleep`, blocking HTTP calls) inside async event loops. Always utilize `anyio` or delegate to Celery.
- **ORM & Database:**
  - SQLAlchemy 2.0 style syntax exclusively (`select(...)`, `session.execute(...)`).
  - No legacy query API (`session.query(...)`).
  - Async sessions (`AsyncSession`) with explicit transaction contexts (`async with session.begin():`).

### 1.2. JavaScript (Frontend: `apps/web/`)
- **Standard:** Modern Vanilla JavaScript (ES2022+ modules).
- **Prohibitions:** Strictly NO frontend component frameworks (No React, Vue, Svelte, Next, Angular).
- **Modularity:** Use native browser ES modules (`import`/`export`).
- **DOM Access:** Centralize DOM queries and event bindings within dedicated controller classes. Never inject raw unsanitized HTML via `innerHTML` without strict escaping.
- **Event Listeners:** Always retain references to event listeners for proper teardown on page unmount or view navigation to prevent memory leaks.

### 1.3. CSS & Design Tokens (`apps/web/css/`)
- **Standard:** Vanilla CSS3 utilizing CSS Custom Properties.
- **Token Naming:** Prefix all design tokens with `--tv-` (e.g., `--tv-color-surface-bg`, `--tv-font-mono`, `--tv-space-md`).
- **Component Classes:** BEM-like naming prefixed with `.tv-` (e.g., `.tv-card`, `.tv-btn--primary`, `.tv-table__header`).
- **Responsiveness:** Mobile-first media queries (`@media (min-width: 768px)`).
- **Accessibility:** High contrast ratios (WCAG AA minimum 4.5:1), visible focus rings (`--tv-focus-ring`), and `@media (prefers-reduced-motion: reduce)` support.

### 1.4. SQL & Database Schema Conventions
- **Identifiers:** Lowercase `snake_case` for all table names, columns, indexes, and constraints.
- **Pluralization:** Table names are plural (e.g., `users`, `events`, `rounds`, `ranked_attempts`).
- **Primary Keys:** Standard `id UUID PRIMARY KEY DEFAULT gen_random_uuid()` or composite keys where event isolation demands it.
- **Timestamps:** Every persistent entity must include `created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()` and `updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()`.
- **Constraint Naming:**
  - Primary Key: `pk_{table}`
  - Foreign Key: `fk_{source_table}_{target_table}_{column}`
  - Unique Constraint: `uq_{table}_{column_or_columns}`
  - Check Constraint: `ck_{table}_{rule_description}`
  - Index: `ix_{table}_{column_or_columns}`

---

## 2. Environment & Secrets Management Policy

1. **Zero Hardcoded Secrets:**
   - No passwords, private keys, API secrets, or session secrets may ever be committed to git.
   - Any accidental credential commit requires immediate credential revocation and rotation; deleting the line is insufficient.
2. **Configuration Loading:**
   - All backend configuration is loaded via Pydantic Settings (`pydantic-settings`) validating environment variables at application startup.
   - Missing or invalid critical configuration must cause startup failure immediately (`sys.exit(1)`) rather than running in an insecure state.
3. **Safe Placeholder Templates:**
   - `.env.example` must contain only safe documentation placeholders (e.g., `POSTGRES_PASSWORD=local_dev_password_change_me`).
4. **Client-Side Secret Isolation:**
   - The browser frontend (`apps/web/`) must never receive or process database credentials, Celery broker URLs, signing secrets, or third-party API private keys.

---

## 3. Database Migration Safety Rules

1. **Reversibility & Forward Compatibility:**
   - Every Alembic migration must include both a functional `upgrade()` and a safe `downgrade()` where technically feasible.
2. **Zero Destructive Routine Migrations:**
   - Never issue `DROP TABLE` or `DROP COLUMN ... CASCADE` in routine production migration paths.
   - Schema modifications on existing high-volume tables must follow the **Expand/Contract Pattern**:
     - *Phase 1 (Expand):* Add new column as nullable; dual-write in application layer.
     - *Phase 2 (Backfill):* Migrate historical data in small, non-locking batches.
     - *Phase 3 (Contract):* Enforce `NOT NULL` constraint and deprecate old column.
3. **Migration Verification Workflow:**
   - Test migrations against an empty database.
   - Verify upgrades on pre-existing populated schemas.
   - Measure lock acquisition times during migration execution to prevent connection timeouts.

---

## 4. Multi-Tier Testing Strategy

```
                              TESTING PYRAMID
                                    ▲
                                   / \
                                  / E2E\
                                 /Journey\
                                /─────────\
                               /Concurrency\
                              / & Race Tests\
                             /───────────────\
                            /Integration (PG) \
                           /───────────────────\
                          /Unit, Property & Gold\
                         /───────Vectors─────────\
```

1. **Tier 1: Unit & Property-Based Tests (`tests/unit/`)**
   - Pure logic testing: diff alignment algorithms, WPM mathematical formulas, sequence state transitions.
   - Property-based testing via `hypothesis` to fuzz boundary inputs, malformed Unicode, and extreme timer durations.
2. **Tier 2: Golden Vectors (`tests/golden_vectors/`)**
   - Exact, frozen input-to-score vectors verifying that `arena-score-v1` computes identical results across all environments.
3. **Tier 3: PostgreSQL Database Integration (`tests/integration/`)**
   - Real PostgreSQL test container (never SQLite).
   - Verifies constraint enforcement, foreign key cascades, atomic capacity reservations, and outbox writes.
4. **Tier 4: Concurrency & Protocol Conformance (`tests/concurrency/`, `tests/protocol/`)**
   - Multi-threaded / async simulations of concurrent WebSocket writers, stale-writer fencing, and registration capacity boundary races.
5. **Tier 5: End-to-End User Journeys (`tests/e2e/`)**
   - Complete verification of user journeys from registration through live typing round to official result publication.
6. **Tier 6: Accessibility & UI Verification**
   - Automated WCAG checks, keyboard-only manual verification, high-contrast validation, and reduced-motion enforcement.

---

## 5. Strict Definition of Done (DoD)

Before any phase, prompt, or pull request is marked as complete:
- [ ] **Architecture Alignment:** Fully adheres to Blueprint v4.0 boundaries and active ADRs; introduces no forbidden frameworks or infrastructure.
- [ ] **Code Quality:** All Python code passes `ruff check`, `ruff format --check`, and `mypy --strict`. All JavaScript passes linting.
- [ ] **Database & Migrations:** All schema changes have safe, reversible Alembic migrations tested against clean PostgreSQL.
- [ ] **Test Coverage & Verification:** All corresponding unit, integration, or concurrency tests pass with recorded terminal evidence.
- [ ] **Security & Privacy:** No hardcoded secrets, no PII leakage in public views or logs, CSRF and RBAC permissions strictly enforced.
- [ ] **Truthfulness & Honest States:** UI displays genuine server state (`Local`, `Pending`, `Saved`, `Provisional`, `Official`, `Unavailable`); zero fake metrics or dead buttons.
- [ ] **Documentation & Handoff:** All 5 handoff documents (`docs/agent/*.md`) and RTM updated to reflect actual progress and open blockers.

