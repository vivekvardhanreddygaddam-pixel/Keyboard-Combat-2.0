# ADR-007: Server-Side Session Authentication, CSRF Defense, and Verified Identity Separation

## Status
Accepted (2026-11-04)

## Context
TypeVector Arena hosts competitive typing tournaments and practice tracks with public, participant, and organizer experiences. In tournament operations, integrity and immediate revocability are paramount:
1. **Revocation & Anti-Cheat Requirements:** If a competitor is flagged for botting or macro execution during an active tournament, organizers and anti-cheat reviewers must be able to immediately revoke their session and deny further submissions. Stateless JWTs cannot be invalidated without building a distributed revocation blocklist (which reintroduces state).
2. **Credential Storage Security:** Storing raw session tokens or credentials in local storage exposes them to theft via Cross-Site Scripting (XSS). Persisting plaintext tokens in the database exposes all active sessions to any read-level SQL breach.
3. **Identity Verification vs Self-Assertion:** In educational and institutional tournaments, participants must often be enrolled students or verified members of an organization. Self-asserted attributes (such as roll numbers or department codes) cannot be trusted as authoritative without cryptographic or administrative verification.
4. **Registration Race Hazards:** In high-demand tournaments with hard capacity limits (e.g., 64 or 128 seats), concurrent registration requests create Time-Of-Check to Time-Of-Use (TOCTOU) race conditions leading to overbooking.

## Decision

### 1. Argon2id Password Hashing
We adopt **Argon2id** (`argon2-cffi`) as the exclusive password hashing algorithm, configured with OWASP baseline parameters:
- `time_cost`: 2 iterations
- `memory_cost`: 65,536 KiB (64 MiB)
- `parallelism`: 2 threads
- Minimum password length: 12 characters

### 2. Server-Side Hashed Sessions & Cookie Transport
- Session tokens are generated using cryptographically secure pseudorandomness (`secrets.token_urlsafe(32)`, 256 bits of entropy).
- **Hashed Persistence:** The raw session token is returned once to the client in an `HttpOnly`, `SameSite=Lax`, `Secure` cookie named `tv_session`. The database table `user_sessions` stores only the `SHA-256` digest of the token. A database leak will not compromise active sessions.
- **Sliding Expiration:** Sessions expire after a configured duration (`SESSION_EXPIRY_SECONDS`, default 7 days) and refresh their `last_active_at` timestamp on active requests.
- **Immediate Revocation:** Any session row can be deleted immediately by the user (`/identity/logout`) or an administrator, revoking access across all connected devices in real time.

### 3. Session-Bound HMAC-SHA256 CSRF Defense
To prevent Cross-Site Request Forgery while supporting cookie-based session authentication:
- Every active session generates a cryptographic CSRF token: `HMAC_SHA256(server_secret, session_id)`.
- All state-mutating requests (`POST`, `PUT`, `PATCH`, `DELETE`) are gated by the `enforce_csrf` FastAPI dependency, which requires an `X-CSRF-Token` header matching the session HMAC using `secrets.compare_digest`.
- Safe idempotent methods (`GET`, `HEAD`, `OPTIONS`) do not require CSRF tokens.

### 4. Separation of User Account, Identity Claims, and Verified Identity
We establish a strict three-tier identity model:
1. **User Account (`users`):** The credential container (email, display name, password hash, platform role).
2. **Identity Claim (`identity_claims`):** A self-asserted institutional attribute (e.g., `claim_type="roll_number"`, `claim_value="CS-2024-001"`). Newly submitted claims enter `status="pending"`.
3. **Verified Identity:** A claim transitioned to `status="verified"` by an organization administrator or platform reviewer via `verify_claim`, recording `verified_by_user_id`, `verified_at`, and auditable verification evidence notes. Restricted tournament eligibility requires verified claims.

### 5. Multi-Tenant Scoped Authorization (Deny by Default)
- Multi-tenancy is enforced using the `require_org_role` dependency.
- Every protected organization action validates that the authenticated user holds an active membership with the required role (`member`, `organizer`, `admin`, `owner`) in that specific organization.
- Cross-tenant requests are explicitly rejected with `403 Forbidden`.

### 6. Atomic, Race-Safe Event Registration
- Event registrations execute within an explicit database transaction.
- The registration service issues a `SELECT ... FOR UPDATE` row lock on the targeted `Event`.
- Confirmed registrations are counted against `max_participants`. If the event is at capacity, the transaction rejects the registration with `409 Conflict`.
- Re-registering by the same user is naturally idempotent (returns existing registration).
- Relational integrity is enforced by the composite unique constraint `uq_event_registrations_event_id_user_id`.
- Registration changes emit transactional outbox events (`event_registration.confirmed`, `event_registration.cancelled`) for reliable asynchronous event processing.

## Consequences

### Positive
- **Instant Session Invalidation:** Anti-cheat reviewers can revoke compromised accounts immediately without distributed blocklist overhead.
- **Robust Defense in Depth:** Session cookies protected by `HttpOnly`, `SameSite=Lax`, and `Secure` combined with header-based HMAC CSRF protection eliminate standard browser credential abuse.
- **Truthful Identity Guarantees:** Institutional claims cannot masquerade as verified credentials without an auditable reviewer approval trail.
- **Capacity Determinism:** Hard tournament caps cannot be breached, even under heavy concurrent registration bursts.

### Negative / Trade-offs
- Every authenticated request performs a database lookup on `user_sessions` (indexed on `token_hash`).
- Mutating AJAX / Fetch requests from the vanilla frontend must supply the `X-CSRF-Token` header (handled transparently by `apps/web/js/api-client.js`).

