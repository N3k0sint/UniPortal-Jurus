# UniKL PJ Research Collaboration Portal

The **UniKL PJ Research Collaboration Portal** (Universiti Kuala Lumpur Petaling Jaya) is a secure, production-ready web platform developed for the **JURUS Level 1 (Analyst) Cyber Engineering Challenge**. 

This system enables researchers, administrators, and collaborators to securely share project details, submit research proposals, manage collaboration requests, and review administrative audit logs.

---

## 🔒 Implemented Security Hardening

This project implements robust defense-in-depth measures based on the **JURUS Analyst Rubric** and the **Secure Coding Implementation Guide**:

### 1. Secure Coding (OWASP ASVS Controls)
* **Input Validation (WTForms)**: Strict alphanumeric input whitelisting for usernames, and sanitization of form parameters.
* **SQL Injection Defenses**: Enforced parameterized queries via the SQLAlchemy Object-Relational Mapper (ORM) exclusively.
* **Access Control (RBAC)**: Endpoint security decorators restrict page access based on user security roles (**Admin**, **Researcher**, **Collaborator**).
* **IDOR Prevention**: Application logic validates user identity from the active session directly rather than accepting parameter IDs, preventing IDOR tampering on profiles.
* **Administrative Lockout & Self-Demotion Prevention**: Enforces a strict minimum of **one active administrator** in the system. Uses SQL row-level locking (`with_for_update()`) to prevent race conditions (such as concurrent mutual demotions or deletions between multiple administrators) that could result in zero administrators.
* **Sensitive Data Protection**: Passwords are hashed using `bcrypt` (adaptive hashing). Traceback stack leaks are disabled on error handlers (custom 400, 403, 404, 500 error pages).
* **Secure File Upload**:
  * Files are restricted strictly to the `.pdf` extension.
  * Deep packet inspection validates file content signatures (`python-magic`/`libmagic`) to block masquerading executable scripts.
  * Files are renamed on write to random UUIDs (preventing traversal and resource sniffing).
  * Storage is isolated outside the web directory (`/var/www/uniklpj_uploads/`) to prevent remote code execution (RCE).
* **Web Session Hardening**: Enforces CSRF token injection on forms. Cookies are configured with `HttpOnly`, `Secure`, and `SameSite=Strict`. Enforces a strict 1-hour session timeout.

### 2. Operating System & Network Hardening
* **Firewall Configuration (UFW)**: Default-deny inbound policy. Opens HTTP (80 - redirects to HTTPS), HTTPS (443), and custom SSH (2222).
* **SSH Hardening**: Custom port 2222, disabled root login (`PermitRootLogin no`), disabled password authentication (RSA SSH-key access only), and strict request rate throttling (`MaxAuthTries 3`).
* **Web Server Hardening (Nginx)**: Hides version tokens (`server_tokens off;`), enforces **TLS 1.3 only**, and injects secure headers (`Content-Security-Policy`, `X-Frame-Options`, `X-Content-Type-Options`).
* **Active Defense (Fail2ban)**: Monitors SSH on port 2222 and Nginx access logs to dynamically block malicious IPs via iptables for 30 minutes after 5 failures.

### 3. Business Continuity (BCP/DR)
* **Automated Encrypted Backups**: Daily Cron script (`backup.sh`) dumps the database, packages uploaded files, encrypts the archive via GPG symmetric AES-256, and purges logs older than 7 days.
* **Disaster Recovery Restore Utility**: Recovery script (`restore.sh`) drops tables, rebuilds databases, reinstates files, and logs the elapsed Recovery Time Objective (RTO).

---

## 🚀 How to Run, Start, and Restart the Server

If you are coming from JavaScript/Node.js, here is how python/Flask commands map to what you know:
* **Development Mode** (equivalent to `npm run dev` / hot-reloading)
* **Production Mode** (equivalent to `npm start` / runs in background)

### Lifecycle Command Comparison Table

| Operational Action | Development Mode (`npm run dev`) | Production Mode (`npm start`) |
| :--- | :--- | :--- |
| **Start Server** | `flask run --debug` | `sudo systemctl start uniklpj` |
| **Stop Server** | Press `Ctrl + C` in terminal | `sudo systemctl stop uniklpj` |
| **Restart Server** | Auto-restarts on code save | `sudo systemctl restart uniklpj` |
| **Check Logs/Status** | Output prints directly in terminal | `sudo systemctl status uniklpj` <br> `sudo journalctl -u uniklpj -f` |

---

## 🛠️ Step-by-Step Execution Guide

### 1. Running in Development Mode (For Code Modifications)
Use this when you are editing code and want the server to auto-reload instantly:
```bash
cd /home/jurus/Documents/Project/UniPortal-Jurus/
source venv/bin/activate
export FLASK_APP=wsgi.py
export FLASK_ENV=development
export FLASK_DEBUG=True
flask run --host=127.0.0.1 --port=5000
```
*Access the site at `http://127.0.0.1:5000`.*

### 2. Running in Production Mode (For Hardening & Pentests)
Use this when you want the server to run continuously in the background like a real internet server:
```bash
# 1. Run the system setup script once to install and configure:
sudo ./scripts/setup_system.sh

# 2. Manage the daemon service:
sudo systemctl start uniklpj       # Start server in background
sudo systemctl restart uniklpj     # Restart server (after code updates)
sudo systemctl stop uniklpj        # Stop server
```
*Access the secure site at `https://localhost`.*

---

## 🛠️ Port & Access Reference
* **Secure URL**: `https://localhost` (proxied by Nginx to loopback Gunicorn port 5000)
* **Secure SSH Port**: `2222`
* **Default Database URL**: `postgresql://portal_user:PortalSecure@2026!@localhost/uniklpj_db`
* **Seeded Admin Account**:
  * **Username**: `admin`
  * **Password**: `UniKL@PJ2026!`
