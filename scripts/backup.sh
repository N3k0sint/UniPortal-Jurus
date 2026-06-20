#!/bin/bash

# ==============================================================================
# UniKL PJ Collaboration Portal - BCP Encryption Backup Script (RPO)
# Designed for automated execution via Cron Job
# ==============================================================================

# Setup Directories and variables
BACKUP_DIR="/var/backups/uniklpj"
UPLOAD_DIR="/var/www/uniklpj_uploads"
TEMP_DIR="/tmp/uniklpj_backup_tmp"
DB_NAME="uniklpj_db"
DB_USER="portal_user"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_NAME="uniklpj_backup_${TIMESTAMP}"

# Load credentials from .env to read passphrase
PROJECT_DIR="/home/jurus/Documents/Project/UniPortal-Jurus"
if [ -f "$PROJECT_DIR/.env" ]; then
    # Source .env safely
    export $(grep -v '^#' "$PROJECT_DIR/.env" | xargs)
fi

# Fallback pass if not defined in .env
PASSPHRASE=${BACKUP_PASSPHRASE:-"UniKLBackupPassphrase2026!"}

echo "[+] Starting automated security backup at $(date)"

# Ensure backup directory exists
mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"

# Create clean temp workspace
rm -rf "$TEMP_DIR"
mkdir -p "$TEMP_DIR"

# 1. Execute PostgreSQL Database Dump (using pg_dump)
echo "[+] Dumping PostgreSQL database..."
# Run pg_dump as pg user or via local connection. We use password from PGPASSWORD if needed,
# but since local Unix socket is peer-authorized for postgres, we run as postgres or supply password
export PGPASSWORD="PortalSecure@2026!"
pg_dump -h localhost -U "$DB_USER" -F c -b -v -f "$TEMP_DIR/db_dump.dump" "$DB_NAME" 2>/dev/null

if [ $? -ne 0 ]; then
    echo "[-] DATABASE DUMP FAILED! Using pg_dump as postgres user fallback..."
    sudo -u postgres pg_dump -F c -b -v -f "$TEMP_DIR/db_dump.dump" "$DB_NAME"
fi

# 2. Package database dump and uploaded proposals
echo "[+] Archiving file resources and database dump..."
cp -r "$UPLOAD_DIR" "$TEMP_DIR/uploads"
tar -czf "$TEMP_DIR/archive.tar.gz" -C "$TEMP_DIR" db_dump.dump uploads

# 3. Encrypt archive with AES-256 (GPG Symmetric Encryption)
echo "[+] Encrypting archive using GPG symmetric AES-256..."
gpg --batch --yes --passphrase "$PASSPHRASE" --symmetric --cipher-algo AES256 -o "$BACKUP_DIR/${BACKUP_NAME}.tar.gz.gpg" "$TEMP_DIR/archive.tar.gz"

# Enforce secure file permissions (Only read/write by root/operator)
chmod 600 "$BACKUP_DIR/${BACKUP_NAME}.tar.gz.gpg"

# Clean up temp files
rm -rf "$TEMP_DIR"

# 4. Enforce 7-day Retention Policy (Delete older backups)
echo "[+] Enforcing 7-day retention policy..."
find "$BACKUP_DIR" -type f -name "uniklpj_backup_*.tar.gz.gpg" -mtime +7 -delete

echo "[+] Backup Completed Successfully: $BACKUP_DIR/${BACKUP_NAME}.tar.gz.gpg"
