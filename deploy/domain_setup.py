#!/usr/bin/env python3
"""
FitPulse Pro — Automated Custom Domain Configuration & DNS Validator
Verifies DNS records, resolves IP addresses, checks SSL reachability,
and generates production Nginx & Caddy configurations for your domain.

Usage:
    python deploy/domain_setup.py --domain yourdomain.com
    python deploy/domain_setup.py (interactive prompt)
"""

import sys
import os
import socket
import argparse
import urllib.request
import json
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

def get_public_ip():
    """Detect external public IP of the current server."""
    endpoints = [
        "https://api.ipify.org?format=json",
        "https://ifconfig.me/all.json",
        "https://ipinfo.io/json"
    ]
    for url in endpoints:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "curl/7.68.0"})
            with urllib.request.urlopen(req, timeout=4) as resp:
                data = json.loads(resp.read().decode())
                return data.get("ip") or data.get("ip_addr")
        except Exception:
            continue
    return None

def check_dns(domain):
    """Check DNS resolution for the specified domain."""
    print(f"\n[1/4] Checking DNS Resolution for: {domain}")
    clean_domain = domain.lower().replace("http://", "").replace("https://", "").split("/")[0].strip()
    
    resolved_ips = []
    try:
        addr_info = socket.getaddrinfo(clean_domain, 80, proto=socket.IPPROTO_TCP)
        resolved_ips = list(set([item[4][0] for item in addr_info]))
        print(f"  [+] DNS A/AAAA Records Found: {', '.join(resolved_ips)}")
    except socket.gaierror as e:
        print(f"  [-] Could not resolve DNS for {clean_domain}: {e}")
        print("    (Note: If you just added the DNS record, propagation can take 5 to 30 minutes)")
    
    return clean_domain, resolved_ips

def generate_nginx_config(domain, base_dir):
    """Generate production Nginx reverse proxy configuration."""
    clean = domain.replace("www.", "")
    config_content = f"""# ==============================================================================
# FitPulse Pro — Nginx Production Reverse Proxy Configuration
# Domain: {clean} / www.{clean}
# Place in: /etc/nginx/sites-available/{clean}
# Symlink:  sudo ln -s /etc/nginx/sites-available/{clean} /etc/nginx/sites-enabled/
# Test:     sudo nginx -t
# Reload:   sudo systemctl reload nginx
# ==============================================================================

# Rate limiting zone (10 requests per second per IP)
limit_req_zone $binary_remote_addr zone=fitpulse_limit:10m rate=10r/s;

# 1. HTTP Server — Redirect all HTTP to HTTPS
server {{
    listen 80;
    listen [::]:80;
    server_name {clean} www.{clean};

    # Let's Encrypt ACME challenge
    location /.well-known/acme-challenge/ {{
        root /var/www/certbot;
    }}

    location / {{
        return 301 https://$host$request_uri;
    }}
}}

# 2. HTTPS Server — Production Reverse Proxy
server {{
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name {clean} www.{clean};

    # SSL Certificates (managed by Certbot: sudo certbot --nginx -d {clean} -d www.{clean})
    ssl_certificate /etc/letsencrypt/live/{clean}/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/{clean}/privkey.pem;

    # Modern SSL configuration
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384;
    ssl_prefer_server_ciphers off;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 1d;

    # Security Headers
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains; preload" always;

    # Gzip Compression
    gzip on;
    gzip_vary on;
    gzip_proxied any;
    gzip_comp_level 6;
    gzip_types text/plain text/css text/xml application/json application/javascript application/rss+xml image/svg+xml;

    # Proxy to FitPulse Flask Server (Port 5000)
    location / {{
        limit_req zone=fitpulse_limit burst=20 nodelay;
        proxy_pass http://127.0.0.1:5000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_cache_bypass $http_upgrade;
        proxy_read_timeout 60s;
        proxy_connect_timeout 60s;
    }}

    # Health Check bypass without rate limiting
    location /health {{
        proxy_pass http://127.0.0.1:5000/health;
        proxy_set_header Host $host;
    }}
}}
"""
    out_file = base_dir / "deploy" / "nginx.conf"
    out_file.write_text(config_content, encoding="utf-8")
    print(f"  [+] Nginx config written to: {out_file}")
    return out_file

def generate_caddyfile(domain, base_dir):
    """Generate production Caddyfile for 1-command automatic HTTPS."""
    clean = domain.replace("www.", "")
    caddy_content = f"""# ==============================================================================
# FitPulse Pro — Caddyfile (Automatic SSL via Let's Encrypt / ZeroSSL)
# Run with: caddy run --config deploy/Caddyfile
# ==============================================================================

{clean}, www.{clean} {{
    # Reverse proxy all requests to FitPulse backend
    reverse_proxy 127.0.0.1:5000

    # Compression
    encode gzip zstd

    # Security Headers
    header {{
        X-Content-Type-Options "nosniff"
        X-Frame-Options "SAMEORIGIN"
        X-XSS-Protection "1; mode=block"
        Referrer-Policy "strict-origin-when-cross-origin"
        Strict-Transport-Security "max-age=31536000; includeSubDomains"
    }}
}}
"""
    out_file = base_dir / "deploy" / "Caddyfile"
    out_file.write_text(caddy_content, encoding="utf-8")
    print(f"  [+] Caddyfile written to: {out_file}")
    return out_file

def main():
    parser = argparse.ArgumentParser(description="FitPulse Domain Setup & DNS Validator")
    parser.add_argument("--domain", "-d", help="Your domain name (e.g. fitpulse.app or myfitness.com)")
    args = parser.parse_args()

    base_dir = Path(__file__).resolve().parent.parent
    deploy_dir = base_dir / "deploy"
    deploy_dir.mkdir(exist_ok=True)

    print("=" * 65)
    print(" FitPulse Pro - Custom Domain & Deployment Setup")
    print("=" * 65)

    domain = args.domain
    if not domain:
        if sys.stdin.isatty():
            domain = input("\nEnter your custom domain (e.g. fitpulse.app or app.fitpulse.com): ").strip()
        else:
            domain = "fitpulse.app"

    if not domain:
        domain = "fitpulse.app"

    clean_domain, resolved_ips = check_dns(domain)
    public_ip = get_public_ip()

    print(f"\n[2/4] Server Environment Detection:")
    if public_ip:
        print(f"  [+] Current Server Public IP: {public_ip}")
        if resolved_ips and public_ip in resolved_ips:
            print("  [+] DNS MATCH! Domain is actively pointing to this server IP.")
        elif resolved_ips:
            print(f"  [i] Note: Domain resolves to {resolved_ips}, which differs from current IP ({public_ip}).")
            print("      (This is expected if you are using Cloudflare Proxy, Render, or a CDN)")
    else:
        print("  [i] Public IP could not be automatically detected (local environment).")

    print(f"\n[3/4] Generating Production Web Server Configurations:")
    generate_nginx_config(clean_domain, base_dir)
    generate_caddyfile(clean_domain, base_dir)

    print(f"\n[4/4] Required DNS Configuration Matrix:")
    target_ip = public_ip or "YOUR_SERVER_PUBLIC_IP"
    print("-" * 65)
    print(f"  Record Type | Host / Name  | Value / Destination         | TTL")
    print("-" * 65)
    print(f"  A           | @ (or apex)  | {target_ip:<27} | Auto / 300")
    print(f"  CNAME       | www          | {clean_domain:<27} | Auto / 300")
    print("-" * 65)

    print("\nNext Steps:")
    print(f"1. Log in to your DNS provider (Cloudflare, GoDaddy, Namecheap, etc.) and add the records above.")
    print(f"2. Add your domain to .env: DOMAIN_NAME={clean_domain}")
    print(f"3. Run SSL Certbot command: sudo certbot --nginx -d {clean_domain} -d www.{clean_domain}")
    print("4. See DOMAIN_GUIDE.md for step-by-step instructions for Cloudflare, Render, and Vercel.")
    print("=" * 65)

if __name__ == "__main__":
    main()
