# 🚀 FitPulse Pro / FitPlus — Production Deployment Guide

A complete, production-ready guide to deploying, configuring, securing, and maintaining the FitPulse Pro full-stack fitness platform for real-world commercial operations.

---

## 1. Project Architecture

* **Frontend:** Responsive Multi-Page Web Architecture (HTML5, Vanilla CSS Design System, Vanilla JavaScript). Zero heavy client build dependencies; maximum performance, fast first-contentful paint, and low latency across mobile, tablet, and desktop devices.
* **Backend:** Python 3.10+ / Flask Application with WSGI compatibility (Gunicorn for Linux / Waitress for Windows).
* **Database:** SQLite 3 with Write-Ahead Logging (`WAL` mode) and multi-table normalized schema (Users, Profiles, Nutrition Logs, Workouts, Payments, Orders, Support Tickets, Contact Enquiries, Admin Logs).
* **Authentication:** Multi-round cryptographic hashing (`bcrypt` or Werkzeug `scrypt`), secure 256-bit hex session tokens, `HttpOnly` and `SameSite=Lax` cookie flags, server-side authorization enforcement.
* **Payments:** Razorpay (India: Cards, UPI, NetBanking) and Stripe (International cards, Checkout sessions) with server-side HMAC-SHA256 signature and webhook verification.
* **AI Coach:** Multi-model routing engine supporting Groq (`llama-3.3-70b`), Google Gemini (`gemini-1.5-flash`), OpenAI (`gpt-4o-mini`), Anthropic Claude, and built-in heuristic nutrition/workout reasoning engine.
* **Email:** Transactional email delivery engine with SMTP and SendGrid integrations for password resets, payment receipts, and contact notifications.

---

## 2. Prerequisites

* **Server:** Linux VPS (Ubuntu 22.04 LTS / Debian 12 recommended) with minimum 1 CPU, 1 GB RAM, 20 GB SSD/NVMe disk.
* **Runtime:** Python 3.10 or higher, `pip`, `python3-venv`.
* **Reverse Proxy:** Nginx or Caddy.
* **Process Manager:** `systemd` or Docker.
* **Domain:** A registered custom domain (e.g. `yourfitness.com`).
* **Payment Credentials:** Razorpay Merchant Account (Live/Test keys).
* **Email Credentials:** SMTP server (Google Workspace App Password, SendGrid, Amazon SES, or Brevo).

---

## 3. Local Development Setup

```bash
# 1. Clone or navigate to the repository
cd fitpulse-pro-main

# 2. Create and activate a Python virtual environment
python -m venv venv
# On Windows:
venv\Scripts\activate
# On Linux/macOS:
source venv/bin/activate

# 3. Install required dependencies
pip install -r requirements.txt

# 4. Copy environment configuration
cp .env.example .env

# 5. Run automated test suite
python test_server.py

# 6. Start the development server
python server.py
```
Open [http://localhost:5000/fitpulse/index.html](http://localhost:5000/fitpulse/index.html) in your browser.

---

## 4. Environment-Variable Reference

Create `.env` in the project root with the following production values:

| Variable | Required in Prod? | Description | Example / Recommendation |
| :--- | :---: | :--- | :--- |
| `FLASK_SECRET_KEY` | **YES** | 64-char random hex key for session signing | `python -c "import secrets; print(secrets.token_hex(32))"` |
| `FLASK_ENV` | **YES** | Environment mode | `production` (enables secure cookies, disables dev token leaks) |
| `PORT` | Optional | Web server listen port | `5000` |
| `DATABASE_PATH` | Optional | Absolute or relative path to database | `fitpulse.db` |
| `DOMAIN_NAME` | **YES** | Primary production domain | `fitpulse.app` or `yourdomain.com` |
| `FRONTEND_URL` | **YES** | Public base URL used in emails/links | `https://yourdomain.com` |
| `CORS_ORIGINS` | **YES** | Allowed CORS origins (comma-separated) | `https://yourdomain.com,https://www.yourdomain.com` |
| `ADMIN_EMAIL` | **YES** | Initial administrator email | `admin@yourdomain.com` |
| `ADMIN_PASSWORD` | **YES** | Strong administrator password | Random 16+ character password |
| `ADMIN_NAME` | Optional | Administrator display name | `Platform Administrator` |
| `RAZORPAY_KEY_ID` | For Payments | Razorpay Live Key ID | `rzp_live_...` |
| `RAZORPAY_KEY_SECRET` | For Payments | Razorpay Live Secret Key | Never share or commit to Git |
| `RAZORPAY_WEBHOOK_SECRET` | For Webhooks | Razorpay Webhook Secret | Configured in Razorpay Webhooks tab |
| `STRIPE_SECRET_KEY` | Optional | Stripe Secret Key | `sk_live_...` |
| `STRIPE_PUBLISHABLE_KEY` | Optional | Stripe Publishable Key | `pk_live_...` |
| `EMAIL_PROVIDER` | Optional | Email mode | `smtp` or `sendgrid` |
| `SMTP_HOST` | For Email | SMTP mail server hostname | `smtp.gmail.com` or `smtp.sendgrid.net` |
| `SMTP_PORT` | For Email | SMTP server port | `587` (TLS) or `465` (SSL) |
| `SMTP_USER` | For Email | SMTP authenticated username | `noreply@yourdomain.com` |
| `SMTP_PASSWORD` | For Email | SMTP password or app password | App-specific password |
| `SMTP_FROM_NAME` | For Email | Sender display name | `FitPulse Support` |
| `SMTP_FROM_EMAIL` | For Email | Sender address | `noreply@yourdomain.com` |
| `GROQ_API_KEY` | For AI Coach | Groq fast LLM API key | Generous free tier at console.groq.com |
| `GEMINI_API_KEY` | For AI Coach | Google Gemini API key | Google AI Studio |
| `OPENAI_API_KEY` | For AI Coach | OpenAI API key | platform.openai.com |

---

## 5. Database Setup & Migrations

FitPulse Pro initializes its database schema automatically on boot through `init_db()` in `server.py`.

* **Initialization:** Simply starting the application creates `fitpulse.db` with all primary tables and performance indexes (`users`, `profiles`, `nutrition_logs`, `workouts`, `payments`, `orders`, `tickets`, `contact_enquiries`, `admin_logs`).
* **Concurrency:** The database enables `PRAGMA journal_mode=WAL` (Write-Ahead Logging) and `PRAGMA foreign_keys=ON`, allowing concurrent readers without blocking writes.
* **Schema Updates:** To apply custom SQL schema changes in production:
  ```bash
  sqlite3 fitpulse.db "ALTER TABLE users ADD COLUMN phone TEXT;"
  ```

---

## 6. Production Build & Execution Commands

In production on Linux, **do not** use `python server.py` directly. Run with Gunicorn WSGI:

```bash
# Start Gunicorn with 4 worker processes bound to localhost port 5000
gunicorn -w 4 -b 127.0.0.1:5000 --timeout 60 --access-logfile - --error-logfile - server:app
```

---

## 7. Hosting Configuration (VPS with Systemd & Nginx)

### A. Create a Systemd Service
Create `/etc/systemd/system/fitpulse.service`:
```ini
[Unit]
Description=FitPulse Pro Full-Stack Application
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory=/var/www/fitpulse/fitpulse-pro-main
Environment="PATH=/var/www/fitpulse/venv/bin"
ExecStart=/var/www/fitpulse/venv/bin/gunicorn -w 4 -b 127.0.0.1:5000 --timeout 60 server:app
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```
Enable and start the service:
```bash
sudo systemctl daemon-reload
sudo systemctl enable fitpulse
sudo systemctl start fitpulse
```

### B. Configure Nginx Reverse Proxy
Copy the included `deploy/nginx.conf` or create `/etc/nginx/sites-available/fitpulse`:
```nginx
server {
    listen 80;
    server_name yourdomain.com www.yourdomain.com;

    client_max_body_size 16M;

    # Static assets caching
    location /css/ {
        alias /var/www/fitpulse/fitpulse-pro-main/public/fitpulse/css/;
        expires 30d;
        add_header Cache-Control "public, no-transform";
    }

    location /js/ {
        alias /var/www/fitpulse/fitpulse-pro-main/public/fitpulse/js/;
        expires 7d;
        add_header Cache-Control "public, no-transform";
    }

    # Proxy all traffic to Gunicorn
    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```
Link and test Nginx:
```bash
sudo ln -s /etc/nginx/sites-available/fitpulse /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

---

## 8. Domain & SSL Setup (HTTPS)

1. **DNS Records:** In your domain registrar (Cloudflare, Namecheap, GoDaddy):
   * `A` record: `@` pointing to your VPS public IPv4 address.
   * `CNAME` record: `www` pointing to `yourdomain.com`.
2. **Issue Free Automated SSL Certificate:**
   ```bash
   sudo apt install -y certbot python3-certbot-nginx
   sudo certbot --nginx -d yourdomain.com -d www.yourdomain.com
   ```
Certbot will configure HTTPS certificates and auto-renewal cron tasks.

---

## 9. Payment Gateway Configuration (Razorpay)

1. Log in to [Razorpay Dashboard](https://dashboard.razorpay.com).
2. Complete KYC and business verification (PAN, bank account, business details).
3. Navigate to **Settings** → **API Keys** → Generate **Live Keys**.
4. Set `RAZORPAY_KEY_ID` and `RAZORPAY_KEY_SECRET` in `.env`.
5. In production (`FLASK_ENV=production`), simulated/demo payments are strictly blocked to prevent unauthorized access.

---

## 10. Webhook Configuration

1. In Razorpay Dashboard, go to **Settings** → **Webhooks** → **Add New Webhook**.
2. **Webhook URL:** `https://yourdomain.com/api/payments/webhook`
3. **Secret:** Generate a secret string and place it in `.env` under `RAZORPAY_WEBHOOK_SECRET`.
4. **Active Events:** Check:
   * `order.paid`
   * `payment.captured`
   * `payment.failed`
5. Save Webhook.

---

## 11. Email Service Configuration

1. **Using Gmail / Google Workspace:**
   * Enable 2-Step Verification on your sender account.
   * Generate an **App Password** (16 characters).
   * In `.env`:
     ```env
     EMAIL_PROVIDER=smtp
     SMTP_HOST=smtp.gmail.com
     SMTP_PORT=587
     SMTP_USER=you@yourdomain.com
     SMTP_PASSWORD=your-app-password
     SMTP_FROM_EMAIL=you@yourdomain.com
     SMTP_FROM_NAME=FitPulse Pro
     ```
2. **Using SendGrid / Amazon SES:**
   * Set `SMTP_HOST=smtp.sendgrid.net` and `SMTP_USER=apikey`.
   * Set `SMTP_PASSWORD=your_sendgrid_api_key`.

---

## 12. Admin Account Setup

* In `.env`, set:
  ```env
  ADMIN_EMAIL=your-real-admin@yourdomain.com
  ADMIN_PASSWORD=YourStrongUniquePassword123!
  ADMIN_NAME=Head Administrator
  ```
* On initial launch, the system automatically creates the admin account.
* Log in via `https://yourdomain.com/fitpulse/login.html` and access the Admin Overview at `https://yourdomain.com/fitpulse/admin.html`.

---

## 13. Testing Instructions

Run the automated test suite locally or on the staging server:
```bash
python test_server.py
```
This tests:
* Static pages delivery (30 HTML pages + legal policies + error handlers).
* User registration and password hashing.
* Admin login and authorization enforcement.
* Nutrition, hydration, sleep, habits, workouts tracking.
* AI coach context reasoning.
* Support tickets creation and member reply flows.
* Contact inquiries persistence and admin viewing.
* User orders and invoice history.
* Stripe and Razorpay order session creation.
* Health check and configuration endpoints.
* Custom 404 / 500 handlers.

---

## 14. Backup & Recovery Recommendations

Because SQLite stores all data in `fitpulse.db`, backups are simple and atomic:

1. **Daily SQLite Backup Script:**
   Create `/var/www/fitpulse/backup.sh`:
   ```bash
   #!/bin/bash
   BACKUP_DIR="/var/backups/fitpulse"
   mkdir -p $BACKUP_DIR
   DATE=$(date +%Y%m%d_%H%M%S)
   sqlite3 /var/www/fitpulse/fitpulse-pro-main/fitpulse.db ".backup $BACKUP_DIR/fitpulse_$DATE.db"
   # Keep last 14 days
   find $BACKUP_DIR -name "fitpulse_*.db" -mtime +14 -delete
   ```
2. **Automate via Cron:**
   ```bash
   0 3 * * * /bin/bash /var/www/fitpulse/backup.sh
   ```
3. Optional: Sync `$BACKUP_DIR` to AWS S3, Cloudflare R2, or Google Cloud Storage using `rclone`.

---

## 15. Troubleshooting Instructions

* **Issue: "502 Bad Gateway" on Nginx**
  * Check if Gunicorn is running: `sudo systemctl status fitpulse`
  * Inspect application logs: `sudo journalctl -u fitpulse -n 50 --no-pager`
* **Issue: Payment Modal does not open on checkout**
  * Verify `RAZORPAY_KEY_ID` in `.env`.
  * Ensure Content Security Policy allows `https://checkout.razorpay.com` (already included in `server.py`).
* **Issue: Password reset email not arriving**
  * Verify `SMTP_HOST`, `SMTP_PORT`, and credentials in `.env`.
  * In development mode, check terminal output for the reset URL fallback.
* **Issue: Database locked error under high concurrency**
  * Ensure `fitpulse.db` has WAL mode enabled (`PRAGMA journal_mode=WAL;`), which is enabled by default in `server.py`.

---

## 16. Final Pre-Launch Checklist

- [ ] `.env` file created with static `FLASK_SECRET_KEY` (never default).
- [ ] `FLASK_ENV=production` set.
- [ ] Strong custom `ADMIN_PASSWORD` configured.
- [ ] Custom domain DNS records (`A` and `CNAME`) pointing to server IP.
- [ ] SSL certificate active (`https://` padlock visible in browser).
- [ ] Razorpay Live Key ID and Secret configured in `.env`.
- [ ] Razorpay Webhook configured at `/api/payments/webhook`.
- [ ] SMTP email credentials configured and tested with forgot-password flow.
- [ ] Legal pages verified: Terms of Service, Privacy Policy, Cancellation & Refund Policy.
- [ ] Automated backup cron job configured.
- [ ] `test_server.py` ran with 100% passing tests.
