# ADR-014: Celery Background Processing, PostgreSQL Outbox Dispatcher, and Privacy-Aware Integrations

**Status:** Accepted  
**Date:** 2026-11-05  
**Deciders:** Principal Product Architect & Technical Lead  
**Consulted:** Engineering Team, DevOps Engineers, Security Reviewers  
**Informed:** Platform Operators, UI/UX Engineers, Participant Community  

---

## Context & Problem Statement

Asynchronous work in TypeVector Arena spans critical domain activities:
1. **Event Dispatch:** Broadcasting lifecycle transitions and live tournament metrics to Redis pub/sub.
2. **Notification Pipelines:** Delivering transactional emails, check-in alerts, and appeal resolutions.
3. **Data Exports:** Asynchronously generating large CSV and JSON files for event organizers.
4. **Data Retention & Compliance:** Pruning expired sessions, purging unverified claims, and cleaning temporary export files.

Executing these operations synchronously inside HTTP request cycles threatens API latency, risks partial failures, and creates race conditions. Furthermore:
- **Broker Vulnerabilities:** Using insecure serialization (such as Python `pickle`) creates remote code execution (RCE) attack vectors (CWE-502).
- **Outbox Inconsistencies:** If background workers crash mid-flight, events must not be lost or permanently blocked.
- **Dual-Scheduler Races:** Running Celery Beat across multiple container replicas can trigger duplicate task execution unless protected by single-scheduler distributed locking.
- **Untruthful Delivery Claims:** Systems often claim messages were "sent" even when external providers are unconfigured.
- **Overly Aggressive Deletions:** Unchecked retention scripts risk purging essential competition evidence, scores, or audit logs.

---

## Decision Drivers

1. **PostgreSQL as Sole Authoritative Store:** Outbox events are committed transactionally to PostgreSQL within the same atomic transaction as the business mutation. Redis remains strictly ephemeral.
2. **Safe Serialization Protocol:** Celery is strictly restricted to JSON serialization (`task_serializer="json"`, `accept_content=["json"]`). Pickle and untrusted serializers are explicitly prohibited.
3. **Crash Resilience & Late Acknowledgments:** Workers use `task_acks_late=True` and `task_reject_on_worker_lost=True`, ensuring tasks remain in the broker if a worker dies abruptly.
4. **PostgreSQL Outbox Claiming & Reconciliation:** Outbox rows are claimed using `SELECT ... FOR UPDATE SKIP LOCKED` (or atomic state updates) to prevent duplicate processing. A periodic reconciliation task recovers rows stuck in `in_progress` due to worker failure.
5. **Truthful Notification Pipeline:** The system provides explicit provider abstraction (`MockNotificationProvider`, `LogOnlyNotificationProvider`, `SMTPNotificationProvider`). External providers without genuine credentials report `is_configured=False` and refuse to falsely claim successful delivery.
6. **CWE-1236 Formula Injection Defense:** All exported CSV cells starting with `=`, `+`, `-`, `@`, `\t`, or `\r` are sanitized with a single-quote prefix.
7. **Protected Competition & Audit Records:** Automated retention sweeps are hardcoded to reject any deletion of permanent entities (`User`, `UserCredential`, `ParticipantScore`, `RankedAttempt`, `RankedInputBatch`, `ChallengePrompt`, `PublishedResult`, `PublishedRankRow`, `AuditEvent`).
8. **Beat Single-Scheduler Safeguard:** `SingleInstanceBeatScheduler` uses a Redis distributed lock (`tv:beat:active_scheduler_lock`) with TTL to ensure only one scheduler fires tasks across clustered deployments.

---

## Five-Axis Code Review

### Axis 1: Concurrency & Race-Safety
- **Atomic Outbox Claiming:** Concurrent worker processes claim outbox rows safely via `SKIP LOCKED` semantics without double-processing.
- **Beat Distributed Lock:** Renewable distributed lock on Redis prevents duplicate scheduling when multiple Celery Beat containers are deployed.
- **Prefetch Control:** `worker_prefetch_multiplier=1` guarantees fair task distribution across worker slots.

### Axis 2: Authorization & Access Control
- **Export Download Scoping:** Organizers can only download export files belonging to their active organization; requests outside the tenant boundary or on expired files are rejected with HTTP 403 / 404.
- **Worker Health Guard:** `GET /operations/worker-health` requires privileged organizer or platform_admin authorization.
- **Unconfigured Provider Guard:** External SMTP delivery throws `ProviderNotConfiguredError` if invoked without explicit credentials.

### Axis 3: Data Integrity & Immutability
- **Transactional Outbox Commitment:** Outbox events are written in the same PostgreSQL transaction as domain entities; if the business transaction rolls back, zero outbox rows exist.
- **Non-Negotiable Retention Guard:** Critical competition evidence and audit logs are hardcoded as protected and cannot be deleted by automated retention routines.
- **Poison Payload Isolation:** Corrupted or malformed outbox payloads are quarantined with `status='failed'` without crashing worker loops.

### Axis 4: Error Handling & Observability
- **Bounded Exponential Backoff:** Outbox failures retry up to `MAX_OUTBOX_RETRIES` (5 attempts) with exponential backoff before transitioning to terminal failure.
- **Stuck Event Recovery:** Any event abandoned in `in_progress` for > 300 seconds is automatically reset to `pending` by the reconciliation task.
- **Privacy-Aware Logging:** Keystroke arrays, typing prompts, passwords, and tokens are scrubbed before task logging.

### Axis 5: Operational Truthfulness & Transparency
- **Genuine Worker Telemetry:** Worker health probes inspect actual Redis connectivity, active worker process counts, queue list lengths, and oldest pending outbox age.
- **Zero Delivery Fabrication:** Mock and log-only providers explicitly flag results as simulated; no false outbound delivery is claimed.

---

## Consequences

### Positive
- Reliable, observable, and retryable asynchronous task execution across all domain workflows.
- Absolute isolation of PostgreSQL business authority from broker outages.
- Elimination of RCE risks through strict JSON serialization.
- Verifiable protection against spreadsheet formula injection attacks (CWE-1236).

### Negative / Trade-offs
- Redis DB 1 is required as the Celery broker; during complete Redis outages, background tasks and ephemeral broadcast are delayed until Redis recovers (though DB data remains safe).

