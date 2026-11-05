# Backup and Disaster Recovery Runbook

**Document Version:** 1.0.0  
**Last Updated:** 2026-11-05  
**System Classification:** Production Runbook  
**System of Record:** PostgreSQL 16 (Authoritative)  
**Ephemeral State:** Redis 7 (Non-authoritative, rebuildable cache and Celery broker)

---

## 1. Objectives and Scope

| Metric | Target | Description |
|---|---|---|
| **RPO (Recovery Point Objective)** | $\le 1\text{ hour}$ (WAL continuous archiving) / $\le 24\text{ hours}$ (daily snapshot) | Maximum allowable data loss window during total infrastructure failure. |
| **RTO (Recovery Time Objective)** | $\le 30\text{ minutes}$ | Maximum allowable duration from incident declaration to verified database online status. |
| **Authoritative Scope** | 26 PostgreSQL relational tables | All accounts, event rules, immutable attempts, published results, audit logs, and outbox records. |
| **Non-Authoritative Scope** | Redis instances | Ephemeral rate-limit tokens, spectator pub/sub broadcasts, and Celery broker queues. No persistent data resides exclusively in Redis. |

---

## 2. Backup Architecture and Policies

### 2.1 Snapshot Backup Cadence
- **Frequency:** Automated daily cron at `02:00 UTC` via Celery Beat or host scheduler.
- **Format:** PostgreSQL custom archive format (`-Fc`), gzip compression level 6 (`-Z 6`).
- **Integrity Validation:** SHA-256 checksum generated immediately after export and stored alongside as `.sha256`.
- **Local Retention:** 7-day rolling window managed automatically by [`scripts/backup_database.sh`](file:///e:/keyboard/scripts/backup_database.sh) / [`scripts/backup_database.ps1`](file:///e:/keyboard/scripts/backup_database.ps1).
- **Offsite Replication:** Encrypted upload to S3/GCS immutable object storage with Object Lock (WORM policy) for 90 days.

### 2.2 Continuous WAL Archiving (Production PITR)
In production cloud environments, continuous Write-Ahead Log (WAL) archiving must be enabled via `wal_level = replica`, `archive_mode = on`, and tools such as `pgBackRest` or `wal-g`. This enables Point-In-Time Recovery to any specific second prior to an operational incident.

---

## 3. Restoration Runbook

### Step 1: Incident Assessment & Blast Radius Containment
1. If restoring due to corruption or malicious attack, isolate the compromised database:
   ```bash
   # Terminate active client connections
   SELECT pg_terminate_backend(pid) FROM pg_stat_activity 
   WHERE datname = 'typevector_prod' AND pid <> pg_backend_pid();
   ```
2. Put the API application into maintenance mode or scale API pods to 0 to prevent partial writes.

### Step 2: Acquire and Verify Backup Archive
1. Retrieve the latest verified `.dump` file and corresponding `.sha256` checksum.
2. Verify checksum locally before initiating restore:
   ```bash
   sha256sum -c typevector_prod_20261105_020000Z.dump.sha256
   ```

### Step 3: Execute Restoration Script
Execute the platform-appropriate restore script with the `--confirm` flag (or interactively type `RESTORE`):

**POSIX / Linux / Docker:**
```bash
export POSTGRES_PASSWORD="<production-password>"
./scripts/restore_database.sh /backups/postgres/typevector_prod_20261105_020000Z.dump --confirm
```

**PowerShell / Windows:**
```powershell
$env:POSTGRES_PASSWORD = "<production-password>"
.\scripts\restore_database.ps1 -BackupFile ".\backups\postgres\typevector_prod_20261105_020000Z.dump" -ConfirmRestore
```

### Step 4: Post-Restore Verification Checklist
The restore script automatically executes and prints verification queries. Validate the output against expected baselines:

```sql
-- 1. Verify schema completeness
SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public';
-- Expected: >= 26 tables

-- 2. Verify core entity counts
SELECT count(*) FROM users;
SELECT count(*) FROM events;
SELECT count(*) FROM ranked_attempts;
SELECT count(*) FROM published_results;

-- 3. Verify outbox state
SELECT status, count(*) FROM outbox_events GROUP BY status;
-- Note: 'pending' outbox events will be safely dispatched once Celery workers resume.
```

### Step 5: Application Reconnection & Liveness Verification
1. Restart/scale up FastAPI backend services.
2. Probe application readiness endpoint:
   ```bash
   curl -f http://localhost:8000/readyz
   # Must return {"status": "ready", "database": "connected"}
   ```
3. Restart Celery worker processes. Workers will automatically resume processing any pending outbox rows without data loss.

---

## 4. Rehearsal Status and Verification Record

> [!WARNING]
> **Operational Status:**  
> - **Automation Scripts:** [`scripts/backup_database.sh`](file:///e:/keyboard/scripts/backup_database.sh), [`scripts/backup_database.ps1`](file:///e:/keyboard/scripts/backup_database.ps1), [`scripts/restore_database.sh`](file:///e:/keyboard/scripts/restore_database.sh), and [`scripts/restore_database.ps1`](file:///e:/keyboard/scripts/restore_database.ps1) are authored, syntax-checked, and committed.  
> - **Live Cloud Drill:** **UNVERIFIED (PENDING STAGING CLUSTER PROVISIONING)**. Because external cloud staging infrastructure is not provisioned in this local environment, a full multi-gigabyte disaster recovery rehearsal must be executed on the provisioned staging cluster prior to live competition launch.
