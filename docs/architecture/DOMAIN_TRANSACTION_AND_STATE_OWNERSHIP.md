# TypeVector Arena — Domain Transaction & State Ownership Architecture

**Document Version:** 1.0.0  
**Date:** 2026-11-04  
**Status:** Approved Architectural Standard  

---

## 1. Domain Responsibility & Layer Separation

TypeVector Arena follows a clean separation of concerns within a modular monolith:

```
[ HTTP / WebSocket Request ]
            │
            ▼
┌───────────────────────────┐
│       FastAPI Router      │  <-- Thin HTTP coordination: param parsing, auth extraction,
└─────────────┬─────────────┘      HTTP status mapping, and OpenAPI contracts.
              │
              ▼
┌───────────────────────────┐
│       Domain Service      │  <-- Owns business logic, domain invariants, state machines,
└─────────────┬─────────────┘      and multi-entity transaction boundaries.
              │
              ▼
┌───────────────────────────┐
│     SQLAlchemy Model      │  <-- Declarative entities with PostgreSQL constraints,
└─────────────┬─────────────┘      composite keys, and JSONB schemas.
              │
              ▼
┌───────────────────────────┐
│    PostgreSQL Database    │  <-- Single source of authoritative truth.
└───────────────────────────┘
```

---

## 2. Domain State Transitions & Mutation Ownership

| Domain Module | Primary State Machine / Entity | Allowed Transitions | Invariant Owner | Transaction Boundary Rule |
| :--- | :--- | :--- | :--- | :--- |
| **`identity`** | `User`, `UserSession` | `active` -> `suspended` -> `deleted` | `IdentityService` | Single-user transaction. Session rotation invalidates previous session token hash atomically. |
| **`organizations`**| `Organization`, `OrganizationMember` | `active` -> `suspended` | `OrganizationService` | Multi-tenant scoping. Member roles (`owner`, `organizer`, `reviewer`, `member`) checked before mutating org state. |
| **`events`** | `Event` (`draft` -> `published` -> `registration_open` -> `live` -> `paused` -> `scoring` -> `finalized` -> `archived`) | Linear lifecycle state machine with optimistic locking (`version`). | `EventService` | Lifecycle transitions require atomic optimistic version increment (`WHERE version = :current_version`). |
| **`registrations`**| `EventRegistration` (`pending` -> `confirmed`, `waitlisted`, `cancelled`) | Capacity check (`COUNT(confirmed) < capacity`). Cancelled releases reservation. | `RegistrationService` | Atomic row-lock `SELECT ... FOR UPDATE` on `events` capacity counter during registration races. |
| **`rounds`** | `Round` (`scheduled` -> `active` -> `paused` -> `closed`, `voided`) | Progression order (`sequence_number`). Prompts must be pinned before activating. | `RoundService` | Active round transition pins immutable `challenge_prompts` version and SHA-256 checksum. |
| **`ranked_input`**| `RankedAttempt`, `RankedInputBatch` | Monotonic batch sequence (`batch_sequence_number`). Writer generation fencing (`socket_writer_generation`). | `RankedInputService` | Input ACK is strictly dispatched AFTER `ranked_input_batches` row commits to PostgreSQL. Stale writer generations rejected. |
| **`scoring`** | `ParticipantScore` (`provisional` -> `reviewed` -> `official`, `voided`) | Score calculated strictly server-side. Completion gating: accuracy >= `min_accuracy_pct` and `arena_score` integer. | `ScoringService` | Attempt completion atomically creates or updates `participant_scores` with deterministic canonical hash. |
| **`results`** | `PublishedResult`, `PublishedRankRow` | Immutable version increment (`version_number = N + 1`). Prior versions marked `is_current = False`. | `ResultsService` | Dual-step atomic publication: unsets previous `is_current`, inserts new `PublishedResult` and all `PublishedRankRow`s in one transaction. |
| **`integrity_review`**| `IntegrityCase`, `IntegrityAppeal` | `flagged` -> `under_review` -> `upheld`, `dismissed`. Dual-approval for severe sanctions. | `IntegrityReviewService` | Flagging does not immediately disqualify; flags append to review queue for human organizer review. |
| **`broadcast`** | Redis Pub/Sub Channels (Ephemeral) | No persistent state machine. Non-authoritative fanout. | `BroadcastService` | Dispatched asynchronously or via transactional outbox worker. Redis outage never corrupts database. |
| **`notifications`**| `TransactionalOutbox`, `NotificationDelivery` | `pending` -> `dispatched`, `failed` (retry <= 5). | `NotificationService` | Domain events written to `transactional_outbox` in the SAME transaction as the business entity mutation. |
| **`exports`** | `ExportJob` (`queued` -> `processing` -> `ready`, `failed`) | Async generation worker. CSV sanitization guards against formula injection (`=`, `@`, `+`, `-`). | `ExportService` | Job record created in DB, executed by Celery worker, writes file path upon completion. |
| **`audit`** | `AuditEvent` (Append-Only) | INSERT only. Updates and deletes are prohibited. | `AuditService` | Privileged actions write an unmodifiable audit row recording actor, IP, timestamp, and diff payload. |
| **`operations`** | `RetentionJob` (`running` -> `completed`, `failed`) | Sweep executed periodically or on demand. Purges expired sessions and audit retention windows. | `OperationsService` | Bulk operations run in bounded batches (`LIMIT 1000`) to prevent transaction lock exhaustion. |

---

## 3. Database Layer Invariants & Anti-Corruption Rules

1. **Composite Foreign Keys Prevent Cross-Event Bleed:**
   - A participant's ranked attempt must reference a `round_id` and `event_id` matching `rounds(id, event_id)` AND an `event_id` and `user_id` matching `event_registrations(event_id, user_id)`.
   - It is physically impossible to submit an attempt for Event A using a round from Event B or a user registered only for Event C.
2. **Integer Scoring Authority:**
   - `arena_score` is stored as an integer (`BigInteger`). Floating point inaccuracies are eliminated at the schema level.
3. **Immutability of Historical Evidence:**
   - Challenge prompts and published results are versioned (`version_number`). Published results are signed (`signed_hash`) and never overwritten in place. Amendments publish a new version.
4. **Outbox Guarantee:**
   - Background workers poll `transactional_outbox` with `SELECT ... FOR UPDATE SKIP LOCKED` to avoid duplicate processing and guarantee at-least-once delivery to Redis/email providers.

