# ADR-015: Cross-Project Security, Privacy, Accessibility, and Product-Truth Hardening

**Status:** Accepted  
**Date:** 2026-11-05  
**Deciders:** Principal Product Architect & Technical Lead  
**Consulted:** Engineering Team, Security Auditors, Accessibility Specialists  
**Informed:** Platform Operators, UI/UX Engineers, Participant Community  

---

## Context & Problem Statement

Prior to comprehensive integration and load testing (Phase 14), TypeVector Arena required a dedicated cross-project hardening pass. The objective of this pass was to discover, eliminate, and document material vulnerabilities, privacy violations, accessibility gaps, and unsubstantiated product claims across the entire implemented codebase.

Key risk vectors identified during the architecture audit included:
1. **PII Exposure via Public Lookups:** `GET /api/v1/identity/users/{user_id}` previously serialized full user records including email addresses, opening the system to automated email scraping.
2. **Missing Tenant & Resource Authorization (IDOR/BOLA):**
   - Results preview (`/api/v1/results/events/{id}/preview`) lacked organization tenant verification, allowing any authenticated user to inspect unreleased event scores.
   - Integrity case details and appeal rulings lacked explicit verification that the reviewer belonged to the host organization of the contested event.
   - Attempt scores and raw typing streams could be queried by non-owner users if the attempt UUID was known.
   - Organization export files and notification summaries lacked strict identity/tenant boundaries.
3. **Missing Statutory Privacy Controls:** Absence of user profile rectification (GDPR Art. 16), self-service account deactivation (GDPR Art. 17), and explicit under-18 consent gates during registration.
4. **WebSocket Connection Hardening:** Spectator and broadcast WebSocket channels lacked RFC 6455 origin verification and strict frame payload length limits.
5. **Modal Accessibility & Focus Management:** Frontend modal dialogs in the Organizer Command Center lacked keyboard focus trapping, Escape dismissal listeners, and focus restoration to the previously active element upon closure.
6. **Untruthful or Unqualified Product Claims:** Residual documentation and UI copy claimed "cheat-proof" scoring, "tamper-proof" results, "guaranteed zero latency", and "WCAG certification" without formal audit backing.

---

## Decision Drivers

1. **Defense-in-Depth Authorization:** Relying solely on obscure UUIDs is prohibited. Every endpoint exposing sensitive, provisional, or organizational data must verify both authentication and resource authorization (tenant membership or ownership).
2. **Privacy by Design & Data Minimization:** Public endpoints must strictly exclude PII. Telemetry and logging sinks must never record raw challenge prompts or live keystroke buffers.
3. **Statutory User Rights:** Users must possess technical mechanisms to rectify their profile information and deactivate their account, with all active sessions immediately revoked.
4. **WebSocket Robustness:** Real-time channels must enforce origin checks, per-connection rate limits, payload size limits, and stale connection fencing (`4409`).
5. **Accessibility as a First-Class Requirement:** Dialogs and interactive flows must comply with WCAG 2.1 Success Criteria 2.1.2 (No Keyboard Trap) and 2.4.3 (Focus Order).
6. **Product-Truth Transparency:** Product copy and technical documentation must strictly describe observed, reproducible characteristics (e.g., "bounded <= 5.0ms target clock uncertainty" rather than "guaranteed").

---

## Five-Axis Code Review

### Axis 1: Concurrency & Session Security
- **Stale Connection Fencing:** When a new WebSocket session authenticates for an attempt, prior connections are evicted with close code `4409 (Stale Session)`.
- **Token Family Revocation:** Account deactivation triggers `revoke_all_sessions`, immediately invalidating all refresh tokens associated with the user.
- **WebSocket Message Cap:** Real-time input frames are capped at 30 frames/second per socket and 1,024 bytes per message to thwart socket exhaustion attacks.

### Axis 2: Authorization & Access Control (IDOR Elimination)
- **Public Profile Sanitization:** `GET /api/v1/identity/users/{user_id}` returns `PublicUserRead(id, display_name, status, role, created_at)`, completely omitting `email`.
- **Tenant-Scoped Results Preview & Publishing:** `GET /api/v1/results/events/{event_id}/preview`, `publish`, and `amend` verify caller organization membership and reject outsiders with HTTP 403.
- **Integrity Case Tenant Scoping & Separation of Powers:** Reviewers can only inspect and act upon integrity cases for events hosted by their active organization. Appellate decisions enforce strict judge separation: the resolving reviewer cannot decide an appeal.
- **Attempt & Score Ownership Scoping:** `GET /api/v1/scores/attempts/{attempt_id}` and `GET /api/v1/arena/attempts/{attempt_id}` restrict access to the attempt owner or authorized organizers of the hosting event.

### Axis 3: Privacy, Consent & Data Minimization
- **Profile Rectification:** `PATCH /api/v1/identity/me` allows participants to update their display name with comprehensive audit event logging (`user.profile_updated`).
- **Account Deactivation:** `POST /api/v1/identity/deactivate` marks user status as `deactivated`, clears the authentication cookie, and writes `user.deactivated` audit log.
- **Under-18 Registration Gate:** Added `is_age_confirmed_18` boolean validation to registration schema and service. Incomplete consent triggers HTTP 422 `UNDER_18_BLOCKED`.
- **Telemetry Boundaries:** Challenge text and keystroke content are strictly prohibited from Prometheus metric labels and structured worker logs.

### Axis 4: Malicious Input & WebSocket Defenses
- **Spectator WebSocket Origin Validation:** Spectator streams enforce RFC 6455 `Origin` validation against `settings.cors_origins_list` with `WS_1008_POLICY_VIOLATION` for untrusted origins.
- **Frame Size Limits:** Inbound spectator and ranked input frames exceeding 1,024 bytes are rejected with `WS_1009_MESSAGE_TOO_BIG`.
- **CSV Formula Injection Sanitization:** Maintained CWE-1236 sanitization across all export generation pipelines.

### Axis 5: Product-Truth & Accessibility
- **Modal Dialog Keyboard & Focus Trapping:** Implemented vanilla JavaScript focus capture in [command-center.js](file:///e:/keyboard/apps/web/js/command-center.js). Captures `document.activeElement`, binds `Escape` keyboard dismissal, automatically shifts focus to modal inputs, and restores original focus upon closing.
- **Claim Qualification:** Rewrote marketing copy from "tamper-proof" to "server-authoritative", qualified NTP clock uncertainty as a bounded target rather than a hardware guarantee, and clarified password validation rules in registration UI.
- **Metric Status Semantics:** Transparently documented system state transitions: `Local`, `Pending`, `Saved`, `Provisional`, `Official`, and `Unavailable`.

---

## Decision Outcome

Adopted the cross-project hardening changes across all affected domain routers, services, frontend controllers, and documentation.

### Consequences

**Positive:**
- Eliminates automated scraping of participant email addresses.
- Prevents cross-tenant viewing of unreleased tournament results and integrity cases.
- Provides compliant GDPR Art. 16 and Art. 17 self-service mechanisms.
- Hardens real-time WebSocket channels against cross-site hijacking and socket flooding.
- Guarantees keyboard accessibility and screen-reader usability for dialog workflows.
- Establishes honest, defensible claims regarding system security and operational limits.

**Negative / Operational Overheads:**
- Additional database queries required on attempt and result queries to verify organization membership.
- Anonymous spectators must connect via whitelisted origins in production environments.
- Registration requires an additional affirmative age-confirmation checkbox.

---

## References & Evidence

- **Control Register:** [OWASP_ASVS_AND_WEBSOCKET_SECURITY_REGISTER.md](file:///e:/keyboard/docs/security/OWASP_ASVS_AND_WEBSOCKET_SECURITY_REGISTER.md)
- **Automated Test Suite:** [test_security_privacy_and_hardening.py](file:///e:/keyboard/apps/api/tests/test_security_privacy_and_hardening.py) (13 tests verifying PII sanitization, IDOR guards, GDPR rights, age gating, origin filtering, and judge separation)
- **Frontend Controller:** [command-center.js](file:///e:/keyboard/apps/web/js/command-center.js#L140-L185) (Focus trapping & Escape handling)

