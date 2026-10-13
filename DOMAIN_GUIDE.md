# 🌐 FitPulse Pro — Complete Domain, SSL & Production Deployment Guide

This guide explains how to connect your own domain (e.g., `fitpulse.app`, `yourfitness.com`, or `app.yourdomain.com`) to the FitPulse Pro platform, set up free automated SSL certificates, and configure live public URLs.

---

## ⚡ Quick Start: 3 Ways to Deploy Your Domain

| Method | Best For | SSL Setup | Time |
|---|---|---|---|
| **Option 1: Free Cloud Hosting (Render / Railway / Vercel)** | Easiest zero-maintenance cloud deploy | Automatic 1-Click | ~3 minutes |
| **Option 2: Custom VPS (Ubuntu / Debian / AWS / DigitalOcean)** | Complete control & self-hosting | Let's Encrypt / Certbot | ~5 minutes |
| **Option 3: Instant Public Tunnel (Cloudflare Quick Tunnel / ngrok)** | Instant live testing & client demo | Pre-configured HTTPS | ~30 seconds |

---

## 🛠️ Method 1: Cloud Deployment with Custom Domain

### A. Deploy to Render.com (Recommended Free/Low-Cost)
1. Push this repository to GitHub or GitLab.
2. In [Render Dashboard](https://dashboard.render.com), click **New +** → **Web Service**.
3. Connect your repository.
4. Render automatically detects `render.yaml` or use these settings:
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn -w 4 -b 0.0.0.0:$PORT server:app`
5. **Connect Custom Domain**:
   - In your Render Web Service settings, go to **Custom Domains**.
   - Enter your domain (e.g., `app.yourfitness.com` or `yourfitness.com`).
   - Render gives you a DNS target (e.g., `fitpulse-pro.onrender.com`).
   - Add the CNAME record in your registrar (see DNS table below).
   - Render automatically provisions a free Let's Encrypt SSL certificate!

### B. Deploy to Railway.app
1. Go to [Railway.app](https://railway.app) → **New Project** → **Deploy from GitHub repo**.
2. Railway will read `Procfile` and start `python server.py`.
3. In **Settings** → **Networking** → Click **Custom Domain**.
4. Enter your domain and point your DNS CNAME to the Railway domain target.

---

## 🏢 Method 2: Custom VPS Setup (Nginx + Let's Encrypt)

If you are running FitPulse on an Ubuntu/Debian VPS (AWS EC2, DigitalOcean Droplet, Linode, Hetzner, etc.):

### Step 1: Run Domain Setup CLI
FitPulse includes an automated configuration generator:
```bash
python deploy/domain_setup.py --domain yourfitness.com
```
This automatically verifies DNS resolution and writes tailored configs to:
- `deploy/nginx.conf`
- `deploy/Caddyfile`

### Step 2: Configure DNS Records
Log in to your domain registrar (Cloudflare, GoDaddy, Namecheap, Hostinger, etc.):

| Type | Name / Host | Target / Value | TTL |
|---|---|---|---|
| **A** | `@` (or apex) | `YOUR_SERVER_PUBLIC_IP` | 300 (or Auto) |
| **CNAME** | `www` | `yourfitness.com` | 300 (or Auto) |

*(If using a subdomain like `app.yourfitness.com`, add a CNAME record with Host `app` pointing to your server/host)*

### Step 3: Install Nginx & Certbot on VPS
```bash
sudo apt update
sudo apt install -y nginx certbot python3-certbot-nginx
```

### Step 4: Link Nginx Configuration
```bash
sudo cp deploy/nginx.conf /etc/nginx/sites-available/fitpulse
sudo ln -s /etc/nginx/sites-available/fitpulse /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### Step 5: Issue Free SSL Certificate (HTTPS)
```bash
sudo certbot --nginx -d yourfitness.com -d www.yourfitness.com
```
Certbot will obtain the certificate from Let's Encrypt and automatically set up automated 90-day renewal cron tasks!

---

## 🚀 Method 3: Instant Live Public URL (For Client Demos Right Now)

If you want to share a live, secure HTTPS URL of FitPulse running on your machine with a client or test it on your mobile phone without buying a domain:

### Cloudflare Quick Tunnel (Free, No Account Needed)
1. Download Cloudflare Tunnel CLI (`cloudflared`).
2. Run:
   ```bash
   cloudflared tunnel --url http://localhost:5000
   ```
3. Cloudflare gives you an instant public URL:
   `https://random-words.trycloudflare.com`
   Any mobile phone or client can open this URL directly and test FitPulse!

---

## 🔒 Production Security & Environment Variables

When deploying to a public domain, ensure your `.env` contains:

```ini
# Domain configuration
DOMAIN_NAME=yourfitness.com
FRONTEND_URL=https://yourfitness.com
FLASK_ENV=production
FLASK_SECRET_KEY=your_secure_64_char_random_hex_key

# Payment Gateways (Use live keys in production)
RAZORPAY_KEY_ID=rzp_live_xxxxxxxx
RAZORPAY_KEY_SECRET=xxxxxxxxxxxxxxxxxxxx
RAZORPAY_WEBHOOK_SECRET=xxxxxxxxxxxxxxxxxxxx

# Or Stripe (for international payments)
STRIPE_SECRET_KEY=sk_live_xxxxxxxx
STRIPE_PUBLISHABLE_KEY=pk_live_xxxxxxxx

# Live AI Coach (OpenAI or Gemini or Groq)
OPENAI_API_KEY=sk-proj-xxxxxxxx
OPENAI_MODEL=gpt-4o-mini
# Or:
# GEMINI_API_KEY=AIzaxxxxxxxx
# GROQ_API_KEY=gsk_xxxxxxxx
```

---

## 🩺 Verifying Your Deployment Health

FitPulse provides automated health check endpoints for uptime monitors (UptimeRobot, BetterStack, Datadog):

- **Health Check URL**: `https://yourdomain.com/api/health` or `/health`
- **Response**:
```json
{
  "status": "healthy",
  "uptimeSeconds": 1420,
  "database": "connected",
  "domain": "yourfitness.com",
  "version": "2.1.0",
  "environment": "production",
  "gateways": {
    "razorpay": true,
    "stripe": true
  },
  "ai": {
    "provider": "openai",
    "live": true
  }
}
```
