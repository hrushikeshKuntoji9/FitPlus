#!/usr/bin/env python3
"""
FitPulse Pro — Production-Ready Full-Stack Server
Flask + SQLite with proper security, authentication, Razorpay payments,
subscription management, and comprehensive REST API.
"""

import os
import sys
import json
import sqlite3
import hashlib
import secrets
import datetime
import urllib.request
import urllib.parse
import uuid
import csv
import io
import hmac
import time
import functools
from collections import defaultdict
from pathlib import Path

# Optional imports — graceful degradation
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    import bcrypt
    HAS_BCRYPT = True
except ImportError:
    HAS_BCRYPT = False

try:
    from werkzeug.security import generate_password_hash, check_password_hash
    HAS_WERKZEUG = True
except ImportError:
    HAS_WERKZEUG = False

if not HAS_BCRYPT and not HAS_WERKZEUG:
    print("[FitPulse] WARNING: Neither bcrypt nor werkzeug installed. Using SHA-256 fallback.")

try:
    import razorpay
    HAS_RAZORPAY = True
except ImportError:
    HAS_RAZORPAY = False
    print("[FitPulse] WARNING: razorpay SDK not installed. Payment features disabled.")

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False
    print("[FitPulse] WARNING: requests library not installed.")

from flask import Flask, request, jsonify, send_from_directory, redirect, make_response, g, abort

from email_service import (
    email_status,
    send_contact_ack,
    send_email,
    send_password_reset,
    send_payment_confirmation,
    send_verification,
)

# ==============================================================================
# CONFIGURATION (all secrets from environment variables)
# ==============================================================================

BASE_DIR = Path(__file__).resolve().parent
PUBLIC_DIR = BASE_DIR / "public" / "fitpulse"
DATA_DIR = PUBLIC_DIR / "data"
DB_PATH = Path(os.environ.get("DATABASE_PATH", str(BASE_DIR / "fitpulse.db")))

FLASK_ENV = os.environ.get("FLASK_ENV", "development")
_secret_from_env = os.environ.get("FLASK_SECRET_KEY", "")
if FLASK_ENV == "production" and not _secret_from_env:
    print("[FitPulse] FATAL: FLASK_SECRET_KEY is required when FLASK_ENV=production.")
    sys.exit(1)
FLASK_SECRET = _secret_from_env or secrets.token_hex(32)
SESSION_EXPIRY_HOURS = int(os.environ.get("SESSION_EXPIRY_HOURS", "168"))  # 7 days
LEGACY_SALT = os.environ.get("PASSWORD_SALT", "")
MIN_PASSWORD_LENGTH = 8

GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")

# Razorpay Payment Gateway
RAZORPAY_KEY_ID = os.environ.get("RAZORPAY_KEY_ID", "")
RAZORPAY_KEY_SECRET = os.environ.get("RAZORPAY_KEY_SECRET", "")
RAZORPAY_WEBHOOK_SECRET = os.environ.get("RAZORPAY_WEBHOOK_SECRET", "")

# Stripe Payment Gateway
STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_PUBLISHABLE_KEY = os.environ.get("STRIPE_PUBLISHABLE_KEY", "")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")

# AI Coach Providers (OpenAI, Google Gemini, Groq, Anthropic Claude)
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-1.5-flash")

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-3-5-haiku-20241022")

# Production Domain & Networking
DOMAIN_NAME = os.environ.get("DOMAIN_NAME", "localhost")
FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:5000").rstrip("/")
_default_cors = f"{FRONTEND_URL},http://127.0.0.1:5000,http://localhost:5000"
CORS_ORIGINS = [o.strip() for o in os.environ.get("CORS_ORIGINS", _default_cors).split(",") if o.strip()]
RATE_LIMIT_LOGIN = int(os.environ.get("RATE_LIMIT_LOGIN", "5"))
RATE_LIMIT_REGISTER = int(os.environ.get("RATE_LIMIT_REGISTER", "3"))
RATE_LIMIT_API = int(os.environ.get("RATE_LIMIT_API", "100"))

ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@fitpulse.app")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")
ADMIN_NAME = os.environ.get("ADMIN_NAME", "FitPulse Admin")
SEED_DEMO_DATA = os.environ.get("SEED_DEMO_DATA", "0" if FLASK_ENV == "production" else "1").lower() in ("1", "true", "yes")
ALLOW_DEMO_PAYMENTS = os.environ.get("ALLOW_DEMO_PAYMENTS", "0" if FLASK_ENV == "production" else "1").lower() in ("1", "true", "yes")

# Razorpay client
rzp_client = None
if HAS_RAZORPAY and RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET:
    rzp_client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))

app = Flask(__name__, static_folder=str(PUBLIC_DIR))
app.config["SECRET_KEY"] = FLASK_SECRET

# ==============================================================================
# DATABASE SCHEMA & INITIALIZATION
# ==============================================================================

def get_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    conn = get_db()
    c = conn.cursor()

    c.executescript("""
    -- Core user tables
    CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        role TEXT DEFAULT 'user' CHECK(role IN ('user', 'admin')),
        plan TEXT DEFAULT 'free' CHECK(plan IN ('free', 'premium')),
        plan_type TEXT DEFAULT 'monthly',
        plan_start TEXT,
        plan_expiry TEXT,
        payment_status TEXT DEFAULT 'none',
        status TEXT DEFAULT 'active' CHECK(status IN ('active', 'suspended')),
        email_verified INTEGER DEFAULT 0,
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS sessions (
        token TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        created_at TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS profiles (
        user_id TEXT PRIMARY KEY,
        name TEXT,
        email TEXT,
        age INTEGER DEFAULT 28,
        gender TEXT DEFAULT 'male',
        height REAL DEFAULT 175,
        weight REAL DEFAULT 75,
        start_weight REAL DEFAULT 80,
        target_weight REAL DEFAULT 70,
        goal TEXT DEFAULT 'lose',
        activity TEXT DEFAULT 'moderate',
        diet TEXT DEFAULT 'vegetarian',
        experience TEXT DEFAULT 'intermediate',
        onboarded INTEGER DEFAULT 1,
        updated_at TEXT,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );

    -- Tracking tables
    CREATE TABLE IF NOT EXISTS nutrition_logs (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        date TEXT NOT NULL,
        meal TEXT NOT NULL,
        name TEXT NOT NULL,
        calories INTEGER NOT NULL,
        protein REAL DEFAULT 0,
        carbs REAL DEFAULT 0,
        fat REAL DEFAULT 0,
        fiber REAL DEFAULT 0,
        serving TEXT,
        qty REAL DEFAULT 1,
        created_at TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS workout_logs (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        date TEXT NOT NULL,
        name TEXT NOT NULL,
        minutes INTEGER NOT NULL,
        calories INTEGER NOT NULL,
        category TEXT,
        completed INTEGER DEFAULT 1,
        created_at TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS water_logs (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        date TEXT NOT NULL,
        ml INTEGER NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS sleep_logs (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        date TEXT NOT NULL,
        bedtime TEXT,
        wake TEXT,
        hours REAL NOT NULL,
        quality TEXT DEFAULT 'Rested',
        created_at TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS habit_logs (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        date TEXT NOT NULL,
        habit_id TEXT NOT NULL,
        completed INTEGER DEFAULT 1,
        created_at TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS weight_logs (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        date TEXT NOT NULL,
        kg REAL NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS step_logs (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        date TEXT NOT NULL,
        steps INTEGER NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );

    -- Content tables
    CREATE TABLE IF NOT EXISTS foods (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        category TEXT,
        calories INTEGER NOT NULL,
        protein REAL DEFAULT 0,
        carbs REAL DEFAULT 0,
        fat REAL DEFAULT 0,
        fiber REAL DEFAULT 0,
        serving TEXT,
        is_custom INTEGER DEFAULT 0,
        created_by TEXT
    );

    CREATE TABLE IF NOT EXISTS workouts (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        category TEXT,
        level TEXT,
        minutes INTEGER NOT NULL,
        calories INTEGER NOT NULL,
        equipment TEXT,
        focus TEXT,
        exercises_json TEXT,
        is_custom INTEGER DEFAULT 0,
        premium INTEGER DEFAULT 0,
        status TEXT DEFAULT 'published',
        created_by TEXT
    );

    CREATE TABLE IF NOT EXISTS meal_plans (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        goal TEXT,
        calories INTEGER NOT NULL,
        diet TEXT,
        days_json TEXT NOT NULL
    );

    -- Support
    CREATE TABLE IF NOT EXISTS tickets (
        id TEXT PRIMARY KEY,
        email TEXT NOT NULL,
        name TEXT,
        subject TEXT NOT NULL,
        category TEXT DEFAULT 'Technical',
        priority TEXT DEFAULT 'medium',
        status TEXT DEFAULT 'open',
        created_at TEXT NOT NULL,
        messages_json TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS settings (
        user_id TEXT PRIMARY KEY,
        theme TEXT DEFAULT 'light',
        units TEXT DEFAULT 'metric',
        notifications INTEGER DEFAULT 1,
        public_profile INTEGER DEFAULT 0,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );

    -- Payment & Subscription tables (NEW)
    CREATE TABLE IF NOT EXISTS membership_plans (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        slug TEXT UNIQUE NOT NULL,
        price INTEGER NOT NULL,
        currency TEXT DEFAULT 'INR',
        duration_months INTEGER NOT NULL,
        features_json TEXT,
        active INTEGER DEFAULT 1,
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS orders (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        plan_id TEXT,
        amount INTEGER NOT NULL,
        currency TEXT DEFAULT 'INR',
        gateway_order_id TEXT,
        coupon_code TEXT,
        discount INTEGER DEFAULT 0,
        gst INTEGER DEFAULT 0,
        status TEXT DEFAULT 'created' CHECK(status IN ('created', 'paid', 'failed', 'refunded', 'expired')),
        created_at TEXT NOT NULL,
        updated_at TEXT,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS payments (
        id TEXT PRIMARY KEY,
        order_id TEXT NOT NULL,
        user_id TEXT NOT NULL,
        gateway_payment_id TEXT,
        gateway_signature TEXT,
        amount INTEGER NOT NULL,
        currency TEXT DEFAULT 'INR',
        method TEXT,
        status TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'captured', 'failed', 'refunded')),
        created_at TEXT NOT NULL,
        FOREIGN KEY (order_id) REFERENCES orders(id),
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );

    -- Fitness goals & measurements (NEW)
    CREATE TABLE IF NOT EXISTS fitness_goals (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        goal_type TEXT NOT NULL,
        target_value REAL,
        current_value REAL,
        unit TEXT,
        status TEXT DEFAULT 'active' CHECK(status IN ('active', 'completed', 'abandoned')),
        start_date TEXT,
        target_date TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS body_measurements (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        date TEXT NOT NULL,
        chest REAL,
        waist REAL,
        hips REAL,
        arms REAL,
        thighs REAL,
        neck REAL,
        body_fat REAL,
        notes TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );

    -- Contact enquiries (NEW)
    CREATE TABLE IF NOT EXISTS contact_enquiries (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        email TEXT NOT NULL,
        phone TEXT,
        subject TEXT NOT NULL,
        message TEXT NOT NULL,
        status TEXT DEFAULT 'new' CHECK(status IN ('new', 'read', 'replied', 'closed')),
        created_at TEXT NOT NULL
    );

    -- Password reset tokens (NEW)
    CREATE TABLE IF NOT EXISTS password_resets (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        token_hash TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        used INTEGER DEFAULT 0,
        created_at TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );

    -- Login attempt tracking for rate limiting (NEW)
    CREATE TABLE IF NOT EXISTS login_attempts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT,
        ip TEXT,
        success INTEGER DEFAULT 0,
        created_at TEXT NOT NULL
    );

    -- Notifications (NEW)
    CREATE TABLE IF NOT EXISTS notifications (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        type TEXT DEFAULT 'info',
        title TEXT NOT NULL,
        message TEXT,
        read INTEGER DEFAULT 0,
        created_at TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS email_verifications (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        token_hash TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        used INTEGER DEFAULT 0,
        created_at TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS webhook_events (
        id TEXT PRIMARY KEY,
        provider TEXT NOT NULL,
        event_id TEXT NOT NULL UNIQUE,
        event_type TEXT,
        processed_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS admin_logs (
        id TEXT PRIMARY KEY,
        admin_id TEXT NOT NULL,
        action TEXT NOT NULL,
        target_type TEXT,
        target_id TEXT,
        details TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY (admin_id) REFERENCES users(id) ON DELETE SET NULL
    );
    """)
    conn.commit()

    # Run migrations for existing databases BEFORE creating indexes on potentially new columns
    _migrate_db(conn)

    c.executescript("""
    -- Indexes for performance
    CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
    CREATE INDEX IF NOT EXISTS idx_sessions_expires ON sessions(expires_at);
    CREATE INDEX IF NOT EXISTS idx_nutrition_user_date ON nutrition_logs(user_id, date);
    CREATE INDEX IF NOT EXISTS idx_workout_logs_user ON workout_logs(user_id, date);
    CREATE INDEX IF NOT EXISTS idx_water_user_date ON water_logs(user_id, date);
    CREATE INDEX IF NOT EXISTS idx_weight_user_date ON weight_logs(user_id, date);
    CREATE INDEX IF NOT EXISTS idx_orders_user ON orders(user_id);
    CREATE INDEX IF NOT EXISTS idx_payments_order ON payments(order_id);
    CREATE INDEX IF NOT EXISTS idx_login_attempts ON login_attempts(email, created_at);
    CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications(user_id, read);
    CREATE INDEX IF NOT EXISTS idx_tickets_email ON tickets(email);
    CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
    CREATE INDEX IF NOT EXISTS idx_webhook_events_event ON webhook_events(event_id);
    """)
    conn.commit()
    try:
        c.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_payments_gateway_id ON payments(gateway_payment_id)")
        conn.commit()
    except sqlite3.OperationalError:
        pass

    # Seed if users table is empty
    c.execute("SELECT COUNT(*) FROM users")
    if c.fetchone()[0] == 0 and SEED_DEMO_DATA:
        seed_data(conn)
    else:
        _ensure_admin_account(conn)

    # Seed membership plans if empty
    c.execute("SELECT COUNT(*) FROM membership_plans")
    if c.fetchone()[0] == 0:
        _seed_membership_plans(conn)

    conn.close()


def _migrate_db(conn):
    """Add columns to existing tables if missing (safe for re-runs)."""
    c = conn.cursor()
    migrations = [
        ("users", "email_verified", "ALTER TABLE users ADD COLUMN email_verified INTEGER DEFAULT 0"),
        ("sessions", "expires_at", "ALTER TABLE sessions ADD COLUMN expires_at TEXT DEFAULT ''"),
        ("workouts", "premium", "ALTER TABLE workouts ADD COLUMN premium INTEGER DEFAULT 0"),
        ("workouts", "status", "ALTER TABLE workouts ADD COLUMN status TEXT DEFAULT 'published'"),
    ]
    for table, column, sql in migrations:
        try:
            c.execute(f"SELECT {column} FROM {table} LIMIT 1")
        except sqlite3.OperationalError:
            try:
                c.execute(sql)
                print(f"[FitPulse] Migration: added {table}.{column}")
            except sqlite3.OperationalError:
                pass
    conn.commit()


def _seed_membership_plans(conn):
    """Seed default membership plans."""
    c = conn.cursor()
    now = _now_iso()
    plans = [
        ("plan_free", "Free", "free", 0, "INR", 0,
         json.dumps(["Food, water, sleep & habit tracking", "Workout library", "7-day progress charts"]), 1),
        ("plan_monthly", "Premium Monthly", "monthly", 199, "INR", 1,
         json.dumps(["Everything in Free", "AI Coach — unlimited", "Personal meal plans", "90-day analytics & badges"]), 1),
        ("plan_yearly", "Premium Yearly", "yearly", 1499, "INR", 12,
         json.dumps(["Everything in Monthly", "Save 37% vs monthly", "Priority support", "Early access features"]), 1),
    ]
    for p in plans:
        c.execute("""
            INSERT OR IGNORE INTO membership_plans (id, name, slug, price, currency, duration_months, features_json, active, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (*p, now))
    conn.commit()


# ==============================================================================
# PASSWORD HASHING (bcrypt / Werkzeug scrypt with legacy SHA-256 migration)
# ==============================================================================

def hash_password(password: str) -> str:
    """Hash password with bcrypt (preferred), Werkzeug scrypt, or salted SHA-256 fallback."""
    if HAS_BCRYPT:
        return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    if HAS_WERKZEUG:
        return generate_password_hash(password)
    # Fallback: SHA-256 with per-password random salt
    salt = secrets.token_hex(16)
    h = hashlib.sha256((salt + password).encode()).hexdigest()
    return f"sha256${salt}${h}"


def verify_password(password: str, password_hash: str) -> bool:
    """Verify password against stored hash, supporting multiple formats."""
    if not password or not password_hash:
        return False

    # Werkzeug hashes (scrypt: or pbkdf2:)
    if password_hash.startswith("scrypt:") or password_hash.startswith("pbkdf2:"):
        if HAS_WERKZEUG:
            try:
                return check_password_hash(password_hash, password)
            except Exception:
                return False

    # bcrypt hashes start with $2b$ or $2a$
    if password_hash.startswith("$2b$") or password_hash.startswith("$2a$"):
        if HAS_BCRYPT:
            try:
                return bcrypt.checkpw(password.encode('utf-8'), password_hash.encode('utf-8'))
            except Exception:
                return False
        return False

    # New SHA-256 format: sha256$salt$hash
    if password_hash.startswith("sha256$"):
        parts = password_hash.split("$")
        if len(parts) == 3:
            salt = parts[1]
            expected = parts[2]
            return hashlib.sha256((salt + password).encode()).hexdigest() == expected
        return False

    # Legacy format: single SHA-256 with static salt
    legacy_hash = hashlib.sha256((LEGACY_SALT + password).encode()).hexdigest()
    if legacy_hash == password_hash:
        return True

    # Legacy demo weakHash format from frontend
    if password_hash.startswith("h") and len(password_hash) < 16:
        h = 0
        for ch in password:
            h = (h * 31 + ord(ch)) & 0xFFFFFFFF
            if h >= 0x80000000:
                h -= 0x100000000
        return ("h" + str(abs(h))) == password_hash

    return False


def _upgrade_password_hash(conn, user_id: str, password: str):
    """Re-hash a password with modern hasher if currently using a legacy format."""
    if HAS_BCRYPT or HAS_WERKZEUG:
        new_hash = hash_password(password)
        conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (new_hash, user_id))
        conn.commit()


# ==============================================================================
# HELPERS
# ==============================================================================

def _now_iso():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()

def _today_iso():
    return datetime.date.today().isoformat()

def _gen_id(prefix=""):
    return prefix + secrets.token_hex(8)

def _safe_int(val, default=0):
    try:
        return int(val)
    except (TypeError, ValueError):
        return default

def _safe_float(val, default=0.0):
    try:
        return float(val)
    except (TypeError, ValueError):
        return default

def _sanitize_str(val, max_len=500):
    """Sanitize string input to prevent XSS."""
    if not val:
        return ""
    s = str(val).strip()[:max_len]
    # Strip HTML tags
    import re
    return re.sub(r'<[^>]+>', '', s)


# ==============================================================================
# RATE LIMITING (in-memory, per-IP)
# ==============================================================================

_rate_limits = defaultdict(list)  # key -> [timestamps]

def _check_rate_limit(key: str, max_requests: int, window_seconds: int = 900) -> bool:
    """Returns True if request is allowed, False if rate-limited."""
    if app.testing:
        return True
    now = time.time()
    timestamps = _rate_limits[key]
    # Clean old entries
    _rate_limits[key] = [t for t in timestamps if now - t < window_seconds]
    if len(_rate_limits[key]) >= max_requests:
        return False
    _rate_limits[key].append(now)
    return True

def _get_client_ip():
    return request.headers.get("X-Forwarded-For", request.remote_addr or "unknown").split(",")[0].strip()


# ==============================================================================
# AUTHENTICATION & SECURITY MIDDLEWARE
# ==============================================================================

@app.before_request
def before_request_hook():
    """Attach DB connection and apply coarse API rate limits."""
    g.db = get_db()
    if request.method == "OPTIONS":
        return None
    path = request.path or ""
    if path.startswith("/api/") and path not in ("/api/health", "/health", "/healthz"):
        ip = _get_client_ip()
        if not _check_rate_limit(f"api:{ip}", RATE_LIMIT_API, 60):
            return jsonify({"ok": False, "error": "Too many requests. Slow down."}), 429

@app.teardown_appcontext
def teardown_db(exception):
    db = g.pop('db', None)
    if db is not None:
        db.close()

@app.after_request
def add_security_headers(response):
    """Add CORS and security headers to every response."""
    origin = request.headers.get("Origin", "")

    if origin and origin in CORS_ORIGINS:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Vary"] = "Origin"
        response.headers["Access-Control-Allow-Credentials"] = "true"
    elif not origin and FLASK_ENV != "production":
        response.headers["Access-Control-Allow-Origin"] = FRONTEND_URL

    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-Session-Token"

    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if FLASK_ENV == "production":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://accounts.google.com https://checkout.razorpay.com; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "img-src 'self' data: https:; "
            "connect-src 'self' https://accounts.google.com https://api.razorpay.com https://lumberjack.razorpay.com; "
            "frame-src https://api.razorpay.com https://checkout.razorpay.com https://accounts.google.com"
        )

    return response


def get_current_user(conn=None):
    """Extract and validate the current user from the session token."""
    if conn is None:
        conn = g.get('db') or get_db()

    auth_header = request.headers.get("Authorization", "")
    token = None
    if auth_header.startswith("Bearer "):
        token = auth_header.split(" ", 1)[1]
    elif "fitpulse_token" in request.cookies:
        token = request.cookies.get("fitpulse_token")

    if not token:
        token = request.headers.get("X-Session-Token")

    if not token:
        return None

    c = conn.cursor()
    now = _now_iso()
    c.execute("""
        SELECT u.* FROM users u
        JOIN sessions s ON u.id = s.user_id
        WHERE s.token = ? AND (s.expires_at = '' OR s.expires_at > ?)
    """, (token, now))
    row = c.fetchone()
    if row:
        return dict(row)
    return None


def require_login(f):
    """Decorator: requires authenticated user."""
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if request.method == "OPTIONS":
            return jsonify({"ok": True})
        user = get_current_user()
        if not user:
            return jsonify({"ok": False, "error": "Authentication required."}), 401
        if user.get("status") == "suspended":
            return jsonify({"ok": False, "error": "Account suspended. Contact support."}), 403
        g.user = user
        return f(*args, **kwargs)
    return decorated


def require_admin(f):
    """Decorator: requires admin role (verified server-side)."""
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if request.method == "OPTIONS":
            return jsonify({"ok": True})
        user = get_current_user()
        if not user:
            return jsonify({"ok": False, "error": "Authentication required."}), 401
        if user.get("role") != "admin":
            return jsonify({"ok": False, "error": "Admin access required."}), 403
        g.user = user
        return f(*args, **kwargs)
    return decorated


def _auth_required_tuple():
    user = get_current_user()
    if not user:
        return None, (jsonify({"ok": False, "error": "Authentication required."}), 401)
    if user.get("status") == "suspended":
        return None, (jsonify({"ok": False, "error": "Account suspended. Contact support."}), 403)
    return user, None


def _demo_payments_allowed():
    if rzp_client:
        return False
    if app.testing:
        return True
    if FLASK_ENV == "production" and not ALLOW_DEMO_PAYMENTS:
        return False
    return ALLOW_DEMO_PAYMENTS


def _admin_log(conn, action, target_type="", target_id="", details=""):
    admin = getattr(g, "user", None) or {}
    conn.execute(
        """INSERT INTO admin_logs (id, admin_id, action, target_type, target_id, details, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (_gen_id("alog_"), admin.get("id", ""), action, target_type, target_id, details[:1000], _now_iso()),
    )


def _activate_paid_order(conn, order, plan=None, payment_id="", signature="", method="razorpay"):
    """Mark order paid and activate membership. Idempotent if already paid."""
    c = conn.cursor()
    now = _now_iso()
    if order.get("status") == "paid":
        return dict(order)

    if payment_id:
        c.execute("SELECT id FROM payments WHERE gateway_payment_id = ?", (payment_id,))
        if c.fetchone():
            c.execute("UPDATE orders SET status = 'paid', updated_at = ? WHERE id = ?", (now, order["id"]))
            return dict(order)

    c.execute("""
        INSERT INTO payments (id, order_id, user_id, gateway_payment_id, gateway_signature, amount, currency, method, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, 'INR', ?, 'captured', ?)
    """, (_gen_id("pay_"), order["id"], order["user_id"], payment_id or None, signature or "",
          order["amount"], method, now))
    c.execute("UPDATE orders SET status = 'paid', updated_at = ? WHERE id = ?", (now, order["id"]))

    if plan is None:
        c.execute("SELECT * FROM membership_plans WHERE id = ?", (order.get("plan_id"),))
        plan_row = c.fetchone()
        plan = dict(plan_row) if plan_row else {}

    duration = int(plan.get("duration_months") or 1)
    today = datetime.date.today()
    expiry = today + datetime.timedelta(days=duration * 30)
    c.execute("""
        UPDATE users SET plan = 'premium', plan_type = ?, plan_start = ?, plan_expiry = ?, payment_status = 'paid'
        WHERE id = ?
    """, (plan.get("slug", "monthly"), today.isoformat(), expiry.isoformat(), order["user_id"]))
    c.execute("""
        INSERT INTO notifications (id, user_id, type, title, message, created_at)
        VALUES (?, ?, 'payment', 'Premium Activated!', ?, ?)
    """, (_gen_id("notif_"), order["user_id"],
          f"Your {plan.get('name', 'Premium')} plan is active until {expiry.isoformat()}.", now))
    conn.commit()
    order["status"] = "paid"
    order["_expiry"] = expiry.isoformat()
    order["_plan_name"] = plan.get("name", "Premium")
    return order


def _create_session(conn, user_id: str) -> str:
    """Create a new session token with expiry."""
    token = secrets.token_hex(32)
    now = _now_iso()
    expires = (datetime.datetime.now(datetime.timezone.utc) +
               datetime.timedelta(hours=SESSION_EXPIRY_HOURS)).isoformat()
    conn.execute("INSERT INTO sessions (token, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
                 (token, user_id, now, expires))
    conn.commit()
    return token


def _clean_user_response(user: dict) -> dict:
    """Strip sensitive fields from user data before sending to client."""
    return {
        "id": user["id"],
        "name": user["name"],
        "email": user["email"],
        "role": user["role"],
        "plan": user["plan"],
        "planType": user.get("plan_type", "monthly"),
        "planStart": user.get("plan_start", ""),
        "planExpiry": user.get("plan_expiry", ""),
        "status": user["status"],
        "emailVerified": bool(user.get("email_verified", 0)),
        "created": user["created_at"],
    }


def _set_auth_cookie(resp, token: str):
    """Set the authentication cookie with proper security flags."""
    is_prod = FLASK_ENV == "production"
    resp.set_cookie(
        "fitpulse_token",
        token,
        httponly=True,
        samesite="Lax",
        secure=is_prod,
        max_age=SESSION_EXPIRY_HOURS * 3600,
    )
    return resp


# ==============================================================================
# API: CONFIGURATION (Public non-sensitive settings)
# ==============================================================================

@app.route("/api/config", methods=["GET"])
def api_public_config():
    """Return public configuration for frontend (safe to expose)."""
    ai_provider = "heuristic"
    if OPENAI_API_KEY:
        ai_provider = "openai"
    elif GEMINI_API_KEY:
        ai_provider = "gemini"
    elif GROQ_API_KEY:
        ai_provider = "groq"
    elif ANTHROPIC_API_KEY:
        ai_provider = "anthropic"

    return jsonify({
        "ok": True,
        "googleClientId": GOOGLE_CLIENT_ID,
        "razorpayKeyId": RAZORPAY_KEY_ID,
        "hasRazorpay": HAS_RAZORPAY and bool(RAZORPAY_KEY_ID),
        "stripePublishableKey": STRIPE_PUBLISHABLE_KEY,
        "hasStripe": bool(STRIPE_PUBLISHABLE_KEY),
        "aiProvider": ai_provider,
        "hasLiveAi": ai_provider != "heuristic",
        "domain": DOMAIN_NAME,
        "environment": FLASK_ENV,
        "emailConfigured": email_status()["configured"],
        "demoAccountsEnabled": SEED_DEMO_DATA,
        "minPasswordLength": MIN_PASSWORD_LENGTH,
    })


# ==============================================================================
# API: AUTHENTICATION
# ==============================================================================

@app.route("/api/auth/register", methods=["POST", "OPTIONS"])
def api_register():
    if request.method == "OPTIONS":
        return jsonify({"ok": True})

    ip = _get_client_ip()
    if not _check_rate_limit(f"register:{ip}", RATE_LIMIT_REGISTER, 900):
        return jsonify({"ok": False, "error": "Too many registration attempts. Try again later."}), 429

    data = request.get_json(silent=True) or {}
    name = _sanitize_str(data.get("name", ""), 100)
    email = (data.get("email") or "").strip().lower()[:254]
    password = data.get("password") or ""

    if len(name) < 2:
        return jsonify({"ok": False, "error": "Name is required (minimum 2 characters)."}), 400
    if "@" not in email or "." not in email:
        return jsonify({"ok": False, "error": "Valid email is required."}), 400
    if len(password) < MIN_PASSWORD_LENGTH:
        return jsonify({"ok": False, "error": f"Password must be at least {MIN_PASSWORD_LENGTH} characters."}), 400
    if len(password) > 128:
        return jsonify({"ok": False, "error": "Password too long."}), 400

    conn = g.db
    c = conn.cursor()
    c.execute("SELECT id FROM users WHERE email = ?", (email,))
    if c.fetchone():
        return jsonify({"ok": False, "error": "An account with that email already exists."}), 409

    user_id = _gen_id("user_")
    pw_hash = hash_password(password)
    now = _now_iso()

    c.execute("""
        INSERT INTO users (id, name, email, password_hash, role, plan, plan_type, status, email_verified, created_at)
        VALUES (?, ?, ?, ?, 'user', 'free', 'monthly', 'active', 0, ?)
    """, (user_id, name, email, pw_hash, now))

    c.execute("""
        INSERT INTO profiles (user_id, name, email, updated_at)
        VALUES (?, ?, ?, ?)
    """, (user_id, name, email, now))

    token = _create_session(conn, user_id)

    verify_token = secrets.token_urlsafe(32)
    c.execute("""
        INSERT INTO email_verifications (id, user_id, token_hash, expires_at, used, created_at)
        VALUES (?, ?, ?, ?, 0, ?)
    """, (_gen_id("ev_"), user_id, hashlib.sha256(verify_token.encode()).hexdigest(),
          (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=2)).isoformat(), now))

    c.execute("""
        INSERT INTO notifications (id, user_id, type, title, message, created_at)
        VALUES (?, ?, 'welcome', 'Welcome to FitPulse!', 'Start by completing your fitness profile in the onboarding wizard.', ?)
    """, (_gen_id("notif_"), user_id, now))
    conn.commit()

    verify_url = f"{FRONTEND_URL}/fitpulse/login.html?verify={verify_token}"
    send_verification(email, verify_url)

    user_data = {
        "id": user_id, "name": name, "email": email,
        "role": "user", "plan": "free", "status": "active",
        "emailVerified": False, "created": now,
    }
    resp = jsonify({"ok": True, "token": token, "data": user_data})
    _set_auth_cookie(resp, token)
    return resp


@app.route("/api/auth/login", methods=["POST", "OPTIONS"])
def api_login():
    if request.method == "OPTIONS":
        return jsonify({"ok": True})

    ip = _get_client_ip()
    if not _check_rate_limit(f"login:{ip}", RATE_LIMIT_LOGIN, 900):
        return jsonify({"ok": False, "error": "Too many login attempts. Try again in 15 minutes."}), 429

    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    now = _now_iso()

    conn = g.db
    c = conn.cursor()

    # Record login attempt
    c.execute("INSERT INTO login_attempts (email, ip, success, created_at) VALUES (?, ?, 0, ?)",
              (email, ip, now))
    conn.commit()

    c.execute("SELECT * FROM users WHERE email = ?", (email,))
    row = c.fetchone()
    if not row:
        return jsonify({"ok": False, "error": "Invalid email or password."}), 401

    user = dict(row)
    if not verify_password(password, user["password_hash"]):
        return jsonify({"ok": False, "error": "Invalid email or password."}), 401

    if user["status"] == "suspended":
        return jsonify({"ok": False, "error": "This account is suspended. Contact support."}), 403

    # Upgrade legacy password hash to bcrypt
    _upgrade_password_hash(conn, user["id"], password)

    # Mark login attempt as successful
    c.execute("UPDATE login_attempts SET success = 1 WHERE email = ? AND created_at = ?", (email, now))

    token = _create_session(conn, user["id"])
    conn.commit()

    clean_user = _clean_user_response(user)
    resp = jsonify({"ok": True, "token": token, "data": clean_user})
    _set_auth_cookie(resp, token)
    return resp


@app.route("/api/auth/logout", methods=["POST", "OPTIONS"])
def api_logout():
    if request.method == "OPTIONS":
        return jsonify({"ok": True})

    conn = g.db
    auth_header = request.headers.get("Authorization", "")
    token = None
    if auth_header.startswith("Bearer "):
        token = auth_header.split(" ", 1)[1]
    else:
        token = request.cookies.get("fitpulse_token")

    if token:
        conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
        conn.commit()

    resp = jsonify({"ok": True})
    resp.set_cookie("fitpulse_token", "", expires=0)
    return resp


@app.route("/api/auth/google", methods=["POST", "OPTIONS"])
def api_google_auth():
    if request.method == "OPTIONS":
        return jsonify({"ok": True})

    data = request.get_json(silent=True) or {}
    token_str = data.get("token")

    if not token_str:
        return jsonify({"ok": False, "error": "No token provided."}), 400

    if not GOOGLE_CLIENT_ID:
        return jsonify({"ok": False, "error": "Google OAuth not configured. Set GOOGLE_CLIENT_ID in .env"}), 501

    try:
        req_url = "https://oauth2.googleapis.com/tokeninfo?id_token=" + urllib.parse.quote(token_str)
        try:
            import ssl
            ctx = ssl.create_default_context()
            with urllib.request.urlopen(req_url, context=ctx, timeout=10) as response:
                idinfo = json.loads(response.read().decode())
        except Exception:
            return jsonify({"ok": False, "error": "Invalid Google token."}), 401

        if idinfo.get("aud") != GOOGLE_CLIENT_ID:
            return jsonify({"ok": False, "error": "Token audience mismatch."}), 401

        email = idinfo.get("email", "").lower()
        name = _sanitize_str(idinfo.get("name", "Google User"), 100)

        conn = g.db
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE email = ?", (email,))
        row = c.fetchone()
        now = _now_iso()

        if row:
            user = dict(row)
        else:
            user_id = _gen_id("user_g_")
            pw_hash = hash_password(secrets.token_hex(32))
            c.execute("""
                INSERT INTO users (id, name, email, password_hash, role, plan, plan_type, status, email_verified, created_at)
                VALUES (?, ?, ?, ?, 'user', 'free', 'monthly', 'active', 1, ?)
            """, (user_id, name, email, pw_hash, now))
            c.execute("INSERT INTO profiles (user_id, name, email, updated_at) VALUES (?, ?, ?, ?)",
                      (user_id, name, email, now))
            conn.commit()
            c.execute("SELECT * FROM users WHERE id = ?", (user_id,))
            user = dict(c.fetchone())

        session_token = _create_session(conn, user["id"])
        conn.commit()

        clean_user = _clean_user_response(user)
        resp = jsonify({"ok": True, "token": session_token, "data": clean_user})
        _set_auth_cookie(resp, session_token)
        return resp

    except Exception:
        return jsonify({"ok": False, "error": "Google sign-in failed."}), 401


@app.route("/api/auth/me", methods=["GET"])
def api_auth_me():
    conn = g.db
    user = get_current_user(conn)
    if not user:
        return jsonify({"ok": False, "error": "Not authenticated."}), 401

    c = conn.cursor()
    c.execute("SELECT * FROM profiles WHERE user_id = ?", (user["id"],))
    prof_row = c.fetchone()
    profile = dict(prof_row) if prof_row else {}

    return jsonify({
        "ok": True,
        "user": _clean_user_response(user),
        "profile": profile
    })


@app.route("/api/auth/forgot-password", methods=["POST", "OPTIONS"])
def api_forgot_password():
    """Request a password reset. In production, sends email with reset link."""
    if request.method == "OPTIONS":
        return jsonify({"ok": True})

    ip = _get_client_ip()
    if not _check_rate_limit(f"forgot:{ip}", 3, 900):
        return jsonify({"ok": False, "error": "Too many requests. Try again later."}), 429

    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()

    if not email or "@" not in email:
        return jsonify({"ok": False, "error": "Valid email is required."}), 400

    conn = g.db
    c = conn.cursor()
    c.execute("SELECT id FROM users WHERE email = ?", (email,))
    row = c.fetchone()

    # Always return success to prevent email enumeration
    if not row:
        return jsonify({"ok": True, "message": "If an account exists with that email, a reset link has been sent."})

    user_id = row[0]
    reset_token = secrets.token_urlsafe(48)
    token_hash = hashlib.sha256(reset_token.encode()).hexdigest()
    expires = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1)).isoformat()
    now = _now_iso()

    # Invalidate previous tokens
    c.execute("UPDATE password_resets SET used = 1 WHERE user_id = ? AND used = 0", (user_id,))
    c.execute("""
        INSERT INTO password_resets (id, user_id, token_hash, expires_at, used, created_at)
        VALUES (?, ?, ?, ?, 0, ?)
    """, (_gen_id("rst_"), user_id, token_hash, expires, now))
    conn.commit()

    reset_url = f"{FRONTEND_URL}/fitpulse/login.html?reset_token={reset_token}"
    sent, reason = send_password_reset(email, reset_url)
    if not sent and FLASK_ENV != "production":
        print(f"[FitPulse] Password reset URL for {email}: {reset_url} ({reason})")

    payload = {
        "ok": True,
        "message": "If an account exists with that email, a reset link has been sent.",
        "emailQueued": sent,
    }
    if app.testing or (FLASK_ENV != "production" and not sent):
        payload["_dev_token"] = reset_token
    return jsonify(payload)


@app.route("/api/auth/reset-password", methods=["POST", "OPTIONS"])
def api_reset_password():
    """Reset password using a valid reset token."""
    if request.method == "OPTIONS":
        return jsonify({"ok": True})

    data = request.get_json(silent=True) or {}
    reset_token = data.get("token", "")
    new_password = data.get("password", "")

    if not reset_token:
        return jsonify({"ok": False, "error": "Reset token is required."}), 400
    if len(new_password) < MIN_PASSWORD_LENGTH:
        return jsonify({"ok": False, "error": f"Password must be at least {MIN_PASSWORD_LENGTH} characters."}), 400

    token_hash = hashlib.sha256(reset_token.encode()).hexdigest()
    now = _now_iso()

    conn = g.db
    c = conn.cursor()
    c.execute("""
        SELECT pr.*, u.email FROM password_resets pr
        JOIN users u ON pr.user_id = u.id
        WHERE pr.token_hash = ? AND pr.used = 0 AND pr.expires_at > ?
    """, (token_hash, now))
    row = c.fetchone()

    if not row:
        return jsonify({"ok": False, "error": "Invalid or expired reset token."}), 400

    reset = dict(row)
    new_hash = hash_password(new_password)

    c.execute("UPDATE users SET password_hash = ? WHERE id = ?", (new_hash, reset["user_id"]))
    c.execute("UPDATE password_resets SET used = 1 WHERE id = ?", (reset["id"],))
    # Invalidate all sessions for this user
    c.execute("DELETE FROM sessions WHERE user_id = ?", (reset["user_id"],))
    conn.commit()

    return jsonify({"ok": True, "message": "Password has been reset. Please log in with your new password."})


@app.route("/api/auth/change-password", methods=["POST", "OPTIONS"])
@require_login
def api_change_password():
    """Change password for authenticated user."""
    if request.method == "OPTIONS":
        return jsonify({"ok": True})

    data = request.get_json(silent=True) or {}
    current_password = data.get("currentPassword", "")
    new_password = data.get("newPassword", "")

    if len(new_password) < MIN_PASSWORD_LENGTH:
        return jsonify({"ok": False, "error": f"New password must be at least {MIN_PASSWORD_LENGTH} characters."}), 400

    conn = g.db
    c = conn.cursor()
    c.execute("SELECT password_hash FROM users WHERE id = ?", (g.user["id"],))
    row = c.fetchone()

    if not verify_password(current_password, row[0]):
        return jsonify({"ok": False, "error": "Current password is incorrect."}), 401

    new_hash = hash_password(new_password)
    c.execute("UPDATE users SET password_hash = ? WHERE id = ?", (new_hash, g.user["id"]))
    conn.commit()

    return jsonify({"ok": True, "message": "Password changed successfully."})


@app.route("/api/auth/verify-email", methods=["POST", "OPTIONS"])
def api_verify_email():
    if request.method == "OPTIONS":
        return jsonify({"ok": True})
    data = request.get_json(silent=True) or {}
    token = data.get("token") or request.args.get("token") or ""
    if not token:
        return jsonify({"ok": False, "error": "Verification token is required."}), 400
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    now = _now_iso()
    c = g.db.cursor()
    c.execute("""
        SELECT * FROM email_verifications
        WHERE token_hash = ? AND used = 0 AND expires_at > ?
    """, (token_hash, now))
    row = c.fetchone()
    if not row:
        return jsonify({"ok": False, "error": "Invalid or expired verification link."}), 400
    rec = dict(row)
    c.execute("UPDATE users SET email_verified = 1 WHERE id = ?", (rec["user_id"],))
    c.execute("UPDATE email_verifications SET used = 1 WHERE id = ?", (rec["id"],))
    g.db.commit()
    return jsonify({"ok": True, "message": "Email verified."})


# ==============================================================================
# API: PROFILE & ONBOARDING
# ==============================================================================

@app.route("/api/profile", methods=["GET", "POST", "OPTIONS"])
def api_profile():
    if request.method == "OPTIONS":
        return jsonify({"ok": True})

    conn = g.db
    user, err = _auth_required_tuple()
    if err:
        return err

    c = conn.cursor()
    if request.method == "GET":
        c.execute("SELECT * FROM profiles WHERE user_id = ?", (user["id"],))
        row = c.fetchone()
        profile = dict(row) if row else {"name": user["name"], "email": user["email"]}
        return jsonify({"ok": True, "data": profile})

    # POST (Update)
    data = request.get_json(silent=True) or {}
    fields = ["name", "age", "gender", "height", "weight", "target_weight", "goal", "activity", "diet", "experience", "onboarded"]
    now = _now_iso()

    c.execute("SELECT * FROM profiles WHERE user_id = ?", (user["id"],))
    existing = c.fetchone()
    if not existing:
        c.execute("INSERT INTO profiles (user_id, name, email, updated_at) VALUES (?, ?, ?, ?)",
                  (user["id"], user["name"], user["email"], now))

    update_parts = []
    vals = []
    for f in fields:
        if f in data:
            update_parts.append(f"{f} = ?")
            vals.append(data[f])

    if update_parts:
        update_parts.append("updated_at = ?")
        vals.append(now)
        vals.append(user["id"])
        c.execute(f"UPDATE profiles SET {', '.join(update_parts)} WHERE user_id = ?", vals)

    if "name" in data and data["name"]:
        sanitized_name = _sanitize_str(data["name"], 100)
        c.execute("UPDATE users SET name = ? WHERE id = ?", (sanitized_name, user["id"]))

    if "weight" in data and data["weight"]:
        today = _today_iso()
        c.execute("INSERT OR REPLACE INTO weight_logs (id, user_id, date, kg, created_at) VALUES (?, ?, ?, ?, ?)",
                  (f"wt_{today}_{user['id']}", user["id"], today, _safe_float(data["weight"]), now))

    conn.commit()
    c.execute("SELECT * FROM profiles WHERE user_id = ?", (user["id"],))
    saved = dict(c.fetchone())
    return jsonify({"ok": True, "data": saved})


# ==============================================================================
# API: NUTRITION & FOODS
# ==============================================================================

@app.route("/api/nutrition", methods=["GET", "POST", "DELETE", "OPTIONS"])
def api_nutrition():
    if request.method == "OPTIONS":
        return jsonify({"ok": True})

    conn = g.db
    user, err = _auth_required_tuple()
    if err:
        return err

    date = request.args.get("date") or _today_iso()
    c = conn.cursor()

    if request.method == "GET":
        c.execute("SELECT * FROM nutrition_logs WHERE user_id = ? AND date = ? ORDER BY created_at ASC",
                  (user["id"], date))
        rows = [dict(r) for r in c.fetchall()]
        meals = {"breakfast": [], "lunch": [], "dinner": [], "snacks": []}
        totals = {"calories": 0, "protein": 0, "carbs": 0, "fat": 0, "fiber": 0}

        for row in rows:
            m = row["meal"]
            if m not in meals:
                meals[m] = []
            item = {
                "logId": row["id"], "name": row["name"], "calories": row["calories"],
                "protein": row["protein"], "carbs": row["carbs"], "fat": row["fat"],
                "fiber": row["fiber"], "serving": row["serving"], "qty": row["qty"]
            }
            meals[m].append(item)
            q = row["qty"] or 1
            totals["calories"] += int(row["calories"] * q)
            totals["protein"] += row["protein"] * q
            totals["carbs"] += row["carbs"] * q
            totals["fat"] += row["fat"] * q
            totals["fiber"] += row["fiber"] * q

        for k in totals:
            totals[k] = round(totals[k])
        return jsonify({"ok": True, "meals": meals, "totals": totals, "date": date})

    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        meal = data.get("meal", "breakfast")
        food = data.get("food", {})
        log_id = _gen_id("nl_")
        now = _now_iso()

        c.execute("""
            INSERT INTO nutrition_logs (id, user_id, date, meal, name, calories, protein, carbs, fat, fiber, serving, qty, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (log_id, user["id"], date, meal, _sanitize_str(food.get("name", "Custom Food"), 200),
              _safe_int(food.get("calories", 0)), _safe_float(food.get("protein", 0)),
              _safe_float(food.get("carbs", 0)), _safe_float(food.get("fat", 0)),
              _safe_float(food.get("fiber", 0)), food.get("serving", "1 serving"),
              _safe_float(food.get("qty", 1)), now))
        conn.commit()
        return jsonify({"ok": True, "logId": log_id, "message": "Food logged successfully."})

    if request.method == "DELETE":
        log_id = request.args.get("id")
        if log_id:
            # Users can only delete their own logs
            c.execute("DELETE FROM nutrition_logs WHERE id = ? AND user_id = ?", (log_id, user["id"]))
            conn.commit()
        return jsonify({"ok": True, "message": "Food removed."})


@app.route("/api/foods", methods=["GET", "POST", "DELETE", "OPTIONS"])
def api_foods():
    if request.method == "OPTIONS":
        return jsonify({"ok": True})

    conn = g.db
    c = conn.cursor()

    if request.method == "GET":
        q = (request.args.get("q") or "").lower()
        cat = request.args.get("cat") or ""
        sql = "SELECT * FROM foods WHERE 1=1"
        params = []
        if q:
            sql += " AND LOWER(name) LIKE ?"
            params.append(f"%{q}%")
        if cat and cat != "All":
            sql += " AND category = ?"
            params.append(cat)
        sql += " ORDER BY name ASC LIMIT 200"
        c.execute(sql, params)
        foods = [dict(r) for r in c.fetchall()]
        return jsonify({"ok": True, "data": foods})

    if request.method == "POST":
        user = get_current_user(conn)
        if not user:
            return jsonify({"ok": False, "error": "Authentication required."}), 401
        data = request.get_json(silent=True) or {}
        fid = _gen_id("c_")
        c.execute("""
            INSERT INTO foods (id, name, category, calories, protein, carbs, fat, fiber, serving, is_custom, created_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
        """, (fid, _sanitize_str(data.get("name"), 200), data.get("category", "General"),
              _safe_int(data.get("calories", 0)), _safe_float(data.get("protein", 0)),
              _safe_float(data.get("carbs", 0)), _safe_float(data.get("fat", 0)),
              _safe_float(data.get("fiber", 0)), data.get("serving", "1 serving"), user["id"]))
        conn.commit()
        return jsonify({"ok": True, "id": fid, "message": "Custom food added."})

    if request.method == "DELETE":
        user = get_current_user(conn)
        if not user or user.get("role") != "admin":
            return jsonify({"ok": False, "error": "Admin access required."}), 403
        fid = request.args.get("id")
        if fid:
            c.execute("DELETE FROM foods WHERE id = ?", (fid,))
            conn.commit()
        return jsonify({"ok": True, "message": "Food deleted."})


# ==============================================================================
# API: WORKOUTS
# ==============================================================================

@app.route("/api/workouts", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])
def api_workouts():
    if request.method == "OPTIONS":
        return jsonify({"ok": True})

    conn = g.db
    c = conn.cursor()

    if request.method == "GET":
        c.execute("SELECT * FROM workouts WHERE status = 'published' ORDER BY id ASC")
        rows = [dict(r) for r in c.fetchall()]
        for r in rows:
            r["exercises"] = json.loads(r["exercises_json"] or "[]")
        return jsonify({"ok": True, "data": rows})

    if request.method == "POST":
        user = get_current_user(conn)
        if not user or user.get("role") != "admin":
            return jsonify({"ok": False, "error": "Admin access required."}), 403
        data = request.get_json(silent=True) or {}
        wid = _gen_id("w_")
        c.execute("""
            INSERT INTO workouts (id, name, category, level, minutes, calories, equipment, focus, exercises_json, is_custom, premium, status, created_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, 'published', ?)
        """, (wid, _sanitize_str(data.get("name"), 200), data.get("category", "Strength"),
              data.get("level", "Beginner"), _safe_int(data.get("minutes", 30)),
              _safe_int(data.get("calories", 200)), data.get("equipment", "None"),
              data.get("focus", "Full Body"), json.dumps(data.get("exercises", [])),
              _safe_int(data.get("premium", 0)), user["id"]))
        conn.commit()
        return jsonify({"ok": True, "id": wid, "message": "Workout added."})

    if request.method == "PUT":
        user = get_current_user(conn)
        if not user or user.get("role") != "admin":
            return jsonify({"ok": False, "error": "Admin access required."}), 403
        data = request.get_json(silent=True) or {}
        wid = data.get("id")
        if not wid:
            return jsonify({"ok": False, "error": "Workout ID required."}), 400
        fields = []
        vals = []
        for f in ["name", "category", "level", "minutes", "calories", "equipment", "focus", "premium", "status"]:
            if f in data:
                fields.append(f"{f} = ?")
                vals.append(data[f])
        if "exercises" in data:
            fields.append("exercises_json = ?")
            vals.append(json.dumps(data["exercises"]))
        if fields:
            vals.append(wid)
            c.execute(f"UPDATE workouts SET {', '.join(fields)} WHERE id = ?", vals)
            conn.commit()
        return jsonify({"ok": True, "message": "Workout updated."})

    if request.method == "DELETE":
        user = get_current_user(conn)
        if not user or user.get("role") != "admin":
            return jsonify({"ok": False, "error": "Admin access required."}), 403
        wid = request.args.get("id")
        if wid:
            c.execute("UPDATE workouts SET status = 'archived' WHERE id = ?", (wid,))
            conn.commit()
        return jsonify({"ok": True, "message": "Workout archived."})


@app.route("/api/workouts/complete", methods=["POST", "OPTIONS"])
def api_workout_complete():
    if request.method == "OPTIONS":
        return jsonify({"ok": True})

    conn = g.db
    user, err = _auth_required_tuple()
    if err:
        return err

    data = request.get_json(silent=True) or {}
    wid = _gen_id("wkl_")
    date = data.get("date") or _today_iso()
    now = _now_iso()

    c = conn.cursor()
    c.execute("""
        INSERT INTO workout_logs (id, user_id, date, name, minutes, calories, category, completed, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)
    """, (wid, user["id"], date, _sanitize_str(data.get("name", "Completed Workout"), 200),
          _safe_int(data.get("minutes", 30)), _safe_int(data.get("calories", 200)),
          data.get("category", "Fitness"), now))

    c.execute("INSERT OR REPLACE INTO habit_logs (id, user_id, date, habit_id, completed, created_at) VALUES (?, ?, ?, 'workout', 1, ?)",
              (f"hb_{date}_{user['id']}_workout", user["id"], date, now))

    conn.commit()
    return jsonify({"ok": True, "id": wid, "message": "Workout logged!"})


@app.route("/api/workouts/history", methods=["GET"])
def api_workout_history():
    conn = g.db
    user, err = _auth_required_tuple()
    if err:
        return err

    c = conn.cursor()
    limit = min(_safe_int(request.args.get("limit"), 50), 200)
    c.execute("SELECT * FROM workout_logs WHERE user_id = ? ORDER BY date DESC, created_at DESC LIMIT ?",
              (user["id"], limit))
    rows = [dict(r) for r in c.fetchall()]
    return jsonify({"ok": True, "data": rows})


@app.route("/api/meal-plans", methods=["GET"])
def api_meal_plans():
    conn = g.db
    c = conn.cursor()
    c.execute("SELECT * FROM meal_plans ORDER BY id ASC")
    rows = [dict(r) for r in c.fetchall()]
    for r in rows:
        r["days"] = json.loads(r["days_json"] or "{}")
    return jsonify({"ok": True, "data": rows})


# ==============================================================================
# API: TRACKERS (WATER, SLEEP, HABITS, STEPS, WEIGHT, PROGRESS)
# ==============================================================================

@app.route("/api/water", methods=["GET", "POST", "OPTIONS"])
def api_water():
    if request.method == "OPTIONS":
        return jsonify({"ok": True})

    conn = g.db
    user, err = _auth_required_tuple()
    if err:
        return err
    date = request.args.get("date") or _today_iso()
    c = conn.cursor()

    if request.method == "GET":
        c.execute("SELECT * FROM water_logs WHERE user_id = ? AND date = ? ORDER BY created_at ASC",
                  (user["id"], date))
        rows = [dict(r) for r in c.fetchall()]
        total = sum(r["ml"] for r in rows)
        return jsonify({"ok": True, "total": total, "entries": rows, "date": date})

    data = request.get_json(silent=True) or {}
    ml = _safe_int(data.get("ml", 250))
    wid = _gen_id("wt_")
    now = _now_iso()

    c.execute("INSERT INTO water_logs (id, user_id, date, ml, created_at) VALUES (?, ?, ?, ?, ?)",
              (wid, user["id"], date, ml, now))
    conn.commit()

    c.execute("SELECT SUM(ml) FROM water_logs WHERE user_id = ? AND date = ?", (user["id"], date))
    total = c.fetchone()[0] or 0
    return jsonify({"ok": True, "total": total, "id": wid})


@app.route("/api/sleep", methods=["GET", "POST", "OPTIONS"])
def api_sleep():
    if request.method == "OPTIONS":
        return jsonify({"ok": True})

    conn = g.db
    user, err = _auth_required_tuple()
    if err:
        return err
    date = request.args.get("date") or _today_iso()
    c = conn.cursor()

    if request.method == "GET":
        c.execute("SELECT * FROM sleep_logs WHERE user_id = ? AND date = ? ORDER BY created_at DESC LIMIT 1",
                  (user["id"], date))
        row = c.fetchone()
        return jsonify({"ok": True, "data": dict(row) if row else None})

    data = request.get_json(silent=True) or {}
    sid = _gen_id("sl_")
    now = _now_iso()

    c.execute("""
        INSERT OR REPLACE INTO sleep_logs (id, user_id, date, bedtime, wake, hours, quality, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (sid, user["id"], date, data.get("bedtime", "23:00"), data.get("wake", "07:00"),
          _safe_float(data.get("hours", 8.0)), data.get("quality", "Rested"), now))
    conn.commit()
    return jsonify({"ok": True, "message": "Sleep logged."})


@app.route("/api/habits", methods=["GET", "POST", "OPTIONS"])
def api_habits():
    if request.method == "OPTIONS":
        return jsonify({"ok": True})

    conn = g.db
    user, err = _auth_required_tuple()
    if err:
        return err
    date = request.args.get("date") or _today_iso()
    c = conn.cursor()

    if request.method == "GET":
        c.execute("SELECT habit_id, completed FROM habit_logs WHERE user_id = ? AND date = ?",
                  (user["id"], date))
        habits = {r["habit_id"]: bool(r["completed"]) for r in c.fetchall()}
        return jsonify({"ok": True, "data": habits, "date": date})

    data = request.get_json(silent=True) or {}
    hid = data.get("habit_id")
    if not hid:
        return jsonify({"ok": False, "error": "habit_id is required."}), 400

    c.execute("SELECT completed FROM habit_logs WHERE user_id = ? AND date = ? AND habit_id = ?",
              (user["id"], date, hid))
    row = c.fetchone()
    new_status = 0 if (row and row["completed"]) else 1
    now = _now_iso()

    c.execute("""
        INSERT OR REPLACE INTO habit_logs (id, user_id, date, habit_id, completed, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (f"hb_{date}_{user['id']}_{hid}", user["id"], date, hid, new_status, now))
    conn.commit()

    c.execute("SELECT habit_id, completed FROM habit_logs WHERE user_id = ? AND date = ?",
              (user["id"], date))
    habits = {r["habit_id"]: bool(r["completed"]) for r in c.fetchall()}
    return jsonify({"ok": True, "data": habits})


@app.route("/api/steps", methods=["GET", "POST", "OPTIONS"])
def api_steps():
    if request.method == "OPTIONS":
        return jsonify({"ok": True})

    conn = g.db
    user, err = _auth_required_tuple()
    if err:
        return err
    date = request.args.get("date") or _today_iso()
    c = conn.cursor()

    if request.method == "GET":
        c.execute("SELECT steps FROM step_logs WHERE user_id = ? AND date = ?", (user["id"], date))
        row = c.fetchone()
        return jsonify({"ok": True, "steps": row["steps"] if row else 0, "date": date})

    data = request.get_json(silent=True) or {}
    steps = _safe_int(data.get("steps", 0))
    now = _now_iso()
    c.execute("""
        INSERT OR REPLACE INTO step_logs (id, user_id, date, steps, created_at)
        VALUES (?, ?, ?, ?, ?)
    """, (f"st_{date}_{user['id']}", user["id"], date, steps, now))
    conn.commit()
    return jsonify({"ok": True, "steps": steps})


@app.route("/api/weight", methods=["POST", "OPTIONS"])
def api_weight():
    if request.method == "OPTIONS":
        return jsonify({"ok": True})

    conn = g.db
    user, err = _auth_required_tuple()
    if err:
        return err
    data = request.get_json(silent=True) or {}
    kg = _safe_float(data.get("kg", 75))
    date = data.get("date") or _today_iso()
    now = _now_iso()

    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO weight_logs (id, user_id, date, kg, created_at) VALUES (?, ?, ?, ?, ?)",
              (f"wt_{date}_{user['id']}", user["id"], date, kg, now))
    c.execute("UPDATE profiles SET weight = ?, updated_at = ? WHERE user_id = ?", (kg, now, user["id"]))
    conn.commit()
    return jsonify({"ok": True, "weight": kg, "date": date})


@app.route("/api/progress", methods=["GET"])
def api_progress():
    conn = g.db
    user, err = _auth_required_tuple()
    if err:
        return err

    c = conn.cursor()
    c.execute("SELECT * FROM profiles WHERE user_id = ?", (user["id"],))
    prof = dict(c.fetchone() or {})

    c.execute("SELECT date, kg FROM weight_logs WHERE user_id = ? ORDER BY date ASC", (user["id"],))
    weights = [dict(r) for r in c.fetchall()]

    curr_wt = weights[-1]["kg"] if weights else prof.get("weight", 75.0)
    start_wt = prof.get("start_weight", curr_wt)
    target_wt = prof.get("target_weight", 70.0)
    ht = prof.get("height", 175)
    bmi_val = round(curr_wt / ((ht / 100) ** 2), 1) if ht else 23.0

    total_delta = abs(start_wt - target_wt) or 1
    done_delta = abs(start_wt - curr_wt)
    percent = round(min(100, max(0, (done_delta / total_delta) * 100)))

    return jsonify({
        "ok": True,
        "current": curr_wt,
        "start": start_wt,
        "target": target_wt,
        "lost": round(start_wt - curr_wt, 1),
        "bmi": bmi_val,
        "percent": percent,
        "weights": weights
    })


# ==============================================================================
# API: FITNESS GOALS & BODY MEASUREMENTS
# ==============================================================================

@app.route("/api/goals", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])
@require_login
def api_goals():
    if request.method == "OPTIONS":
        return jsonify({"ok": True})

    conn = g.db
    c = conn.cursor()

    if request.method == "GET":
        c.execute("SELECT * FROM fitness_goals WHERE user_id = ? ORDER BY created_at DESC", (g.user["id"],))
        goals = [dict(r) for r in c.fetchall()]
        return jsonify({"ok": True, "data": goals})

    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        gid = _gen_id("goal_")
        now = _now_iso()
        c.execute("""
            INSERT INTO fitness_goals (id, user_id, goal_type, target_value, current_value, unit, status, start_date, target_date, created_at)
            VALUES (?, ?, ?, ?, ?, ?, 'active', ?, ?, ?)
        """, (gid, g.user["id"], _sanitize_str(data.get("goal_type", "weight_loss"), 50),
              _safe_float(data.get("target_value")), _safe_float(data.get("current_value")),
              data.get("unit", "kg"), data.get("start_date", _today_iso()),
              data.get("target_date"), now))
        conn.commit()
        return jsonify({"ok": True, "id": gid, "message": "Goal created."})

    if request.method == "PUT":
        data = request.get_json(silent=True) or {}
        gid = data.get("id")
        if not gid:
            return jsonify({"ok": False, "error": "Goal ID required."}), 400
        fields = []
        vals = []
        for f in ["current_value", "status", "target_date"]:
            if f in data:
                fields.append(f"{f} = ?")
                vals.append(data[f])
        if fields:
            vals.append(gid)
            vals.append(g.user["id"])
            c.execute(f"UPDATE fitness_goals SET {', '.join(fields)} WHERE id = ? AND user_id = ?", vals)
            conn.commit()
        return jsonify({"ok": True, "message": "Goal updated."})

    if request.method == "DELETE":
        gid = request.args.get("id")
        if gid:
            c.execute("DELETE FROM fitness_goals WHERE id = ? AND user_id = ?", (gid, g.user["id"]))
            conn.commit()
        return jsonify({"ok": True, "message": "Goal deleted."})


@app.route("/api/measurements", methods=["GET", "POST", "DELETE", "OPTIONS"])
@require_login
def api_measurements():
    if request.method == "OPTIONS":
        return jsonify({"ok": True})

    conn = g.db
    c = conn.cursor()

    if request.method == "GET":
        limit = min(_safe_int(request.args.get("limit"), 30), 200)
        c.execute("SELECT * FROM body_measurements WHERE user_id = ? ORDER BY date DESC LIMIT ?",
                  (g.user["id"], limit))
        measurements = [dict(r) for r in c.fetchall()]
        return jsonify({"ok": True, "data": measurements})

    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        mid = _gen_id("meas_")
        now = _now_iso()
        c.execute("""
            INSERT INTO body_measurements (id, user_id, date, chest, waist, hips, arms, thighs, neck, body_fat, notes, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (mid, g.user["id"], data.get("date", _today_iso()),
              _safe_float(data.get("chest")), _safe_float(data.get("waist")),
              _safe_float(data.get("hips")), _safe_float(data.get("arms")),
              _safe_float(data.get("thighs")), _safe_float(data.get("neck")),
              _safe_float(data.get("body_fat")), _sanitize_str(data.get("notes", ""), 500), now))
        conn.commit()
        return jsonify({"ok": True, "id": mid, "message": "Measurements recorded."})

    if request.method == "DELETE":
        mid = request.args.get("id")
        if mid:
            c.execute("DELETE FROM body_measurements WHERE id = ? AND user_id = ?", (mid, g.user["id"]))
            conn.commit()
        return jsonify({"ok": True, "message": "Measurement deleted."})


# ==============================================================================
# API: TICKETS & SUPPORT
# ==============================================================================

@app.route("/api/tickets", methods=["GET", "POST", "PUT", "OPTIONS"])
def api_tickets():
    if request.method == "OPTIONS":
        return jsonify({"ok": True})

    conn = g.db
    user = get_current_user(conn)
    c = conn.cursor()

    if request.method == "GET":
        if not user:
            return jsonify({"ok": False, "error": "Authentication required."}), 401
        if user.get("role") == "admin":
            c.execute("SELECT * FROM tickets ORDER BY created_at DESC")
        else:
            c.execute("SELECT * FROM tickets WHERE email = ? ORDER BY created_at DESC", (user["email"],))
        rows = [dict(r) for r in c.fetchall()]
        for r in rows:
            r["messages"] = json.loads(r["messages_json"] or "[]")
        return jsonify({"ok": True, "data": rows})

    if request.method == "POST":
        if not user:
            return jsonify({"ok": False, "error": "Authentication required."}), 401
        data = request.get_json(silent=True) or {}
        tid = "TK-" + str(secrets.randbelow(9000) + 1000)
        now = _now_iso()
        msg = _sanitize_str(data.get("message", ""), 2000)
        if len(msg) < 5:
            return jsonify({"ok": False, "error": "Message is required."}), 400
        msgs = [{"from": "user", "text": msg, "at": now}]

        ticket_email = user["email"]
        ticket_name = user["name"]

        c.execute("""
            INSERT INTO tickets (id, email, name, subject, category, priority, status, created_at, messages_json)
            VALUES (?, ?, ?, ?, ?, ?, 'open', ?, ?)
        """, (tid, ticket_email, _sanitize_str(ticket_name, 100),
              _sanitize_str(data.get("subject", "Inquiry"), 200),
              data.get("category", "Technical"), data.get("priority", "medium"),
              now, json.dumps(msgs)))
        conn.commit()
        return jsonify({"ok": True, "id": tid, "message": "Support ticket created."})

    if request.method == "PUT":
        if not user:
            return jsonify({"ok": False, "error": "Authentication required."}), 401
        data = request.get_json(silent=True) or {}
        tid = data.get("id")
        if not tid:
            return jsonify({"ok": False, "error": "Ticket ID required."}), 400

        is_admin = user.get("role") == "admin"
        reply_text = (data.get("reply") or "").strip()

        if is_admin and "status" in data:
            c.execute("UPDATE tickets SET status = ? WHERE id = ?", (data["status"], tid))

        if reply_text:
            if is_admin:
                c.execute("SELECT messages_json FROM tickets WHERE id = ?", (tid,))
            else:
                c.execute("SELECT messages_json FROM tickets WHERE id = ? AND email = ?", (tid, user["email"]))
            row = c.fetchone()
            if not row:
                return jsonify({"ok": False, "error": "Ticket not found or permission denied."}), 404

            msgs = json.loads(row[0] or "[]")
            sender = "admin" if is_admin else "user"
            msgs.append({"from": sender, "text": _sanitize_str(reply_text, 2000), "at": _now_iso()})
            new_status = data.get("status", "pending") if is_admin else "open"
            c.execute("UPDATE tickets SET messages_json = ?, status = ? WHERE id = ?", (json.dumps(msgs), new_status, tid))
        elif not is_admin:
            return jsonify({"ok": False, "error": "Only administrators can update ticket status without a reply."}), 403

        conn.commit()
        return jsonify({"ok": True, "message": "Ticket updated."})


# ==============================================================================
# API: CONTACT ENQUIRIES
# ==============================================================================

@app.route("/api/contact", methods=["POST", "OPTIONS"])
def api_contact():
    if request.method == "OPTIONS":
        return jsonify({"ok": True})

    ip = _get_client_ip()
    if not _check_rate_limit(f"contact:{ip}", 3, 900):
        return jsonify({"ok": False, "error": "Too many submissions. Try again later."}), 429

    data = request.get_json(silent=True) or {}
    if (data.get("website") or data.get("company_url") or "").strip():
        return jsonify({"ok": True, "message": "Your enquiry has been submitted. We'll get back to you soon."})
    name = _sanitize_str(data.get("name", ""), 100)
    email = (data.get("email") or "").strip().lower()[:254]
    subject = _sanitize_str(data.get("subject", ""), 200)
    message = _sanitize_str(data.get("message", ""), 2000)

    if len(name) < 2:
        return jsonify({"ok": False, "error": "Name is required."}), 400
    if "@" not in email:
        return jsonify({"ok": False, "error": "Valid email is required."}), 400
    if len(subject) < 3:
        return jsonify({"ok": False, "error": "Subject is required."}), 400
    if len(message) < 10:
        return jsonify({"ok": False, "error": "Message must be at least 10 characters."}), 400

    conn = g.db
    cid = _gen_id("cq_")
    now = _now_iso()
    conn.execute("""
        INSERT INTO contact_enquiries (id, name, email, phone, subject, message, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, 'new', ?)
    """, (cid, name, email, _sanitize_str(data.get("phone", ""), 30), subject, message, now))
    conn.commit()
    send_contact_ack(email, name)

    return jsonify({"ok": True, "id": cid, "message": "Your enquiry has been submitted. We'll get back to you soon."})


# ==============================================================================
# API: PAYMENTS & SUBSCRIPTIONS (Razorpay)
# ==============================================================================

@app.route("/api/membership-plans", methods=["GET"])
def api_membership_plans():
    """Get active membership plans."""
    conn = g.db
    c = conn.cursor()
    c.execute("SELECT * FROM membership_plans WHERE active = 1 ORDER BY price ASC")
    plans = []
    for r in c.fetchall():
        plan = dict(r)
        plan["features"] = json.loads(plan.get("features_json") or "[]")
        plans.append(plan)
    return jsonify({"ok": True, "data": plans})


@app.route("/api/subscription", methods=["GET"])
@require_login
def api_subscription():
    """Get current user's subscription status."""
    conn = g.db
    c = conn.cursor()
    user = g.user
    today = _today_iso()

    # Check if premium has expired
    if user.get("plan") == "premium" and user.get("plan_expiry"):
        if user["plan_expiry"] < today:
            c.execute("UPDATE users SET plan = 'free', payment_status = 'expired' WHERE id = ?", (user["id"],))
            conn.commit()
            user["plan"] = "free"
            user["payment_status"] = "expired"

    # Get payment history
    c.execute("""
        SELECT o.*, p.gateway_payment_id, p.method as payment_method, p.status as payment_status
        FROM orders o
        LEFT JOIN payments p ON o.id = p.order_id
        WHERE o.user_id = ?
        ORDER BY o.created_at DESC LIMIT 20
    """, (user["id"],))
    orders = [dict(r) for r in c.fetchall()]

    return jsonify({
        "ok": True,
        "plan": user["plan"],
        "planType": user.get("plan_type", ""),
        "planStart": user.get("plan_start", ""),
        "planExpiry": user.get("plan_expiry", ""),
        "paymentStatus": user.get("payment_status", ""),
        "orders": orders,
    })


@app.route("/api/user/orders", methods=["GET"])
@require_login
def api_user_orders():
    """Retrieve verified order and receipt history for current user."""
    conn = g.db
    c = conn.cursor()
    c.execute("""
        SELECT o.id, o.amount, o.currency, o.status, o.coupon_code, o.discount, o.gst,
               o.created_at, p.name as plan_name, p.slug as plan_slug,
               pay.gateway_payment_id, pay.method as payment_method
        FROM orders o
        LEFT JOIN membership_plans p ON o.plan_id = p.id
        LEFT JOIN payments pay ON o.id = pay.order_id
        WHERE o.user_id = ?
        ORDER BY o.created_at DESC
    """, (g.user["id"],))
    orders = [dict(r) for r in c.fetchall()]
    return jsonify({"ok": True, "data": orders})


@app.route("/api/payments/create-order", methods=["POST", "OPTIONS"])
@require_login
def api_create_order():
    """Create a Razorpay order for subscription payment."""
    if request.method == "OPTIONS":
        return jsonify({"ok": True})

    data = request.get_json(silent=True) or {}
    plan_slug = data.get("plan", "yearly")
    coupon_code = (data.get("coupon") or "").strip().upper()

    conn = g.db
    c = conn.cursor()

    # Get plan
    c.execute("SELECT * FROM membership_plans WHERE slug = ? AND active = 1", (plan_slug,))
    plan_row = c.fetchone()
    if not plan_row:
        return jsonify({"ok": False, "error": "Invalid plan selected."}), 400
    plan = dict(plan_row)

    if plan["price"] == 0:
        return jsonify({"ok": False, "error": "Free plan does not require payment."}), 400

    # Calculate pricing
    base_price = plan["price"]
    discount = 0
    if coupon_code == "FIT20":
        discount = round(base_price * 0.2)

    subtotal = base_price - discount
    gst = round(subtotal * 0.18)
    total = subtotal + gst
    total_paise = total * 100  # Razorpay uses paise

    # Create internal order
    order_id = _gen_id("ord_")
    now = _now_iso()

    gateway_order_id = None

    if rzp_client:
        try:
            rzp_order = rzp_client.order.create({
                "amount": total_paise,
                "currency": "INR",
                "receipt": order_id,
                "notes": {
                    "user_id": g.user["id"],
                    "plan": plan_slug,
                    "user_email": g.user["email"]
                }
            })
            gateway_order_id = rzp_order["id"]
        except Exception:
            return jsonify({"ok": False, "error": "Payment gateway error. Try again or contact support."}), 500
    elif _demo_payments_allowed():
        gateway_order_id = f"order_demo_{secrets.token_hex(8)}"
    else:
        return jsonify({
            "ok": False,
            "error": "Online payments are not configured. Set RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET."
        }), 503

    c.execute("""
        INSERT INTO orders (id, user_id, plan_id, amount, currency, gateway_order_id, coupon_code, discount, gst, status, created_at, updated_at)
        VALUES (?, ?, ?, ?, 'INR', ?, ?, ?, ?, 'created', ?, ?)
    """, (order_id, g.user["id"], plan["id"], total, gateway_order_id, coupon_code or None,
          discount, gst, now, now))
    conn.commit()

    return jsonify({
        "ok": True,
        "orderId": order_id,
        "gatewayOrderId": gateway_order_id,
        "amount": total,
        "amountPaise": total_paise,
        "currency": "INR",
        "planName": plan["name"],
        "basePrice": base_price,
        "discount": discount,
        "gst": gst,
        "total": total,
        "razorpayConfigured": rzp_client is not None,
        "razorpayKeyId": RAZORPAY_KEY_ID if rzp_client else "",
        "userEmail": g.user["email"],
        "userName": g.user["name"],
    })


@app.route("/api/payments/verify", methods=["POST", "OPTIONS"])
@require_login
def api_verify_payment():
    """Verify Razorpay payment signature and activate subscription."""
    if request.method == "OPTIONS":
        return jsonify({"ok": True})

    data = request.get_json(silent=True) or {}
    order_id = data.get("orderId", "")
    razorpay_payment_id = data.get("razorpayPaymentId", "")
    razorpay_signature = data.get("razorpaySignature", "")
    razorpay_order_id = data.get("razorpayOrderId", "")

    conn = g.db
    c = conn.cursor()

    # Get our order
    c.execute("SELECT * FROM orders WHERE id = ? AND user_id = ?", (order_id, g.user["id"]))
    order_row = c.fetchone()
    if not order_row:
        return jsonify({"ok": False, "error": "Order not found."}), 404
    order = dict(order_row)

    if order["status"] == "paid":
        return jsonify({
            "ok": True,
            "message": "This order was already paid.",
            "plan": "premium",
            "planExpiry": g.user.get("plan_expiry"),
        })

    now = _now_iso()
    verified = False

    if rzp_client and RAZORPAY_KEY_SECRET:
        try:
            verify_data = {
                "razorpay_order_id": razorpay_order_id or order.get("gateway_order_id"),
                "razorpay_payment_id": razorpay_payment_id,
                "razorpay_signature": razorpay_signature,
            }
            rzp_client.utility.verify_payment_signature(verify_data)
            verified = True
        except Exception:
            c.execute("""
                INSERT INTO payments (id, order_id, user_id, gateway_payment_id, gateway_signature, amount, currency, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, 'INR', 'failed', ?)
            """, (_gen_id("pay_"), order_id, g.user["id"], razorpay_payment_id, razorpay_signature, order["amount"], now))
            c.execute("UPDATE orders SET status = 'failed', updated_at = ? WHERE id = ?", (now, order_id))
            conn.commit()
            return jsonify({"ok": False, "error": "Payment verification failed. If you were charged, please contact support."}), 400
    elif _demo_payments_allowed():
        verified = True
        if not razorpay_payment_id:
            razorpay_payment_id = f"pay_demo_{secrets.token_hex(8)}"
    else:
        return jsonify({"ok": False, "error": "Payment gateway is not configured. This order cannot be marked paid."}), 503

    if not verified:
        return jsonify({"ok": False, "error": "Payment could not be verified."}), 400

    updated = _activate_paid_order(
        conn, order, payment_id=razorpay_payment_id, signature=razorpay_signature,
        method=data.get("method", "razorpay")
    )
    c.execute("SELECT email FROM users WHERE id = ?", (g.user["id"],))
    email_row = c.fetchone()
    if email_row:
        send_payment_confirmation(
            email_row[0], updated.get("_plan_name", "Premium"),
            order["amount"], updated.get("_expiry", ""), order_id
        )

    return jsonify({
        "ok": True,
        "message": "Payment verified! Your premium plan is now active.",
        "plan": "premium",
        "planExpiry": updated.get("_expiry"),
    })


@app.route("/api/payments/webhook", methods=["POST"])
def api_payment_webhook():
    """Handle Razorpay webhook events with signature verification."""
    if not RAZORPAY_WEBHOOK_SECRET:
        return jsonify({"ok": False, "error": "Webhook not configured."}), 501

    # Verify webhook signature
    webhook_signature = request.headers.get("X-Razorpay-Signature", "")
    webhook_body = request.get_data()

    try:
        expected_signature = hmac.new(
            RAZORPAY_WEBHOOK_SECRET.encode('utf-8'),
            webhook_body,
            hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(webhook_signature, expected_signature):
            return jsonify({"ok": False, "error": "Invalid webhook signature."}), 401
    except Exception:
        return jsonify({"ok": False, "error": "Signature verification failed."}), 401

    event = request.get_json(silent=True) or {}
    event_type = event.get("event", "")
    payload = event.get("payload", {})
    event_id = event.get("id") or f"{event_type}:{payload.get('payment', {}).get('entity', {}).get('id', secrets.token_hex(8))}"

    conn = g.db
    c = conn.cursor()
    now = _now_iso()

    try:
        c.execute(
            "INSERT INTO webhook_events (id, provider, event_id, event_type, processed_at) VALUES (?, 'razorpay', ?, ?, ?)",
            (_gen_id("wh_"), event_id, event_type, now),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        return jsonify({"ok": True, "message": "Already processed."})

    if event_type == "payment.captured":
        payment_entity = payload.get("payment", {}).get("entity", {})
        rzp_order_id = payment_entity.get("order_id", "")
        rzp_payment_id = payment_entity.get("id", "")

        # Check for duplicate processing (idempotency)
        c.execute("SELECT id FROM payments WHERE gateway_payment_id = ?", (rzp_payment_id,))
        if c.fetchone():
            return jsonify({"ok": True, "message": "Already processed."})

        # Find our order
        c.execute("SELECT * FROM orders WHERE gateway_order_id = ?", (rzp_order_id,))
        order_row = c.fetchone()
        if order_row:
            order = dict(order_row)
            if order["status"] != "paid":
                _activate_paid_order(
                    conn, order, payment_id=rzp_payment_id,
                    method=payment_entity.get("method", "razorpay")
                )

    elif event_type == "payment.failed":
        payment_entity = payload.get("payment", {}).get("entity", {})
        rzp_order_id = payment_entity.get("order_id", "")
        c.execute("UPDATE orders SET status = 'failed', updated_at = ? WHERE gateway_order_id = ?", (now, rzp_order_id))
        conn.commit()

    return jsonify({"ok": True})


@app.route("/api/subscription/cancel", methods=["POST", "OPTIONS"])
@require_login
def api_cancel_subscription():
    """Cancel premium subscription (keeps access until expiry)."""
    if request.method == "OPTIONS":
        return jsonify({"ok": True})

    conn = g.db
    c = conn.cursor()
    now = _now_iso()

    if g.user.get("plan") != "premium":
        return jsonify({"ok": False, "error": "No active premium subscription."}), 400

    # Don't revoke immediately — keep until expiry
    c.execute("UPDATE users SET payment_status = 'cancelled' WHERE id = ?", (g.user["id"],))

    c.execute("""
        INSERT INTO notifications (id, user_id, type, title, message, created_at)
        VALUES (?, ?, 'subscription', 'Subscription Cancelled',
                'Your premium access continues until your current billing period ends.', ?)
    """, (_gen_id("notif_"), g.user["id"], now))
    conn.commit()

    return jsonify({
        "ok": True,
        "message": f"Premium cancelled. Access continues until {g.user.get('plan_expiry', 'end of billing period')}."
    })


# ==============================================================================
# API: AI COACH (OpenAI, Gemini, Groq, Claude + Context-Aware Fallback Engine)
# ==============================================================================

def _get_user_fitness_context(user_id=None, profile_override=None):
    """Retrieve full user metrics and today's logs to inject into the AI system prompt."""
    context = {
        "name": "Member",
        "age": 28,
        "gender": "male",
        "height": 175,
        "weight": 70,
        "target_weight": 68,
        "activity": "moderate",
        "goal": "stay fit",
        "diet": "vegetarian",
        "calories_consumed": 0,
        "calories_target": 2200,
        "protein_consumed": 0,
        "protein_target": 120,
        "carbs_consumed": 0,
        "carbs_target": 250,
        "fat_consumed": 0,
        "fat_target": 70,
        "water_ml": 0,
        "water_target": 3000,
        "sleep_hours": 0,
        "sleep_quality": "normal",
        "streak": 5,
        "workouts_today": []
    }

    if profile_override and isinstance(profile_override, dict):
        for k in ["name", "age", "gender", "height", "weight", "targetWeight", "goal", "diet", "activity", "streak"]:
            if k in profile_override and profile_override[k]:
                target_key = "target_weight" if k == "targetWeight" else k
                context[target_key] = profile_override[k]

    if user_id:
        try:
            conn = get_db()
            c = conn.cursor()
            today = _today_iso()

            # Profile
            c.execute("SELECT u.name, p.* FROM users u LEFT JOIN profiles p ON u.id = p.user_id WHERE u.id = ?", (user_id,))
            row = c.fetchone()
            if row:
                r = dict(row)
                if r.get("name"): context["name"] = r["name"]
                if r.get("age"): context["age"] = r["age"]
                if r.get("gender"): context["gender"] = r["gender"]
                if r.get("height"): context["height"] = r["height"]
                if r.get("weight"): context["weight"] = r["weight"]
                if r.get("target_weight"): context["target_weight"] = r["target_weight"]
                if r.get("goal"): context["goal"] = r["goal"]
                if r.get("diet"): context["diet"] = r["diet"]
                if r.get("activity"): context["activity"] = r["activity"]

            # Calculate BMR & Targets
            h = float(context["height"])
            w = float(context["weight"])
            a = float(context["age"])
            bmr = (10 * w) + (6.25 * h) - (5 * a) + (5 if str(context["gender"]).lower() == "male" else -161)
            mult = {"sedentary": 1.2, "light": 1.375, "moderate": 1.55, "very": 1.725}.get(str(context["activity"]).lower(), 1.4)
            tdee = bmr * mult
            if str(context["goal"]).lower() in ["lose", "weight_loss"]:
                target_cal = round(tdee - 450)
                target_prot = round(w * 1.8)
            elif str(context["goal"]).lower() in ["gain", "muscle_gain"]:
                target_cal = round(tdee + 350)
                target_prot = round(w * 2.0)
            else:
                target_cal = round(tdee)
                target_prot = round(w * 1.6)

            context["calories_target"] = max(1400, target_cal)
            context["protein_target"] = max(60, target_prot)

            # Nutrition logs for today
            c.execute("SELECT calories, protein, carbs, fat FROM nutrition_logs WHERE user_id = ? AND date = ?", (user_id, today))
            for n in c.fetchall():
                context["calories_consumed"] += n[0] or 0
                context["protein_consumed"] += n[1] or 0
                context["carbs_consumed"] += n[2] or 0
                context["fat_consumed"] += n[3] or 0

            # Water logs for today
            c.execute("SELECT COALESCE(SUM(ml), 0) FROM water_logs WHERE user_id = ? AND date = ?", (user_id, today))
            context["water_ml"] = c.fetchone()[0]

            # Sleep logs
            c.execute("SELECT hours, quality FROM sleep_logs WHERE user_id = ? ORDER BY date DESC LIMIT 1", (user_id,))
            s_row = c.fetchone()
            if s_row:
                context["sleep_hours"] = s_row[0] or 0
                context["sleep_quality"] = s_row[1] or "normal"

            # Workouts logged today
            c.execute("SELECT name FROM workout_logs WHERE user_id = ? AND date = ?", (user_id, today))
            context["workouts_today"] = [w[0] for w in c.fetchall() if w[0]]

            conn.close()
        except Exception as e:
            print(f"[FitPulse AI] Error loading context: {e}")

    return context


def _heuristic_fitness_coach(query, ctx):
    """Calibrated, context-aware rule-based coaching engine when LLM keys are absent."""
    q = (query or "").lower().strip()
    cal_left = ctx["calories_target"] - ctx["calories_consumed"]
    prot_gap = max(0, ctx["protein_target"] - ctx["protein_consumed"])
    is_veg = str(ctx["diet"]).lower() in ["vegetarian", "vegan"]
    first_name = ctx["name"].split()[0] if ctx["name"] else "there"

    if any(k in q for k in ["protein", "protien", "macros"]):
        if prot_gap <= 0:
            return (f"Awesome job, {first_name}! You've reached {ctx['protein_consumed']}g of protein today, "
                    f"hitting your {ctx['protein_target']}g goal. Your muscles have optimal amino acids for recovery. Keep hydrating!")
        sources = "150g curd (11g protein), 100g paneer (18g), 1 cup sprouted moong (9g), or a scoop of whey (24g)" if is_veg else \
                  "150g grilled chicken breast (38g protein), 3 whole eggs (18g), or 150g fish fillet (32g)"
        return (f"You're currently at **{ctx['protein_consumed']}g / {ctx['protein_target']}g protein** today (gap: {prot_gap}g). "
                f"To hit your target before bedtime, consider: {sources}.")

    if any(k in q for k in ["dinner", "lunch", "eat", "food", "meal", "hungry"]):
        if cal_left > 0:
            rec = "2 multigrain rotis + palak paneer + cucumber salad (~420 kcal, 18g protein) or a dal khichdi bowl with curd" if is_veg else \
                  "grilled chicken or fish with 1 roti, stir-fry broccoli, and mint chutney (~450 kcal, 36g protein)"
            return (f"You have **{cal_left} kcal** left in your daily budget. "
                    f"A great choice for your {ctx['diet']} goal ({ctx['goal']}): {rec}. "
                    f"Try to eat at least 2 hours before bedtime for optimal digestion and deep sleep.")
        else:
            return (f"You've already hit your calorie target ({ctx['calories_consumed']}/{ctx['calories_target']} kcal) today. "
                    f"If you're feeling hungry, go for zero/low-calorie options like warm green tea, tender coconut water, or a fresh cucumber/tomato bowl.")

    if any(k in q for k in ["workout", "train", "exercise", "routine", "gym"]):
        w_done = len(ctx["workouts_today"])
        status = f"You already logged {w_done} workout today — great discipline!" if w_done else "You haven't logged a workout today yet."
        plan = "focus on compound lifts: squats, overhead press, and barbell rows (45 mins, progressive overload)" if str(ctx["goal"]).lower() in ["gain", "muscle_gain"] else \
               "try a 25-minute HIIT circuit or a 5k interval run, followed by 10 minutes of core strengthening"
        return (f"{status} For your goal to **{ctx['goal']}**, {plan}. "
                f"Check the **Workouts** tab in FitPulse to start your live timer and exercise countdown!")

    if any(k in q for k in ["sleep", "recovery", "tired", "rest"]):
        hrs = ctx["sleep_hours"]
        if hrs > 0:
            analysis = f"You logged {hrs} hours last night." + (" That is solid recovery!" if hrs >= 7 else " Aim for at least 7.5 hours tonight.")
        else:
            analysis = "You haven't recorded last night's sleep yet on the Sleep page."
        return (f"{analysis} Quality sleep directly drives fat loss and muscle repair. "
                f"Tips: Avoid blue-light screens 45 minutes before sleep, keep your room cool, and stop caffeine intake after 3 PM.")

    if any(k in q for k in ["plateau", "stuck", "weight", "stall", "scale"]):
        return (f"Weight stalls are completely normal, {first_name}! You are currently at **{ctx['weight']} kg** (target: {ctx['target_weight']} kg). "
                f"To break through: 1) Weigh food portions precisely for 5 days. 2) Increase daily non-exercise steps by 2,000. "
                f"3) Maintain at least {ctx['protein_target']}g protein to preserve lean muscle mass. Water retention often hides fat loss for up to 2 weeks!")

    if any(k in q for k in ["water", "hydrat", "drink"]):
        ml = ctx["water_ml"]
        liters = round(ml / 1000, 1)
        return (f"You've recorded **{liters}L of 3.0L** today. "
                f"Proper hydration boosts metabolic rate by up to 30% and curbs false hunger signals. Keep a water bottle at your desk and take a sip now!")

    # Default overview
    return (f"Hello {first_name}! Here is your current snapshot: "
            f"**{ctx['calories_consumed']}/{ctx['calories_target']} kcal**, "
            f"**{ctx['protein_consumed']}/{ctx['protein_target']}g protein**, "
            f"and **{round(ctx['water_ml']/1000, 1)}L hydration** today. Streak: **{ctx['streak']} days** 🔥. "
            f"Ask me anything about your dinner choices, protein gaps, customized workout plans, or recovery!")


@app.route("/api/ai/coach", methods=["POST", "OPTIONS"])
def api_ai_coach():
    """Context-aware AI Coach powered by OpenAI, Gemini, Groq, Claude, or intelligent heuristic engine."""
    if request.method == "OPTIONS":
        return jsonify({"ok": True})

    data = request.get_json(silent=True) or {}
    messages = data.get("messages", [])
    profile_override = data.get("profile")

    # Get user question from direct message or last message in chat history
    user_query = data.get("message", "")
    if not user_query and messages:
        user_msgs = [m for m in messages if isinstance(m, dict) and m.get("from") in ["me", "user"]]
        if user_msgs:
            user_query = user_msgs[-1].get("text", "")

    user = get_current_user()
    user_id = user["id"] if user else None

    # Retrieve context from database (or request profile)
    ctx = _get_user_fitness_context(user_id=user_id, profile_override=profile_override)

    # Format conversation history
    clean_history = []
    for m in messages:
        if isinstance(m, dict) and m.get("text"):
            role = "user" if m.get("from") in ["me", "user"] else "assistant"
            clean_history.append({"role": role, "content": m["text"]})

    if not clean_history and user_query:
        clean_history.append({"role": "user", "content": user_query})

    system_prompt = (
        f"You are FitPulse AI Coach, a supportive, evidence-based fitness, nutrition, and wellness expert. "
        f"User Profile: Name: {ctx['name']}, Age: {ctx['age']}, Gender: {ctx['gender']}, Height: {ctx['height']} cm, "
        f"Weight: {ctx['weight']} kg (Target: {ctx['target_weight']} kg), Primary Goal: {ctx['goal']}, "
        f"Diet: {ctx['diet']}, Activity: {ctx['activity']}. "
        f"Today's Live Metrics: Calories consumed: {ctx['calories_consumed']} kcal / Target: {ctx['calories_target']} kcal "
        f"(Remaining: {max(0, ctx['calories_target'] - ctx['calories_consumed'])} kcal). "
        f"Protein: {ctx['protein_consumed']} g / Target: {ctx['protein_target']} g. "
        f"Hydration: {round(ctx['water_ml'] / 1000, 1)} L / 3.0 L target. "
        f"Sleep last night: {ctx['sleep_hours']} hrs. Workouts today: {', '.join(ctx['workouts_today']) if ctx['workouts_today'] else 'None logged yet'}. "
        f"Streak: {ctx['streak']} days. "
        f"Provide warm, concise (2-4 paragraphs max), scientifically sound advice tailored to their logged nutrition, Indian and global meal options, "
        f"progressive workouts, and sleep recovery. If they ask about dinners, recommend specific items fitting their remaining calories and protein gap."
    )

    ai_reply = None
    ai_provider = None

    # 1. Try OpenAI if configured
    if HAS_REQUESTS and OPENAI_API_KEY and not ai_reply:
        try:
            headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
            payload = {
                "model": OPENAI_MODEL,
                "messages": [{"role": "system", "content": system_prompt}] + clean_history[-6:],
                "max_tokens": 500,
                "temperature": 0.7
            }
            resp = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload, timeout=12)
            if resp.status_code == 200:
                ai_reply = resp.json()["choices"][0]["message"]["content"]
                ai_provider = "openai"
        except Exception as e:
            print(f"[FitPulse AI] OpenAI error: {e}")

    # 2. Try Google Gemini if configured
    if HAS_REQUESTS and GEMINI_API_KEY and not ai_reply:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
            prompt_text = f"{system_prompt}\n\nUser Question:\n{user_query or (clean_history[-1]['content'] if clean_history else 'Hello')}"
            payload = {
                "contents": [{"parts": [{"text": prompt_text}]}],
                "generationConfig": {"maxOutputTokens": 600, "temperature": 0.7}
            }
            resp = requests.post(url, json=payload, timeout=12)
            if resp.status_code == 200:
                ai_reply = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
                ai_provider = "gemini"
        except Exception as e:
            print(f"[FitPulse AI] Gemini error: {e}")

    # 3. Try Groq if configured
    if HAS_REQUESTS and GROQ_API_KEY and not ai_reply:
        try:
            headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
            payload = {
                "model": GROQ_MODEL,
                "messages": [{"role": "system", "content": system_prompt}] + clean_history[-6:],
                "max_tokens": 500,
                "temperature": 0.7
            }
            resp = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload, timeout=12)
            if resp.status_code == 200:
                ai_reply = resp.json()["choices"][0]["message"]["content"]
                ai_provider = "groq"
        except Exception as e:
            print(f"[FitPulse AI] Groq error: {e}")

    # 4. Try Anthropic Claude if configured
    if HAS_REQUESTS and ANTHROPIC_API_KEY and not ai_reply:
        try:
            headers = {
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json"
            }
            payload = {
                "model": CLAUDE_MODEL,
                "system": system_prompt,
                "messages": clean_history[-6:] or [{"role": "user", "content": "Hello"}],
                "max_tokens": 600
            }
            resp = requests.post("https://api.anthropic.com/v1/messages", headers=headers, json=payload, timeout=12)
            if resp.status_code == 200:
                ai_reply = resp.json()["content"][0]["text"]
                ai_provider = "anthropic"
        except Exception as e:
            print(f"[FitPulse AI] Anthropic error: {e}")

    # 5. Smart Heuristic Fallback Engine
    if not ai_reply:
        ai_reply = _heuristic_fitness_coach(user_query or (clean_history[-1]["content"] if clean_history else ""), ctx)
        ai_provider = "heuristic"

    return jsonify({
        "ok": True,
        "reply": ai_reply,
        "provider": ai_provider,
        "context": {
            "name": ctx["name"],
            "caloriesConsumed": ctx["calories_consumed"],
            "caloriesTarget": ctx["calories_target"],
            "proteinConsumed": ctx["protein_consumed"],
            "proteinTarget": ctx["protein_target"],
            "waterMl": ctx["water_ml"],
            "sleepHours": ctx["sleep_hours"],
            "streak": ctx["streak"]
        }
    })


# ==============================================================================
# API: PAYMENTS (Stripe Integration)
# ==============================================================================

@app.route("/api/payments/stripe/create-checkout-session", methods=["POST", "OPTIONS"])
@require_login
def api_stripe_create_session():
    """Create a Stripe Checkout Session for international card payments."""
    if request.method == "OPTIONS":
        return jsonify({"ok": True})

    data = request.get_json(silent=True) or {}
    plan_slug = data.get("plan", "yearly")
    coupon_code = (data.get("coupon") or "").strip().upper()

    conn = g.db
    c = conn.cursor()
    c.execute("SELECT * FROM membership_plans WHERE slug = ? AND active = 1", (plan_slug,))
    plan_row = c.fetchone()
    if not plan_row:
        return jsonify({"ok": False, "error": "Invalid plan selected."}), 400
    plan = dict(plan_row)

    base_price = plan["price"]
    discount = round(base_price * 0.2) if coupon_code == "FIT20" else 0
    subtotal = base_price - discount
    gst = round(subtotal * 0.18)
    total = subtotal + gst
    order_id = _gen_id("ord_")
    now = _now_iso()

    c.execute("""
        INSERT INTO orders (id, user_id, plan_id, amount, currency, gateway_order_id, coupon_code, discount, gst, status, created_at, updated_at)
        VALUES (?, ?, ?, ?, 'INR', ?, ?, ?, ?, 'created', ?, ?)
    """, (order_id, g.user["id"], plan["id"], total, f"stripe_{order_id}", coupon_code or None,
          discount, gst, now, now))
    conn.commit()

    if not STRIPE_SECRET_KEY and not _demo_payments_allowed():
        return jsonify({"ok": False, "error": "Stripe is not configured."}), 503

    if HAS_REQUESTS and STRIPE_SECRET_KEY:
        try:
            stripe_url = "https://api.stripe.com/v1/checkout/sessions"
            headers = {"Authorization": f"Bearer {STRIPE_SECRET_KEY}"}
            payload = {
                "payment_method_types[]": "card",
                "line_items[0][price_data][currency]": "inr",
                "line_items[0][price_data][product_data][name]": f"FitPulse {plan['name']}",
                "line_items[0][price_data][unit_amount]": str(total * 100),
                "line_items[0][quantity]": "1",
                "mode": "payment",
                "client_reference_id": order_id,
                "customer_email": g.user["email"],
                "success_url": f"{FRONTEND_URL}/fitpulse/checkout.html?status=success&session_id={{CHECKOUT_SESSION_ID}}&order_id={order_id}",
                "cancel_url": f"{FRONTEND_URL}/fitpulse/checkout.html?status=cancelled",
            }
            resp = requests.post(stripe_url, headers=headers, data=payload, timeout=12)
            if resp.status_code == 200:
                s_data = resp.json()
                return jsonify({
                    "ok": True,
                    "orderId": order_id,
                    "sessionId": s_data.get("id"),
                    "checkoutUrl": s_data.get("url"),
                    "provider": "stripe"
                })
        except Exception as e:
            print(f"[FitPulse Stripe] Error: {e}")

    if _demo_payments_allowed():
        return jsonify({
            "ok": True,
            "orderId": order_id,
            "sessionId": f"cs_demo_{secrets.token_hex(12)}",
            "checkoutUrl": f"/fitpulse/checkout.html?simulated=stripe&order_id={order_id}",
            "provider": "stripe_simulated"
        })
    return jsonify({"ok": False, "error": "Could not create Stripe checkout session."}), 502


@app.route("/api/payments/stripe/webhook", methods=["POST"])
def api_stripe_webhook():
    """Handle Stripe payment webhooks."""
    if not STRIPE_WEBHOOK_SECRET:
        return jsonify({"ok": False, "error": "Webhook not configured."}), 501
    sig = request.headers.get("Stripe-Signature", "")
    body = request.get_data()
    try:
        parts = dict(p.split("=", 1) for p in sig.split(",") if "=" in p)
        timestamp = parts.get("t", "")
        v1 = parts.get("v1", "")
        signed = f"{timestamp}.{body.decode('utf-8')}".encode()
        expected = hmac.new(STRIPE_WEBHOOK_SECRET.encode(), signed, hashlib.sha256).hexdigest()
        if not v1 or not hmac.compare_digest(expected, v1):
            return jsonify({"ok": False, "error": "Invalid webhook signature."}), 401
    except Exception:
        return jsonify({"ok": False, "error": "Signature verification failed."}), 401

    event = request.get_json(silent=True) or {}
    event_type = event.get("type", "")
    event_id = event.get("id") or f"stripe:{event_type}:{secrets.token_hex(8)}"
    try:
        g.db.execute(
            "INSERT INTO webhook_events (id, provider, event_id, event_type, processed_at) VALUES (?, 'stripe', ?, ?, ?)",
            (_gen_id("wh_"), event_id, event_type, _now_iso()),
        )
        g.db.commit()
    except sqlite3.IntegrityError:
        return jsonify({"received": True, "message": "Already processed."})

    if event_type == "checkout.session.completed":
        session_obj = event.get("data", {}).get("object", {})
        order_id = session_obj.get("client_reference_id")
        stripe_payment_id = session_obj.get("payment_intent") or session_obj.get("id")

        if order_id:
            conn = get_db()
            c = conn.cursor()
            now = _now_iso()
            c.execute("SELECT * FROM orders WHERE id = ?", (order_id,))
            order_row = c.fetchone()
            if order_row:
                order = dict(order_row)
                c.execute("UPDATE orders SET status = 'paid', updated_at = ? WHERE id = ?", (now, order_id))
                c.execute("""
                    INSERT OR IGNORE INTO payments (id, order_id, user_id, gateway_payment_id, amount, currency, method, status, created_at)
                    VALUES (?, ?, ?, ?, ?, 'INR', 'stripe', 'captured', ?)
                """, (_gen_id("pay_"), order_id, order["user_id"], stripe_payment_id, order["amount"], now))

                c.execute("SELECT duration_months, slug FROM membership_plans WHERE id = ?", (order.get("plan_id"),))
                plan_row = c.fetchone()
                if plan_row:
                    months = plan_row[0] or 1
                    expiry = datetime.date.today() + datetime.timedelta(days=months * 30)
                    c.execute("""
                        UPDATE users SET plan = 'premium', plan_type = ?, plan_start = ?, plan_expiry = ?, payment_status = 'paid'
                        WHERE id = ?
                    """, (plan_row[1], _today_iso(), expiry.isoformat(), order["user_id"]))
                conn.commit()
            conn.close()

    return jsonify({"received": True})


# ==============================================================================
# API: HEALTH & PRODUCTION MONITORING
# ==============================================================================

SERVER_START_TIME = time.time()

@app.route("/health", methods=["GET"])
@app.route("/healthz", methods=["GET"])
@app.route("/api/health", methods=["GET"])
def api_health_check():
    """Production health check for Docker, Render, Railway, Kubernetes, and uptime checkers."""
    db_ok = False
    try:
        conn = get_db()
        conn.execute("SELECT 1").fetchone()
        conn.close()
        db_ok = True
    except Exception:
        db_ok = False

    uptime_sec = round(time.time() - SERVER_START_TIME)

    ai_provider = "heuristic"
    if OPENAI_API_KEY: ai_provider = "openai"
    elif GEMINI_API_KEY: ai_provider = "gemini"
    elif GROQ_API_KEY: ai_provider = "groq"
    elif ANTHROPIC_API_KEY: ai_provider = "anthropic"

    return jsonify({
        "status": "healthy" if db_ok else "unhealthy",
        "uptimeSeconds": uptime_sec,
        "timestamp": _now_iso(),
        "database": "connected" if db_ok else "disconnected",
        "domain": DOMAIN_NAME,
        "version": "2.1.0",
        "environment": FLASK_ENV,
        "gateways": {
            "razorpay": bool(rzp_client),
            "stripe": bool(STRIPE_SECRET_KEY)
        },
        "ai": {
            "provider": ai_provider,
            "live": ai_provider != "heuristic"
        }
    }), (200 if db_ok else 503)


# Standard WSGI entry point for Gunicorn / Waitress / uWSGI
application = app


# ==============================================================================
# API: NOTIFICATIONS
# ==============================================================================

@app.route("/api/notifications", methods=["GET", "PUT", "OPTIONS"])
@require_login
def api_notifications():
    if request.method == "OPTIONS":
        return jsonify({"ok": True})

    conn = g.db
    c = conn.cursor()

    if request.method == "GET":
        c.execute("SELECT * FROM notifications WHERE user_id = ? ORDER BY created_at DESC LIMIT 50", (g.user["id"],))
        notifs = [dict(r) for r in c.fetchall()]
        unread = sum(1 for n in notifs if not n["read"])
        return jsonify({"ok": True, "data": notifs, "unread": unread})

    if request.method == "PUT":
        data = request.get_json(silent=True) or {}
        if data.get("markAllRead"):
            c.execute("UPDATE notifications SET read = 1 WHERE user_id = ?", (g.user["id"],))
        elif data.get("id"):
            c.execute("UPDATE notifications SET read = 1 WHERE id = ? AND user_id = ?", (data["id"], g.user["id"]))
        conn.commit()
        return jsonify({"ok": True})


# ==============================================================================
# API: ADMIN DASHBOARD & MANAGEMENT
# ==============================================================================

@app.route("/api/admin/stats", methods=["GET"])
@require_admin
def api_admin_stats():
    conn = g.db
    c = conn.cursor()
    today = _today_iso()

    c.execute("SELECT COUNT(*) FROM users WHERE role != 'admin'")
    total_members = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM users WHERE plan = 'premium' AND role != 'admin'")
    premium_members = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM users WHERE role != 'admin' AND created_at >= ?",
              ((datetime.date.today() - datetime.timedelta(days=30)).isoformat(),))
    new_signups = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM tickets WHERE status != 'closed'")
    open_tickets = c.fetchone()[0]

    # Real revenue from verified payments
    c.execute("SELECT COALESCE(SUM(amount), 0) FROM payments WHERE status = 'captured'")
    total_revenue = c.fetchone()[0]

    # Expiring memberships (next 30 days)
    next_30 = (datetime.date.today() + datetime.timedelta(days=30)).isoformat()
    c.execute("SELECT COUNT(*) FROM users WHERE plan = 'premium' AND plan_expiry BETWEEN ? AND ?",
              (today, next_30))
    expiring = c.fetchone()[0]

    # Recent workout activity
    c.execute("SELECT COUNT(*) FROM workout_logs WHERE date >= ?",
              ((datetime.date.today() - datetime.timedelta(days=7)).isoformat(),))
    weekly_workouts = c.fetchone()[0]

    # Contact enquiries
    c.execute("SELECT COUNT(*) FROM contact_enquiries WHERE status = 'new'")
    new_enquiries = c.fetchone()[0]

    return jsonify({
        "ok": True,
        "members": total_members,
        "premium": premium_members,
        "newSignups": new_signups,
        "openTickets": open_tickets,
        "revenue": total_revenue,
        "revenueFormatted": f"₹{total_revenue:,}",
        "expiringMemberships": expiring,
        "weeklyWorkouts": weekly_workouts,
        "newEnquiries": new_enquiries,
    })


@app.route("/api/admin/users", methods=["GET"])
@require_admin
def api_admin_users():
    conn = g.db
    c = conn.cursor()
    search = request.args.get("q", "").lower()
    plan_filter = request.args.get("plan", "")
    status_filter = request.args.get("status", "")
    page = max(1, _safe_int(request.args.get("page"), 1))
    per_page = min(_safe_int(request.args.get("per_page"), 25), 100)

    sql = "SELECT id, name, email, role, plan, plan_type, plan_start, plan_expiry, payment_status, status, email_verified, created_at FROM users WHERE role != 'admin'"
    params = []
    if search:
        sql += " AND (LOWER(name) LIKE ? OR LOWER(email) LIKE ?)"
        params.extend([f"%{search}%", f"%{search}%"])
    if plan_filter:
        sql += " AND plan = ?"
        params.append(plan_filter)
    if status_filter:
        sql += " AND status = ?"
        params.append(status_filter)

    # Count total
    count_sql = sql.replace("SELECT id, name, email, role, plan, plan_type, plan_start, plan_expiry, payment_status, status, email_verified, created_at", "SELECT COUNT(*)")
    c.execute(count_sql, params)
    total = c.fetchone()[0]

    sql += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
    params.extend([per_page, (page - 1) * per_page])
    c.execute(sql, params)
    rows = [dict(r) for r in c.fetchall()]

    return jsonify({"ok": True, "data": rows, "total": total, "page": page, "perPage": per_page})


@app.route("/api/admin/users/<user_id>", methods=["PUT", "DELETE"])
@require_admin
def api_admin_user_action(user_id):
    conn = g.db
    c = conn.cursor()

    # Prevent admin from modifying their own account or other admins
    c.execute("SELECT role FROM users WHERE id = ?", (user_id,))
    target = c.fetchone()
    if not target:
        return jsonify({"ok": False, "error": "User not found."}), 404
    if target[0] == "admin":
        return jsonify({"ok": False, "error": "Cannot modify admin accounts."}), 403

    if request.method == "PUT":
        data = request.get_json(silent=True) or {}
        allowed = ["status", "plan", "plan_type", "plan_start", "plan_expiry", "payment_status"]
        fields = []
        vals = []
        for f in allowed:
            if f in data:
                fields.append(f"{f} = ?")
                vals.append(data[f])
        if fields:
            vals.append(user_id)
            c.execute(f"UPDATE users SET {', '.join(fields)} WHERE id = ?", vals)
            _admin_log(conn, "user.update", "user", user_id, str(data)[:400])
            conn.commit()
        return jsonify({"ok": True, "message": "User updated."})

    if request.method == "DELETE":
        # Soft delete: suspend the account
        c.execute("UPDATE users SET status = 'suspended' WHERE id = ?", (user_id,))
        c.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
        _admin_log(conn, "user.suspend", "user", user_id)
        conn.commit()
        return jsonify({"ok": True, "message": "User suspended."})


@app.route("/api/admin/orders", methods=["GET"])
@require_admin
def api_admin_orders():
    """Get all orders with pagination."""
    conn = g.db
    c = conn.cursor()
    page = max(1, _safe_int(request.args.get("page"), 1))
    per_page = min(_safe_int(request.args.get("per_page"), 25), 100)
    status_filter = request.args.get("status", "")

    sql = """
        SELECT o.*, u.name as user_name, u.email as user_email,
               p.gateway_payment_id, p.method as payment_method
        FROM orders o
        JOIN users u ON o.user_id = u.id
        LEFT JOIN payments p ON o.id = p.order_id
    """
    params = []
    if status_filter:
        sql += " WHERE o.status = ?"
        params.append(status_filter)
    sql += " ORDER BY o.created_at DESC LIMIT ? OFFSET ?"
    params.extend([per_page, (page - 1) * per_page])

    c.execute(sql, params)
    orders = [dict(r) for r in c.fetchall()]
    return jsonify({"ok": True, "data": orders})


@app.route("/api/admin/enquiries", methods=["GET", "PUT"])
@require_admin
def api_admin_enquiries():
    conn = g.db
    c = conn.cursor()

    if request.method == "GET":
        c.execute("SELECT * FROM contact_enquiries ORDER BY created_at DESC LIMIT 100")
        enquiries = [dict(r) for r in c.fetchall()]
        return jsonify({"ok": True, "data": enquiries})

    if request.method == "PUT":
        data = request.get_json(silent=True) or {}
        eid = data.get("id")
        new_status = data.get("status")
        if eid and new_status:
            c.execute("UPDATE contact_enquiries SET status = ? WHERE id = ?", (new_status, eid))
            conn.commit()
        return jsonify({"ok": True, "message": "Enquiry updated."})


@app.route("/api/admin/logs", methods=["GET"])
@require_admin
def api_admin_logs():
    c = g.db.cursor()
    c.execute("""
        SELECT a.id, a.action, a.target_type, a.target_id, a.details, a.created_at, u.email as admin_email
        FROM admin_logs a LEFT JOIN users u ON a.admin_id = u.id
        ORDER BY a.created_at DESC LIMIT 100
    """)
    return jsonify({"ok": True, "data": [dict(r) for r in c.fetchall()]})


@app.route("/api/admin/membership-plans", methods=["GET", "POST", "PUT"])
@require_admin
def api_admin_membership_plans():
    conn = g.db
    c = conn.cursor()

    if request.method == "GET":
        c.execute("SELECT * FROM membership_plans ORDER BY price ASC")
        plans = []
        for r in c.fetchall():
            plan = dict(r)
            plan["features"] = json.loads(plan.get("features_json") or "[]")
            plans.append(plan)
        return jsonify({"ok": True, "data": plans})

    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        pid = _gen_id("plan_")
        now = _now_iso()
        c.execute("""
            INSERT INTO membership_plans (id, name, slug, price, currency, duration_months, features_json, active, created_at)
            VALUES (?, ?, ?, ?, 'INR', ?, ?, 1, ?)
        """, (pid, _sanitize_str(data.get("name"), 100), data.get("slug", ""),
              _safe_int(data.get("price")), _safe_int(data.get("duration_months", 1)),
              json.dumps(data.get("features", [])), now))
        conn.commit()
        return jsonify({"ok": True, "id": pid, "message": "Plan created."})

    if request.method == "PUT":
        data = request.get_json(silent=True) or {}
        pid = data.get("id")
        if not pid:
            return jsonify({"ok": False, "error": "Plan ID required."}), 400
        fields = []
        vals = []
        for f in ["name", "price", "duration_months", "active"]:
            if f in data:
                fields.append(f"{f} = ?")
                vals.append(data[f])
        if "features" in data:
            fields.append("features_json = ?")
            vals.append(json.dumps(data["features"]))
        if fields:
            vals.append(pid)
            c.execute(f"UPDATE membership_plans SET {', '.join(fields)} WHERE id = ?", vals)
            conn.commit()
        return jsonify({"ok": True, "message": "Plan updated."})


@app.route("/api/admin/export/<data_type>", methods=["GET"])
@require_admin
def api_admin_export(data_type):
    """Export data as CSV for admin reporting."""
    conn = g.db
    c = conn.cursor()
    output = io.StringIO()
    writer = csv.writer(output)

    if data_type == "users":
        writer.writerow(["ID", "Name", "Email", "Plan", "Plan Type", "Status", "Created"])
        c.execute("SELECT id, name, email, plan, plan_type, status, created_at FROM users WHERE role != 'admin' ORDER BY created_at DESC")
        for r in c.fetchall():
            writer.writerow(list(r))

    elif data_type == "orders":
        writer.writerow(["Order ID", "User Email", "Amount", "Status", "Gateway Order", "Created"])
        c.execute("""
            SELECT o.id, u.email, o.amount, o.status, o.gateway_order_id, o.created_at
            FROM orders o JOIN users u ON o.user_id = u.id ORDER BY o.created_at DESC
        """)
        for r in c.fetchall():
            writer.writerow(list(r))

    elif data_type == "enquiries":
        writer.writerow(["ID", "Name", "Email", "Subject", "Status", "Created"])
        c.execute("SELECT id, name, email, subject, status, created_at FROM contact_enquiries ORDER BY created_at DESC")
        for r in c.fetchall():
            writer.writerow(list(r))
    else:
        return jsonify({"ok": False, "error": "Unknown export type."}), 400

    resp = make_response(output.getvalue())
    resp.headers["Content-Type"] = "text/csv"
    resp.headers["Content-Disposition"] = f"attachment; filename=fitpulse_{data_type}_{_today_iso()}.csv"
    return resp


# ==============================================================================
# SEED DATA
# ==============================================================================

def _ensure_admin_account(conn, password=None):
    """Create the initial admin from env if none exists. Never uses a hardcoded production password."""
    c = conn.cursor()
    c.execute("SELECT id FROM users WHERE role = 'admin' LIMIT 1")
    if c.fetchone():
        return True
    pw = password if password is not None else ADMIN_PASSWORD
    if FLASK_ENV == "production" and (not pw or pw == "admin1234"):
        print("[FitPulse] No admin account. Set ADMIN_EMAIL and a strong ADMIN_PASSWORD, then run: python server.py --create-admin")
        return False
    if not pw:
        pw = "admin1234" if SEED_DEMO_DATA else ""
    if not pw:
        return False
    now_iso = _now_iso()
    admin_id = "user_admin_1"
    c.execute("""
        INSERT INTO users (id, name, email, password_hash, role, plan, plan_type, plan_start, plan_expiry, payment_status, status, email_verified, created_at)
        VALUES (?, ?, ?, ?, 'admin', 'premium', 'yearly', ?, ?, 'paid', 'active', 1, ?)
    """, (admin_id, ADMIN_NAME, ADMIN_EMAIL, hash_password(pw), _today_iso(),
          (datetime.date.today() + datetime.timedelta(days=365)).isoformat(), now_iso))
    c.execute("""
        INSERT OR IGNORE INTO profiles (user_id, name, email, onboarded, updated_at)
        VALUES (?, ?, ?, 1, ?)
    """, (admin_id, ADMIN_NAME, ADMIN_EMAIL, now_iso))
    conn.commit()
    print(f"[FitPulse] Admin account created for {ADMIN_EMAIL}. Change the password after first login.")
    return True


def seed_data(conn):
    c = conn.cursor()
    now_iso = _now_iso()
    today = _today_iso()

    # 1. Seed Demo User & Admin User
    demo_id = "user_demo_1"
    admin_id = "user_admin_1"

    c.execute("""
        INSERT INTO users (id, name, email, password_hash, role, plan, plan_type, plan_start, plan_expiry, payment_status, status, email_verified, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (demo_id, "Aarav Sharma", "demo@fitpulse.app", hash_password("demo1234"), "user", "premium", "yearly", "2026-01-01", "2027-01-01", "paid", "active", 1, now_iso))

    c.execute("""
        INSERT INTO users (id, name, email, password_hash, role, plan, plan_type, plan_start, plan_expiry, payment_status, status, email_verified, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (admin_id, ADMIN_NAME, ADMIN_EMAIL, hash_password(ADMIN_PASSWORD or "admin1234"), "admin", "premium", "yearly", "2026-01-01", "2028-01-01", "paid", "active", 1, now_iso))

    c.execute("""
        INSERT INTO profiles (user_id, name, email, age, gender, height, weight, start_weight, target_weight, goal, activity, diet, experience, onboarded, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (demo_id, "Aarav Sharma", "demo@fitpulse.app", 28, "male", 176, 78.4, 84.0, 72.0, "lose", "moderate", "vegetarian", "intermediate", 1, now_iso))

    c.execute("""
        INSERT INTO profiles (user_id, name, email, age, gender, height, weight, start_weight, target_weight, goal, activity, diet, experience, onboarded, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (admin_id, ADMIN_NAME, ADMIN_EMAIL, 32, "male", 180, 76.0, 76.0, 76.0, "maintain", "active", "non-vegetarian", "advanced", 1, now_iso))

    # 2. Seed community members
    community_members = [
        ("Ishita Rao", "ishita.rao@mail.com", "premium", "active", 64.0, 162),
        ("Kabir Menon", "kabir.menon@mail.com", "free", "active", 82.0, 178),
        ("Nisha Patel", "nisha.patel@mail.com", "premium", "active", 58.0, 158),
        ("Rohan Gupta", "rohan.gupta@mail.com", "free", "active", 74.0, 172),
        ("Meera Iyer", "meera.iyer@mail.com", "premium", "active", 61.0, 165),
        ("Dev Khanna", "dev.khanna@mail.com", "free", "active", 88.0, 183),
        ("Sara Ali", "sara.ali@mail.com", "premium", "active", 55.0, 160),
        ("Vikram Bose", "vikram.bose@mail.com", "free", "suspended", 92.0, 175),
        ("Ananya Das", "ananya.das@mail.com", "premium", "active", 60.0, 167),
        ("Tanvi Shah", "tanvi.shah@mail.com", "free", "active", 53.0, 155),
    ]

    for i, (name, email, plan, status, wt, ht) in enumerate(community_members):
        uid = f"user_comm_{i+1}"
        c.execute("""
            INSERT INTO users (id, name, email, password_hash, role, plan, plan_type, plan_start, plan_expiry, payment_status, status, email_verified, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (uid, name, email, hash_password("demo1234"), "user", plan,
              "monthly" if plan == "premium" else "free", "2026-02-01", "2026-08-01",
              "paid" if plan == "premium" else "none", status, 0, now_iso))

        c.execute("""
            INSERT INTO profiles (user_id, name, email, age, gender, height, weight, start_weight, target_weight, goal, activity, diet, experience, onboarded, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (uid, name, email, 24 + i, "female" if i % 2 == 0 else "male", ht, wt, wt + 4, wt - 3,
              "lose" if i % 2 == 0 else "maintain", "moderate",
              "vegetarian" if i % 3 != 0 else "non-vegetarian", "intermediate", 1, now_iso))

    # 3. Seed 30 days of activity for Demo user
    base_date = datetime.date.today()
    foods_seed = [
        ("breakfast", "Poha", 180, 4, 32, 4, 2, "1 bowl"),
        ("breakfast", "Milk (Toned)", 103, 8, 12, 2.4, 0, "250ml"),
        ("lunch", "Roti (Whole Wheat)", 240, 8, 44, 4, 6, "2 pieces"),
        ("lunch", "Dal (Toor)", 150, 9, 20, 3, 6, "1 bowl"),
        ("lunch", "Curd (Dahi)", 98, 11, 4, 4, 0, "150g"),
        ("snacks", "Sprouts (Moong)", 106, 9, 19, 0.5, 4, "1 bowl"),
        ("dinner", "Paneer", 265, 18, 6, 20, 0, "100g"),
        ("dinner", "Rice (Cooked)", 205, 4, 45, 0.4, 1, "1 cup")
    ]

    for day_offset in range(30, -1, -1):
        d_date = (base_date - datetime.timedelta(days=day_offset)).isoformat()
        day_weight = round(84.0 - (30 - day_offset) * (5.6 / 30), 1)

        c.execute("INSERT INTO weight_logs (id, user_id, date, kg, created_at) VALUES (?, ?, ?, ?, ?)",
                  (f"wt_{day_offset}", demo_id, d_date, day_weight, now_iso))

        steps = 8200 if day_offset == 0 else (7500 + (day_offset * 123) % 4500)
        c.execute("INSERT INTO step_logs (id, user_id, date, steps, created_at) VALUES (?, ?, ?, ?, ?)",
                  (f"st_{day_offset}", demo_id, d_date, steps, now_iso))

        water = 2500 if day_offset == 0 else 3000
        c.execute("INSERT INTO water_logs (id, user_id, date, ml, created_at) VALUES (?, ?, ?, ?, ?)",
                  (f"wt_log_{day_offset}", demo_id, d_date, water, now_iso))

        sleep_h = 7.5 if day_offset % 2 == 0 else 8.0
        c.execute("INSERT INTO sleep_logs (id, user_id, date, bedtime, wake, hours, quality, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                  (f"sl_{day_offset}", demo_id, d_date, "23:00", "07:00", sleep_h, "Rested", now_iso))

        for hid in ["water", "workout", "steps", "meal", "sleep", "meditate"]:
            c.execute("INSERT INTO habit_logs (id, user_id, date, habit_id, completed, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                      (f"hb_{day_offset}_{hid}", demo_id, d_date, hid, 1 if day_offset % 3 != 0 else 0, now_iso))

        for idx, (meal, fname, cal, pro, carb, fat, fib, srv) in enumerate(foods_seed):
            c.execute("""
                INSERT INTO nutrition_logs (id, user_id, date, meal, name, calories, protein, carbs, fat, fiber, serving, qty, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (f"nl_{day_offset}_{idx}", demo_id, d_date, meal, fname, cal, pro, carb, fat, fib, srv, 1.0, now_iso))

        if day_offset % 2 == 0:
            c.execute("""
                INSERT INTO workout_logs (id, user_id, date, name, minutes, calories, category, completed, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (f"wkl_{day_offset}", demo_id, d_date, "Full Body Strength", 45, 320, "Strength", 1, now_iso))

    # 4. Load Foods JSON
    foods_json_path = DATA_DIR / "foods.json"
    if foods_json_path.exists():
        with open(foods_json_path, "r", encoding="utf-8") as f:
            food_items = json.load(f)
            for item in food_items:
                c.execute("""
                    INSERT OR IGNORE INTO foods (id, name, category, calories, protein, carbs, fat, fiber, serving, is_custom)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (str(item.get("id")), item.get("name"), item.get("category"), item.get("calories"),
                      item.get("protein", 0), item.get("carbs", 0), item.get("fat", 0), item.get("fiber", 0),
                      item.get("serving", "1 serving"), 0))

    # 5. Load Workouts JSON
    workouts_json_path = DATA_DIR / "workouts.json"
    if workouts_json_path.exists():
        with open(workouts_json_path, "r", encoding="utf-8") as f:
            workout_items = json.load(f)
            for item in workout_items:
                c.execute("""
                    INSERT OR IGNORE INTO workouts (id, name, category, level, minutes, calories, equipment, focus, exercises_json, is_custom, premium, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, 'published')
                """, (str(item.get("id")), item.get("name"), item.get("category"), item.get("level"),
                      item.get("minutes"), item.get("calories"), item.get("equipment", "None"),
                      item.get("focus", "General"), json.dumps(item.get("exercises", []))))

    # 6. Load Meal Plans JSON
    meal_plans_path = DATA_DIR / "meal-plans.json"
    if meal_plans_path.exists():
        with open(meal_plans_path, "r", encoding="utf-8") as f:
            meal_items = json.load(f)
            for item in meal_items:
                c.execute("""
                    INSERT OR IGNORE INTO meal_plans (id, name, goal, calories, diet, days_json)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (str(item.get("id")), item.get("name"), item.get("goal"), item.get("calories"),
                      item.get("diet"), json.dumps(item.get("days", {}))))

    # 7. Seed Support Tickets
    c.execute("""
        INSERT INTO tickets (id, email, name, subject, category, priority, status, created_at, messages_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, ("TK-1042", "demo@fitpulse.app", "Aarav Sharma", "AI Coach personalization tips", "Feedback", "medium", "open", now_iso, json.dumps([
        {"from": "user", "text": "Can the AI coach recommend more millet-based recipes like Ragi Dosa?", "at": now_iso},
        {"from": "admin", "text": "Absolutely! We added Ragi Dosa to the database and your coach now includes millets in recovery meal recommendations.", "at": now_iso}
    ])))

    c.execute("""
        INSERT INTO tickets (id, email, name, subject, category, priority, status, created_at, messages_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, ("TK-1041", "nisha.patel@mail.com", "Nisha Patel", "Yearly plan invoice receipt", "Billing", "low", "closed", now_iso, json.dumps([
        {"from": "user", "text": "Could I get a GST receipt for my yearly subscription?", "at": now_iso},
        {"from": "admin", "text": "Receipt dispatched to your registered email address with 18% GST breakdown.", "at": now_iso}
    ])))

    conn.commit()
    print("[FitPulse] Database initialized and seeded successfully.")


# Initialize and migrate database on module load
init_db()


# ==============================================================================
# STATIC WEB HOSTING
# ==============================================================================

@app.route("/")
def serve_root():
    return redirect("/fitpulse/index.html")

@app.route("/robots.txt")
def serve_robots():
    return send_from_directory(str(PUBLIC_DIR), "robots.txt")

@app.route("/sitemap.xml")
def serve_sitemap():
    return send_from_directory(str(PUBLIC_DIR), "sitemap.xml")

@app.route("/fitpulse/")
def serve_fitpulse_root():
    return send_from_directory(str(PUBLIC_DIR), "index.html")

@app.route("/fitpulse/<path:filename>")
def serve_fitpulse_file(filename):
    file_path = PUBLIC_DIR / filename
    if file_path.is_file():
        return send_from_directory(str(PUBLIC_DIR), filename)
    html_path = PUBLIC_DIR / (filename + ".html")
    if html_path.is_file():
        return send_from_directory(str(PUBLIC_DIR), filename + ".html")
    return send_from_directory(str(PUBLIC_DIR), "404.html"), 404


@app.errorhandler(404)
def handle_404(err):
    if request.path.startswith("/api/"):
        return jsonify({"ok": False, "error": "Not found."}), 404
    return send_from_directory(str(PUBLIC_DIR), "404.html"), 404


@app.errorhandler(500)
def handle_500(err):
    if request.path.startswith("/api/"):
        return jsonify({"ok": False, "error": "Server error."}), 500
    return send_from_directory(str(PUBLIC_DIR), "500.html"), 500

@app.route("/<page_name>.html")
def serve_clean_html(page_name):
    file_path = PUBLIC_DIR / (page_name + ".html")
    if file_path.is_file():
        return send_from_directory(str(PUBLIC_DIR), page_name + ".html")
    return redirect("/fitpulse/index.html")


# ==============================================================================
# PERIODIC CLEANUP
# ==============================================================================

def _cleanup_expired_sessions():
    """Remove expired sessions (called periodically)."""
    try:
        conn = get_db()
        conn.execute("DELETE FROM sessions WHERE expires_at != '' AND expires_at < ?", (_now_iso(),))
        conn.commit()
        conn.close()
    except Exception:
        pass

# Run cleanup on startup
import atexit
import threading

def _periodic_cleanup():
    _cleanup_expired_sessions()
    timer = threading.Timer(3600, _periodic_cleanup)  # every hour
    timer.daemon = True
    timer.start()


# ==============================================================================
# MAIN ENTRY POINT
# ==============================================================================

if __name__ == "__main__":
    if "--create-admin" in sys.argv:
        pw = ADMIN_PASSWORD
        if not pw:
            print("Set ADMIN_PASSWORD in the environment before --create-admin.")
            sys.exit(1)
        conn = get_db()
        ok = _ensure_admin_account(conn, password=pw)
        conn.close()
        sys.exit(0 if ok else 1)

    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    # Delete old database for clean re-seed if schema changed significantly
    # Remove this block in production!
    if FLASK_ENV == "development" and DB_PATH.exists():
        try:
            conn_test = sqlite3.connect(str(DB_PATH))
            cursor = conn_test.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='membership_plans'")
            if not cursor.fetchone():
                conn_test.close()
                DB_PATH.unlink()
                print("[FitPulse] Old database removed for schema upgrade. Re-seeding...")
            else:
                conn_test.close()
        except Exception:
            pass

    init_db()
    _periodic_cleanup()

    port = int(os.environ.get("PORT", 5000))
    ai_status = "OpenAI" if OPENAI_API_KEY else ("Gemini" if GEMINI_API_KEY else ("Groq" if GROQ_API_KEY else ("Claude" if ANTHROPIC_API_KEY else "Context-Aware Heuristic Engine")))
    print("=" * 65)
    print(f"[FitPulse] Production-Ready Server v2.1")
    print(f"[*] Running at:   http://127.0.0.1:{port}")
    print(f"[*] Web App:      http://127.0.0.1:{port}/fitpulse/index.html")
    print(f"[*] Admin Portal: http://127.0.0.1:{port}/fitpulse/admin.html")
    print(f"[*] Health Check: http://127.0.0.1:{port}/api/health")
    print(f"[*] Domain:       {DOMAIN_NAME}")
    print(f"[*] Environment:  {FLASK_ENV}")
    print(f"[*] Razorpay:     {'Configured' if rzp_client else 'Demo mode (ready for keys)'}")
    print(f"[*] Stripe:       {'Configured' if STRIPE_SECRET_KEY else 'Demo mode (ready for keys)'}")
    print(f"[*] AI Coach:     {ai_status}")
    print(f"[*] Security:     {'Bcrypt' if HAS_BCRYPT else ('Werkzeug (scrypt)' if HAS_WERKZEUG else 'SHA-256')}")
    print("=" * 65)
    app.run(host="0.0.0.0", port=port, debug=(FLASK_ENV == "development"))
