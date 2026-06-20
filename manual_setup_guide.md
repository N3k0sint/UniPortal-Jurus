# UniKL PJ Research Collaboration Portal - Manual Setup & Hardening Guide

This document lists every command and configuration edit required to set up your environment manually on your Ubuntu VM. You can copy these commands one-by-one, run them, and capture screenshots for your JURUS project report.

---

## 🛠️ Step 1: Install System Packages
Run this command to update your system repositories and install Nginx (web server), PostgreSQL (database), Fail2ban (intrusion prevention), UFW (firewall), SSH daemon, and PAM/security components:

```bash
sudo apt-get update
sudo apt-get install -y python3-pip python3-venv nginx postgresql postgresql-contrib libmagic1 fail2ban ufw libpam-pwquality openssl openssh-server
```
> **Screenshot opportunity**: Capture the successful installation logs showing packages being installed.

---

## 📂 Step 2: Configure Directory Permissions
Create secure, isolated directories for document storage, custom logging, and static assets, assigning ownership to your administrative user (`jurus`) and web server group (`www-data`):

```bash
# Create directories
sudo mkdir -p /var/www/uniklpj_uploads
sudo mkdir -p /var/log/uniklpj
sudo mkdir -p /var/www/uniklpj/static

# Assign permissions to upload directory
sudo chown -R jurus:www-data /var/www/uniklpj_uploads
sudo chmod 770 /var/www/uniklpj_uploads

# Assign permissions to application logs directory
sudo chown -R jurus:www-data /var/log/uniklpj
sudo chmod 770 /var/log/uniklpj

# Copy static assets to secure web directory and configure permissions
sudo cp -r /home/jurus/Documents/Project/UniPortal-Jurus/uniklpj_portal/static/* /var/www/uniklpj/static/
sudo chown -R jurus:www-data /var/www/uniklpj/static
sudo chmod -R 750 /var/www/uniklpj/static
```
*Verify upload permissions using `ls -ld /var/www/uniklpj_uploads` (should output `drwxrwx--- 2 jurus www-data`).*

---

## 🐍 Step 3: Python Environment Setup
Isolate the web application's dependencies in a Python Virtual Environment (`venv`):

```bash
cd /home/jurus/Documents/Project/UniPortal-Jurus/

# Create the virtual environment
python3 -m venv venv

# Upgrade pip inside venv
./venv/bin/pip install --upgrade pip

# Install requirements
./venv/bin/pip install -r requirements.txt

# Ensure file ownership is clean
sudo chown -R jurus:jurus /home/jurus/Documents/Project/UniPortal-Jurus/
```

---

## 🔑 Step 4: Generate SSL Certificate (TLS 1.3)
Generate a self-signed OpenSSL certificate for the portal (valid for 365 days) and secure the private key:

```bash
# Generate the keys
sudo openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout /etc/ssl/private/uniklpj.key \
  -out /etc/ssl/certs/uniklpj.crt \
  -subj "/C=MY/ST=Selangor/L=Petaling Jaya/O=UniKL PJ/OU=Cybersecurity/CN=localhost"

# Hardened file permissions
sudo chmod 600 /etc/ssl/private/uniklpj.key
sudo chmod 644 /etc/ssl/certs/uniklpj.crt
```

---

## 🔒 Step 5: SSH Daemon Hardening
We will modify `/etc/ssh/sshd_config` to enforce keys only and change the default port.

1. Create a backup first:
   ```bash
   sudo cp /etc/ssh/sshd_config /etc/ssh/sshd_config.bak
   ```
2. Open the file in a terminal editor:
   ```bash
   sudo nano /etc/ssh/sshd_config
   ```
3. Locate or add the following directives (make sure they are not commented out with a `#`):
   ```text
   Port 2222
   PermitRootLogin no
   PasswordAuthentication no
   PubkeyAuthentication yes
   MaxAuthTries 3
   X11Forwarding no
   ```
4. Save and exit (in Nano: press `Ctrl+O`, then `Enter`, then `Ctrl+X`).
5. Restart the SSH daemon to apply:
   ```bash
   sudo systemctl restart ssh
   ```
> **Warning**: Ensure you have copied your client SSH public key (`authorized_keys`) into `/home/jurus/.ssh/` before logging out of this terminal, otherwise password access will be rejected.

---

## 🧱 Step 6: Configure UFW Firewall
Enforce a default-deny rule and open only the necessary ports:

```bash
# Reset UFW to default settings
sudo ufw --force reset

# Set default policies
sudo ufw default deny incoming
sudo ufw default allow outgoing

# Allow specific secure ports
sudo ufw allow 2222/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp

# Enable firewall
sudo ufw --force enable
```
*Verify status using `sudo ufw status verbose`.*

---

## 🔐 Step 7: Configure PAM Password Complexity
Enforce complexity policies for local system accounts:

1. Open the PAM common-password file:
   ```bash
   sudo nano /etc/pam.d/common-password
   ```
2. Locate the line containing `pam_pwquality.so` (usually around line 23):
   ```text
   password        requisite                       pam_pwquality.so retry=3
   ```
3. Edit that line to include the complexity requirements:
   ```text
   password        requisite                       pam_pwquality.so retry=3 minlen=8 ucredit=-1 lcredit=-1 dcredit=-1 ocredit=-1
   ```
   *(This enforces: minimum 8 characters, at least 1 uppercase, 1 lowercase, 1 digit, and 1 special character).*
4. Save and close.

---

## 🗄️ Step 8: Setup PostgreSQL Database
Configure your database and establish user permissions.

1. Ensure the PostgreSQL service is active:
   ```bash
   sudo systemctl start postgresql
   sudo systemctl enable postgresql
   ```
2. Switch to the `postgres` administrator account and launch the SQL terminal:
   ```bash
   sudo -u postgres psql
   ```
3. Execute these SQL statements inside the `psql` terminal one-by-one:
   ```sql
   -- Create database
   CREATE DATABASE uniklpj_db;

   -- Create portal user with secure password
   CREATE USER portal_user WITH ENCRYPTED PASSWORD 'PortalSecure@2026!';

   -- Grant privileges
   GRANT ALL PRIVILEGES ON DATABASE uniklpj_db TO portal_user;
   
   -- Exit the SQL terminal
   \q
   ```
4. Grant schema permissions to the user inside the database:
   ```bash
   sudo -u postgres psql -d uniklpj_db -c "GRANT ALL ON SCHEMA public TO portal_user;"
   ```

---

## ⚡ Step 9: Configure Nginx & Systemd Services

### A. Deploy Systemd Background Service
1. Copy the systemd configuration file:
   ```bash
   sudo cp /home/jurus/Documents/Project/UniPortal-Jurus/uniklpj.service /etc/systemd/system/uniklpj.service
   ```
2. Reload daemon, enable service, and start Gunicorn:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable uniklpj
   sudo systemctl start uniklpj
   ```
*Check status using `sudo systemctl status uniklpj`.*

### B. Configure Nginx Reverse Proxy
1. Copy the Nginx configuration:
   ```bash
   sudo cp /home/jurus/Documents/Project/UniPortal-Jurus/nginx_uniklpj.conf /etc/nginx/sites-available/uniklpj
   ```
2. Enable the site configuration:
   ```bash
   sudo ln -sf /etc/nginx/sites-available/uniklpj /etc/nginx/sites-enabled/
   ```
3. Remove Nginx default index site:
   ```bash
   sudo rm -f /etc/nginx/sites-enabled/default
   ```
4. Verify config and reload Nginx:
   ```bash
   sudo nginx -t
   sudo systemctl restart nginx
   ```
*Open `https://localhost` in the browser to confirm the dashboard renders securely.*

---

## 🚨 Step 10: Configure Fail2ban Jails
Enable Fail2ban active defense.

1. Create a custom jail file:
   ```bash
   sudo nano /etc/fail2ban/jail.d/uniklpj.local
   ```
2. Paste this configuration:
   ```ini
   [sshd]
   enabled = true
   port = 2222
   filter = sshd
   logpath = /var/log/auth.log
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
   ```
3. Save, close, and restart Fail2ban:
   ```bash
   sudo systemctl restart fail2ban
   sudo systemctl enable fail2ban
   ```
*Check active jails with `sudo fail2ban-client status`.*
