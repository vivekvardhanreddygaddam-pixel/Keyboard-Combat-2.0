#!/usr/bin/env bash
# ==============================================================================
# TypeVector Arena — Automated Database Backup Script (POSIX)
# Creates a compressed, checksummed PostgreSQL backup archive.
# ==============================================================================

set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/backups/postgres}"
TIMESTAMP=$(date -u +"%Y%m%d_%H%M%SZ")
DB_HOST="${DB_HOST:-postgres}"
DB_PORT="${DB_PORT:-5432}"
DB_USER="${POSTGRES_USER:-typevector}"
DB_NAME="${POSTGRES_DB:-typevector_prod}"

mkdir -p "${BACKUP_DIR}"

BACKUP_FILE="${BACKUP_DIR}/${DB_NAME}_${TIMESTAMP}.dump"
CHECKSUM_FILE="${BACKUP_FILE}.sha256"

echo "=== Starting PostgreSQL Backup: ${DB_NAME} at ${TIMESTAMP} ==="

# Execute pg_dump with custom format and compression
PGPASSWORD="${POSTGRES_PASSWORD}" pg_dump \
    -h "${DB_HOST}" \
    -p "${DB_PORT}" \
    -U "${DB_USER}" \
    -d "${DB_NAME}" \
    -Fc \
    -Z 6 \
    -f "${BACKUP_FILE}"

# Calculate SHA-256 checksum for tamper-evidence
sha256sum "${BACKUP_FILE}" | awk '{print $1}' > "${CHECKSUM_FILE}"
CHECKSUM=$(cat "${CHECKSUM_FILE}")

FILE_SIZE=$(du -h "${BACKUP_FILE}" | awk '{print $1}')
echo "[OK] Backup successfully generated:"
echo "     File:     ${BACKUP_FILE} (${FILE_SIZE})"
echo "     SHA-256:  ${CHECKSUM}"

# Prune local backups older than 7 days
find "${BACKUP_DIR}" -name "${DB_NAME}_*.dump*" -type f -mtime +7 -delete
echo "[OK] Pruned backup archives older than 7 days."
