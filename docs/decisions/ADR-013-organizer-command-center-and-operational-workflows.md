# ADR-013: Organizer Command Center, Tenant Scoping, Operational Truthfulness, and Export Security

**Status:** Accepted  
**Date:** 2026-11-05  
**Deciders:** Principal Product Architect & Technical Lead  
**Consulted:** Competition Organizers, Tournament Directors, Security Engineers, Platform Operators  
**Informed:** Development Team, Frontend Engineers, Participant Community  

---

## Context & Problem Statement

Operating live competitive typing tournaments requires an administrative command center that is safe, responsive, strictly auditable, and resilient to operator error or adversarial exploitation:
1. **Tenant Isolation Failures (IDOR):** Organizers must never inspect, modify, or export data belonging to another organization. In multi-tenant tournament platforms, broken object-level authorization (BOLA/IDOR) on rosters, audit trails, exports, and live controls poses catastrophic confidentiality and integrity risks.
2. **Post-Draft Mutability:** Modifying rulesets, round sequence numbers, or challenge prompt text after an event has been published or scheduled compromises competitive fairness.
3. **Fabricated Telemetry & Vanity Metrics:** Operational dashboards often display synthetic "0ms" or fake 100% metrics when services or rounds are inactive. Operators require genuine, transparent telemetry (e.g. `None` / `Unavailable` for latency when no active input batches are executing) to make accurate incident determinations.
4. **CSV Formula Injection (CWE-1236):** Participant names, emails, and external claims may contain spreadsheet formula prefixes (`=`, `+`, `-`, `@`, `\t`, `\r`). Exporting raw roster or result CSV files opens organizer endpoints to client-side code execution in Excel / Google Sheets.
5. **Accidental Premature Standings Publication:** Previewing leaderboard or event standings must be strictly read-only; inspecting standings during live review must never create or mutate authoritative published results.
6. **Auditing Gaps in Administrative Actions:** Manual roster corrections, participant check-in overrides, round voiding, and organization member removals have historically lacked structured, searchable actor attribution with secret redaction.

---

## Decision Drivers

1. **Strict Server-Authoritative Scoping:** Every command center endpoint validates active organization membership (`owner`, `organizer`, or `judge`) before evaluating queries or mutations. Cross-tenant access attempts return HTTP 403 / 404 with zero data leakage.
2. **Draft-Only Mutation Invariant:** Modifying event metadata, updating rulesets, adding rounds, and pinning challenge prompts are strictly restricted to `EventStatus.DRAFT`. Once published, configuration is permanently frozen.
3. **Operational Truthfulness:** Metrics returned by `OperationsService` must reflect verified system state. Active socket counts derive from the live connection manager; PostgreSQL and Redis execute real probes; `durable_ack_latency_p95_ms` returns `None` when dormant rather than a fabricated `0.0`.
4. **Formula Injection Sanitization:** All CSV exports sanitize text cells by stripping leading whitespace and prepending a single quote (`'`) to any cell starting with `=`, `+`, `-`, `@`, `\t`, or `\r`.
5. **Read-Only Results Preview:** The results preview endpoint calculates projected standings in-memory using the immutable scoring engine without creating or updating `PublishedResult` records.
6. **Mandatory Audit Logging with Secret Redaction:** All administrative mutations (roster corrections, event status updates, member removal, export creation) emit structured `AuditEvent` records with explicit `actor_id` and reason, while sensitive keys (`password`, `secret`, `token`, `session`) are automatically masked.
7. **Zero-Framework Vanilla JS Command Surface:** The organizer frontend is built with pure vanilla JavaScript ES modules, scoped DOM utilities, and zero external runtime frameworks, ensuring minimal bundle size, complete auditability, and zero dependency drift.

---

## Architectural & Security Specifications

### 1. Tenant Boundary & Authorization Matrix

```
                      [Incoming Request]
                             │
                     (Auth & CSRF Guard)
                             │
                     (Role & Tenant Check)
                             │
     ┌───────────────────────┼───────────────────────┐
     ▼                       ▼                       ▼
[Platform Admin]      [Org Owner / Organizer]    [Org Judge]
  - Global scope        - Tenant event CRUD        - Restricted judging queue
  - System health       - Roster & check-in        - Case review & vote
  - Cross-org support   - Round setup & prompts    - No member removal
                        - Results preview & pub    - No export downloads
                        - Export generation        
                        - Member management
```

### 2. Operational Live Metrics Contract

`EventLiveMetricsRead` guarantees transparency:
- `connected_sessions_count`: Live count from `ranked_connection_manager.get_active_count(event_id)`.
- `durable_ack_latency_p95_ms`: Calculated from the active round's rolling ACK latency histogram; explicitly `None` when the round is dormant or closed.
- `postgres_healthy` / `redis_healthy`: Probed synchronously via `SELECT 1` and Redis ping.
- `service_status`: Explicit classification (`healthy`, `redis_degraded`, `database_degraded`, `event_paused`).

### 3. CSV Formula Injection Defense (CWE-1236)

Export generation in `ExportService` processes every string field through `sanitize_csv_value`:
```python
def sanitize_csv_value(value: object | None) -> str:
    if value is None:
        return ""
    val_str = str(value)
    clean = val_str.strip()
    if clean and clean[0] in ("=", "+", "-", "@", "\t", "\r"):
        return f"'{clean}"
    return val_str
```

---

## Five-Axis Code Review

### Axis 1: Concurrency & Race-Safety
- **Optimistic Locking:** Round and event updates check and increment the entity `version` column, rejecting stale concurrent writes with `ConflictError`.
- **Atomic Export File Creation:** Export jobs generate unique UUID filenames in a dedicated staging directory, preventing collision or partial read vulnerabilities across concurrent export workers.
- **Connection Count Precision:** Active socket tracking uses in-memory thread-safe sets per event within `RankedConnectionManager`.

### Axis 2: Authorization & IDOR Defense
- **Strict Tenant Scoping:** Every query joins on `organization_id` or validates membership. Export downloads verify that the requesting user belongs to the owning organization or is a platform admin.
- **Judge Least-Privilege:** Judges are granted access to judging cases and appeals, but blocked from modifying event configuration, initiating export downloads, or removing organization members.
- **Cookie & CSRF Enforcement:** All command center mutations require valid session credentials and matching `X-CSRF-Token` headers.

### Axis 3: Data Integrity & Immutability
- **Lifecycle Transition Guards:** Once an event transitions out of `DRAFT`, `RoundService.create_round` and `pin_challenge_prompt` reject all modifications with `InvariantViolationError`.
- **Isolated Standings Preview:** Standings preview executes in-memory aggregation via `ResultsService.preview_results` without modifying persistent `published_results` tables.
- **Sanitized Persistence:** No unsanitized participant formulas escape into downloaded CSV files.

### Axis 4: Error Handling & Observability
- **RFC 7807 Compliance:** All API errors return structured Problem Details JSON (`title`, `status`, `detail`, `code`).
- **Domain Exceptions:** Clear segregation of `EntityNotFoundError` (404), `ForbiddenError` (403), `ConflictError` (409), and `InvariantViolationError` (422).
- **Searchable Audit Trail:** Audit logs support filtering by `target_type`, `event_type`, `date_from`, and `date_to`, enabling incident post-mortems and compliance reviews.

### Axis 5: Operational Truthfulness & Privacy
- **Honest Metrics:** Latency metrics never fabricate synthetic zeros; `None` communicates dormant status clearly to operators.
- **Secret Redaction:** `AuditService.redact_payload` recursively masks passwords, secret keys, and bearer tokens in audit entries.
- **Client Zero-Scoring Authority:** The frontend command interface displays server-computed rankings and telemetry exclusively; no client-side arithmetic determines rank or scores.

---

## Consequences

### Positive
- Fully functional, highly audited, and tenant-isolated command center for competition organizers.
- Zero risk of formula injection attacks via exported rosters or results.
- Complete operational clarity during live rounds without misleading telemetry.
- Zero client-side framework bloat; fast loading vanilla JS ES modules.

### Negative / Trade-offs
- Export jobs write sanitized files to disk; requires periodic cleanup or disk quota monitoring (addressed in Operations Domain retention jobs).
- In-memory result preview on events with large participant rosters (1,000+ competitors) incurs CPU time for ranking compilation; acceptable given tournament scale and bounded rounds.

