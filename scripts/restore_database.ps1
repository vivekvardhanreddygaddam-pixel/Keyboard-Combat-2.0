<#
.SYNOPSIS
    TypeVector Arena - Database Restore & Verification Script (PowerShell / Windows)
.DESCRIPTION
    Restores a compressed PostgreSQL custom-format dump with checksum verification,
    safety gates, and post-restore integrity count queries.
.EXAMPLE
    .\scripts\restore_database.ps1 -BackupFile ".\backups\postgres\typevector_prod_20261105.dump" -ConfirmRestore
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string]$BackupFile,

    [switch]$ConfirmRestore,

    [string]$DbHost = $env:DB_HOST,
    [string]$DbPort = $env:DB_PORT,
    [string]$DbUser = $env:POSTGRES_USER,
    [string]$DbName = $env:POSTGRES_DB,
    [string]$DbPassword = $env:POSTGRES_PASSWORD
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -Path $BackupFile)) {
    throw "Backup file '$BackupFile' does not exist."
}

if (-not $DbHost) { $DbHost = "localhost" }
if (-not $DbPort) { $DbPort = "5432" }
if (-not $DbUser) { $DbUser = "typevector" }
if (-not $DbName) { $DbName = "typevector_prod" }

Write-Host "==================================================================" -ForegroundColor Cyan
Write-Host "TypeVector Arena - Database Restore Procedure" -ForegroundColor Cyan
Write-Host "Target DB: ${DbUser}@${DbHost}:${DbPort}/${DbName}"
Write-Host "Dump File: $BackupFile"
Write-Host "=================================================================="

# 1. SHA-256 Checksum Verification
$ChecksumFile = "${BackupFile}.sha256"
if (Test-Path -Path $ChecksumFile) {
    Write-Host "--> Verifying SHA-256 checksum..." -ForegroundColor Yellow
    $ExpectedHash = (Get-Content -Path $ChecksumFile).Trim().ToLower()
    $ActualHash = (Get-FileHash -Path $BackupFile -Algorithm SHA256).Hash.ToLower()
    if ($ExpectedHash -ne $ActualHash) {
        throw "FATAL: Checksum mismatch! Expected: $ExpectedHash, Actual: $ActualHash"
    }
    Write-Host "[OK] Checksum verified: $ActualHash" -ForegroundColor Green
} else {
    Write-Host "WARNING: No .sha256 file found for '$BackupFile'. Proceeding without pre-verification." -ForegroundColor DarkYellow
}

# 2. Safety Gate
if (-not $ConfirmRestore) {
    Write-Host ""
    Write-Host "WARNING: Restoring this backup will overwrite existing data in '$DbName'!" -ForegroundColor Red
    $UserInput = Read-Host "Type 'RESTORE' to proceed"
    if ($UserInput -ne "RESTORE") {
        Write-Host "Aborted by user." -ForegroundColor Yellow
        exit 0
    }
}

# 3. Execute pg_restore
Write-Host "--> Executing pg_restore with --clean --if-exists..." -ForegroundColor Yellow
if ($DbPassword) {
    $env:PGPASSWORD = $DbPassword
}

try {
    if (-not (Get-Command "pg_restore" -ErrorAction SilentlyContinue)) {
        throw "pg_restore executable not found in PATH."
    }

    & pg_restore -h $DbHost -p $DbPort -U $DbUser -d $DbName --clean --if-exists --no-owner --no-privileges $BackupFile
    if ($LASTEXITCODE -gt 1) {
        throw "pg_restore failed with exit code $LASTEXITCODE"
    }
    Write-Host "[OK] Restore completed successfully." -ForegroundColor Green

    # 4. Post-Restore Verification Checklist
    if (Get-Command "psql" -ErrorAction SilentlyContinue) {
        Write-Host "--> Running post-restore database integrity checks..." -ForegroundColor Yellow
        $VerifySql = @"
SELECT 'Tables in schema public:' AS check_item, count(*)::text AS count
FROM information_schema.tables WHERE table_schema = 'public'
UNION ALL
SELECT 'Users:', count(*)::text FROM users
UNION ALL
SELECT 'Events:', count(*)::text FROM events
UNION ALL
SELECT 'Ranked Attempts:', count(*)::text FROM ranked_attempts
UNION ALL
SELECT 'Published Results:', count(*)::text FROM published_results
UNION ALL
SELECT 'Pending Outbox Events:', count(*)::text FROM outbox_events WHERE status = 'pending';
"@
        & psql -h $DbHost -p $DbPort -U $DbUser -d $DbName -v ON_ERROR_STOP=1 -c $VerifySql
    }
}
finally {
    if ($env:PGPASSWORD) {
        Remove-Item env:PGPASSWORD -ErrorAction SilentlyContinue
    }
}

Write-Host "==================================================================" -ForegroundColor Cyan
Write-Host "[SUCCESS] Database restore and verification completed." -ForegroundColor Green
Write-Host "==================================================================" -ForegroundColor Cyan
