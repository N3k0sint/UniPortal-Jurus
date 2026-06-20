#!/bin/bash

# ==============================================================================
# UniKL PJ Collaboration Portal - Disaster Crash Simulation Utility
# Must be run as root (sudo ./simulate_crash.sh)
# ==============================================================================

if [ "$EUID" -ne 0 ]; then
  echo "[-] ERROR: This script must be run as root. Please run with sudo."
  exit 1
fi

echo "[!] WARNING: This will drop the production database and wipe out all uploaded proposals!"
echo -n "[?] Are you sure you want to simulate a total system crash? (yes/no): "
read RESPONSE

if [ "$RESPONSE" != "yes" ]; then
    echo "[+] Operation cancelled."
    exit 0
fi

echo "[+] Simulating crash..."
echo "[+] Stopping UniKL PJ Web Portal..."
systemctl stop uniklpj

echo "[+] Dropping PostgreSQL Database 'uniklpj_db'..."
sudo -u postgres psql -c "DROP DATABASE IF EXISTS uniklpj_db;"

echo "[+] Deleting all uploaded proposal files..."
rm -rf /var/www/uniklpj_uploads/*

# Start the portal (which will fail to load projects/DB and raise errors/500, simulating failure)
echo "[+] Starting Web Portal in corrupted state (will crash/raise errors)..."
systemctl start uniklpj

echo "[!] CRASH SIMULATION COMPLETE."
echo "[!] The database is dropped and uploads are wiped. Check the browser: you will see errors."
echo "[*] Run 'sudo ./restore.sh' to recover the system."
