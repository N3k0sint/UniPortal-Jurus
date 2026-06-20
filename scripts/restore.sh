#!/bin/bash

# ==============================================================================
# UniKL PJ Collaboration Portal - Disaster Recovery Restore Script (RTO)
# Must be run as root (sudo ./restore.sh)
# ==============================================================================

# Ensure script is run as root
if [ "$EUID" -ne 0 ]; then
  echo "[-] ERROR: This script must be run as root. Please run with sudo."
  exit 1
fi

BACKUP_DIR="/var/backups/uniklpj"
TEMP_DIR="/tmp/uniklpj_restore_tmp"
UPLOAD_DIR="/var/www/uniklpj_uploads"
DB_NAME="uniklpj_db"
DB_USER="portal_user"

# Find latest backup file
LATEST_BACKUP=$(ls -t "$BACKUP_DIR"/uniklpj_backup_*.tar.gz.gpg 2>/dev/null | head -n 1)

if [ -z "$LATEST_BACKUP" ]; then
    echo "[-] ERROR: No backup files found in $BACKUP_DIR"
    exit 1
fi

echo "[+] Latest backup archive detected: $LATEST_BACKUP"
echo -n "[?] Enter GPG Decryption Passphrase: "
read -s PASSPHRASE
echo ""

if [ -z "$PASSPHRASE" ]; then
    echo "[-] ERROR: Passphrase cannot be empty."
    exit 1
fi

# Start stopwatch for RTO measurement
START_TIME=$(date +%s)

echo "[+] Starting Disaster Recovery restore operation..."

# Stop portal background service to prevent active connections
echo "[+] Stopping UniKL PJ Portal web service..."
systemctl stop uniklpj

# Setup clean workspace
rm -rf "$TEMP_DIR"
mkdir -p "$TEMP_DIR"

# 1. Decrypt GPG symmetric archive
echo "[+] Decrypting backup file..."
gpg --batch --passphrase "$PASSPHRASE" --decrypt -o "$TEMP_DIR/archive.tar.gz" "$LATEST_BACKUP"

if [ $? -ne 0 ]; then
    echo "[-] ERROR: Decryption failed. Incorrect passphrase or corrupted backup."
    rm -rf "$TEMP_DIR"
    systemctl start uniklpj
    exit 1
fi

# 2. Extract files
echo "[+] Extracting archive archive files..."
tar -xzf "$TEMP_DIR/archive.tar.gz" -C "$TEMP_DIR"

# 3. Restore uploaded proposals
echo "[+] Restoring uploaded files..."
rm -rf "$UPLOAD_DIR"
cp -r "$TEMP_DIR/uploads" "$UPLOAD_DIR"
chown -R jurus:www-data "$UPLOAD_DIR"
chmod 770 "$UPLOAD_DIR"

# 4. Restore PostgreSQL Database
echo "[+] Recreating database schema..."
# Drop and recreate db to clear current data
sudo -u postgres psql -c "DROP DATABASE IF EXISTS $DB_NAME;"
sudo -u postgres psql -c "CREATE DATABASE $DB_NAME OWNER $DB_USER;"
sudo -u postgres psql -d $DB_NAME -c "GRANT ALL ON SCHEMA public TO $DB_USER;"

echo "[+] Restoring database dump..."
export PGPASSWORD="PortalSecure@2026!"
pg_restore -h localhost -U "$DB_USER" -d "$DB_NAME" -v "$TEMP_DIR/db_dump.dump" 2>/dev/null

if [ $? -ne 0 ]; then
    echo "[!] Warning: pg_restore reported warnings/errors. Attempting postgres administrator override..."
    sudo -u postgres pg_restore -d "$DB_NAME" -v "$TEMP_DIR/db_dump.dump"
fi

# 5. Bring server back online
echo "[+] Restarting Web Portal service..."
systemctl start uniklpj

# Clean up workspace
rm -rf "$TEMP_DIR"

# Stop stopwatch and calculate RTO
END_TIME=$(date +%s)
ELAPSED=$((END_TIME - START_TIME))

echo "[+] SUCCESS: System restored to normal operational parameters."
echo "[*] Total Recovery Time (RTO): ${ELAPSED} seconds."
EOF
