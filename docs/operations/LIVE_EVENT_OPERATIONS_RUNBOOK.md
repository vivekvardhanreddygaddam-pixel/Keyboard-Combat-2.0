# Live Event Operations & Incident Response Runbook

**Document Version:** 1.0.0  
**Effective Date:** 2026-11-05  
**Audience:** Tournament Directors, On-Call Site Reliability Engineers (SRE), Integrity Officials  
**System:** TypeVector Arena Live Competition Infrastructure

---

## 1. Operational Roles & Command Structure

During live ranked tournaments, operational authority is divided according to strict separation of duties:

| Role | Primary Responsibilities | Authorized Actions |
|---|---|---|
| **Incident Commander (IC)** | Overall incident coordination, event pause/resume decisions, public status updates. | Event lifecycle state transitions (`pause`, `void`, `resume`), deadline extensions. |
| **On-Call SRE** | Infrastructure health, WebSocket connectivity, database capacity, worker queues. | Scaling container replicas, restarting workers, database connection draining. |
| **Integrity Lead (Judge)** | Keystroke playback review, suspicious telemetry investigation, disqualification. | Flagging attempts, reviewing replay vectors, issuing integrity holds. |
| **Communications Officer** | Real-time competitor broadcasts, lobby announcements, status page updates. | Publishing broadcast notices via Organizer Command Center. |

---

## 2. Standard Event Lifecycle Checkpoints

### 2.1 T-60 Minutes: Pre-Flight Readiness Checklist
- [ ] Database connection pool utilization $< 20\%$ (`typevector_db_pool_utilization_ratio < 0.20`).
- [ ] Redis cluster reachable, memory usage $< 50\%$ of max (`512MB`).
- [ ] Celery outbox worker lag is zero (`typevector_outbox_pending_count == 0`).
- [ ] Server NTP synchronization verified: clock offset $\le 2\text{ ms}$ (`chronyc tracking`).
- [ ] Organizer Command Center loaded with valid administrative session.
- [ ] Emergency communication channels active (Discord / Slack / In-app announcement banner).

### 2.2 T-15 Minutes: Lobby & Check-In Window
- Monitor check-in rate. Verify competitors receive check-in badges.
- Verify capacity limits: total checked-in roster $\le$ event capacity.
- Verify WebSocket connection rates: observe connection surge as competitors enter the lobby.

### 2.3 T-0: Round Start
- Automated countdown dispatch: 3... 2... 1... GO.
- Verify participant active socket count matches checked-in roster.
- Monitor WebSocket ACK latency ($p95 \le 15\text{ ms}$).

### 2.4 Post-Round: Provisional Scoring & Publication
- Verify 100% of submitted attempts transition from `pending` to `scored`.
- Integrity review period: audit top 10% leaderboard entries for anomalies.
- Organizer approves and signs official publication snapshot (generates SHA-256 cryptographic root digest).

---

## 3. Incident Response Playbooks

---

### Incident 1: Degraded WebSocket ACK Latency ($p95 > 50\text{ ms}$)

**Detection:** Alert `HighWebSocketAckLatency` fires ($p95 > 50\text{ ms}$ for $> 30\text{ s}$).  
**Impact:** Typists perceive lag; client-side buffer queues unacknowledged strokes.

**Immediate Actions:**
1. Check FastAPI backend CPU and Event Loop latency:
   ```bash
   docker stats typevector-api
   ```
2. Check database transaction latency on `ranked_input_batches` table:
   ```sql
   SELECT query, calls, mean_exec_time, max_exec_time 
   FROM pg_stat_statements 
   WHERE query LIKE '%ranked_input_batches%' 
   ORDER BY mean_exec_time DESC LIMIT 5;
   ```
3. If database I/O is saturated, scale FastAPI worker threads or enable transaction batching.
4. If latency exceeds $150\text{ ms}$ across $> 20\%$ of competitors:
   - **IC Decision:** Trigger **Event Pause** via Organizer Command Center (`POST /api/v1/command/events/{id}/pause`).
   - The pause freezes client timers and preserves committed keystroke state without penalty.

---

### Incident 2: Database Connection Pool Exhaustion (`503 Service Unavailable`)

**Detection:** Alert `DbConnectionPoolExhausted` fires (`utilization > 95%`). FastAPI logs show `TimeoutError: QueuePool limit of size 10 overflow 5 reached`.  
**Impact:** New HTTP requests and WebSocket connections fail with 500/503 errors.

**Immediate Actions:**
1. Inspect active database queries holding connections open:
   ```sql
   SELECT pid, now() - query_start AS duration, state, query 
   FROM pg_stat_activity 
   WHERE state != 'idle' 
   ORDER BY duration DESC;
   ```
2. Terminate long-running non-essential analytics or report queries:
   ```sql
   SELECT pg_cancel_backend(pid) FROM pg_stat_activity 
   WHERE query LIKE '%export%' AND now() - query_start > interval '30 seconds';
   ```
3. If Celery background workers are holding excessive connections, scale down worker concurrency:
   ```bash
   docker-compose -f infra/docker/docker-compose.prod.yml up -d --scale worker-exports=0
   ```
4. Adjust pool parameters in `.env.production` (`DB_MAX_OVERFLOW=15`) and perform a rolling restart.

---

### Incident 3: Redis Broker Outage or Partition

**Detection:** Alert `RedisUnavailable` fires. Celery logs report `ConnectionRefusedError: Error 111 connecting to redis:6379`.  
**Impact:** Real-time spectator pub/sub broadcasts stall; Celery task dispatch paused. **Ranked competition input is NOT lost** because transactions commit directly to PostgreSQL outbox.

**Immediate Actions:**
1. Confirm system status:
   - Competitor WebSocket connections remain functional (persisting batches directly to PostgreSQL).
   - Outbox rows accumulate in PostgreSQL with `status = 'pending'`.
2. Inspect Redis container:
   ```bash
   docker logs --tail 100 typevector-redis
   docker restart typevector-redis
   ```
3. Once Redis is restored, Celery workers automatically resume outbox event dispatch.
4. Reconcile stuck outbox records if workers were restarted during an active claim:
   ```sql
   UPDATE outbox_events 
   SET status = 'pending', claimed_at = NULL 
   WHERE status = 'processing' AND claimed_at < now() - interval '5 minutes';
   ```

---

### Incident 4: Outbox Dispatch Lag & Worker Stalls

**Detection:** Alert `OutboxLagCritical` fires (`pending_count > 500` or `oldest_age > 120s`).  
**Impact:** Notifications and export tasks delayed; eventual consistency lag.

**Immediate Actions:**
1. Check Celery worker process health:
   ```bash
   docker logs --tail 50 typevector-worker-outbox
   ```
2. If worker stalled on an external I/O call (e.g. SMTP timeout), restart the worker container:
   ```bash
   docker restart typevector-worker-outbox
   ```
3. Scale up outbox worker instances to drain backpressure:
   ```bash
   docker-compose -f infra/docker/docker-compose.prod.yml up -d --scale worker-outbox=3
   ```

---

### Incident 5: Mass Disconnection Event (Network Blip)

**Detection:** Simultaneous disconnection of $> 25\%$ of competitors within a 5-second window.  
**Impact:** Competitors dropped mid-round; risk of unequal competition conditions.

**Immediate Actions:**
1. **IC Action:** Immediately invoke **Event-Wide Pause** (`POST /api/v1/command/events/{id}/pause`).
2. Verify reason for disconnect (CDN failure, hosting provider routing issue, or platform crash).
3. Once connectivity stabilizes:
   - Announce resumption via event chat/broadcast.
   - Grant a **Uniform Deadline Extension** (e.g. $+30\text{ seconds}$ added to round duration for all competitors).
   - Resume round (`POST /api/v1/command/events/{id}/resume`).
   - Competitors reconnect; client resumes seamlessly from the last acknowledged sequence number (`last_sequence_number`).

---

### Incident 6: Server Clock Drift / NTP Uncertainty ($> 5\text{ ms}$)

**Detection:** Alert `NtpClockDrift` fires (`clock_offset_ms > 5.0`).  
**Impact:** Monotonic ordering timestamps between distributed servers may disagree; anti-cheat timestamp validations risk false positives.

**Immediate Actions:**
1. Check chrony / NTP daemon status on host:
   ```bash
   chronyc sources -v
   chronyc tracking
   ```
2. Force immediate NTP slew:
   ```bash
   chronyc -a makestep
   ```
3. If clock jump cannot be resolved within 60 seconds, pause round until server times are synchronized.

---

### Incident 7: Result Correction & Post-Publication Amendment

**Detection:** An error in round challenge text, scoring algorithm parameter, or a confirmed disqualification requires retroactive adjustment after publication.  
**Rule:** **Published results are never mutated in-place.** All amendments must be published as a new, cryptographic child version.

**Procedure:**
1. Tournament Director logs into Organizer Command Center (`/command/events/{id}/results`).
2. Select **Amend Results**.
3. Enter explicit **Reason for Amendment** (required for audit logging).
4. Review the diff preview (shows exact delta of ranks, points, and disqualified attempts).
5. Confirm amendment. System creates Version 2.0 with:
   - `version = 2`
   - `superseded_version = 1`
   - Cryptographic parent hash referencing Version 1.0 SHA-256 digest.
   - Audit trail entry recorded in `audit_logs`.
6. System dispatches `EVENT_RESULTS_AMENDED` notification to all participants.
