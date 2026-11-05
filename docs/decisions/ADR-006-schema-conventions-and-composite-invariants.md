# ADR-006: Database Schema Conventions, Composite Relational Invariants, and Migration Lifecycle

## Status
Accepted (2026-11-04)

## Context
TypeVector Arena requires absolute multi-tenant and multi-event fairness and integrity. A fundamental hazard in tournament and ranked typing systems is cross-event data corruption (e.g., an attempt submitted under Event A referencing a round or registration belonging to Event B) or tenant isolation leakage. Relying purely on application-layer `WHERE` clauses introduces severe risks of developer oversight or subtle race conditions. Furthermore, constraint naming must be deterministic to support automated, safe schema migrations across versions.

## Decision
1. **Strict Naming Conventions:**
   All database objects use explicit PostgreSQL naming conventions:
   - Primary Keys: `pk_%(table_name)s`
   - Unique Constraints: `uq_%(table_name)s_%(column_0_name)s`
   - Check Constraints: `ck_%(table_name)s_%(constraint_name)s`
   - Foreign Keys: `fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s`
   - Indexes: `ix_%(column_0_label)s`

2. **Composite Relational Invariants for Event Isolation:**
   Cross-event data integrity is enforced physically at the PostgreSQL engine level:
   - `rounds` exposes `UniqueConstraint("id", "event_id")`.
   - `event_registrations` exposes `UniqueConstraint("event_id", "user_id")`.
   - `ranked_attempts` enforces composite foreign keys:
     - `ForeignKeyConstraint(["round_id", "event_id"], ["rounds.id", "rounds.event_id"])`
     - `ForeignKeyConstraint(["event_id", "user_id"], ["event_registrations.event_id", "event_registrations.user_id"])`
   - `ranked_input_batches` enforces composite foreign key:
     - `ForeignKeyConstraint(["attempt_id", "event_id"], ["ranked_attempts.id", "ranked_attempts.event_id"])`
   - `participant_scores` enforces composite foreign key:
     - `ForeignKeyConstraint(["attempt_id", "event_id"], ["ranked_attempts.id", "ranked_attempts.event_id"])`

3. **Transaction Ownership:**
   - FastAPI routers remain thin HTTP adapters.
   - Domain services own transaction boundaries and invariant checks.
   - `get_db_session` dependency manages unit of work (commits on clean completion, rolls back on exception).
   - PostgreSQL Transactional Outbox pattern (`transactional_outbox`) guarantees atomic database writes and external message dispatches without distributed transactions.

4. **Migration Strategy:**
   - Alembic manages forward and reverse migrations.
   - Routine paths strictly prohibit destructive `DROP ... CASCADE`.
   - Migrations are tested via offline SQL compilation (`upgrade --sql` and `downgrade --sql`) and verified against PostgreSQL.

## Consequences
### Positive
- Cross-event contamination is physically rejected by PostgreSQL constraint engines, even if an application bug omitted a filter.
- Schema migrations produce clean, predictable DDL with zero auto-generated random constraint hashes.
- Auditing and data lineage are deterministic.

### Negative / Trade-offs
- Child tables must carry redundant `event_id` columns to satisfy composite foreign key references.
- Slightly higher index storage overhead in PostgreSQL for composite unique keys.

