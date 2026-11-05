# TypeVector Arena — Threat Model & Security Architecture

**Document Version:** 1.1.0  
**Effective Date:** 2026-11-05 (Updated in Phase 13 Hardening Pass)  
**Author:** Principal Product Architect & Security Engineering Lead  
**Scope:** Authentication, Session Management, CSRF Defense, Tenant Isolation (RBAC/IDOR), Concurrency Controls, WebSocket Security, and Privacy/GDPR Safeguards

---

## 1. Executive Summary & Security Objectives

TypeVector Arena is a competitive typing platform that hosts high-stakes institutional tournaments and public practice tracks. The primary security objectives are:
1. **Tournament Fairness & Integrity:** Prevent unauthorized score submissions, registration tampering, impersonation, and capacity bypasses.
2. **Tenant Isolation:** Enforce strict administrative boundaries so organizations cannot inspect or manipulate other organizations' rosters, events, or evidence.
3. **Identity Verification Assurance:** Explicitly decouple self-asserted claims (e.g. college roll numbers) from verified credentials to eliminate credential spoofing.
4. **Defense in Depth:** Prevent OWASP Top 10 vulnerabilities (Injection, Broken Authentication, IDOR, CSRF, Security Misconfiguration, Concurrency Races).

---

## 2. Threat Actors & Attack Surface

### 2.1 Threat Actors
* **Malicious Competitor:** Attempts to bypass event capacity limits, claim false institutional credentials, forge session tokens, or launch CSRF attacks to register/cancel competitors.
* **Curious Participant:** Probes API endpoints for Insecure Direct Object References (IDOR) to access other users' registrations or private event metadata.
* **Rogue Organizer:** Attempts horizontal privilege escalation to view or tamper with competitor lists of other organizations.
* **Automated Bot / Brute-Forcer:** Floods registration or authentication endpoints to cause resource starvation or credential stuffing.

### 2.2 Attack Surface
| Component | Protocol / Port | Threat Vector | Primary Controls |
| :--- | :--- | :--- | :--- |
| **Session Cookie (`tv_session`)** | HTTPS / Cookie | Theft via XSS, network sniffing, CSRF | `HttpOnly`, `SameSite=Lax`, `Secure`, 256-bit entropy, SHA-256 DB digest |
| **CSRF Protection** | HTTP Header (`X-CSRF-Token`) | Cross-site request forgery on mutations | Session-keyed HMAC-SHA256 verification via `enforce_csrf` dependency |
| **Identity Verification** | REST API (`/identity/claims`) | Claim forgery, self-verification spoofing | Claims require reviewer role (`org_admin`/`platform_admin`); self-verification strictly forbidden |
| **Multi-Tenant Access** | REST API (`/organizations/`) | IDOR, horizontal privilege escalation | `require_org_role` database-backed role validation, Deny-by-default |
| **Event Capacity** | REST API (`/events/{id}/register`) | TOCTOU race conditions, double booking | Pessimistic `SELECT ... FOR UPDATE` row locks, composite unique constraints |

---

## 3. STRIDE Threat Analysis & Implemented Mitigations

### 3.1 Spoofing (Identity & Authentication)
* **Threat S1: Session Token Forgery or Guessing**
  * *Attack:* Attacker guesses a session token or generates weak tokens to hijack user sessions.
  * *Mitigation:* Tokens are generated using Python `secrets.token_urlsafe(32)` providing 256 bits of cryptographically secure pseudorandom entropy.
  * *Database Protection:* The database never stores raw tokens. It stores the `SHA-256` hex digest. A database read breach does not compromise active browser session tokens.
* **Threat S2: Password Brute-Forcing & Credential Stuffing**
  * *Attack:* High-volume password guessing against participant accounts.
  * *Mitigation:* Passwords are hashed using **Argon2id** (`argon2-cffi`) with OWASP recommended baseline parameters: `time_cost=2`, `memory_cost=65536` (64 MB), `parallelism=2`. Passwords have a minimum length requirement (12 characters).
* **Threat S3: Self-Asserted Claim Masquerading as Verified Proof**
  * *Attack:* A competitor registers claiming roll number `CS-2024-001` and is immediately granted access to an institutional bracket.
  * *Mitigation:* Separation of Concerns between `User`, `IdentityClaim` (unverified claim), and verification state. Newly submitted claims enter `status="pending"`. Only an organization admin or platform admin can verify a claim via `verify_claim`, leaving an audit trail with `verified_by_user_id` and timestamp.

---

### 3.2 Tampering (Data Integrity & CSRF)
* **Threat T1: Cross-Site Request Forgery (CSRF) on Mutating Operations**
  * *Attack:* An attacker lures an authenticated competitor to an external malicious webpage that submits a form to `/events/{id}/register` or `/identity/claims`.
  * *Mitigation:*
    1. Modern browsers enforce `SameSite=Lax` on `tv_session` cookies, preventing cross-site POST cookie transmission in standard form actions.
    2. Backend enforces strict CSRF verification on all mutating HTTP methods (`POST`, `PUT`, `PATCH`, `DELETE`). The client must supply an `X-CSRF-Token` header.
    3. The CSRF token is computed as an HMAC-SHA256 over `session_id` using a server secret. Tokens cannot be guessed or forged without the server secret and active session ID.
* **Threat T2: Event Registration Overbooking via Concurrent Submissions (Race Condition)**
  * *Attack:* 100 competitors submit simultaneous registration requests for an event with only 2 remaining seats. Without concurrency control, all 100 read `confirmed_count < max_participants` and register (Time-Of-Check to Time-Of-Use race).
  * *Mitigation:*
    1. Pessimistic locking: `SELECT ... FOR UPDATE` is executed on the specific `Event` row within the transaction before inspecting capacity.
    2. Registrations are counted atomically against `max_participants`.
    3. Natural idempotency: Re-registering by the same user is a safe no-op.
    4. Database constraint: Unique constraint `uq_event_registrations_event_id_user_id` prevents duplicate registrations at the relational engine level.

---

### 3.3 Repudiation (Audit Logging & Accountability)
* **Threat R1: Unauthorized Account State Mutation without Audit Trail**
  * *Attack:* An organizer cancels a competitor's registration or approves a fraudulent claim and denies having performed the action.
  * *Mitigation:*
    1. Critical domain operations write immutable `AuditEvent` records within the same database transaction.
    2. Audit events capture `actor_user_id`, `event_type` (`user.registered`, `user.login`, `claim.submitted`, `claim.verified`, `event_registration.confirmed`, `event_registration.cancelled`), `target_type`, `target_id`, `client_ip`, and `payload_json`.
    3. Domain events emit records to `TransactionalOutbox` ensuring reliable message publishing and asynchronous telemetry delivery.

---

### 3.4 Information Disclosure (Tenant Leaks & IDOR)
* **Threat I1: Insecure Direct Object Reference (IDOR) on Event Registrations**
  * *Attack:* User A submits a DELETE request to cancel User B's registration by passing User B's registration ID.
  * *Mitigation:* The `cancel_registration` service checks that `registration.user_id == current_user.id` unless the caller possesses `org_admin` or `platform_admin` privileges for that event's owning organization. Cross-user cancellation without authority raises `403 Forbidden`.
* **Threat I2: Multi-Tenant Data Leakage Across Organizations**
  * *Attack:* An admin of Organization X queries `/organizations/{org_y_id}/members` or views Organization Y's rosters.
  * *Mitigation:* The `require_org_role` authorization dependency validates the user's membership and required role within the requested organization context directly in PostgreSQL. Any access attempt outside the authorized organization is rejected with `403 Forbidden`.
* **Threat I3: Public Profile Scraping & PII Harvesting**
  * *Attack:* Automated crawlers enumerate `GET /identity/users/{user_id}` to harvest competitor emails, phone numbers, or institutional IDs.
  * *Mitigation:* Public user lookups serialize exclusively through `PublicUserRead(id, display_name, status, role, created_at)`. Email addresses and contact coordinates are completely stripped from public responses.
* **Threat I4: Unauthorized Provisional Results & Attempt Keystroke Inspection**
  * *Attack:* Unprivileged participant or outsider queries `/results/events/{id}/preview`, `/scores/attempts/{id}`, or `/arena/attempts/{id}` to view unannounced standings or inspect keystroke buffers.
  * *Mitigation:* Results preview requires host organization administrative role (`owner`, `organizer`, `admin`). Attempt scores and keystroke projections require attempt ownership or host event organizer privileges; strangers receive `403 Forbidden`.
* **Threat I5: Cross-Tenant Integrity Case Access & Reviewer Collusion**
  * *Attack:* An organizer from Organization A investigates or resolves cheating cases for Organization B, or an original reviewer rules on an appeal of their own sanction.
  * *Mitigation:* Case access verifies membership in the event's host organization. Appeals enforce strict judicial separation: the reviewer who resolved the initial case cannot participate in the appellate decision.

---

### 3.5 Denial of Service (Resource Exhaustion)
* **Threat D1: Password Hash Computation Flooding**
  * *Attack:* An attacker floods `/identity/login` with expensive Argon2id hash computations to exhaust CPU cores.
  * *Mitigation:*
    1. Argon2id parameters are tuned to balance cryptographic strength and CPU cost (64 MB, 2 iterations).
    2. Input validation rejects requests with malformed emails or oversized payloads before invoking Argon2id.
    3. Rate-limiting infrastructure (Tier 1 ingress and Redis sliding window rate limiters) throttles unauthenticated requests per IP.

---

### 3.6 Elevation of Privilege (Access Control)
* **Threat E1: Participant Assuming Organizer Role**
  * *Attack:* A competitor alters request parameters to create events or verify their own claims.
  * *Mitigation:*
    1. System adheres to a strict **Deny-by-Default** authorization model.
    2. Roles are stored authoritatively in the database (`users.role` and `organization_memberships.role`).
    3. Routers guard administrative endpoints using composable FastAPI dependencies (`require_platform_admin`, `require_org_role("admin")`).

---

### 3.7 Ranked WebSocket Protocol & Single-Round Input Security (arena-ws-v1)
* **Threat W1: Split-Brain Ingestion & Stale Tabs (Writer Fencing)**
  * *Attack:* Competitor opens multiple tabs or suffers network flapping, allowing stale socket connections to interleave keystrokes out of order.
  * *Mitigation:* Every new connection increments `socket_writer_generation` under a pessimistic row lock (`SELECT ... FOR UPDATE`). Active connection manager actively evicts older sockets with code `4409` (`STALE_WRITER_EVICTED`). Input batches from stale generations are rejected immediately.
* **Threat W2: Keystroke Sequence Forgery & Out-of-Order Tampering**
  * *Attack:* Malicious client injects arbitrary sequence numbers or replays past inputs.
  * *Mitigation:* Monotonic sequence gating enforces $S = W + 1$. Sequence gaps are rejected. Replayed sequence numbers ($S \le W$) with identical payload digests return the previous committed outcome idempotently (recovering from dropped ACKs); differing digests on the same sequence are rejected as conflicts.
* **Threat W3: Premature Challenge Prompt Leakage**
  * *Attack:* Competitor connects to round WebSocket prior to official start time to obtain challenge text in advance.
  * *Mitigation:* The server withholds challenge content (`challenge_content = None`) in `ROUND_STATE` unless the round status is explicitly `active` or `in_progress`. Prompt versions are immutable once a round opens.
* **Threat W4: Client-Authoritative Scoring Manipulation**
  * *Attack:* Client submits inflated WPM, accuracy, or completion claims.
  * *Mitigation:* Complete zero client score authority. Clients submit only constrained atomic operations (`insert(text)` and `backspace(count)`). The server maintains the authoritative materialized text projection and measures admission timestamps against server clock.
* **Threat W5: WebSocket Denial of Service / Memory Bomb**
  * *Attack:* Client floods the socket with massive batches or high-frequency messages.
  * *Mitigation:* Hard message size cap (`MAX_PAYLOAD_BYTES = 16384`), operation limits (max 50 ops, max 256 chars per insert), and per-connection rate limiting (30 batches/sec).
* **Threat W6: Spectator Cross-Site WebSocket Hijacking (CSWSH) & Socket Bombing**
  * *Attack:* Third-party malicious website initiates spectator WebSocket connections to read live event feeds or flood server buffers.
  * *Mitigation:* Spectator WebSocket endpoint `/ws/broadcast/{event_id}` enforces strict RFC 6455 `Origin` validation against `settings.cors_origins_list` (rejecting invalid origins with `1008`) and imposes an inbound message size cap of 1,024 bytes (rejecting oversize frames with `1009`).

---

### 3.8 Privacy, Data Minimization & Statutory Compliance
* **Threat P1: Inability to Rectify Profile Information (GDPR Art. 16)**
  * *Attack/Risk:* User is locked into outdated or incorrect personal identifiers.
  * *Mitigation:* `PATCH /identity/me` provides validated display name updates with complete immutable audit trail (`user.profile_updated`).
* **Threat P2: Zombie Sessions Remaining Active After Account Deactivation (GDPR Art. 17)**
  * *Attack/Risk:* A user requests account deactivation, but existing refresh/session tokens remain valid in stolen cookie stores.
  * *Mitigation:* `POST /identity/deactivate` marks account `status="deactivated"`, calls `revoke_all_sessions` to revoke all active sessions in the database, clears the session cookie, and logs `user.deactivated`.
* **Threat P3: Minor Account Creation without Statutory Age Consent**
  * *Attack/Risk:* Under-18 participants register without parental knowledge or statutory consent under COPPA/GDPR-K.
  * *Mitigation:* Registration schema enforces `is_age_confirmed_18` boolean validation. Registrations lacking verified confirmation are blocked with HTTP 422 `UNDER_18_BLOCKED`.
* **Threat P4: Telemetry Leakage of Challenge Prompts or Raw Keystrokes**
  * *Attack/Risk:* Prometheus metrics or observability logs leak unreleased challenge prompts or raw participant typing streams.
  * *Mitigation:* Telemetry sinks record only non-sensitive operational metrics (durations, counts, net WPM, HTTP status). Raw text and keystroke buffers are excluded from metrics and log formats.

---

## 4. Cryptographic Standards & Parameter Specification

| Cryptographic Primitive | Algorithm / Standard | Specification & Parameters | Purpose |
| :--- | :--- | :--- | :--- |
| **Password Hashing** | Argon2id | Memory: 64 MiB, Time: 2, Parallelism: 2 (`argon2-cffi`) | Credential storage |
| **Session Identifier** | CSPRNG | 256 bits entropy via `secrets.token_urlsafe(32)` | Client session authentication |
| **Token Storage** | SHA-256 Digest | `hashlib.sha256(raw_token.encode()).hexdigest()` | Database session lookup |
| **CSRF Defense** | HMAC-SHA256 | `hmac.new(secret, session_id, hashlib.sha256).hexdigest()` | Mutation request origin verification |
| **Timing Attack Resistance** | Constant Time Compare | `secrets.compare_digest` | Prevents timing side-channel attacks on CSRF and session checks |

---

## 5. Security Verification & Test Coverage Matrix

| Test Suite File | Threat Vectors Tested | Verification Status |
| :--- | :--- | :--- |
| `tests/test_crypto_security.py` | Argon2id hashing, raw token vs digest separation, CSRF tampering, constant-time compare | PASS (Unit) |
| `tests/test_auth_and_sessions.py` | Registration validation, session cookie issuance, CSRF header rejection, claim audit | PASS (Integration) |
| `tests/test_organizations_and_rbac.py` | Tenant isolation, cross-tenant IDOR access rejection (403), role hierarchy | PASS (Integration) |
| `tests/test_registrations_concurrency_and_idor.py` | Capacity enforcement, race prevention (`SELECT FOR UPDATE`), registration IDOR | PASS (Integration) |
| `tests/test_ranked_input_protocol.py` | Message schema validation, operation limits, deterministic digest calculation | PASS (Unit) |
| `tests/test_ranked_input_engine.py` | Sequence monotonicity property test, projection equivalence to log, no double-apply | PASS (Property/Unit) |
| `tests/test_ranked_input_service.py` | Writer generation fencing, monotonic sequence admission, idempotent replay, deadline cutoff | PASS (Unit) |
| `tests/test_ranked_input_websocket.py` | End-to-end WebSocket protocol, CONNECTED, ROUND_STATE, stale writer eviction (4409) | PASS (Integration) |
| `tests/test_security_privacy_and_hardening.py` | Public PII sanitization, GDPR Art. 16 rectification, Art. 17 deactivation with session revocation, under-18 consent gate, results preview/publish authorization, cross-tenant case isolation, attempt scoring IDOR, practice privacy, spectator WS origin enforcement, export tenant isolation, notification privacy, and appeal judge separation | PASS (Integration/Hardening) |

