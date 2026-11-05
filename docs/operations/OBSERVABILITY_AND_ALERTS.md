# Observability, Metrics, and Alerting Specification

**Document Version:** 1.0.0  
**Effective Date:** 2026-11-05  
**System:** TypeVector Arena Production Observability Infrastructure

---

## 1. Health Probes Specification

The backend exposes standard Kubernetes/Docker liveness and readiness probe endpoints:

### 1.1 Liveness Probe (`GET /healthz`)
- **Purpose:** Verifies that the FastAPI process is alive and responsive to event loop ticks.
- **Dependencies Checked:** None. Does not execute downstream I/O.
- **Success Response:** `HTTP 200 OK`
  ```json
  {
    "status": "healthy",
    "timestamp": "2026-11-05T18:50:00Z"
  }
  ```
- **Failure Action:** Container restart via orchestration supervisor.

### 1.2 Readiness Probe (`GET /readyz`)
- **Purpose:** Verifies that the service can accept incoming participant traffic.
- **Dependencies Checked:**
  1. PostgreSQL connection pool probe (`SELECT 1`).
  2. Redis ping probe (`PING -> PONG`).
- **Success Response:** `HTTP 200 OK`
  ```json
  {
    "status": "ready",
    "checks": {
      "database": "connected",
      "redis": "connected"
    },
    "timestamp": "2026-11-05T18:50:00Z"
  }
  ```
- **Failure Response:** `HTTP 503 Service Unavailable` if database is down. (Redis degradation returns `200` with `"redis": "degraded"` warning, as DB is the sole system of record).
- **Failure Action:** Remove instance from reverse proxy load-balancer upstream pool.

---

## 2. Prometheus Metrics Inventory

All metrics follow standard OpenMetrics / Prometheus naming conventions with the `typevector_` namespace.

| Metric Name | Type | Labels | Description |
|---|---|---|---|
| `typevector_websocket_connections_total` | Gauge | `state` (`lobby`, `competing`, `spectating`) | Active WebSocket client connections. |
| `typevector_websocket_ack_latency_seconds` | Histogram | `route` (`/ws/ranked`) | Duration from socket packet arrival to database commit and ACK dispatch. Buckets: `[0.005, 0.010, 0.025, 0.050, 0.100, 0.250, 0.500, 1.000]` |
| `typevector_active_attempts_total` | Gauge | `event_id`, `round_id` | Number of live ranked attempts currently receiving keystroke streams. |
| `typevector_db_pool_utilization_ratio` | Gauge | `pool` (`api`, `worker`) | Current ratio of checked-out connections to total capacity ($\frac{\text{checked\_out}}{\text{pool\_size} + \text{max\_overflow}}$). |
| `typevector_db_connection_errors_total` | Counter | `error_type` (`timeout`, `disconnect`) | Count of failed database connection attempts. |
| `typevector_outbox_pending_count` | Gauge | `topic` | Count of transactional outbox rows awaiting worker dispatch. |
| `typevector_outbox_oldest_age_seconds` | Gauge | `topic` | Age in seconds of the oldest un-dispatched outbox event. |
| `typevector_celery_task_duration_seconds` | Histogram | `task_name` | Celery background task execution duration. |
| `typevector_celery_task_failures_total` | Counter | `task_name`, `exception` | Count of failed Celery task executions. |
| `typevector_rate_limit_exceeded_total` | Counter | `scope` (`auth`, `api`, `ws`) | Count of requests rejected due to rate limit threshold breaches. |

---

## 3. Prometheus Alerting Rules

```yaml
groups:
  - name: typevector_arena_alerts
    rules:
      # P1 - Critical: WebSocket ACK Latency Degradation
      - alert: HighWebSocketAckLatency
        expr: histogram_quantile(0.95, sum(rate(typevector_websocket_ack_latency_seconds_bucket[1m])) by (le)) > 0.050
        for: 30s
        labels:
          severity: critical
          tier: live_competition
        annotations:
          summary: "WebSocket p95 ACK latency exceeds 50ms"
          description: "Typists are experiencing unacceptable ACK latency (current p95 > 50ms). Investigate database I/O and server load immediately."

      # P1 - Critical: Database Connection Pool Saturated
      - alert: DbConnectionPoolExhausted
        expr: typevector_db_pool_utilization_ratio > 0.90
        for: 30s
        labels:
          severity: critical
          tier: platform
        annotations:
          summary: "Database connection pool utilization > 90%"
          description: "SQLAlchemy connection pool nearing exhaustion. Immediate risk of 503 errors on incoming HTTP and WebSocket connections."

      # P1 - Critical: Transactional Outbox Stalled
      - alert: OutboxLagCritical
        expr: typevector_outbox_pending_count > 500 or typevector_outbox_oldest_age_seconds > 120
        for: 1m
        labels:
          severity: critical
          tier: async_pipeline
        annotations:
          summary: "Transactional outbox events accumulating"
          description: "Outbox worker lag critical (>500 rows or oldest > 120s). Background workers may be stalled or disconnected."

      # P2 - Warning: Redis Broker Unavailable
      - alert: RedisUnavailable
        expr: typevector_redis_up == 0
        for: 30s
        labels:
          severity: warning
          tier: platform
        annotations:
          summary: "Redis broker unreachable"
          description: "Redis instance is down. Spectator real-time fanout disabled; Celery dispatch paused. PostgreSQL outbox is safely retaining state."

      # P2 - Warning: Mass Disconnection Spike
      - alert: WebSocketMassDisconnection
        expr: sum(rate(typevector_websocket_disconnections_total[1m])) > 50
        for: 15s
        labels:
          severity: warning
          tier: live_competition
        annotations:
          summary: "Mass WebSocket disconnection spike detected"
          description: "Sudden spike in client disconnections. Check network routing, CDN status, or ingress proxy health."
```

---

## 4. Structured JSON Logging Schema

All backend components (FastAPI, Celery workers, Beat) output single-line structured JSON to `stdout` in accordance with Cloud-Native 12-factor application standards.

### 4.1 Schema Definition
```json
{
  "timestamp": "2026-11-05T18:50:32.412Z",
  "level": "INFO",
  "logger": "typevector.domains.ranked_input.ws_handler",
  "message": "Input batch committed and acknowledged",
  "correlation_id": "c1f7b029-45e1-487a-85d8-c99b828ea281",
  "request_id": "req-9882a170-13f5-4702-8d77-94a5323bb942",
  "user_id": "018d45e0-7988-7512-82cb-23bca0123456",
  "event_id": "018d45e0-7988-7512-82cb-999999999999",
  "round_id": "018d45e0-7988-7512-82cb-888888888888",
  "attempt_id": "018d45e0-7988-7512-82cb-777777777777",
  "sequence_number": 42,
  "duration_ms": 11.45
}
```

### 4.2 Telemetry Privacy Rules
1. **Keystroke Stream Exclusion:** Raw keystroke characters, text fragments, and full text buffers are strictly forbidden from log output. Only metadata (e.g. `batch_sequence_number`, `operations_count`, `payload_digest_sha256`) may be logged.
2. **Credential Sanitization:** Passwords, session cookies, CSRF tokens, and API secret keys must never appear in log payloads or query string dumps.
3. **Spectator Anonymity:** Unauthenticated spectator socket interactions must log hashed client identifiers rather than raw client IP addresses.
