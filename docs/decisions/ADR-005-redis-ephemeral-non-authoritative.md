# ADR-005: Redis Role strictly as Ephemeral Broker and Non-Authoritative Fanout

**Status:** Accepted  
**Date:** 2026-11-03  
**Deciders:** Principal Product Architect, Core Engineering Team  
**Blueprint Reference:** Blueprint v4.0 — Project-wide non-negotiable rules; Prompts 1, 4, 8, 9, 12  

---

## 1. Context and Problem Statement
TypeVector Arena requires low-latency, real-time message distribution for event lobbies, live round countdowns, spectator leaderboards, and asynchronous task coordination. However, distributed messaging systems often introduce consistency hazards when used as an informal data store. We must rigorously demarcate the architectural role and failure model of Redis within the system.

## 2. Decision Drivers
- Non-negotiable Blueprint v4.0 rule: "PostgreSQL is the authority... Redis is not the system of record."
- Absolute protection against state desynchronization or data loss during Redis server restarts, network partitions, or memory evictions.
- Real-time spectator and participant fanout must not starve or degrade the latency of critical input batch acknowledgments (`INPUT_ACK`).
- Reliable asynchronous job execution (Celery) with at-least-once delivery semantics that cannot corrupt persistent business records.

## 3. Considered Options
1. **Redis strictly as Ephemeral Message Broker & Fanout Layer (Chosen):**
   - Redis Pub/Sub utilized for broadcasting committed event state and cached leaderboard snapshots to WebSocket connection servers.
   - Redis used as the Celery task queue broker.
   - Transient operational metrics and rate-limiting counters stored with explicit TTLs.
   - Complete loss of Redis results only in transient fanout delay or re-queued tasks; zero durable data loss.
2. **Redis as In-Memory State Store (Write-Behind Cache):**
   - Recording live keystrokes, participant connection states, or score tallies in Redis hashes and flushing to PostgreSQL asynchronously.
   - Rejected: Power outages, memory exhaustion, or network splits could cause permanent loss of competitive input or score discrepancies.
3. **Omitting Redis Entirely (PostgreSQL Polling / LISTEN-NOTIFY only):**
   - Polling PostgreSQL for WebSocket state and Celery queueing.
   - Rejected: Heavy database connection contention under hundreds of concurrent spectators and high polling load.

## 4. Decision Outcome
**Chosen Option:** Redis strictly as Ephemeral Broker and Non-Authoritative Fanout.

### Exact System Responsibilities:
1. **Transactional Outbox Bridge:**
   - State mutations (e.g., round status change, approved score, participant check-in) are committed to the PostgreSQL `outbox_events` table within the primary business transaction.
   - A lightweight outbox dispatcher reads committed rows and publishes them to Redis Pub/Sub channels.
   - If Redis is down, outbox events accumulate safely in PostgreSQL. Once Redis recovers, the dispatcher resumes without missing an event.
2. **Spectator Leaderboard Snapshots:**
   - Spectator leaderboards receive throttled/coalesced snapshots (e.g., 1–2 Hz) over Redis channels.
   - These snapshots are clearly labeled as `Non-Authoritative Spectator Preview` and do not trigger database writes.
3. **Asynchronous Background Tasks (Celery):**
   - Redis functions as the Celery broker for background jobs (exports, email notifications, audit archiving).
   - Tasks are idempotent by design; duplicate delivery due to network hiccups or worker crashes does not compromise domain integrity.
4. **WebSocket Fanout Isolation:**
   - WebSocket subscriber loops handling Redis Pub/Sub channels run decoupled from the WebSocket input admission loop. Spectator socket congestion or network backpressure can never block or delay an active typist's `INPUT_ACK`.

## 5. Consequences and Trade-offs
### Positive Consequences
- Fault tolerance: A hard kill or reboot of the Redis instance causes zero loss of participant input, registered users, rounds, or official scores.
- Clear mental model for developers: Redis is a pipe and temporary cache, never a persistent ledger.
- Scalable broadcast: Thousands of spectator connections can receive lobby updates without stressing PostgreSQL connection limits.

### Negative Consequences / Accepted Trade-offs
- Ephemeral delivery: Redis Pub/Sub does not guarantee delivery to disconnected clients. Clients that disconnect and reconnect must perform state catch-up by querying the authoritative PostgreSQL API.
- Overhead of Transactional Outbox: Requires an outbox poller/worker process to bridge PostgreSQL and Redis.

## 6. Compliance, Security, and Privacy Implications
- Redis instances must not be publicly exposed to the internet.
- Redis caches and pub/sub channels must never contain unredacted personal identifiers (emails, phone numbers, raw passwords) or unreviewed integrity flags.

## 7. Validation Strategy
- Chaos/Fault-injection testing: Hard termination of the Redis container during an active round. Verify that all accepted typing batches remain safely committed in PostgreSQL and that the round completes accurately.
- Outbox lag monitoring: Verifying that outbox queue depth recovers to zero after Redis service restoration.

