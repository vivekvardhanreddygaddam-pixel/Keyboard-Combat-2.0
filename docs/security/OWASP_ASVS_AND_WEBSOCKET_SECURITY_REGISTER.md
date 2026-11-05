# OWASP ASVS & WebSocket Security Control Register

**Project:** TypeVector Arena  
**Standard Basis:** OWASP Application Security Verification Standard (ASVS) v4.0.3 (Risk-Selected Level 2 Controls) & `arena-ws-v1` WebSocket Security Checklist  
**Status:** Self-Assessed Technical Control Register  
**Audit Date:** 2026-11-05 (Phase 13 Cross-Project Hardening Pass)  
**Disclaimer:** *This register documents self-verified technical measures implemented within the TypeVector Arena codebase. It does not constitute a formal third-party accredited compliance certification.*

---

## 1. Executive Summary & Verification Methodology

During Phase 13, the TypeVector Arena architecture underwent a cross-project hardening pass applying the **Five-Axis Code Review** framework:
1. **Architectural & Invariant Integrity:** PostgreSQL system-of-record guarantees, explicit outbox transactionality, and tenant bounded contexts.
2. **Security & Cryptographic Hygiene:** IDOR/BOLA elimination, strict authentication token rotation, CSRF cookie tokens, PBKDF2-HMAC-SHA256 password hashing, and RFC 6455 origin gating.
3. **Privacy & Data Minimization:** Zero public PII leakage, user rectification (GDPR Art. 16), account deactivation (GDPR Art. 17), under-18 consent gates, and telemetry payload stripping.
4. **Reliability & Operational Determinism:** Idempotent outbox dispatch, Celery bounded retries, WebSocket monotonic sequence fences, and circuit-breaking.
5. **Product-Truth & Accessibility:** Removal of unsubstantiated marketing superlatives ("tamper-proof", "cheat-proof"), transparent metric status definitions (`Local`, `Pending`, `Saved`, `Provisional`, `Official`, `Unavailable`), WCAG 2.2 AA compliant contrast, focus traps, and keyboard navigation.

---

## 2. Risk-Selected OWASP ASVS v4.0.3 Control Matrix

| ASVS Section | Control ID | Control Description | Implementation File | Verification Evidence | Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **V2: Authentication** | V2.1.1 | Verify minimum password length (>=8 chars, 12+ recommended) and entropy checks. | [schemas.py](file:///e:/keyboard/apps/api/src/typevector/domains/identity/schemas.py#L32-L45) | Pydantic validator rejects passwords < 8 chars. Form instructions updated. | **VERIFIED** |
| | V2.2.1 | Verify passwords are hashed using salted, slow cryptographic hash (PBKDF2-HMAC-SHA256, 600,000 iterations). | [password.py](file:///e:/keyboard/apps/api/src/typevector/crypto/password.py#L1-L40) | [test_crypto_security.py](file:///e:/keyboard/apps/api/tests/test_crypto_security.py) | **VERIFIED** |
| | V2.8.1 | Rate-limit authentication attempts to prevent credential stuffing and brute force. | [rate_limit.py](file:///e:/keyboard/apps/api/src/typevector/security/rate_limit.py#L1-L80) | Redis-backed token bucket rate limits login and register endpoints to 5 attempts/min per IP. | **VERIFIED** |
| | V2.10.1 | Explicit under-18 parental/guardian consent verification policy before account creation. | [service.py](file:///e:/keyboard/apps/api/src/typevector/domains/identity/service.py#L40-L46) | `test_under_18_registration_policy_blocker` in [test_security_privacy_and_hardening.py](file:///e:/keyboard/apps/api/tests/test_security_privacy_and_hardening.py#L52-L65) | **VERIFIED** |
| **V3: Session Management** | V3.2.1 | Issue secure, HTTPOnly, SameSite cookies with strict session lifetimes. | [cookies.py](file:///e:/keyboard/apps/api/src/typevector/security/cookies.py#L1-L60) | Cookies set with `httponly=True`, `samesite="lax"`, `secure=settings.cookie_secure`. | **VERIFIED** |
| | V3.2.4 | Support explicit user logout and full session revocation (token family invalidation). | [service.py](file:///e:/keyboard/apps/api/src/typevector/domains/identity/service.py#L170-L210) | `revoke_all_sessions` marks active sessions revoked in PostgreSQL database. | **VERIFIED** |
| | V3.4.1 | Enforce anti-CSRF token verification on state-changing API endpoints authenticated via cookies. | [csrf.py](file:///e:/keyboard/apps/api/src/typevector/security/csrf.py#L1-L70) | Double-submit CSRF cookie token validated on POST/PATCH/PUT/DELETE. | **VERIFIED** |
| **V4: Access Control** | V4.1.1 | Enforce least-privilege role-based access control (RBAC) across organization tenants. | [dependencies.py](file:///e:/keyboard/apps/api/src/typevector/security/dependencies.py#L1-L80) | `RoleChecker` and tenant validation dependencies. | **VERIFIED** |
| | V4.1.2 | Prevent Insecure Direct Object References (IDOR) on attempt scoring, keystroke projection, and result preview. | [router.py](file:///e:/keyboard/apps/api/src/typevector/domains/scoring/router.py#L25-L60), [router.py](file:///e:/keyboard/apps/api/src/typevector/domains/results/router.py#L30-L75) | `test_attempt_score_and_status_idor_protection` and `test_results_preview_authorization_guard`. | **VERIFIED** |
| | V4.2.1 | Strict tenant isolation: verify caller belongs to host organization before allowing case inspection, scoring reconciliation, or export download. | [router.py](file:///e:/keyboard/apps/api/src/typevector/domains/integrity_review/router.py#L30-L80), [router.py](file:///e:/keyboard/apps/api/src/typevector/domains/exports/router.py#L40-L70) | `test_integrity_review_cross_tenant_rejection` and `test_export_job_inspection_tenant_isolation`. | **VERIFIED** |
| | V4.3.1 | Dual-approval reviewer separation and appellate judge separation on integrity sanctions. | [router.py](file:///e:/keyboard/apps/api/src/typevector/domains/integrity_review/router.py#L110-L160) | `test_integrity_appeal_judge_separation_policy`. Original reviewer cannot decide appeals. | **VERIFIED** |
| **V5: Malicious Input Handling** | V5.1.1 | Input canonicalization and Unicode scalar normalization (NFC for prose, exact scalars for code). | [canonical.py](file:///e:/keyboard/apps/api/src/typevector/domains/scoring/canonical.py#L1-L120) | [test_canonical_scoring.py](file:///e:/keyboard/apps/api/tests/test_canonical_scoring.py). | **VERIFIED** |
| | V5.2.1 | Parameterized queries via SQLAlchemy ORM; zero raw string concatenation in SQL expressions. | Throughout `domains/*/repository.py` | AST audit verified zero `text(f"...")` or raw SQL formatting. | **VERIFIED** |
| | V5.3.1 | Cross-Site Scripting (XSS) prevention: Frontend avoids `innerHTML` with unsanitized user inputs; uses `textContent` and DOM element creation. | [command-center.js](file:///e:/keyboard/apps/web/js/command-center.js#L1-L500) | Audit script verified safe DOM manipulation. | **VERIFIED** |
| | V5.4.1 | CSV Formula Injection (CWE-1236) sanitization on tabular data exports. | [export_service.py](file:///e:/keyboard/apps/api/src/typevector/domains/exports/service.py#L1-L150) | Cells starting with `=`, `+`, `-`, `@`, `\t`, `\r` prepended with single apostrophe `'`. | **VERIFIED** |
| **V8: Cryptography** | V8.1.1 | Pinned challenge cryptographic digest generation (SHA-256) for audit trails and deterministic replays. | [canonical.py](file:///e:/keyboard/apps/api/src/typevector/domains/scoring/canonical.py#L80-L110) | Verified immutable SHA-256 digest in scoring replay manifests. | **VERIFIED** |
| | V8.3.1 | Safe serialization: Celery tasks configured strictly with JSON; zero Python `pickle` serialization. | [celery_app.py](file:///e:/keyboard/apps/api/src/typevector/workers/celery_app.py#L20-L40) | Config sets `task_serializer="json"`, `accept_content=["json"]`. | **VERIFIED** |
| **V13: API & Web Services** | V13.1.1 | Restrict Cross-Origin Resource Sharing (CORS) to explicitly configured allowlists. | [main.py](file:///e:/keyboard/apps/api/src/typevector/main.py#L40-L55) | `CORSMiddleware` restricted to `settings.cors_origins_list`; wildcards disallowed in production. | **VERIFIED** |
| | V13.2.1 | PII sanitization on public profile endpoints (`PublicUserRead` excludes `email`, `phone`, `ip_address`). | [router.py](file:///e:/keyboard/apps/api/src/typevector/domains/identity/router.py#L55-L75) | `test_public_user_profile_zero_pii_sanitization`. | **VERIFIED** |
| | V13.3.1 | User profile rectification (GDPR Art. 16) and account deactivation (GDPR Art. 17). | [service.py](file:///e:/keyboard/apps/api/src/typevector/domains/identity/service.py#L220-L270) | `test_user_profile_rectification_gdpr_art_16` and `test_user_account_deactivation_gdpr_art_17`. | **VERIFIED** |
| **V14: Configuration** | V14.1.1 | Zero hardcoded secrets, test credentials, or private API keys in git repository. | Root repository scan | Automated scan verified zero private keys, API secrets, or real production tokens. | **VERIFIED** |
| | V14.2.1 | Strict cookie security flags in production (`Secure`, `HttpOnly`, `SameSite=Lax`). | [config.py](file:///e:/keyboard/apps/api/src/typevector/config.py#L40-L70) | Verified in configuration defaults and test assertions. | **VERIFIED** |

---

## 3. WebSocket Security Checklist (`arena-ws-v1`)

The real-time ranked input channel (`/ws/arena/{round_id}`) and broadcast channel (`/ws/broadcast/{event_id}`) implement a strict security profile:

| Vector | Mitigating Control | Code Reference | Verification Evidence |
| :--- | :--- | :--- | :--- |
| **Cross-Site WebSocket Hijacking (CSWSH)** | RFC 6455 `Origin` header validation against `settings.cors_origins_list`. Unauthorized origins rejected with `WS_1008_POLICY_VIOLATION`. | [router.py](file:///e:/keyboard/apps/api/src/typevector/domains/ranked_input/router.py#L65-L85), [router.py](file:///e:/keyboard/apps/api/src/typevector/domains/broadcast/router.py#L30-L55) | `test_spectator_websocket_origin_security_policy` in [test_security_privacy_and_hardening.py](file:///e:/keyboard/apps/api/tests/test_security_privacy_and_hardening.py#L110-L125). |
| **Stale Writer / Split-Brain Session** | Authoritative session token binding. When a newer connection authenticates for an attempt, existing sockets are fenced and closed with code `4409 (Stale Session)`. | [socket_manager.py](file:///e:/keyboard/apps/api/src/typevector/domains/ranked_input/socket_manager.py#L50-L80) | Verified in ranked input unit tests. |
| **Message Flooding / DoS** | Sliding-window leaky token bucket per connection strictly capping messages to 30 keystroke frames per second. Excessive frames dropped or socket closed with `1008`. | [socket_manager.py](file:///e:/keyboard/apps/api/src/typevector/domains/ranked_input/socket_manager.py#L90-L120) | Rate limit enforcement unit tests. |
| **Oversized Payloads** | Frame size capped at 1,024 bytes per message (ranked input and spectator stream). Frames exceeding threshold aborted immediately with `WS_1009_MESSAGE_TOO_BIG`. | [router.py](file:///e:/keyboard/apps/api/src/typevector/domains/ranked_input/router.py#L90-L105), [router.py](file:///e:/keyboard/apps/api/src/typevector/domains/broadcast/router.py#L60-L75) | Verified in WebSocket integration tests. |
| **Keystroke Replay / Out-of-Order Frames** | Monotonically increasing sequence counters (`seq_num`). Inbound frames with sequence numbers `<= last_seen_seq` are rejected as duplicate/replayed input. | [socket_manager.py](file:///e:/keyboard/apps/api/src/typevector/domains/ranked_input/socket_manager.py#L130-L155) | Verified in protocol sequence tests. |
| **Premature Prompt Leakage** | Ranked challenge prompt text withheld from client until round state transitions authoritatively to `ACTIVE` with synchronized countdown. | [service.py](file:///e:/keyboard/apps/api/src/typevector/domains/events/service.py#L120-L150) | Invariant checked in round lifecycle transitions. |
| **Durable ACK Truthfulness** | WebSocket ACKs (`INPUT_ACK`) sent only after batch evidence is durably queued in the transactional buffer, guaranteeing client certainty of server receipt. | [socket_manager.py](file:///e:/keyboard/apps/api/src/typevector/domains/ranked_input/socket_manager.py#L160-L180) | Authoritative ACK protocol validation. |

---

## 4. Privacy, Telemetry, and Consent Hygiene

1. **Public Identity Sanitization:**  
   - `GET /api/v1/identity/users/{user_id}` serves `PublicUserRead(id, display_name, status, role, created_at)`.
   - Contact emails, institutional identifiers, phone numbers, and IP addresses are completely excluded from public-facing serializers.
2. **User Data Rights (GDPR Art. 16 & 17):**  
   - Rectification: `PATCH /api/v1/identity/me` allows updating `display_name` with strict audit trail (`user.profile_updated`).
   - Deactivation: `POST /api/v1/identity/deactivate` terminates active sessions (`revoke_all_sessions`), flags account as deactivated, and discards session cookies.
3. **Age Verification Guardrail:**  
   - Registration requires explicit boolean confirmation of legal majority (18+) or verified guardian authorization (`is_age_confirmed_18: bool = Field(...)`).
   - Registration requests lacking confirmation fail with `422 Invariant Violation (UNDER_18_BLOCKED)`.
4. **Telemetry Privacy Boundaries:**  
   - Prometheus metrics, Jaeger traces, and Celery logs record metadata only (e.g., attempt UUID, duration ms, net WPM, error status).
   - Full challenge prompt texts, user typing streams, and unreviewed integrity suspicion tags are barred from operational log sinks.

---

## 5. Accessibility & Product-Truth Verification

1. **Accessibility Standards (WCAG 2.2 AA Target):**
   - **Keyboard Trapping & Escape Handlers:** Modal dialogs in [command-center.js](file:///e:/keyboard/apps/web/js/command-center.js#L140-L180) trap keyboard navigation, close cleanly on `Escape`, and restore focus to `document.activeElement` upon dismissal (WCAG 2.1.2 & 2.4.3).
   - **Contrast & Theming:** High-contrast neutral palette (`--text-main: #f1f5f9`, `--bg-main: #0b0f19`) meeting 7:1 contrast ratio for normal text.
   - **Motion Preferences:** `@media (prefers-reduced-motion: reduce)` disables non-essential animations.
   - **Screen Reader Clarity:** Semantic ARIA roles (`role="dialog"`, `aria-modal="true"`, `aria-live="polite"`) applied to notifications and modal containers.
2. **Product-Truth Commitments:**
   - Deprecated misleading terms ("tamper-proof", "cheat-proof", "guaranteed zero latency").
   - Clock synchronization accurately documented as a "bounded <= 5.0ms target" based on NTP drift characteristics rather than an absolute hardware guarantee.
   - Metric states explicitly mapped:
     - `Local`: Uncommitted client keystrokes.
     - `Pending`: Ingested by WebSocket, awaiting transactional batch persistence.
     - `Saved`: Durably recorded in PostgreSQL transactional outbox.
     - `Provisional`: Computed by scoring engine, pending integrity clearance.
     - `Official`: Host organization certified and published.
     - `Unavailable`: Withheld due to disqualification, sanction, or round void.

---

## 6. Release Blockers & Gaps Register

The following items are identified as intentional operational requirements prior to production mainnet deployment:

| Item | Requirement Description | Mitigation / Current Status | Blocking Severity |
| :--- | :--- | :--- | :--- |
| **Production SMTP Credentials** | Outbox notification processor currently defaults to secure mock provider when `SMTP_HOST` is unconfigured. Real emails are withheld. | Safe fallback implemented; credentials must be provisioned in deployment vault. | **RELEASE BLOCKER** |
| **Formal Legal Privacy Review** | COPPA/GDPR parental consent flow requires formal legal jurisdiction terms and privacy policy publication. | Technical under-18 consent gate active in API and UI. | **PRE-LAUNCH REQUIREMENT** |
| **External Security Audit** | Independent penetration test and accredited third-party ASVS certification. | Internal risk-selected ASVS Level 2 self-audit complete and verified. | **RECOMMENDED POST-V1** |

