#!/usr/bin/env bash
# ==============================================================================
# TypeVector Arena — Database Restore & Verification Script (POSIX)
# Restores a compressed PostgreSQL custom-format dump with integrity verification.
#
# Usage:
#   ./scripts/restore_database.sh <path_to_dump> [--confirm]
# ==============================================================================

set -euo pipefail

BACKUP_FILE="${1:-}"
CONFIRM_FLAG="${2:-}"

if [[ -z "${BACKUP_FILE}" ]]; then
    echo "ERROR: Missing backup file argument."
    echo "Usage: $0 <path_to_dump_file> [--confirm]"
    exit 1
fi

if [[ ! -f "${BACKUP_FILE}" ]]; then
    echo "ERROR: Backup file '${BACKUP_FILE}' does not exist."
    exit 1
fi

DB_HOST="${DB_HOST:-postgres}"
DB_PORT="${DB_PORT:-5432}"
DB_USER="${POSTGRES_USER:-typevector}"
DB_NAME="${POSTGRES_DB:-typevector_prod}"

echo "=================================================================="
echo "TypeVector Arena — Database Restore Procedure"
echo "Target DB: ${DB_USER}@${DB_HOST}:${DB_PORT}/${DB_NAME}"
echo "Dump File: ${BACKUP_FILE}"
echo "=================================================================="

# 1. SHA-256 Checksum Verification
CHECKSUM_FILE="${BACKUP_FILE}.sha256"
if [[ -f "${CHECKSUM_FILE}" ]]; then
    echo "--> Verifying SHA-256 checksum..."
    EXPECTED_HASH=$(awk '{print $1}' "${CHECKSUM_FILE}")
    ACTUAL_HASH=$(sha256sum "${BACKUP_FILE}" | awk '{print $1}')
    if [[ "${EXPECTED_HASH}" != "${ACTUAL_HASH}" ]]; then
        echo "FATAL: Checksum mismatch!"
        echo "  Expected: ${EXPECTED_HASH}"
        echo "  Actual:   ${ACTUAL_HASH}"
        exit 1
    fi
    echo "[OK] Checksum verified: ${ACTUAL_HASH}"
else
    echo "WARNING: No .sha256 file found for '${BACKUP_FILE}'. Proceeding without pre-verification."
fi

# 2. Confirmation Safety Gate
if [[ "${CONFIRM_FLAG}" != "--confirm" ]]; then
    echo ""
    echo "WARNING: Restoring this backup will overwrite existing data in '${DB_NAME}'!"
    read -rp "Type 'RESTORE' to proceed: " USER_INPUT
    if [[ "${USER_INPUT}" != "RESTORE" ]]; then
        echo "Aborted by user."
        exit 0
    fi
fi

# 3. Execute pg_restore
echo "--> Executing pg_restore with --clean --if-exists..."
PGPASSWORD="${POSTGRES_PASSWORD}" pg_restore \
    -h "${DB_HOST}" \
    -p "${DB_PORT}" \
    -U "${DB_USER}" \
    -d "${DB_NAME}" \
    --clean \
    --if-exists \
    --no-owner \
    --no-privileges \
    "${BACKUP_FILE}" || {
        RESTORE_STATUS=$?
        # pg_restore returns 1 on warnings (e.g. drop table when table doesn't exist yet)
        if [[ ${RESTORE_STATUS} -gt 1 ]]; then
            echo "ERROR: pg_restore failed with exit code ${RESTORE_STATUS}"
            exit ${RESTORE_STATUS}
        fi
        echo "[INFO] pg_restore completed with non-fatal notices."
    }

echo "[OK] Restore completed successfully."

# 4. Post-Restore Verification Checklist
echo "--> Running post-restore database integrity checks..."

PGPASSWORD="${POSTGRES_PASSWORD}" psql \
    -h "${DB_HOST}" \
    -p "${DB_PORT}" \
    -U "${DB_USER}" \
    -d "${DB_NAME}" \
    -v ON_ERROR_STOP=1 \
    <<-EOSQL
SELECT 'Tables in schema public:' AS check_item, count(*)::text AS count
FROM information_schema.tables WHERE table_schema = 'public';

SELECT 'Users:' AS check_item, count(*)::text AS count FROM users;
SELECT 'Events:' AS check_item, count(*)::text AS count FROM events;
SELECT 'Ranked Attempts:' AS check_item, count(*)::text AS count FROM ranked_attempts;
SELECT 'Published Results:' AS check_item, count(*)::text AS count FROM published_results;
SELECT 'Pending Outbox Events:' AS check_item, count(*)::text AS count FROM outbox_events WHERE status = 'pending';
EOSQL

echo "=================================================================="
echo "[SUCCESS] Database restore and verification completed."
echo "=================================================================="
