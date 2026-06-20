# JURUS Level 1 (Analyst) - UniKL PJ Collaboration Portal Guide

This guide provides step-by-step instructions to run, verify, pentest, and present the **UniKL PJ Research Collaboration Portal**.

---

## 🚀 Lifecycle Mappings: From Node.js/NPM to Python/Flask

If you are used to JavaScript environments (`npm run dev` and `npm start`), here is how the Python backend lifecycle commands map to what you know:

| Command Purpose | Node.js (What you know) | Python/Flask (What we use) |
| :--- | :--- | :--- |
| **Development Server** <br> (Hot-reloading on save) | `npm run dev` | `source venv/bin/activate` <br> `flask run --debug` |
| **Production Server** <br> (Daemon running in background) | `npm start` (with PM2/Forever) | `sudo systemctl start uniklpj` |
| **Restart App Service** | `pm2 restart app` | `sudo systemctl restart uniklpj` |
| **Stop App Service** | `pm2 stop app` | `sudo systemctl stop uniklpj` |
| **Inspect System Logs** | `pm2 logs` | `sudo journalctl -u uniklpj -f` |

---

## 💻 1. Local Development & Debugging

If you are modifying the code or troubleshooting features, run the Flask application in development mode with hot-reloading:

```bash
# 1. Navigate to the project folder
cd /home/jurus/Documents/Project/UniPortal-Jurus/

# 2. Activate the Python virtual environment
source venv/bin/activate

# 3. Set the Flask environment vars (temporary for dev session)
export FLASK_APP=wsgi.py
export FLASK_ENV=development
export FLASK_DEBUG=True

# 4. Run the debug development server
flask run --host=127.0.0.1 --port=5000
```
*Any changes made to the Python code will instantly hot-reload in your browser at `http://127.0.0.1:5000`.*

---

## 🔍 2. Verifying Production Status

After running `./scripts/setup_system.sh`, the server operates in a secure background daemon configuration. Verify the system states using these commands:

### A. Web Application Daemon (systemd)
Check Gunicorn status and live logs:
```bash
sudo systemctl status uniklpj
# View live application logs (standard out and standard error)
sudo journalctl -u uniklpj -f
```

### B. Reverse Proxy (Nginx)
Verify Nginx is listening on HTTPS (443):
```bash
sudo systemctl status nginx
# View Nginx access & error logs
sudo tail -f /var/log/nginx/access.log
sudo tail -f /var/log/nginx/error.log
```

### C. Host Firewall (UFW)
Verify active rules:
```bash
sudo ufw status verbose
```

### D. Active Defense Jail (Fail2ban)
Check banned IP logs:
```bash
sudo fail2ban-client status
sudo fail2ban-client status sshd
sudo fail2ban-client status nginx-http-auth
# View fail2ban logs
sudo tail -f /var/log/fail2ban.log
```

---

## 🛡️ 3. Security Pentesting (From Kali Linux VM)

Set up a Host-Only or NAT network in VMware to connect your Kali Linux VM to the Ubuntu target.

### A. Port Verification (nmap)
Verify that UFW blocks all ports except 80, 443, and 2222:
```bash
nmap -p- -T4 <ubuntu-vm-ip>
```
*Expected: Only ports 80 (HTTP), 443 (HTTPS), and 2222 (Hardened SSH) are open. Port 5432 (PostgreSQL) must be invisible.*

### B. SSL and Headers Scan (nikto)
Test web server banner hiding and security headers:
```bash
nikto -h https://<ubuntu-vm-ip> -ssl
```
*Expected: No Nginx version banner visible. Secure headers (CSP, X-Frame-Options, X-Content-Type-Options) are detected.*

### C. Active Defense Verification (Fail2ban SSH brute force)
To test that Fail2ban bans malicious actors, attempt multiple quick SSH logins using the wrong port or password from Kali:
```bash
# Attempt login 5 times quickly
ssh -p 2222 admin@<ubuntu-vm-ip>
```
*Expected: On the 6th attempt, connection will time out. Check `sudo fail2ban-client status sshd` on the Ubuntu VM to see the Kali VM IP in the Banned list.*

---

## 💾 4. Disaster Recovery (BCP/DR) Drill

To score maximum marks in Module 6 (BCP/DR), you must demonstrate a simulated crash and recovery under pressure during the live demo:

### Step 1: Verify current operational data
Log in to `https://localhost` as `admin`. Submit a test project and upload a dummy PDF document.

### Step 2: Run the automated backup
Run the symmetric GPG encrypted backup script to create a secure point-in-time recovery state:
```bash
sudo ./scripts/backup.sh
```
*Verify that the encrypted backup `uniklpj_backup_[timestamp].tar.gz.gpg` exists in `/var/backups/uniklpj/` with permissions `600`.*

### Step 3: Simulate a total crash
Run the crash utility:
```bash
sudo ./scripts/simulate_crash.sh
```
Type `yes` when prompted. Navigate to the browser. The database is now dropped and all uploaded PDFs are wiped.

### Step 4: Execute Recovery (RTO Measurement)
Execute the restore utility:
```bash
sudo ./scripts/restore.sh
```
Enter the GPG passphrase (`UniKLBackupPassphrase2026!` or your custom secret).
*Expected: The script restores Nginx, drops/rebuilds PostgreSQL tables, extracts files, and restarts Gunicorn. It will print the exact elapsed RTO recovery time (target: <5 minutes, actual: ~10 seconds).*

---

## 🎤 5. Slide-by-Slide Live Defense Strategy (30 Mins)

Prepare your slides and structure your live demonstration exactly like this:

| Time | Slide/Activity | Key Focus Area | Rubric Mark Alignment |
| :--- | :--- | :--- | :--- |
| **00:00 - 07:00** | **Presentation & Architecture** | Explain your UniKL PJ logical topology. Justify your single-host setup (saving resources on a 4GB VM) and Gunicorn daemon deployment. | **Item 1: Rationale (15%)** |
| **07:00 - 12:00** | **OS & Network Hardening** | Show UFW block rules. Show `/etc/ssh/sshd_config` showing port 2222 and key-auth. Run `nikto` scan to prove Nginx banner is hidden. | **Mod 1 & 2: OS/Net (20%)** |
| **12:00 - 16:00** | **App & DB Lockdown** | Log in to the portal. Demonstrate uploading a `.pdf`. Try to upload a shell script renamed to `.pdf` to show it blocked by python-magic. | **Mod 3 & 4: App/DB (20%)** |
| **16:00 - 20:00** | **Monitoring & Logs** | Show the **Audit Logs** panel inside the portal admin dashboard. Show Fail2ban logs. Trigger a lockout ban using wrong credentials. | **Mod 5: Monitoring (5%)** |
| **20:00 - 25:00** | **Disaster Recovery Drill** | Run `./scripts/simulate_crash.sh` live. Show the error page. Run `./scripts/restore.sh`. Show the app restored and print the RTO metric. | **Mod 6 & Item 3: BCP (15%)** |
| **25:00 - 30:00** | **Q&A Sesi Soal Jawab** | Answer questions using professional cyber engineering concepts (e.g. defense-in-depth, least-privilege, isolation). | **Item 4: Q&A (10%)** |
