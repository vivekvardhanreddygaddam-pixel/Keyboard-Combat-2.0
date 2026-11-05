# TypeVector Arena — Known Limitations & Unverified Claims (KNOWN_LIMITATIONS.md)

**Document Version:** 1.13.0  
**Current Phase:** Phase 15 of 15 (Deployment, Observability, Backup/Restore, and Release Decision Complete)  
**Last Updated:** 2026-11-05  
**Lead Architect:** Principal Product Architect & Technical Lead  

---

## 1. Intentionally Unsupported Features (Blueprint Non-Goals)

The following capabilities are deliberately out of scope for TypeVector Arena:
1. **Frontend Component Frameworks:** React, Next.js, Vue, Angular, Svelte, and client-side virtual DOM libraries are explicitly disallowed. The frontend is exclusively vanilla HTML5, CSS3, and ES modules.
2. **Microservices & Distributed Service Mesh:** The architecture is strictly a modular monolith. Microservices, Istio/Linkerd, and gRPC service-to-service networks are excluded.
3. **Heavy Message Queues:** Kafka, RabbitMQ, and AWS SQS are excluded; Celery with Redis and the PostgreSQL Transactional Outbox handle all async requirements.
4. **AI/Automated Proctoring Disqualification:** Automated bans or disqualifications based on webcam tracking, audio analysis, or opaque heuristic fraud scores are excluded. Integrity signals are strictly flags for human reviewers.
5. **Monetary Prize Payout Infrastructure:** Built-in payment gateways, cryptocurrency wallets, or automated prize disbursements are out of scope.
6. **Client-Authoritative Scoring:** The browser is never permitted to calculate or submit official scores, rank order, or eligibility status.

---

## 2. Environment & Tooling Limitations

1. **Host Environment (Windows PowerShell):**
   - The workspace operates on Windows with PowerShell. Shell execution patterns require forward-slash path normalization for URLs and explicit virtual environment execution via `uv run`.
2. **Local Infrastructure Dependency:**
   - Development and testing rely on local PostgreSQL 16 and Redis 7 services. The test suite uses in-memory SQLite and mock engines for isolated CI/CD testing, while full integration requires running databases.
3. **Single Monolith Deployment:**
   - The modular monolith must be deployed as a unified artifact; independent zero-downtime deployment of individual domain packages is not supported.

---

## 3. Unverified Claims & Explicit Release Blockers

In adherence to the platform's core truthfulness requirement:
- **Production Packaging & Release Audit:** All software artifacts, container packaging (`Dockerfile.api`, `Dockerfile.web`), reverse proxy configurations (`nginx.conf`, `Caddyfile`), compose specs (`docker-compose.prod.yml`), backup/restore scripts (`scripts/backup_database.*`, `scripts/restore_database.*`), runbooks, and observability specifications are fully completed. The platform has been audited against all 10 Blueprint Release Gates in [`RELEASE_READINESS_REPORT.md`](file:///e:/keyboard/docs/release/RELEASE_READINESS_REPORT.md), resulting in an official **CONDITIONAL GO** verdict.
- **Scalability & Concurrency Targets:** Local micro-benchmarks confirmed sub-0.1ms p95 algorithmic execution across diffing, scoring, and protocol operations. Candidate SLOs are proposed in `WORKLOAD_MODEL_AND_CAPACITY_TARGETS.md` and await live multi-node staging cluster verification.
- **Security & Compliance Certification:** No claim of accredited OWASP ASVS compliance, ISO certification, or legal GDPR/FERPA compliance is made. Controls are documented in the [SECURITY_CONTROL_REGISTER.md](file:///e:/keyboard/docs/security/SECURITY_CONTROL_REGISTER.md) as self-verified technical measures.
- **"Cheat-Proof" Integrity:** No typing platform can claim 100% immunity to hardware-level keystroke injection or sophisticated cheating. TypeVector Arena provides evidence-backed, server-authoritative auditability and human review workflows, not mathematical impossibility of cheating.

### Explicit Operational Release Blockers
Prior to opening production tournaments to the public, platform operators must resolve the four items documented in [`RELEASE_READINESS_REPORT.md`](file:///e:/keyboard/docs/release/RELEASE_READINESS_REPORT.md):
1. **BLOCKER-01 (Production SMTP Credentials):** Outbox email notification worker defaults to a secure mock provider when credentials are unconfigured. Production SMTP credentials must be provisioned in deployment secrets before account activation emails and notification dispatches can reach real inboxes.
2. **BLOCKER-02 (Multi-Node Staging Load Soak Rehearsal):** While local micro-benchmarks verified sub-millisecond compute throughput, synthetic load testing with 1,000 concurrent typists across separate physical nodes must be rehearsed on staging infrastructure.
3. **BLOCKER-03 (Live Staging Backup & Restore Drill):** POSIX and PowerShell backup and restore scripts have been authored, checksum-validated, and committed. A live end-to-end rehearsal restoring a 1GB+ dump onto a secondary staging PostgreSQL instance must be completed and signed off.
4. **BLOCKER-04 (Legal Review of Under-18 Participant Terms):** Under-18 competitors are restricted from participating in cash-prize tournaments without parental consent. Final terms of service and COPPA/GDPR-K privacy disclosures require formal legal counsel sign-off.


---

## 4. Pending High-Impact Decisions (Product Owner Status)

The following items are documented with safe engineering defaults, pending final Product Owner sign-off before prize events:
1. **Scoring Formula Approval (`POD-01`):** `arena-score-v1` formula and its completion gating (<=699 incomplete, >=700 exact completion) implemented with golden vector test validation. Test events permitted; prize events gated.
2. **Curriculum Level Criteria (`POD-02`):** Skill track progression criteria (Foundation to Expert) implemented with multi-attempt minimum requirements.
3. **Event-Wide Pause & Void Thresholds (`POD-03`):** Event-wide pause/void/restart policies implemented; selective per-participant extensions prohibited.
4. **Identity Verification Provider (`POD-04`):** Institutional identity claims implemented with dual-state verification (`pending` -> `verified` by admin).
5. **Minor Participant & Legal Privacy Policy (`POD-05`):** Technical age verification gate (`is_age_confirmed_18`) active in registration schemas and UI.
