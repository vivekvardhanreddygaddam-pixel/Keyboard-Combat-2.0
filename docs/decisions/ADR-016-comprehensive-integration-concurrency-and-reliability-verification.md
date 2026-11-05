# ADR-016: Comprehensive Integration, Concurrency, and Reliability Verification

**Status:** Accepted  
**Date:** 2026-11-05  
**Deciders:** Principal Product Architect & Technical Lead  
**Consulted:** Engineering Team, QA Engineers, Reliability Leads  
**Informed:** Platform Operators, UI/UX Engineers, Participant Community  

---

## Context & Problem Statement

Prior to operational deployment (Phase 15), TypeVector Arena required a comprehensive quality, concurrency, resilience, and capacity verification pass. Key technical risks addressed during this verification included:
1. **TOCTOU Registration Races:** Concurrent competitor sign-ups exceeding event capacity due to uncoordinated reads and writes.
2. **Conflicting Lifecycle Mutations:** Competing organizer commands triggering ambiguous state transitions or double starts/closes.
3. **Split-Brain WebSocket Ingestion:** Concurrent browser tabs or socket flapping causing out-of-order typing batches.
4. **Phantom ACKs under Rollback:** WebSocket acknowledgments being dispatched to clients before database transactions reliably commit.
5. **Idempotency & Replay Ambiguity:** Replayed sequence numbers must be distinguished between benign duplicate transmissions and malicious tampering.
6. **Unsubstantiated Performance Claims:** The platform must not claim untested concurrent user limits or latencies as achieved production SLAs.

---

## Decision Drivers

1. **Deterministic Quality & Zero Regressions:** All 16 domain packages must be verified via reproducible integration and unit test suites.
2. **PostgreSQL as Sole System of Record:** Database rollbacks must guarantee zero state leakage, zero phantom ACKs, and safe outbox buffering during downstream outages.
3. **Pessimistic & Optimistic Concurrency Controls:**
   - Registration capacity enforced via row-level pessimistic locking (`SELECT ... FOR UPDATE`).
   - Event and round lifecycles protected via monotonic optimistic versioning (`version`).
4. **Strict Sequence & Writer Fencing:**
   - Monotonic sequence gating ($S = W + 1$) on inbound keystrokes.
   - Writer-generation fencing with code `4409` socket termination for stale connections.
5. **Truth in Telemetry & Workload Modeling:**
   - Clearly document mathematical workload models and empirical micro-benchmark baselines.
   - Propose candidate SLO targets without claiming unverified multi-node production certification.

---

## Five-Axis Code Review

### Axis 1: Concurrency & Race-Safety
- **Capacity Race Verification:** High-concurrency test simulating 20 simultaneous registration threads for 3 seats resulted in exactly 3 confirmations and 17 safe rejections with zero overbooking.
- **Optimistic Locking Conflict Detection:** Competing mutations referencing an outdated event version are rejected with `ConflictError`.
- **Writer Fencing:** Sockets from older generations are closed with `4409` upon newer session connection.

### Axis 2: Authorization & Access Control
- **Cross-Tenant Isolation:** Maintained strict tenant verification on results preview, scoring recalculation, and integrity review.
- **Separation of Powers:** Maintained dual-approval reviewer separation and independent appellate judge boundaries.

### Axis 3: Data Integrity & Immutability
- **Post-Commit ACK Guarantee:** ACKs are emitted strictly after PostgreSQL transaction commits. Rollbacks produce zero ACKs.
- **Idempotent Replay Handling:** Duplicate sequence numbers with matching digests return prior ACKs without duplicate operations.
- **Tampering Detection:** Duplicate sequence numbers with conflicting digests raise `ConflictError`.

### Axis 4: Error Handling & Observability
- **Resilient Outbox Fallback:** Redis outages keep outbox rows in PostgreSQL in `pending` status, resuming delivery upon broker restoration.
- **Sequence Gap Detection:** Out-of-order sequence frames ($S > W + 1$) are rejected with explicit sequence gap errors.

### Axis 5: Product-Truth & Workload Modeling
- **Empirical Micro-Benchmarks:** Measured sub-0.1ms p95 execution across diff engine, scoring engine, canonicalization, and projection mutations.
- **SLO Candidate Designation:** Explicitly categorized performance metrics as candidate targets pending multi-node staging cluster soak tests.

---

## Decision Outcome

Accepted the verification suite and empirical baselines. All 164 functional tests pass with zero failures.

### References & Evidence

- **Integration Test Suite:** [`test_integration_concurrency_and_reliability.py`](file:///e:/keyboard/apps/api/tests/test_integration_concurrency_and_reliability.py) (14 tests covering user journeys, race conditions, and failure injection)
- **Workload Models:** [`WORKLOAD_MODEL_AND_CAPACITY_TARGETS.md`](file:///e:/keyboard/docs/testing/WORKLOAD_MODEL_AND_CAPACITY_TARGETS.md)
- **Reliability Report:** [`INTEGRATION_AND_RELIABILITY_REPORT.md`](file:///e:/keyboard/docs/testing/INTEGRATION_AND_RELIABILITY_REPORT.md)
- **Benchmark Artifact:** [`local_benchmark_results.json`](file:///e:/keyboard/docs/testing/artifacts/local_benchmark_results.json)

