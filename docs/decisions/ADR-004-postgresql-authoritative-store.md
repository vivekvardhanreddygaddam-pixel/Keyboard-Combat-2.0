# ADR-004: PostgreSQL as Exclusive System of Record and Source of Truth

**Status:** Accepted  
**Date:** 2026-11-03  
**Deciders:** Principal Product Architect, Core Engineering Team  
**Blueprint Reference:** Blueprint v4.0 — Project-wide non-negotiable rules; Prompts 1, 4, 8, 10  

---

## 1. Context and Problem Statement
In a competitive typing platform, data integrity is paramount. Competition outcomes, prize eligibility, and participant rankings depend on absolute precision. We must establish a clear, unequivocal system of record that prevents race conditions, ensures atomicity, and eliminates any ambiguity regarding state authority during network disruptions, node failures, or concurrent actions.

## 2. Decision Drivers
- Absolute durability and ACID consistency for identity, event rules, immutable prompts, accepted ranked input batches, score revisions, appeals, and published results.
- Prevention of duplicate registrations and capacity overbooking under high-concurrency registration spikes.
- Prevention of input data loss or duplicate commits in WebSocket ranked attempt sessions.
- Inability for client-side manipulation or cache-level desynchronization to forge or alter official records.

## 3. Considered Options
1. **PostgreSQL as Exclusive Authority (Chosen):**
   - Single relational database engine owning all durable domain state.
   - Rich relational constraints: Foreign keys, unique indexes, check constraints, composite isolation keys.
   - Serialized or Read Committed transactions with explicit row-level locking where required (`SELECT FOR UPDATE`).
   - Transactional Outbox pattern implemented in PostgreSQL to ensure downstream messaging consistency.
2. **Dual-Authority / Split-Brain Model (PostgreSQL + Redis):**
   - Storing live ranked attempts and scores in Redis and persisting to PostgreSQL only upon round completion.
   - High risk of data loss on Redis crashes, failovers, or network partitions; unacceptable for official competition integrity.
3. **NoSQL / Document Database (e.g., MongoDB, DynamoDB):**
   - Lacks the rigid relational constraints, composite foreign keys, and multi-entity cross-table integrity guarantees needed to enforce event and organization boundaries.

## 4. Decision Outcome
**Chosen Option:** PostgreSQL as the exclusive System of Record and single source of truth.

### Key Architectural Invariants:
1. **Single-Transaction Ranked Input Admission:**
   - Every accepted ranked input batch (`INPUT_BATCH`) is admitted inside a single PostgreSQL transaction.
   - The transaction validates: round state, writer generation fencing, monotonic sequence number, and size limits.
   - The transaction writes: the immutable batch record, updates the materialized attempt text projection and watermark, and inserts a message into the transactional outbox table.
   - The WebSocket `INPUT_ACK` is dispatched to the client **only after** the PostgreSQL transaction successfully commits.
2. **Cross-Tenant and Cross-Event Referential Integrity:**
   - Enforced directly at the schema layer via composite foreign keys (e.g., `(event_id, round_id)` and `(event_id, registration_id)`). It is physically impossible at the database level for an attempt to link to a round from Event A and a registration from Event B.
3. **Immutability of Historical Versions:**
   - Official published results, rule versions, challenge prompts, and canonicalization configurations are strictly append-only. Updates in place are disallowed. Amendments create new immutable versions with links to prior revisions.

## 5. Consequences and Trade-offs
### Positive Consequences
- Rock-solid consistency: No ghost registrations, no lost input batches, and zero score drift.
- Audit readiness: Every privileged action, score change, and lifecycle shift has durable relational evidence and timestamps.
- Simple, proven backup and point-in-time recovery (PITR) procedures.

### Negative Consequences / Accepted Trade-offs
- Write throughput to PostgreSQL must be carefully managed. Transaction duration during input batch ingestion must be minimal (sub-millisecond lock duration).
- Connection pooling must be strictly configured (via PgBouncer or SQLAlchemy async pool) to prevent connection starvation under load.

## 6. Compliance, Security, and Privacy Implications
- Role-based database permissions: Backend application connects with least-privilege credentials.
- PII (emails, roll numbers) is isolated and access-controlled; test fixtures and lower environments never receive production dumps.
- Deletion tombstones and retention sweeps are executed via audited database procedures.

## 7. Validation Strategy
- Concurrency test suites: Simultaneous registrations at capacity limit to prove zero overbooking.
- Crash injection tests: Terminating the API process after database commit to verify idempotent recovery on reconnect without duplicate input.
- Schema constraint tests verifying that cross-tenant and cross-event references fail immediately at the database level.

