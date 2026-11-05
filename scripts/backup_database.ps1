<#
.SYNOPSIS
    TypeVector Arena - Automated Database Backup Script (PowerShell / Windows)
.DESCRIPTION
    Creates a compressed, checksummed PostgreSQL backup archive using pg_dump.
    Calculates SHA-256 checksum for tamper-evidence and prunes archives older than 7 days.
#>

[CmdletBinding()]
param(
    [string]$BackupDir = $env:BACKUP_DIR,
    [string]$DbHost = $env:DB_HOST,
    [string]$DbPort = $env:DB_PORT,
    [string]$DbUser = $env:POSTGRES_USER,
    [string]$DbName = $env:POSTGRES_DB,
    [string]$DbPassword = $env:POSTGRES_PASSWORD,
    [int]$RetentionDays = 7
)

$ErrorActionPreference = "Stop"

if (-not $BackupDir) { $BackupDir = "./backups/postgres" }
if (-not $DbHost) { $DbHost = "localhost" }
if (-not $DbPort) { $DbPort = "5432" }
if (-not $DbUser) { $DbUser = "typevector" }
if (-not $DbName) { $DbName = "typevector_prod" }

if (-not (Test-Path -Path $BackupDir)) {
    New-Item -ItemType Directory -Path $BackupDir -Force | Out-Null
}

$Timestamp = (Get-Date).ToUniversalTime().ToString("yyyyMMdd_HHmmssZ")
$BackupFile = Join-Path $BackupDir "${DbName}_${Timestamp}.dump"
$ChecksumFile = "${BackupFile}.sha256"

Write-Host "=== Starting PostgreSQL Backup: $DbName at $Timestamp ===" -ForegroundColor Cyan

if ($DbPassword) {
    $env:PGPASSWORD = $DbPassword
}

try {
    # Check if pg_dump is available
    if (-not (Get-Command "pg_dump" -ErrorAction SilentlyContinue)) {
        throw "pg_dump executable not found in PATH. Ensure PostgreSQL client tools are installed."
    }

    & pg_dump -h $DbHost -p $DbPort -U $DbUser -d $DbName -Fc -Z 6 -f $BackupFile
    if ($LASTEXITCODE -ne 0) {
        throw "pg_dump failed with exit code $LASTEXITCODE"
    }

    # Generate SHA-256 checksum
    $HashResult = Get-FileHash -Path $BackupFile -Algorithm SHA256
    $HashValue = $HashResult.Hash.ToLower()
    $HashValue | Out-File -FilePath $ChecksumFile -Encoding ascii -NoNewline

    $Item = Get-Item $BackupFile
    $SizeMB = [math]::Round($Item.Length / 1MB, 2)

    Write-Host "[OK] Backup successfully generated:" -ForegroundColor Green
    Write-Host "     File:     $BackupFile ($SizeMB MB)"
    Write-Host "     SHA-256:  $HashValue"

    # Prune archives older than RetentionDays
    $CutoffDate = (Get-Date).AddDays(-$RetentionDays)
    $OldFiles = Get-ChildItem -Path $BackupDir -Filter "${DbName}_*.dump*" | Where-Object { $_.LastWriteTime -lt $CutoffDate }
    foreach ($File in $OldFiles) {
        Remove-Item -Path $File.FullName -Force
        Write-Host "     Pruned old backup: $($File.Name)" -ForegroundColor DarkGray
    }
}
finally {
    if ($env:PGPASSWORD) {
        Remove-Item env:PGPASSWORD -ErrorAction SilentlyContinue
    }
}
