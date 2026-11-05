# TypeVector Arena — Risk Analysis, Underspecified Policies & Decisions Log

**Document Version:** 1.0.0  
**Date:** 2026-11-03  
**Status:** Canonical Engineering Risk Assessment  
**Author:** Principal Product Architect & Technical Lead  
**Governing Rule:** Never silently resolve high-impact policy questions. Explicitly separate safe provisional assumptions from decisions requiring Product Owner approval.

---

## 1. Executive Summary
This document records critical architectural, concurrency, schema, privacy, and policy risks identified during Phase 1 technical discovery. In adherence to the core tenets of TypeVector Arena, this document establishes clear boundaries between:
1. **Safe Provisional Assumptions:** Engineering defaults that allow robust, secure foundation building without blocking progress.
2. **Decisions Requiring Product Owner Approval:** High-impact business, competitive, and legal decisions that MUST be formally signed off before hosting real or prize-bearing competitions.

---

## 2. Identified Contradictions & Ambiguities in Blueprint Directives

| ID | Topic | Blueprint Observation | Ambiguity / Contradiction | Engineering Resolution / Recommendation |
| :--- | :--- | :--- | :--- | :--- |
| **C-01** | Identity vs Claim | Blueprint requires roll numbers and emails for event registration, but emphasizes that self-entered identifiers are claims, not verified identity. | If self-entered roll number is unverified, can two users register with the same claim before verification? What releases the claim if an unverified user abandons the event? | Enforce claim uniqueness conditionally: active verified claims lock the identifier. Unverified claims hold a reservation with an expiration timer (e.g., 24 hours), after which the claim expires and releases uniqueness. |
| **C-02** | Ranked Deadline & Late Ingest | Blueprint dictates strict server-observed deadlines while acknowledging possible network packet jitter on WebSocket connections. | If a packet was transmitted by the client 50ms before deadline but arrived at the server 10ms after the server cutoff, is it admitted? | **Strict Server Admission:** To guarantee zero clock-skew exploits, the server-observed admission timestamp is authoritative. Any batch arriving after the server deadline is rejected with code `DEADLINE_EXCEEDED`. |
| **C-03** | Practice vs Ranked Engine Separation | Blueprint requires separate engines and configuration for Practice and Ranked modes, but both calculate WPM, accuracy, and error counts. | Should the underlying diff/comparison algorithm be completely duplicated or share a common mathematical core? | Shared low-level Unicode canonicalization and scalar diff primitives, but completely separated orchestration, metric formulas, and database persistence layers. Practice allows permissive editing; Ranked restricts operations to `insert` and end `backspace`. |
| **C-04** | Global Pause in Live Competitions | Blueprint mentions event-wide pause/void/restart policies while forbidding individual participant deadline extensions. | If an event is paused midway through a round, how are active typists in the middle of a word or sentence handled fairly? | When a global `PAUSE` command is executed, active round timers freeze instantly. Active typing sockets reject further input with `ROUND_PAUSED`. Upon `RESUME`, a standardized 5-second synchronized countdown is enforced across all connected clients before input admission re-opens. |

---

## 3. Concurrency & Race Condition Risks

```
                               CONCURRENCY HAZARD MATRIX
   ┌───────────────────────────┬───────────────────────────┬───────────────────────────┐
   │ Hazard                    │ Concurrency Mechanism     │ Mitigation Architecture   │
   ├───────────────────────────┼───────────────────────────┼───────────────────────────┤
   │ Overbooking at capacity   │ Simultaneous POST /register│ SELECT FOR UPDATE on event│
   │ boundary                  │ requests                  │ capacity row + DB check   │
   ├───────────────────────────┼───────────────────────────┼───────────────────────────┤
   │ Stale WebSocket Writer    │ Split-brain tabs / socket │ Incremental writer        │
   │ session hijacking         │ reconnect race            │ generation fencing        │
   ├───────────────────────────┼───────────────────────────┼───────────────────────────┤
   │ Out-of-order input batch  │ High-frequency keystroke  │ Monotonic sequence check; │
   │ arrival                   │ batches over TCP          │ strict sequence = N + 1   │
   ├───────────────────────────┼───────────────────────────┼───────────────────────────┤
   │ Duplicate publish request │ Multiple organizers clicking│ Optimistic version locking│
   │ for results               │ "Publish Official Results"│ on event state machine    │
   └───────────────────────────┴───────────────────────────┴───────────────────────────┘
```

### Detailed Concurrency Safeguards:
1. **Registration Capacity Race:**
   - Under heavy concurrent load, standard count-then-insert queries cause overselling.
   - **Mitigation:** Use `SELECT current_registrations, capacity_limit FROM events WHERE id = :event_id FOR UPDATE`, verify capacity, insert registration, and increment counter within the same atomic transaction. A PostgreSQL `CHECK (current_registrations <= capacity_limit)` constraint acts as a hard stop.
2. **WebSocket Writer-Generation Fencing:**
   - A user opens two browser tabs or experiences a rapid reconnect while the previous socket is still closing.
   - **Mitigation:** Each connection handshake issues an atomically incremented `writer_generation` integer stored in the attempt record. The admission transaction rejects any `INPUT_BATCH` whose payload generation is lower than the attempt's current `writer_generation`.
3. **Monotonic Sequence Admission:**
   - Client sends batches with monotonically increasing sequences: 1, 2, 3...
   - If Batch 2 is delayed and Batch 3 arrives first, Batch 3 is rejected with `OUT_OF_ORDER_SEQUENCE` and current watermark (1). Client must replay unacknowledged batches starting from watermark + 1.

---

## 4. Privacy, Security & Data Leakage Risks

1. **Public Leaderboard PII Leakage:**
   - *Risk:* Publishing leaderboards with real names, college roll numbers, or emails exposes student PII and violates privacy norms.
   - *Mitigation:* Public leaderboards (`/leaderboards/{eventId}`) only expose randomized participant public handles/aliases or event-scoped codes (e.g., `Typist-4821`). Real names, emails, and identifiers remain strictly confined to the Organizer Command Center behind role-based authorization.
2. **Spreadsheet Formula Injection in CSV Exports:**
   - *Risk:* A malicious user enters `=cmd\|'/C calc'!A0` or `=SUM(...)` as their public alias or name. When an organizer exports the roster to CSV and opens it in Excel, arbitrary code execution or data exfiltration occurs.
   - *Mitigation:* The `exports` domain sanitizes every text field: any string starting with `=`, `+`, `-`, `@`, `\t`, or `\r` is prepended with a single quote (`'`) to disable formula execution.
3. **Telemetry & Structured Log Scrubbing:**
   - *Risk:* Logging WebSocket frames or input batches could inadvertently capture typed passwords, sensitive personal notes, or secret verification codes in application logs.
   - *Mitigation:* Structured logging configuration explicitly strips input payload bodies. Logs record: `attempt_id`, `sequence`, `batch_size_bytes`, `operation_count`, `latency_ms`, and `status`. Typed text is never written to application logs.

---

## 5. Safe Provisional Assumptions (Engineering Defaults)

These assumptions allow implementation to proceed safely without blocking on policy sign-offs.

| ID | Area | Provisional Assumption | Rationale | Reversible? |
| :--- | :--- | :--- | :--- | :--- |
| **SPA-01** | Session Management | Server-issued `HttpOnly; Secure; SameSite=Lax` cookie storing a cryptographically random 256-bit session token with 7-day sliding expiry. | Standard, highly secure pattern resilient to client-side XSS. | Yes, easily replaced with IdP/OAuth. |
| **SPA-02** | Password Policy | Argon2id hashing (m=65536, t=3, p=4); minimum 12 characters length. | Exceeds modern OWASP security standards. | Yes, parameters configurable in settings. |
| **SPA-03** | Score Formula Baseline | Blueprint proposed `arena-score-v1`: gross WPM, net WPM, accuracy, completion penalty (incomplete attempts capped at <=699, exact completion >=700). | Implemented as draft scoring configuration with golden test vectors. Prize events locked until approved. | Yes, versioned formula pattern (`arena-score-v2`). |
| **SPA-04** | Practice Engine Modes | 8 core modes: common words, sentences/punctuation, short/long paragraphs, numbers/symbols, code snippets, speed sprint, accuracy challenge, endurance. | Comprehensive baseline covering all typical typing practice needs. | Yes, content is data-driven in database. |
| **SPA-05** | WebSocket Heartbeat | Ping/Pong intervals of 15 seconds; disconnect detection threshold at 45 seconds of silence. | Balances responsive reconnects with minimal network overhead. | Yes, configurable via environment settings. |
| **SPA-06** | Data Retention Sweep | Inactive practice sessions retained for 90 days; raw WebSocket batch logs for ranked events retained for 180 days after official publication, then archived. | Prevents unbounded database disk growth while preserving audit records. | Yes, retention policies configured per table. |

---

## 6. High-Impact Decisions Requiring Formal Product Owner Approval

The following items are **explicitly blocked from production prize events** until formally reviewed, decided, and signed off by the Product Owner:

| Decision ID | Item Requiring Approval | Core Question for Product Owner | Impact if Misaligned | Current Safe Guardrail |
| :--- | :--- | :--- | :--- | :--- |
| **POD-01** | **Prize-Event Official Scoring Formula Approval** | Is `arena-score-v1` (with incomplete cap <=699 and exact completion >=700) the final legally binding formula for monetary/prize tournaments? | Dispute over tournament payouts, accusations of unfair penalty weighting. | Backend restricts unapproved formulas to `DRAFT` status; `PUBLISH_OFFICIAL_RESULTS` is gated on formal rule approval. |
| **POD-02** | **Skill Track Numerical Level Criteria** | What are the exact WPM, accuracy %, and attempt count thresholds for Foundation, Beginner, Developing, Intermediate, Advanced, and Expert? | Inappropriate skill leveling, user confusion, or false claims of professional certification. | Displayed in UI with prominent `[Draft Criteria — Pending Approval]` badge; multi-attempt qualification implemented with clear disclaimers. |
| **POD-03** | **Event-Wide Pause & Void Thresholds** | Under what exact operational conditions (e.g., >5% of participants disconnected, or ACK latency >500ms for >15 seconds) is an organizer permitted or required to void/restart a round? | Accusations of organizer bias or arbitrary tournament restarts. | Organizer UI requires mandatory text rationale and secondary admin confirmation; pause/void actions log permanent audit events. |
| **POD-04** | **Participant Identity Verification Provider** | Will participant identities (e.g., University Roll Numbers, Corporate IDs) be verified via OAuth SSO, SAML, uploaded photo ID, or manual organizer CSV upload? | Roster fraud, ineligible participant participation, impersonation. | System treats entered identifiers strictly as unverified `IdentityClaim` records until verified by a documented, approved verification adapter. |
| **POD-05** | **Under-18 / Minor Participant Policy & GDPR/FERPA Compliance** | Are participants under the age of 18 permitted to compete in public events? What explicit parental consent and privacy retention rules apply? | Legal and regulatory violations regarding children's online data privacy. | Age verification gate on registration; PII strictly redacted on all public leaderboards. |

