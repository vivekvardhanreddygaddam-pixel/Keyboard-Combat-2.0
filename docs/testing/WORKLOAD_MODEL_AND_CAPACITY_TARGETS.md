# TypeVector Arena — Workload Models & Capacity Baselines

**Document Version:** 1.0.0  
**Effective Date:** 2026-11-05 (Phase 14 Reliability & Verification Pass)  
**Author:** Principal Product Architect & Systems Performance Engineer  
**Status:** Operational Workload Specification & Empirical Baseline Register  
**Governing Rule:** *No hypothetical target may be claimed as an achieved production SLO. All figures are explicitly separated into Mathematical Models, Measured Empirical Baselines, and Candidate SLO Proposals.*

---

## 1. Workload Modeling & Mathematical Formulations

To model platform demand during high-stakes institutional tournaments, workloads are divided into two distinct concurrent streams: **Active Competitors (Ranked Ingestion)** and **Spectators (Broadcast Fanout)**.

### 1.1 Active Competitors Model (Ranked Ingestion)

Let:
- $N_c$: Number of concurrent active typists in a live competition round.
- $W$: Mean typing speed in Words Per Minute (standard convention: 5 keystrokes per word).
- $K$: Keystroke rate in characters per second:
  $$K = \frac{W \times 5}{60}$$
  For a high-tier competitor typing at 120 WPM:
  $$K = \frac{120 \times 5}{60} = 10 \text{ keystrokes/sec}$$
- $B_s$: Batch size (number of keystroke operations coalesced per WebSocket message). Typical client batch window is 100 ms ($B_s \approx 1 \text{ to } 2$ keystrokes).
- $F_m$: WebSocket frame frequency per active competitor:
  $$F_m = \frac{K}{B_s} \approx 5 \text{ to } 10 \text{ batches/sec}$$
- $P_s$: Average payload size per JSON frame ($\approx 250 \text{ bytes}$).

#### Aggregate Ingestion Throughput:
For a 100-competitor institutional sprint:
$$\text{Ingress Message Rate} = N_c \times F_m = 100 \times 10 = 1,000 \text{ frames/sec}$$
$$\text{Ingress Bandwidth} = 1,000 \times 250 \text{ bytes} = 250 \text{ KB/sec} \approx 2.0 \text{ Mbps}$$

Each frame requires:
1. JSON schema parsing and operation validation.
2. Monotonic sequence check ($S = W + 1$) and writer-generation verification.
3. Operations SHA-256 digest verification.
4. Text projection mutation and state persistence.
5. Durable post-commit `INPUT_ACK` dispatch.

### 1.2 Spectator Broadcast Model (Leaderboard Fanout)

Let:
- $N_s$: Number of concurrent spectators observing a tournament.
- $F_s$: Spectator broadcast update frequency. Per ADR-011 and ADR-013, spectator updates are throttled to **1 Hz** (1 frame per second) via Redis pub/sub.
- $P_{lb}$: Leaderboard snapshot payload size ($\approx 2 \text{ KB}$ for top 25 competitors).

#### Aggregate Egress Bandwidth:
$$\text{Fanout Bandwidth} = N_s \times F_s \times P_{lb}$$
- For $N_s = 1,000$ spectators:
  $$\text{Egress Rate} = 1,000 \times 1 \text{ Hz} = 1,000 \text{ msgs/sec}$$
  $$\text{Egress Bandwidth} = 1,000 \times 2 \text{ KB} = 2.0 \text{ MB/sec} \approx 16.0 \text{ Mbps}$$

### 1.3 Network Jitter & Reconnect Pattern Assumptions

- **Flapping Rate:** Modeled at 2% to 5% intermittent disconnects during a 5-minute round.
- **Reconnect Storm:** When clients reconnect, they request `ROUND_STATE` and resubmit unacknowledged sequence numbers with identical digests.
- **Backoff Strategy:** Jittered exponential backoff:
  $$t_{\text{retry}} = \min(t_{\max}, t_{\text{base}} \times 2^{\text{attempt}} + \text{random}(0, 200\text{ms}))$$

---

## 2. Empirical Single-Node Micro-Benchmark Baselines

The following performance baselines were empirically measured using the automated test harness ([`scripts/load_test_harness.py`](file:///e:/keyboard/scripts/load_test_harness.py)) over 1,000 iterations per component.

### 2.1 Benchmark Environment Specifications
- **Operating System:** Windows 11 (AMD64)
- **CPU Architecture:** Intel64 Family 6 Model 154 Stepping 3, GenuineIntel (16 logical cores)
- **Python Runtime:** Python 3.12.10 (64-bit)
- **Raw Evidence Artifact:** [`docs/testing/artifacts/local_benchmark_results.json`](file:///e:/keyboard/docs/testing/artifacts/local_benchmark_results.json)

### 2.2 Measured Latency Distributions & Throughput

| Component / Subsystem | Tested Operation | p50 (Median) | p90 | p95 | p99 | Max | Measured Throughput |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Practice Diff Engine** | Needleman-Wunsch sequence alignment (70 chars) | **0.0777 ms** | 0.0861 ms | 0.0968 ms | 0.1567 ms | 0.2429 ms | **12,274.9 ops/sec** |
| **Canonicalization** | Pinned Unicode extended grapheme segmentation | **0.0163 ms** | 0.0174 ms | 0.0180 ms | 0.0270 ms | 0.1143 ms | **58,730.6 ops/sec** |
| **Official Scorer** | Fixed-point `arena-score-v1` evaluation & manifest | **0.0513 ms** | 0.0561 ms | 0.0590 ms | 0.1133 ms | 0.3118 ms | **18,522.6 ops/sec** |
| **Protocol Digest** | SHA-256 operation digest calculation | **0.0030 ms** | 0.0036 ms | 0.0040 ms | 0.0064 ms | 0.1095 ms | **304,664.7 ops/sec** |
| **Projection Engine** | Incremental tail mutation & NFC canonicalization | **0.0018 ms** | 0.0019 ms | 0.0019 ms | 0.0027 ms | 0.0099 ms | **552,517.4 ops/sec** |

### 2.3 Analysis of Computational Overhead
The micro-benchmark data confirms that pure algorithmic processing (diffing, scoring, canonicalization, digest hashing) introduces **less than 0.1 ms of latency at p95**. The primary latency contributors in live environments are therefore network round-trip time (RTT) and PostgreSQL transactional disk flush (`WAL write`).

---

## 3. Candidate Target SLOs (Pending Multi-Node Staging Verification)

The following metrics are **proposed candidate SLO targets** for production qualification. They are **NOT** claimed as achieved production guarantees until verified under multi-node staging infrastructure in Phase 15.

| Metric | Proposed Candidate Target | Primary Influencing Factors | Current Verification Status |
| :--- | :--- | :--- | :--- |
| **WebSocket `INPUT_ACK` Latency** | $\text{p95} \le 50\text{ ms}, \text{p99} \le 100\text{ ms}$ | Network RTT, DB commit time, row lock contention | Algorithmic path <0.1ms; DB commit pending staging cluster |
| **DB Commit Latency** | $\text{p95} \le 15\text{ ms}$ | SSD I/O, PostgreSQL `synchronous_commit`, connection pool sizing | Local baseline pending live Docker/DB cluster |
| **Clock Synchronization Uncertainty** | $\text{target} \le 5.0\text{ ms}$ | NTP daemon sync, kernel timestamping, hypervisor jitter | Verified target logic in `clock.py`; hardware dependent |
| **Spectator Fanout Latency** | $\le 1.0\text{ s}$ snapshot freshness | Redis pub/sub delivery, 1 Hz throttle window | Verified in pub/sub broadcast unit tests |
| **Capacity Lock Contention** | $0\text{ overbooked seats}$ | `SELECT ... FOR UPDATE` atomic row lock | **VERIFIED:** Concurrency unit test verified 0 overbooking |
| **Stale Writer Eviction** | $\le 10\text{ ms}$ eviction delay | In-memory socket registry lookup | **VERIFIED:** Generation fence test verified instant 4409 closure |

