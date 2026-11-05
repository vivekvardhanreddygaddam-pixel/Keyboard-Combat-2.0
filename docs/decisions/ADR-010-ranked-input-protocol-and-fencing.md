# ADR-010: Server-Authoritative Ranked WebSocket Protocol and Writer-Generation Fencing

**Status:** Accepted  
**Date:** 2026-11-04  
**Deciders:** Principal Product Architect & Technical Lead  
**Consulted:** Engineering Team, Tournament Integrity Reviewers  
**Informed:** Platform Operators, UI Engineers  

---

## Context & Problem Statement

Ranked competitive typing requires absolute fairness, verifiable audit trails, and strict server authority. Traditional typing websites often suffer from:
1. **Client-Authoritative Scoring:** Browsers compute WPM and accuracy locally and upload a summary score, inviting tampering, browser extension injection, and packet modification.
2. **Split-Brain Reconnection / Stale Tabs:** When a user opens multiple tabs or suffers a transient network drop, competing socket connections can overwrite each other's keystrokes.
3. **Out-of-Order Keystroke Ingestion:** High-latency networks or packet reordering can cause keystrokes to arrive out of order, corrupting the typed text projection.
4. **Premature Challenge Exposure:** Prompt texts leaked before the synchronized start time allow participants to memorize or prepare bot scripts.
5. **False Durability Promises:** Imprecise acknowledgments lead users to believe locally buffered inputs are saved on the server before database commit.

---

## Decision Drivers

1. **PostgreSQL as Sole Authority:** Redis is ephemeral and must never acknowledge or own accepted input.
2. **Durable ACKs:** An `INPUT_ACK` is dispatched strictly *after* PostgreSQL transaction commit.
3. **Monotonic Sequences & Idempotent Replay:** Every input batch carries a strictly monotonic sequence number `(attempt_id, sequence)`. Replaying an already committed sequence with identical digest returns the original committed outcome without duplicating text.
4. **Writer-Generation Fencing:** Each connection increments `socket_writer_generation`. Stale generations are rejected and evicted immediately.
5. **Constrained Ranked V1 Operations:** Only `insert(text)` (appends to end) and `backspace(count)` (deletes from end) are supported. Arbitrary cursor positioning and client paste are prohibited.

---

## Architectural & Protocol Specifications

### 1. Protocol Envelope (`arena-ws-v1`)

The WebSocket protocol defines strict schema envelopes for client-to-server and server-to-client messages:
- **Client Messages:** `CONNECT_ATTEMPT`, `INPUT_BATCH`, `HEARTBEAT`, `RESUME_REQUEST`, `CLIENT_STATUS`.
- **Server Messages:** `CONNECTED`, `ROUND_STATE`, `INPUT_ACK`, `INPUT_REJECTED`, `RESUME_STATE`, `CLOCK_SAMPLE`, `SERVICE_STATUS`, `ERROR`.

### 2. Monotonic Sequence Admission & Replay Rules

Let $W$ be the server watermark (`attempt.last_committed_sequence`):
1. **Next Sequence ($S = W + 1$):**
   - Applies operations incrementally to `current_text_projection` in $O(\text{ops})$.
   - Computes deterministic SHA-256 digest of resulting projection.
   - Appends immutable `RankedInputBatch` and `TransactionalOutbox` event.
   - Commits PostgreSQL transaction atomically and dispatches `INPUT_ACK`.
2. **Replay / Duplicate ($S \le W$):**
   - If `payload_digest_sha256 == existing_batch.payload_digest_sha256`: Returns existing committed `INPUT_ACK` (idempotent recovery for dropped network ACKs).
   - If `payload_digest_sha256 != existing_batch.payload_digest_sha256`: Rejects with `CONFLICTING_REPLAY_DIGEST`.
3. **Out-of-Order Gap ($S > W + 1$):**
   - Rejects with `OUT_OF_ORDER_SEQUENCE`, providing `expected_sequence = W + 1` and `recovery_instruction = "REPLAY_FROM_WATERMARK"`.

### 3. Writer-Generation Fencing

- When `CONNECT_ATTEMPT` is processed, `socket_writer_generation` is incremented with row-level locking (`SELECT ... FOR UPDATE`).
- Active connection manager evicts any existing connection for that `attempt_id` with error `STALE_WRITER_EVICTED` and closes with custom code `4409`.
- Any batch with `batch.writer_generation < attempt.socket_writer_generation` is rejected with `STALE_GENERATION`.

### 4. Challenge Prompt Masking & Immutability

- `ChallengePrompt` records are versioned and immutable once a round opens.
- If `round.status not in ("active", "in_progress")`, `ROUND_STATE.challenge_content` is masked as `None`, preventing premature inspection.

### 5. Transparent Client Durability Model

The client UI honestly reflects three distinct states:
1. `LOCAL`: Typed into client memory buffer.
2. `PENDING`: In-flight over WebSocket, awaiting database commit.
3. `SAVED THROUGH SEQ #X`: Confirmed committed to PostgreSQL.
The UI explicitly informs participants: *"Unacknowledged keystrokes are buffered locally in memory. If this tab crashes before an ACK is received, unacknowledged keystrokes are lost."*

---

## Consequences

### Positive
- Zero client score authority: All text mutations, timing measurements, and scoring are server-authoritative.
- Split-brain proof: Multiple tabs cannot interleave keystrokes due to generation fencing.
- Network resilience: Dropped ACKs or packet replays are handled cleanly without text duplication.
- High performance: Incremental projection avoids replaying entire keystroke histories on each batch.

### Negative / Trade-offs
- Every admitted input batch performs a PostgreSQL commit before ACK, requiring connection pooling and batched client dispatch (e.g., 50-100ms debouncing).
- In-memory buffered keystrokes can be lost if browser crashes prior to server ACK.

