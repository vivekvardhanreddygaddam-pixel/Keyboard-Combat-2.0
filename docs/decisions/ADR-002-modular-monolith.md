# ADR-002: Modular Monolith Architecture Pattern over Microservices

**Status:** Accepted  
**Date:** 2026-11-03  
**Deciders:** Principal Product Architect, Core Engineering Team  
**Blueprint Reference:** Blueprint v4.0 — Architecture decisions, Non-goals, Prompt 1, Prompt 4  

---

## 1. Context and Problem Statement
TypeVector Arena encompasses a rich set of 16 distinct domain boundaries (identity, organizations, events, registrations, practice, curriculum, rounds, ranked_input, scoring, results, integrity_review, broadcast, notifications, exports, audit, and operations). The engineering team must decide how to structure these domains to maintain velocity, ensure transactional integrity, and avoid premature distributed systems complexity.

## 2. Decision Drivers
- Need for ACID transactions across cross-domain entities (e.g., admitting an input batch, updating sequence projection, and writing an outbox event in a single commit).
- Blueprint non-goal: Explicit prohibition of microservices, service meshes, and distributed choreographies.
- Simplicity of debugging, local testing, and deployment.
- High cohesion within domains and loose coupling across domains.
- Ability to independently evolve domain logic while retaining compile-time / import-time interface safety.

## 3. Considered Options
1. **Modular Monolith (Chosen):**
   - Single FastAPI backend service (`apps/api`) structured into isolated internal domain packages.
   - Strict DAG (Directed Acyclic Graph) of internal dependencies.
   - Database integrity enforced via PostgreSQL constraints, foreign keys, and single-transaction boundaries.
   - Domain-to-domain communication through well-defined service contracts/interfaces.
2. **Distributed Microservices:**
   - Decomposing into separate services: Auth Service, Competition Service, Scoring Service, Practice Service, etc.
   - Requires distributed transactions (Sagas/2PC), gRPC/REST inter-service networking, independent databases, and complex orchestration.
3. **Layered "Spaghetti" Monolith:**
   - Generic shared models, ubiquitous circular imports, fat ORM models leaking into HTTP routers without domain ownership.

## 4. Decision Outcome
**Chosen Option:** Modular Monolith Architecture.

### Justification:
- Critical competition invariants (such as input sequence admission and capacity-controlled registration) demand single-database transactional guarantees that are fragile and expensive to implement in distributed microservices.
- A modular monolith enforces bounded contexts through strict packaging conventions (`app/domains/{domain_name}/`), explicit public service interfaces, and zero circular dependencies.

## 5. Domain Packaging & Dependency Rules
Every domain package within `apps/api/src/typevector/domains/{domain}/` must follow this structure:
- `models.py`: SQLAlchemy entities owned exclusively by this domain.
- `schemas.py`: Pydantic input/output validation contracts.
- `services.py`: Domain logic, invariant enforcement, and transaction boundaries.
- `router.py`: Thin HTTP and WebSocket endpoint handlers translating web protocols to domain calls.
- `exceptions.py`: Domain-specific error types.

### Dependency Direction (Strict DAG):
- Cross-domain calls must only occur through domain `services.py`, never by directly querying or mutating another domain's private SQLAlchemy models.
- Transaction ownership belongs to the originating domain service. Cross-domain mutations must be coordinated via the Transactional Outbox pattern when async or via explicit service orchestration within an atomic transaction.
- Circular imports between domains are strictly prohibited and caught by linting/import rules.

## 6. Consequences and Trade-offs
### Positive Consequences
- Atomic commits across related entities eliminate eventual consistency lag in high-stakes competition paths.
- Massively simplified local development: a single backend process to start, inspect, and debug.
- Straightforward end-to-end integration testing using isolated PostgreSQL transaction rollbacks.
- Future extraction path: Well-encapsulated domain boundaries leave an option to extract microservices later if scaling data genuinely warrants it.

### Negative Consequences / Accepted Trade-offs
- Codebase discipline is mandatory; developers could inadvertently couple domains if code review rules are bypassed.
- Entire monolith must be redeployed together, requiring robust automated regression test suites.

## 7. Validation Strategy
- Architecture linting / import scanners to verify no circular domain imports.
- Transaction boundary unit and integration tests proving atomic commit and rollback behavior.

