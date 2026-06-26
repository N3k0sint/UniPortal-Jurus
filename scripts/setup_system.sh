#!/bin/bash

# ==============================================================================
# UniKL PJ Research Collaboration Portal - OS Hardening & Setup Script
# MUST BE RUN AS ROOT (sudo ./setup_system.sh)
# ==============================================================================

# Ensure script is run as root
if [ "$EUID" -ne 0 ]; then
  echo "[-] ERROR: This script must be run as root. Please run with sudo."
  exit 1
fi

echo "[+] Starting system configuration and security hardening..."

# 1. Install System Dependencies
echo "[+] Installing system packages (Nginx, PostgreSQL, Fail2ban, UFW, PAM, Rsyslog, Logwatch, Logrotate)..."
apt-get update
apt-get install -y python3-pip python3-venv nginx postgresql postgresql-contrib libmagic1 fail2ban ufw libpam-pwquality openssl openssh-server rsyslog logwatch logrotate

# 2. Setup isolated Directory and Permissions for File Uploads and Logs
echo "[+] Configuring directory paths and permissions..."
mkdir -p /var/www/uniklpj_uploads
mkdir -p /var/log/uniklpj
mkdir -p /var/www/uniklpj/static

# Assign ownership to administrator jurus and allow web server group (www-data) read/write
chown -R jurus:www-data /var/www/uniklpj_uploads
chmod 770 /var/www/uniklpj_uploads

chown -R jurus:www-data /var/log/uniklpj
chmod 770 /var/log/uniklpj

# Copy static assets to secure isolated web directory
cp -r /home/jurus/Documents/Project/UniPortal-Jurus/uniklpj_portal/static/* /var/www/uniklpj/static/
chown -R jurus:www-data /var/www/uniklpj/static
chmod -R 750 /var/www/uniklpj/static

# 3. Setup Python Virtual Environment and install packages
echo "[+] Setting up Python virtual environment..."
PROJECT_DIR="/home/jurus/Documents/Project/UniPortal-Jurus"
python3 -m venv "$PROJECT_DIR/venv"
"$PROJECT_DIR/venv/bin/pip" install --upgrade pip
"$PROJECT_DIR/venv/bin/pip" install -r "$PROJECT_DIR/requirements.txt"
chown -R jurus:jurus "$PROJECT_DIR"

# 4. Generate Self-Signed SSL Certificate for TLS 1.3
echo "[+] Generating self-signed SSL Certificate for UniKL PJ Portal (localhost)..."
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout /etc/ssl/private/uniklpj.key \
  -out /etc/ssl/certs/uniklpj.crt \
  -subj "/C=MY/ST=Selangor/L=Petaling Jaya/O=UniKL PJ/OU=Cybersecurity/CN=localhost"
chmod 600 /etc/ssl/private/uniklpj.key
chmod 644 /etc/ssl/certs/uniklpj.crt

# 5. Apply SSH Security Hardening
echo "[+] Applying SSH Daemon security hardening (key-only, port 2222)..."
SSH_CONFIG="/etc/ssh/sshd_config"

# Backup original config
cp "$SSH_CONFIG" "${SSH_CONFIG}.bak"

# Apply hardening via regex
sed -i 's/^#\?Port.*/Port 2222/' "$SSH_CONFIG"
sed -i 's/^#\?PermitRootLogin.*/PermitRootLogin no/' "$SSH_CONFIG"
sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication no/' "$SSH_CONFIG"
sed -i 's/^#\?PubkeyAuthentication.*/PubkeyAuthentication yes/' "$SSH_CONFIG"
sed -i 's/^#\?MaxAuthTries.*/MaxAuthTries 3/' "$SSH_CONFIG"
sed -i 's/^#\?X11Forwarding.*/X11Forwarding no/' "$SSH_CONFIG"

# Restart SSH service
systemctl restart sshd || systemctl restart ssh
echo "[+] SSH Hardening applied on Port 2222."

# 6. Apply Host Firewall (UFW)
echo "[+] Configuring Host Firewall (UFW) rules..."
ufw --force reset
ufw default deny incoming
ufw default allow outgoing
ufw allow 2222/tcp comment 'Hardened SSH'
ufw allow 80/tcp comment 'HTTP Redirect'
ufw allow 443/tcp comment 'HTTPS Portal'
ufw --force enable
echo "[+] UFW Firewall enabled. Allowed Ports: 2222, 80, 443."

# 7. Apply PAM Password Complexity Hardening
echo "[+] Configuring PAM Password Complexity Policy..."
PAM_CONFIG="/etc/pam.d/common-password"
# Configure pam_pwquality to require at least 8 characters, 1 upper, 1 lower, 1 digit, 1 special
if ! grep -q "pam_pwquality.so" "$PAM_CONFIG"; then
  # Insert rule before pam_unix
  sed -i '/pam_unix.so/i password requisite pam_pwquality.so retry=3 minlen=8 ucredit=-1 lcredit=-1 dcredit=-1 ocredit=-1' "$PAM_CONFIG"
else
  # Replace existing pam_pwquality line
  sed -i 's/.*pam_pwquality.so.*/password requisite pam_pwquality.so retry=3 minlen=8 ucredit=-1 lcredit=-1 dcredit=-1 ocredit=-1/' "$PAM_CONFIG"
fi

# 8. Setup PostgreSQL database for production
echo "[+] Initializing PostgreSQL Production Database..."
systemctl start postgresql
systemctl enable postgresql

# Create Database, User, and Grant Privileges (Safe-guarded scripts)
sudo -u postgres psql -c "CREATE DATABASE uniklpj_db;" 2>/dev/null
# Check if user already exists, if not, create it
sudo -u postgres psql -c "DO \$\$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'portal_user') THEN
    CREATE USER portal_user WITH ENCRYPTED PASSWORD 'PortalSecure@2026!';
  END IF;
END
\$\$;"
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE uniklpj_db TO portal_user;"
# Grant schema privileges (PostgreSQL 15+ needs explicit schema grants)
sudo -u postgres psql -d uniklpj_db -c "GRANT ALL ON SCHEMA public TO portal_user;"

# 9. Configure Gunicorn Systemd background service
echo "[+] Deploying Systemd Service Unit..."
cp "$PROJECT_DIR/uniklpj.service" /etc/systemd/system/uniklpj.service
systemctl daemon-reload
systemctl enable uniklpj
systemctl restart uniklpj

# 10. Configure Nginx Reverse Proxy
echo "[+] Configuring Nginx Reverse Proxy..."
cp "$PROJECT_DIR/nginx_uniklpj.conf" /etc/nginx/sites-available/uniklpj
ln -sf /etc/nginx/sites-available/uniklpj /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default

# Verify Nginx and restart
nginx -t && systemctl restart nginx

# 11. Configure Fail2ban Jails
echo "[+] Configuring Fail2ban active defense jails..."
FAIL2BAN_JAIL="/etc/fail2ban/jail.d/uniklpj.local"
cat <<EOF > "$FAIL2BAN_JAIL"
[sshd]
enabled = true
port = 2222
filter = sshd[mode=aggressive]
backend = systemd
journalmatch = _SYSTEMD_UNIT=ssh.service + _COMM=sshd
maxretry = 5
bantime = 1800
findtime = 600

[nginx-http-auth]
enabled = true
filter = nginx-http-auth
port = http,https
logpath = /var/log/nginx/error.log
maxretry = 5
bantime = 1800
findtime = 600
EOF

systemctl restart fail2ban
systemctl enable fail2ban

# 12. Configure Secure Log Rotation for Portal Logs
echo "[+] Configuring secure log rotation for portal audit logs..."
cat <<EOF > /etc/logrotate.d/uniklpj
/var/log/uniklpj/*.log {
    daily
    rotate 7
    compress
    delaycompress
    missingok
    notifempty
    create 0660 jurus www-data
    sharedscripts
    postrotate
        systemctl reload uniklpj >/dev/null 2>&1 || true
    endscript
}
EOF

echo "[+] SYSTEM CONFIGURATION COMPLETE!"
echo "[*] Web Portal is running at: https://localhost"
echo "[*] Default Admin Seeded: username 'admin', password 'UniKL@PJ2026!'"
echo "[*] SSH is listening on Port 2222 (Enforced SSH key-based auth only)."
EOF
