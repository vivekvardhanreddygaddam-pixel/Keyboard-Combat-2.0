# TypeVector Arena — Celery, Transactional Outbox, and Background Processing Runbook

**Document Version:** 1.0.0  
**Phase:** 12 of 15 (Redis/Celery Integration, Notifications, Outbox, Exports, Retention)  
**Last Updated:** 2026-11-05  
**Governing Principle:** PostgreSQL is the exclusive system of record. Redis is non-authoritative. Background failures must never corrupt or block database transactions.

---

## 1. Architectural Overview

```
 [FastAPI Domain Mutation]
          │ (Single DB Transaction)
          ├── Commit Business Records (Event, Roster, Score)
          └── Commit TransactionalOutbox (status='pending')
                     │
                     ▼
 [Celery Outbox Worker / Dispatcher]
   - Polls / claims pending rows via SELECT ... FOR UPDATE SKIP LOCKED
   - Publishes to Redis pub/sub (ephemeral fanout) or queues background tasks
   - Records delivery timestamps and retry counts
   - Recovers stuck in_progress events on worker crash
                     │
     ┌───────────────┼───────────────┐
     ▼               ▼               ▼
[Redis Broadcast] [Notifications]  [Async Exports & Retention]
  (Spectators)     (Mock / SMTP)     (CWE-1236 Sanitization)
```

---

## 2. Worker Topology & Queue Configuration

Celery workers are partitioned into dedicated queues to prevent resource starvation (e.g., a heavy export job must never delay time-sensitive outbox dispatches or spectator updates):

| Queue Name | Primary Purpose | Concurrency | Prefetch | Time Limits (Soft / Hard) |
| :--- | :--- | :---: | :---: | :---: |
| `outbox` | PostgreSQL outbox polling and Redis channel fanout | 2 | 1 | 30s / 60s |
| `notifications` | Transactional email & alert pipeline | 4 | 1 | 60s / 120s |
| `exports` | Asynchronous CSV/JSON generation & sanitization | 2 | 1 | 240s / 300s |
| `retention` | Data compliance sweeps & expired session purges | 1 | 1 | 180s / 240s |
| `default` | General background tasks | 2 | 1 | 60s / 120s |

### Worker Safety Rules
- **Serialization:** Strictly JSON only (`task_serializer="json"`, `accept_content=["json"]`). Pickle is prohibited (CWE-502 defense).
- **Crash Recovery:** `task_acks_late=True` and `task_reject_on_worker_lost=True`. If a container dies while executing a task, the task remains in the broker and is reassigned.
- **Fair Dispatch:** `worker_prefetch_multiplier=1` ensures workers do not hoard tasks in advance.

---

## 3. Redis Broker Sizing & Memory Policies

Redis instances must be partitioned by database index:
- **DB 0:** Ephemeral pub/sub broadcast and spectator state cache.
- **DB 1:** Celery message broker (queue persistence).
- **DB 2:** Celery task result backend (TTL: 3600 seconds).

### Redis Memory Configuration
- Broker DB (`DB 1`): Must use `maxmemory-policy noeviction`. Redis must NEVER drop Celery tasks due to memory pressure; instead, write operations should fail so alarms trigger.
- Result Backend (`DB 2`): Uses `maxmemory-policy volatile-lru` with automatic 1-hour expiration (`result_expires=3600`).

---

## 4. Failure Modes & Operational Recovery Runbooks

### Runbook A: Redis Broker Outage
1. **Symptoms:** Worker logs show `ConnectionError: Cannot connect to Redis`.
2. **Impact on Core Domain:** **ZERO.** FastAPI API requests continue without interruption. Outbox rows accumulate safely in PostgreSQL with `status='pending'`.
3. **Recovery:**
   - Restore Redis connectivity (`docker compose restart redis` or failover).
   - Once online, the `sweep_pending_outbox` task automatically drains accumulated rows in FIFO order (`created_at ASC`).
   - Telemetry endpoint `GET /api/v1/operations/worker-health` transitions from `critical` back to `healthy`.

### Runbook B: Worker Process Crash Mid-Execution
1. **Symptoms:** Outbox rows left in `status='in_progress'`.
2. **Automated Recovery:**
   - Celery Beat executes `reconcile_stuck_outbox` every 60 seconds.
   - Any row in `in_progress` older than 300 seconds is reset to `status='pending'` and its `retry_count` is incremented.
   - The row is safely claimed by the next available worker.

### Runbook C: Poison Payload Handling
1. **Symptoms:** A corrupted or non-JSON-serializable outbox row is encountered.
2. **Behavior:** The dispatcher isolates the row, marks `status='failed'`, sets `retry_count=5`, logs a structured error, and continues processing the rest of the batch.
3. **Triage:** Query `SELECT * FROM transactional_outbox WHERE status = 'failed'`. Inspect `payload_json` and resolve root cause.

---

## 5. Notification Providers Status Report

| Provider | Status | Behavior & Guarantees |
| :--- | :--- | :--- |
| `MockNotificationProvider` | **Active (Dev/Test)** | Records deliveries in memory; supports simulated failure testing. |
| `LogOnlyNotificationProvider` | **Available** | Emits structured log with masked email (`a***@domain.com`); suppresses network egress. |
| `SMTPNotificationProvider` | **Unconfigured** | Reports `is_configured=False` unless `SMTP_HOST`, `SMTP_PORT`, and credentials are provided. Raises `ProviderNotConfiguredError` rather than claiming delivery. |

---

## 6. Data Retention & Immutability Policy

### Retention Classes
1. `purge_expired_sessions`: Deletes `UserSession` where `expires_at < NOW()`.
2. `prune_unverified_claims`: Prunes `IdentityClaim` where `status = 'pending'` and `created_at < NOW() - 90 days`.
3. `purge_expired_exports`: Physically deletes files older than 7 days from `data/exports/` and marks `ExportJob.status = 'expired'`.

### Non-Negotiable Permanent Records Guard
The following entities are **permanently preserved** and cannot be targeted for automated deletion:
`User`, `UserCredential`, `ParticipantScore`, `RankedAttempt`, `RankedInputBatch`, `ChallengePrompt`, `PublishedResult`, `PublishedRankRow`, `AuditEvent`.

All retention sweeps support `dry_run=True` to audit projected deletions prior to execution.

---

## 7. Local Development Commands

### Start Celery Worker
```bash
uv run celery -A typevector.celery_app worker -l INFO -c 4 -Q outbox,notifications,exports,retention,default
```

### Start Celery Beat Scheduler
```bash
uv run celery -A typevector.celery_app beat -S typevector.workers.beat_scheduler.SingleInstanceBeatScheduler -l INFO
```

### Inspect Worker Fleets
```bash
uv run celery -A typevector.celery_app inspect ping
uv run celery -A typevector.celery_app inspect active
```

