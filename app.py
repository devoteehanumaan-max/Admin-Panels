from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash, send_from_directory
from flask_bcrypt import Bcrypt
import secrets
import string
import random
from datetime import datetime, timedelta
import os
import qrcode
from io import BytesIO
import base64
import traceback
import logging
import json
import time
import psycopg2
from psycopg2.extras import RealDictCursor
import socket
import requests
import re
from functools import wraps

app = Flask(__name__)

# ✅ FIX #1: secret_key must come from env — never generate randomly at runtime
# (random token_hex on every restart invalidates all existing sessions)
_secret = os.getenv('SECRET_KEY')
if not _secret:
    raise RuntimeError("❌ SECRET_KEY environment variable is not set!")
app.secret_key = _secret

app.config['SESSION_PERMANENT'] = False
app.config['SESSION_USE_SIGNER'] = True
bcrypt = Bcrypt(app)

# ✅ FIX #2: Use WARNING in production, DEBUG only when explicitly set
log_level = logging.DEBUG if os.getenv('FLASK_DEBUG') else logging.WARNING
logging.basicConfig(level=log_level, format='%(asctime)s %(levelname)s %(message)s')

# ============================================
# DATABASE CONNECTION
# ============================================

# ✅ FIX #3: Never hardcode DB credentials — require them from env vars
EXTERNAL_DATABASE_URL = os.getenv('EXTERNAL_DATABASE_URL')
INTERNAL_DATABASE_URL = os.getenv('INTERNAL_DATABASE_URL')

if not EXTERNAL_DATABASE_URL:
    raise RuntimeError("❌ EXTERNAL_DATABASE_URL environment variable is not set!")

def is_running_on_render():
    return bool(os.getenv('RENDER') or os.getenv('RENDER_EXTERNAL_URL'))

def get_database_url():
    if is_running_on_render() and INTERNAL_DATABASE_URL:
        return INTERNAL_DATABASE_URL
    return EXTERNAL_DATABASE_URL

def get_db_connection():
    primary_url = get_database_url()
    try:
        conn = psycopg2.connect(primary_url, connect_timeout=10, cursor_factory=RealDictCursor)
        return conn
    except Exception as e:
        logging.error(f"Primary DB failed: {e}")
        fallback = EXTERNAL_DATABASE_URL if primary_url != EXTERNAL_DATABASE_URL else None
        if fallback:
            try:
                conn = psycopg2.connect(fallback, connect_timeout=10, cursor_factory=RealDictCursor)
                logging.info("Fallback DB connection successful")
                return conn
            except Exception as e2:
                logging.error(f"Fallback DB also failed: {e2}")
        raise Exception("Database connection failed")

def init_db():
    try:
        conn = get_db_connection()
        c = conn.cursor()

        c.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username VARCHAR(100) UNIQUE NOT NULL,
                password VARCHAR(255) NOT NULL,
                role VARCHAR(50) DEFAULT 'user',
                credits DECIMAL(10,2) DEFAULT 0,
                total_recharged DECIMAL(10,2) DEFAULT 0,
                discord_id VARCHAR(50) UNIQUE,
                discord_joined_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        c.execute('''
            CREATE TABLE IF NOT EXISTS products (
                id SERIAL PRIMARY KEY,
                name VARCHAR(255) UNIQUE NOT NULL,
                credit_cost_per_day DECIMAL(10,2) NOT NULL,
                price_per_day DECIMAL(10,2) NOT NULL,
                key_type VARCHAR(50) DEFAULT 'standard',
                custom_key_pattern TEXT,
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        c.execute('''
            CREATE TABLE IF NOT EXISTS licenses (
                id SERIAL PRIMARY KEY,
                key TEXT UNIQUE NOT NULL,
                username VARCHAR(100) NOT NULL,
                product_name VARCHAR(255) NOT NULL,
                days INTEGER NOT NULL,
                total_credits DECIMAL(10,2) NOT NULL,
                expiry_date TIMESTAMP NOT NULL,
                status VARCHAR(50) DEFAULT 'active',
                last_reset TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        c.execute('''
            CREATE TABLE IF NOT EXISTS payments (
                id SERIAL PRIMARY KEY,
                username VARCHAR(100) NOT NULL,
                payment_method VARCHAR(20) NOT NULL,
                utr VARCHAR(50) UNIQUE,
                order_id VARCHAR(100) UNIQUE,
                amount DECIMAL(10,2) NOT NULL,
                credits_added DECIMAL(10,2) DEFAULT 0,
                status VARCHAR(50) DEFAULT 'pending',
                rejection_reason TEXT,
                date TIMESTAMP NOT NULL,
                expiry_time TIMESTAMP,
                approved_date TIMESTAMP,
                approved_by VARCHAR(100),
                binance_data TEXT
            )
        ''')

        c.execute('''
            CREATE TABLE IF NOT EXISTS key_types (
                id SERIAL PRIMARY KEY,
                type_name VARCHAR(50) UNIQUE NOT NULL,
                pattern TEXT NOT NULL,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        c.execute('''
            CREATE TABLE IF NOT EXISTS notifications (
                id SERIAL PRIMARY KEY,
                title VARCHAR(255) NOT NULL,
                message TEXT NOT NULL,
                target_user VARCHAR(100),
                is_global BOOLEAN DEFAULT FALSE,
                created_by VARCHAR(100),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                read_by TEXT DEFAULT ''
            )
        ''')

        # Default key types
        default_key_types = [
            ('fluorite', 'RANDOM16', '16 characters random'),
            ('gbox', 'RANDOM16', '16 characters random'),
            ('drip', 'DIGITS10', '10 digits'),
            ('hg', 'HG-{RANDOM6}', 'HG-XXXXXX format'),
            ('brmod', 'USER8\nPASS4', 'Username + Password'),
            ('lkteam', 'LKTEAM-{RANDOM6}', 'LKTEAM-XXXXXX'),
            ('strict', 'STRICT-{DIGITS8}', 'STRICT-8 digits'),
            ('spotify', 'EMAIL8@temp.com\nPASS12', 'Email + Password'),
            ('standard', 'KEY-{RANDOM4}-{RANDOM4}', 'KEY-XXXX-XXXX')
        ]
        for type_name, pattern, desc in default_key_types:
            try:
                c.execute('''
                    INSERT INTO key_types (type_name, pattern, description)
                    VALUES (%s, %s, %s) ON CONFLICT (type_name) DO NOTHING
                ''', (type_name, pattern, desc))
            except Exception:
                pass

        # ✅ FIX #4: Admin password from env — NOT hardcoded in source
        admin_user = os.getenv('ADMIN_USERNAME', 'thedigamber')
        admin_pass = os.getenv('ADMIN_PASSWORD')
        if not admin_pass:
            raise RuntimeError("❌ ADMIN_PASSWORD environment variable is not set!")
        hashed = bcrypt.generate_password_hash(admin_pass).decode('utf-8')
        try:
            c.execute('''
                INSERT INTO users (username, password, role, credits)
                VALUES (%s, %s, %s, %s) ON CONFLICT (username) DO NOTHING
            ''', (admin_user, hashed, 'admin', 10000))
        except Exception:
            pass

        # Default products
        default_products = [
            ('Fluorite FF IOS', 25, 50, 'fluorite'),
            ('Drip Android ApkMod', 6, 12, 'drip'),
            ('Drip Aimkill PC', 12, 25, 'drip'),
            ('Drip SilentAim PC', 10, 20, 'drip'),
            ('Gbox IOS Signer', 18, 36, 'gbox'),
            ('Hg Cheat ApkMod', 7, 14, 'hg'),
            ('Prime Apkmod', 5, 10, 'standard'),
            ('GlitchShotx 8BP IOS', 15, 30, 'gbox'),
            ('Brmod SilentAim PC', 10, 20, 'brmod'),
            ('Brmod Bypass + Silent', 8, 16, 'brmod'),
            ('Gbox Esign Cert', 20, 40, 'gbox'),
            ('Pato Blue ApkMod', 5, 10, 'standard'),
            ('Drip Root Android', 8, 16, 'drip'),
            ('LKTEAM Root + PC', 12, 25, 'lkteam'),
            ('Pato Orange ApkMod', 7, 14, 'standard'),
            ('Pato Green ApkMod', 5, 10, 'standard'),
            ('Strics Br Root', 10, 20, 'strict'),
            ('Shield Pubg Android', 9, 18, 'standard'),
            ('Haxxcker Pro Root', 12, 25, 'standard'),
            ('Spotify Root', 5, 10, 'spotify')
        ]
        for name, credits, price, key_type in default_products:
            try:
                c.execute('''
                    INSERT INTO products (name, credit_cost_per_day, price_per_day, key_type)
                    VALUES (%s, %s, %s, %s) ON CONFLICT (name) DO NOTHING
                ''', (name, credits, price, key_type))
            except Exception:
                pass

        conn.commit()
        conn.close()
        logging.info("Database initialized successfully")
        return True
    except Exception as e:
        logging.error(f"Database initialization error: {e}")
        raise

init_db()

# ============================================
# ADD MISSING COLUMNS
# ============================================

def add_missing_columns():
    checks = [
        ('users', 'discord_id', "ALTER TABLE users ADD COLUMN discord_id VARCHAR(50) UNIQUE"),
        ('users', 'discord_joined_at', "ALTER TABLE users ADD COLUMN discord_joined_at TIMESTAMP"),
        ('payments', 'rejection_reason', "ALTER TABLE payments ADD COLUMN rejection_reason TEXT"),
        ('payments', 'expiry_time', "ALTER TABLE payments ADD COLUMN expiry_time TIMESTAMP"),
        ('payments', 'approved_date', "ALTER TABLE payments ADD COLUMN approved_date TIMESTAMP"),
        ('payments', 'approved_by', "ALTER TABLE payments ADD COLUMN approved_by VARCHAR(100)"),
        ('payments', 'binance_data', "ALTER TABLE payments ADD COLUMN binance_data TEXT"),
    ]
    try:
        conn = get_db_connection()
        c = conn.cursor()
        for table, column, alter_sql in checks:
            c.execute("""
                SELECT column_name FROM information_schema.columns
                WHERE table_name=%s AND column_name=%s
            """, (table, column))
            if not c.fetchone():
                c.execute(alter_sql)
                logging.info(f"Added column {table}.{column}")
        conn.commit()
        conn.close()
    except Exception as e:
        logging.error(f"Error adding columns: {e}")

add_missing_columns()

# ============================================
# CONSTANTS
# ============================================

CREDIT_RATE       = float(os.getenv('CREDIT_RATE', 0.5))
MINIMUM_RECHARGE  = int(os.getenv('MIN_RECHARGE', 1000))
UPI_ID            = os.getenv('UPI_ID', 'prabhu84@ptaxis')
UPI_NAME          = os.getenv('UPI_NAME', 'SM GrowMart HQ')
TELEGRAM_SUPPORT_LINK = os.getenv('TELEGRAM_SUPPORT_LINK', 'TELEGRAM_SUPPORT_LINK')
WHATSAPP_CHANNEL  = os.getenv('WHATSAPP_CHANNEL', 'WHATSAPP_CHANNEL')
USD_TO_INR        = 98
BINANCE_ADDRESS   = '814429508'
BINANCE_GATEWAY_URL = 'https://binance.digamber.in'

DISCORD_BOT_TOKEN   = os.getenv('DISCORD_BOT_TOKEN')
DISCORD_GUILD_ID    = os.getenv('DISCORD_GUILD_ID', '1344323930923601992')
DISCORD_INVITE_LINK = os.getenv('DISCORD_INVITE_LINK', 'https://discord.gg/ATK3JcG7rB')

# ============================================
# AUTH DECORATORS
# ============================================

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'username' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'username' not in session or session.get('role') != 'admin':
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

# ============================================
# DISCORD VERIFICATION WITH CACHING
# ============================================

# ✅ FIX #5: Cache with LRU-style eviction to prevent memory leak
_discord_cache = {}
_CACHE_MAX      = 1000
_CACHE_TTL      = 300  # 5 minutes

def check_discord_membership(discord_user_id):
    discord_user_id = str(discord_user_id).strip()
    now = time.time()

    # Evict expired entries to prevent unbounded growth
    if len(_discord_cache) > _CACHE_MAX:
        expired = [k for k, (ts, _) in _discord_cache.items() if now - ts > _CACHE_TTL]
        for k in expired:
            _discord_cache.pop(k, None)

    if discord_user_id in _discord_cache:
        ts, result = _discord_cache[discord_user_id]
        if now - ts < _CACHE_TTL:
            return result

    if not DISCORD_BOT_TOKEN or not DISCORD_GUILD_ID:
        logging.error("Discord Bot Token or Guild ID not configured")
        # In debug mode bypass; in production deny
        return bool(app.debug)

    if not discord_user_id.isdigit():
        logging.error(f"Invalid Discord ID format: {discord_user_id}")
        return False

    url = f"https://discord.com/api/v10/guilds/{DISCORD_GUILD_ID}/members/{discord_user_id}"
    headers = {"Authorization": f"Bot {DISCORD_BOT_TOKEN}"}
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            _discord_cache[discord_user_id] = (now, True)
            return True
        elif response.status_code == 404:
            _discord_cache[discord_user_id] = (now, False)
            return False
        else:
            # API error — fail open to not block legit users
            _discord_cache[discord_user_id] = (now, True)
            return True
    except Exception as e:
        logging.error(f"Discord API error: {e}")
        _discord_cache[discord_user_id] = (now, True)
        return True

# ============================================
# DISCOUNT ENGINE
# ============================================

def calculate_recharge_credits(amount):
    amount = float(amount)
    base_credits = amount * CREDIT_RATE
    bonus = 0
    if amount >= 10000:
        bonus = 200
    elif amount >= 5000:
        bonus = 80
    elif amount >= 2000:
        bonus = 20
    return round(base_credits + bonus, 2)

def calculate_discounted_credits(base_credit_per_day, days):
    # Multipliers: total cost = base * multiplier (less than days * base = discount)
    tiers = {1: 1.0, 3: 1.5, 7: 2.0, 15: 3.0, 30: 4.0, 60: 5.0, 90: 6.0}
    if days in tiers:
        return base_credit_per_day * tiers[days]
    sorted_tiers = sorted(tiers.keys())
    if days < 1:
        return base_credit_per_day
    if days > 90:
        extra = (days - 90) / 30 * 0.5
        return base_credit_per_day * (6.0 + extra)
    for i in range(len(sorted_tiers) - 1):
        lo, hi = sorted_tiers[i], sorted_tiers[i + 1]
        if lo < days < hi:
            ratio = (days - lo) / (hi - lo)
            mult = tiers[lo] + ratio * (tiers[hi] - tiers[lo])
            return base_credit_per_day * mult
    return base_credit_per_day * days

# ============================================
# KEY GENERATOR
# ============================================

class KeyGenerator:
    def __init__(self):
        self.generators = {
            'fluorite': self._generate_fluorite,
            'gbox':     self._generate_gbox,
            'drip':     self._generate_drip,
            'hg':       self._generate_hg,
            'brmod':    self._generate_brmod,
            'lkteam':   self._generate_lkteam,
            'strict':   self._generate_strict,
            'spotify':  self._generate_spotify,
            'standard': self._generate_standard,
        }

    def generate_key(self, key_type, custom_pattern=None):
        if custom_pattern:
            return self._generate_from_pattern(custom_pattern)
        generator = self.generators.get(key_type, self._generate_standard)
        return generator()

    def _r(self, chars, n):
        return ''.join(secrets.choice(chars) for _ in range(n))

    def _generate_from_pattern(self, pattern):
        AZ09 = string.ascii_uppercase + string.digits
        az09 = string.ascii_lowercase + string.digits
        az   = string.ascii_lowercase
        ALL  = string.ascii_letters + string.digits
        replacements = {
            'RANDOM4':  lambda: self._r(AZ09, 4),
            'RANDOM6':  lambda: self._r(AZ09, 6),
            'RANDOM8':  lambda: self._r(AZ09, 8),
            'RANDOM10': lambda: self._r(AZ09, 10),
            'RANDOM12': lambda: self._r(AZ09, 12),
            'RANDOM16': lambda: self._r(AZ09, 16),
            'DIGITS4':  lambda: self._r(string.digits, 4),
            'DIGITS6':  lambda: self._r(string.digits, 6),
            'DIGITS8':  lambda: self._r(string.digits, 8),
            'DIGITS10': lambda: self._r(string.digits, 10),
            'USER4':    lambda: self._r(az, 4),
            'USER6':    lambda: self._r(az, 6),
            'USER8':    lambda: self._r(az09, 8),
            'PASS4':    lambda: self._r(ALL, 4),
            'PASS6':    lambda: self._r(ALL, 6),
            'PASS8':    lambda: self._r(ALL, 8),
            'PASS12':   lambda: self._r(ALL, 12),
            'DATE':     lambda: datetime.now().strftime('%Y%m%d'),
            'TIME':     lambda: datetime.now().strftime('%H%M%S'),
            'YEAR':     lambda: datetime.now().strftime('%Y'),
            'MONTH':    lambda: datetime.now().strftime('%m'),
            'DAY':      lambda: datetime.now().strftime('%d'),
        }
        result = pattern
        for ph in re.findall(r'\{([^}]+)\}', result):
            if ph in replacements:
                result = result.replace(f'{{{ph}}}', replacements[ph](), 1)
        return result

    def _generate_fluorite(self): return self._r(string.ascii_uppercase + string.digits, 16)
    def _generate_gbox(self):     return self._r(string.ascii_uppercase + string.digits, 16)
    def _generate_drip(self):     return self._r(string.digits, 10)
    def _generate_hg(self):       return f"HG-{self._r(string.ascii_uppercase + string.digits, 6)}"
    def _generate_lkteam(self):   return f"LKTEAM-{self._r(string.ascii_uppercase + string.digits, 6)}"
    def _generate_strict(self):   return f"STRICT-{self._r(string.digits, 8)}"
    def _generate_brmod(self):
        u = self._r(string.ascii_lowercase + string.digits, 8)
        p = self._r(string.ascii_lowercase + string.digits, 4)
        return f"User: {u}\nPass: {p}"
    def _generate_spotify(self):
        u = self._r(string.ascii_lowercase + string.digits, 8)
        p = self._r(string.ascii_letters + string.digits, 12)
        return f"Username: {u}@temp.com\nPassword: {p}"
    def _generate_standard(self):
        p1 = self._r(string.ascii_uppercase + string.digits, 4)
        p2 = self._r(string.ascii_uppercase + string.digits, 4)
        return f"KEY-{p1}-{p2}"

key_gen = KeyGenerator()

# ============================================
# BINANCE API
# ============================================

class BinanceAPI:
    def __init__(self):
        self.base_url = os.getenv('BINANCE_API_URL', 'https://binance-verifier.onrender.com')
        self.timeout  = 30

    def _request(self, endpoint, method='GET', data=None):
        try:
            url = self.base_url + endpoint
            headers = {'Content-Type': 'application/json'}
            if method == 'GET':
                resp = requests.get(url, headers=headers, timeout=self.timeout)
            else:
                resp = requests.post(url, headers=headers, json=data, timeout=self.timeout)
            if resp.status_code == 200:
                return resp.json()
            logging.error(f"Binance API {endpoint}: HTTP {resp.status_code}")
            return {'success': False, 'error': f'HTTP {resp.status_code}'}
        except Exception as e:
            logging.error(f"Binance API error: {e}")
            return {'success': False, 'error': str(e)}

    def create_order(self, amount, email=None):
        try:
            payload = {'amount': float(amount), 'customerEmail': email or f"user{int(time.time())}@temp.com"}
            result = self._request('/api/create-order', 'POST', payload)
            if result and result.get('success'):
                return result
            return {'success': True, 'orderId': f"ORD{int(time.time())}{random.randint(100,999)}", 'amount': amount, 'status': 'pending'}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def check_order(self, order_id):
        try:
            return self._request(f'/api/check/{order_id}') or {'success': True, 'status': 'pending', 'orderId': order_id}
        except Exception:
            return {'success': True, 'status': 'pending', 'orderId': order_id}

    def cancel_order(self, order_id):
        try:
            return self._request(f'/api/cancel/{order_id}', 'POST') or {'success': True, 'message': 'Order cancelled'}
        except Exception as e:
            logging.error(f"Cancel order API error: {e}")
            return {'success': False, 'error': str(e)}

    def get_address(self, order_id): return {'address': BINANCE_ADDRESS}
    def get_qr(self, order_id):      return self._request(f'/api/qr/{order_id}')

binance_api = BinanceAPI()

# ============================================
# HELPERS
# ============================================

def generate_upi_qr(amount):
    try:
        upi_url = f"upi://pay?pa={UPI_ID}&pn={UPI_NAME}&am={amount}&cu=INR"
        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(upi_url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buf = BytesIO()
        img.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode()
    except Exception as e:
        logging.error(f"QR error: {e}")
        return None

def format_datetime(dt):
    if dt is None: return 'N/A'
    if hasattr(dt, 'strftime'): return dt.strftime('%Y-%m-%d %H:%M')
    if isinstance(dt, str): return dt[:16]
    return str(dt)

# ============================================
# NOTIFICATION ROUTES
# ============================================

@app.route('/api/notifications')
@login_required
def get_notifications():
    conn = get_db_connection()
    c = conn.cursor()
    username = session['username']
    # ✅ FIX #6: Use POSITION instead of LIKE to avoid % wildcard injection
    c.execute('''
        SELECT * FROM notifications
        WHERE (is_global = TRUE OR target_user = %s)
          AND (read_by IS NULL OR POSITION(%s IN read_by) = 0)
        ORDER BY created_at DESC LIMIT 50
    ''', (username, username))
    notifications = c.fetchall()
    conn.close()
    return jsonify({'success': True, 'notifications': notifications})

@app.route('/api/notifications/mark_read', methods=['POST'])
@login_required
def mark_notification_read():
    data = request.get_json()
    notification_id = data.get('notification_id')
    username = session['username']
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('SELECT read_by FROM notifications WHERE id = %s', (notification_id,))
    notif = c.fetchone()
    if notif:
        read_list = notif['read_by'] or ''
        if username not in read_list.split(','):
            new_read = f"{read_list},{username}" if read_list else username
            c.execute('UPDATE notifications SET read_by = %s WHERE id = %s', (new_read, notification_id))
            conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/admin/send_notification', methods=['POST'])
@admin_required
def send_notification():
    data = request.get_json()
    title      = data.get('title', 'Announcement')
    message    = data.get('message', '').strip()
    target_user= data.get('target_user') or None
    is_global  = target_user is None
    if not message:
        return jsonify({'success': False, 'error': 'Message required'})
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''
        INSERT INTO notifications (title, message, target_user, is_global, created_by)
        VALUES (%s, %s, %s, %s, %s)
    ''', (title, message, target_user, is_global, session['username']))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/admin/get_users_list')
@admin_required
def get_users_list():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT username FROM users WHERE role != 'admin' ORDER BY username")
    users = [u['username'] for u in c.fetchall()]
    conn.close()
    return jsonify({'success': True, 'users': users})

# ============================================
# AUTH ROUTES
# ============================================

@app.route('/')
def index():
    if 'username' in session:
        if session.get('role') == 'admin':
            return redirect(url_for('admin_dashboard'))
        return redirect(url_for('user_dashboard'))
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        if not username or not password:
            return render_template('login.html', error='Username and password required')
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE username = %s", (username,))
        user = c.fetchone()
        conn.close()
        if user and bcrypt.check_password_hash(user['password'], password):
            session.clear()
            session['username'] = user['username']
            session['role']     = user['role']
            session['credits']  = float(user['credits'] or 0)
            session['user_id']  = user['id']
            return redirect(url_for('admin_dashboard') if user['role'] == 'admin' else url_for('user_dashboard'))
        return render_template('login.html', error='Invalid credentials',
                               telegram_support=TELEGRAM_SUPPORT_LINK,
                               whatsapp_channel=WHATSAPP_CHANNEL)
    return render_template('login.html',
                           telegram_support=TELEGRAM_SUPPORT_LINK,
                           whatsapp_channel=WHATSAPP_CHANNEL)

@app.route('/register', methods=['GET', 'POST'])
def register():
    ctx = dict(discord_invite=DISCORD_INVITE_LINK,
               whatsapp_channel=WHATSAPP_CHANNEL,
               telegram_support=TELEGRAM_SUPPORT_LINK)
    if request.method == 'POST':
        username   = request.form.get('username', '').strip()
        password   = request.form.get('password', '')
        confirm    = request.form.get('confirm_password', '')
        discord_id = request.form.get('discord_id', '').strip()

        if not username or not password or not discord_id:
            return render_template('register.html', error='All fields are required', **ctx)
        if password != confirm:
            return render_template('register.html', error='Passwords do not match', **ctx)
        if len(password) < 6:
            return render_template('register.html', error='Password must be at least 6 characters', **ctx)

        if not check_discord_membership(discord_id):
            return render_template('register.html',
                                   error=f'You must join our Discord server first! → {DISCORD_INVITE_LINK}', **ctx)

        hashed = bcrypt.generate_password_hash(password).decode('utf-8')
        conn = get_db_connection()
        c = conn.cursor()
        try:
            c.execute('''
                INSERT INTO users (username, password, role, credits, discord_id, discord_joined_at)
                VALUES (%s, %s, %s, %s, %s, %s)
            ''', (username, hashed, 'user', 0, discord_id, datetime.now()))
            conn.commit()
            conn.close()
            # ✅ FIX #7: After register, redirect to login (not just render index)
            return redirect(url_for('login'))
        except Exception as e:
            conn.close()
            logging.error(f"Registration error: {e}")
            if 'duplicate key' in str(e).lower():
                return render_template('register.html', error='Username or Discord ID already exists', **ctx)
            return render_template('register.html', error='Registration failed. Please try again.', **ctx)
    return render_template('register.html', **ctx)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# ============================================
# USER DASHBOARD
# ============================================

@app.route('/dashboard')
@login_required
def user_dashboard():
    if session.get('role') != 'user':
        return redirect(url_for('admin_dashboard'))
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE username = %s", (session['username'],))
    user = c.fetchone()
    if not user:
        session.clear()
        conn.close()
        return redirect(url_for('login'))
    session['credits'] = float(user['credits'] or 0)
    c.execute("SELECT * FROM products WHERE is_active = TRUE ORDER BY name")
    products = c.fetchall()
    c.execute("SELECT * FROM licenses WHERE username = %s ORDER BY expiry_date DESC LIMIT 50", (session['username'],))
    licenses = c.fetchall()
    c.execute("SELECT * FROM payments WHERE username = %s ORDER BY date DESC LIMIT 20", (session['username'],))
    payments = c.fetchall()
    conn.close()
    return render_template('dashboard.html', user=user, products=products,
                           licenses=licenses, payments=payments,
                           format_datetime=format_datetime,
                           telegram_support=TELEGRAM_SUPPORT_LINK,
                           whatsapp_channel=WHATSAPP_CHANNEL)

# ============================================
# KEY GENERATION
# ============================================

@app.route('/api/discounted_price', methods=['POST'])
@login_required          # ✅ FIX #8: was unauthenticated — anyone could probe prices
def api_discounted_price():
    data = request.get_json()
    product_id = data.get('product_id')
    days = int(data.get('days', 1))
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT credit_cost_per_day FROM products WHERE id = %s AND is_active = TRUE", (product_id,))
    product = c.fetchone()
    conn.close()
    if not product:
        return jsonify({'success': False, 'error': 'Product not found'})
    base  = float(product['credit_cost_per_day'])
    total = calculate_discounted_credits(base, days)
    return jsonify({
        'success': True,
        'total_credits':  round(total, 2),
        'original_total': round(base * days, 2),
        'savings':        round((base * days) - total, 2)
    })

@app.route('/generate_key', methods=['POST'])
@login_required
def generate_key_route():
    data       = request.get_json()
    product_id = data.get('product_id')
    days       = int(data.get('days', 1))

    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute("SELECT * FROM products WHERE id = %s AND is_active = TRUE", (product_id,))
        product = c.fetchone()
        if not product:
            return jsonify({'success': False, 'error': 'Product not found'})

        base_credit   = float(product['credit_cost_per_day'])
        total_credits = calculate_discounted_credits(base_credit, days)

        # ✅ FIX #9: Atomic credit deduction — prevents race condition & negative balance
        # Only deduct if user CURRENTLY has enough credits (atomic UPDATE + check)
        c.execute('''
            UPDATE users
            SET credits = credits - %s
            WHERE username = %s AND credits >= %s
            RETURNING credits
        ''', (total_credits, session['username'], total_credits))
        updated = c.fetchone()

        if not updated:
            return jsonify({'success': False, 'error': f'Insufficient credits (need {total_credits:.1f})'})

        new_credits = float(updated['credits'])

        # Generate key (retry up to 5 times on collision)
        key    = None
        expiry = datetime.now() + timedelta(days=days)
        for attempt in range(5):
            candidate = key_gen.generate_key(product['key_type'], product.get('custom_key_pattern'))
            try:
                c.execute('''
                    INSERT INTO licenses (key, username, product_name, days, total_credits, expiry_date, status)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                ''', (candidate, session['username'], product['name'], days,
                      total_credits, expiry, 'active'))
                key = candidate
                break
            except Exception:
                # ✅ FIX #10: Key collision — retry; if all retries fail, refund credits
                conn.rollback()
                if attempt == 4:
                    # Refund credits after all retries exhausted
                    c.execute('UPDATE users SET credits = credits + %s WHERE username = %s',
                              (total_credits, session['username']))
                    conn.commit()
                    return jsonify({'success': False, 'error': 'Key generation failed — credits refunded. Please try again.'})

        conn.commit()
        session['credits'] = new_credits
        return jsonify({
            'success': True,
            'key': key,
            'original_price': round(base_credit * days, 2),
            'final_price':    round(total_credits, 2),
            'savings':        round((base_credit * days) - total_credits, 2)
        })
    except Exception as e:
        conn.rollback()
        logging.error(f"Key generation error: {e}")
        return jsonify({'success': False, 'error': 'Server error. Please try again.'})
    finally:
        conn.close()

# ============================================
# PAYMENT ROUTES
# ============================================

@app.route('/payment')
@login_required
def payment_page():
    return render_template('payment.html',
                           min_recharge=MINIMUM_RECHARGE, credit_rate=CREDIT_RATE,
                           upi_id=UPI_ID, usd_to_inr=USD_TO_INR,
                           binance_address=BINANCE_ADDRESS,
                           telegram_support=TELEGRAM_SUPPORT_LINK,
                           whatsapp_channel=WHATSAPP_CHANNEL,
                           calculate_credits=calculate_recharge_credits)

def _payment_ctx(extra=None):
    ctx = dict(min_recharge=MINIMUM_RECHARGE, credit_rate=CREDIT_RATE, upi_id=UPI_ID,
               usd_to_inr=USD_TO_INR, binance_address=BINANCE_ADDRESS,
               telegram_support=TELEGRAM_SUPPORT_LINK, whatsapp_channel=WHATSAPP_CHANNEL,
               calculate_credits=calculate_recharge_credits)
    if extra: ctx.update(extra)
    return ctx

@app.route('/payment/upi', methods=['GET', 'POST'])
@login_required
def upi_payment():
    if request.method == 'POST':
        utr    = request.form.get('utr', '').strip()
        amount = float(request.form.get('amount', 0))

        if amount < MINIMUM_RECHARGE:
            qr = generate_upi_qr(MINIMUM_RECHARGE)
            return render_template('upi_payment.html',
                                   error=f'Minimum amount is ₹{MINIMUM_RECHARGE}',
                                   qr_code=qr, amount=amount,
                                   **_payment_ctx())

        if not utr or len(utr) != 12 or not utr.isdigit():
            qr = generate_upi_qr(amount)
            return render_template('upi_payment.html',
                                   error='Please enter a valid 12-digit UTR number',
                                   qr_code=qr, amount=amount,
                                   **_payment_ctx())

        credits = calculate_recharge_credits(amount)
        conn = get_db_connection()
        c = conn.cursor()
        try:
            c.execute('''
                INSERT INTO payments (username, payment_method, utr, amount, credits_added, status, date)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            ''', (session['username'], 'upi', utr, amount, credits, 'pending', datetime.now()))
            conn.commit()
            conn.close()
            qr = generate_upi_qr(amount)
            return render_template('upi_payment.html',
                                   success=f'Payment submitted! ₹{amount} = {credits:.0f} credits pending approval.',
                                   qr_code=qr, amount=amount, **_payment_ctx())
        except Exception as e:
            conn.close()
            # ✅ FIX #11: Distinguish real errors from duplicate UTR
            error_msg = 'UTR already submitted! Please wait for approval.' if 'unique' in str(e).lower() else 'Submission failed. Please try again.'
            logging.error(f"UPI payment insert error: {e}")
            qr = generate_upi_qr(amount)
            return render_template('upi_payment.html',
                                   error=error_msg, qr_code=qr, amount=amount, **_payment_ctx())

    qr = generate_upi_qr(MINIMUM_RECHARGE)
    return render_template('upi_payment.html', qr_code=qr, amount=MINIMUM_RECHARGE, **_payment_ctx())

@app.route('/payment/binance', methods=['GET', 'POST'])
@login_required
def binance_payment():
    if request.method == 'POST':
        amount_inr = float(request.form.get('amount', 0))
        if amount_inr < MINIMUM_RECHARGE:
            return render_template('binance_payment.html',
                                   error=f'Minimum ₹{MINIMUM_RECHARGE}', **_payment_ctx())
        amount_usd = round(amount_inr / USD_TO_INR, 2)
        result = binance_api.create_order(amount_usd, session['username'])
        if result and result.get('success'):
            order_id = result.get('orderId')
            credits  = calculate_recharge_credits(amount_inr)
            conn = get_db_connection()
            c = conn.cursor()
            try:
                c.execute('''
                    INSERT INTO payments (username, payment_method, order_id, amount, credits_added, status, date, expiry_time, binance_data)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ''', (session['username'], 'binance', order_id, amount_inr, credits, 'pending',
                      datetime.now(), datetime.now() + timedelta(minutes=10), json.dumps(result)))
                conn.commit()
            finally:
                conn.close()
            return render_template('binance_payment.html',
                                   order_id=order_id, amount_inr=amount_inr,
                                   amount_usd=amount_usd, credits=credits,
                                   binance_address=BINANCE_ADDRESS, **_payment_ctx())
        return render_template('binance_payment.html',
                               error='Unable to create Binance order. Please try UPI.', **_payment_ctx())
    return render_template('binance_payment.html', **_payment_ctx())

@app.route('/payment/binance/check/<order_id>')
@login_required
def check_binance_payment(order_id):
    result = binance_api.check_order(order_id)
    if result and result.get('status') == 'completed':
        conn = get_db_connection()
        c = conn.cursor()
        try:
            # ✅ FIX #12: Only credit if status is still pending (prevents double-credit)
            c.execute('''
                UPDATE payments SET status = 'approved', approved_date = %s
                WHERE order_id = %s AND status = 'pending'
                RETURNING username, credits_added, amount
            ''', (datetime.now(), order_id))
            row = c.fetchone()
            if row:
                c.execute('''
                    UPDATE users SET credits = credits + %s, total_recharged = total_recharged + %s
                    WHERE username = %s
                ''', (float(row['credits_added']), float(row['amount']), row['username']))
                conn.commit()
                return jsonify({'success': True, 'status': 'completed', 'credited': True,
                                'credits': float(row['credits_added'])})
        finally:
            conn.close()
    status = (result.get('status', 'pending') if result else 'pending')
    return jsonify({'success': True, 'status': status})

@app.route('/payment/binance/cleanup/<order_id>', methods=['POST'])
@login_required   # ✅ FIX #13: Was completely unauthenticated — anyone could delete payments!
def cleanup_binance_order(order_id):
    conn = get_db_connection()
    c = conn.cursor()
    # Only allow user to delete their OWN pending orders
    c.execute("DELETE FROM payments WHERE order_id = %s AND status = 'pending' AND username = %s",
              (order_id, session['username']))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/generate_payment_qr', methods=['POST'])
@login_required
def generate_payment_qr():
    data   = request.get_json()
    amount = float(data.get('amount', MINIMUM_RECHARGE))
    if amount < MINIMUM_RECHARGE:
        return jsonify({'success': False, 'error': f'Minimum amount is ₹{MINIMUM_RECHARGE}'})
    qr_code = generate_upi_qr(amount)
    return jsonify({'success': True, 'qr_code': qr_code, 'amount': amount,
                    'credits': calculate_recharge_credits(amount)})

# ============================================
# ADMIN DASHBOARD
# ============================================

@app.route('/admin')
@admin_required
def admin_dashboard():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users WHERE role = 'user'")
    total_users = c.fetchone()['count']
    c.execute("SELECT COALESCE(SUM(amount), 0) FROM payments WHERE status = 'approved'")
    total_revenue = float(c.fetchone()['coalesce'])
    c.execute("SELECT COALESCE(SUM(credits_added), 0) FROM payments WHERE status = 'approved'")
    total_credits_sold = float(c.fetchone()['coalesce'])
    c.execute("SELECT COUNT(*) FROM payments WHERE status = 'pending'")
    pending_payments = c.fetchone()['count']
    c.execute("SELECT COUNT(*) FROM licenses WHERE status = 'active'")
    active_keys = c.fetchone()['count']
    c.execute("SELECT * FROM users WHERE role != 'admin' ORDER BY credits DESC")
    users = c.fetchall()
    c.execute("SELECT * FROM payments ORDER BY CASE status WHEN 'pending' THEN 1 ELSE 2 END, date DESC")
    payments = c.fetchall()
    c.execute("SELECT * FROM licenses ORDER BY expiry_date DESC LIMIT 100")
    licenses = c.fetchall()
    c.execute("SELECT * FROM products ORDER BY name")
    products = c.fetchall()
    c.execute("SELECT * FROM key_types ORDER BY type_name")
    key_types = c.fetchall()
    conn.close()
    return render_template('admin.html',
                           users=users, payments=payments, licenses=licenses,
                           products=products, key_types=key_types,
                           total_users=total_users, total_revenue=total_revenue,
                           total_credits_sold=total_credits_sold,
                           pending_payments=pending_payments, active_keys=active_keys,
                           format_datetime=format_datetime,
                           binance_address=BINANCE_ADDRESS,
                           telegram_support=TELEGRAM_SUPPORT_LINK,
                           whatsapp_channel=WHATSAPP_CHANNEL)

# ============================================
# ADMIN — PAYMENT ACTIONS
# ============================================

@app.route('/admin/approve_payment', methods=['POST'])
@admin_required
def approve_payment():
    data       = request.get_json()
    payment_id = data.get('payment_id')
    if not payment_id:
        return jsonify({'success': False, 'error': 'Payment ID required'})
    conn = get_db_connection()
    try:
        c = conn.cursor()
        # ✅ FIX #14: Atomic — only update if status is STILL pending (prevents double-credit)
        c.execute('''
            UPDATE payments
            SET status = 'approved', approved_date = %s, approved_by = %s, rejection_reason = NULL
            WHERE id = %s AND status = 'pending'
            RETURNING username, credits_added, amount
        ''', (datetime.now(), session['username'], payment_id))
        row = c.fetchone()
        if not row:
            return jsonify({'success': False, 'error': 'Payment not found or already processed'})
        c.execute('''
            UPDATE users SET credits = credits + %s, total_recharged = total_recharged + %s
            WHERE username = %s
        ''', (float(row['credits_added']), float(row['amount']), row['username']))
        conn.commit()
        return jsonify({'success': True, 'message': 'Payment approved'})
    except Exception as e:
        conn.rollback()
        logging.error(f"Approve payment error: {e}")
        return jsonify({'success': False, 'error': str(e)})
    finally:
        conn.close()

@app.route('/admin/reject_payment', methods=['POST'])
@admin_required
def reject_payment():
    data       = request.get_json()
    payment_id = data.get('payment_id')
    reason     = data.get('reason', 'Payment rejected by admin')
    if not payment_id:
        return jsonify({'success': False, 'error': 'Payment ID required'})
    conn = get_db_connection()
    try:
        c = conn.cursor()
        c.execute('''
            UPDATE payments SET status = 'rejected', rejection_reason = %s, approved_by = %s
            WHERE id = %s AND status = 'pending'
            RETURNING id
        ''', (reason, session['username'], payment_id))
        if not c.fetchone():
            return jsonify({'success': False, 'error': 'Payment not found or already processed'})
        conn.commit()
        return jsonify({'success': True})
    except Exception as e:
        conn.rollback()
        logging.error(f"Reject payment error: {e}")
        return jsonify({'success': False, 'error': str(e)})
    finally:
        conn.close()

@app.route('/admin/cancel_binance_order', methods=['POST'])
@admin_required
def cancel_binance_order():
    data     = request.get_json()
    order_id = data.get('order_id')
    if not order_id:
        return jsonify({'success': False, 'error': 'Order ID required'})
    conn = get_db_connection()
    try:
        binance_result = binance_api.cancel_order(order_id)
        c = conn.cursor()
        c.execute("DELETE FROM payments WHERE order_id = %s", (order_id,))
        conn.commit()
        return jsonify({'success': True, 'message': 'Order cancelled'})
    except Exception as e:
        conn.rollback()
        logging.error(f"Cancel order error: {e}")
        return jsonify({'success': False, 'error': str(e)})
    finally:
        conn.close()

# ============================================
# ADMIN — PRODUCT MANAGEMENT
# ============================================

@app.route('/admin/add_product', methods=['POST'])
@admin_required
def add_product():
    data    = request.get_json()
    name    = data.get('name', '').strip()
    credits = float(data.get('credit_cost_per_day', 0))
    price   = float(data.get('price_per_day', 0))
    key_type= data.get('key_type', 'standard')
    pattern = data.get('custom_key_pattern') or None
    if not name or credits <= 0 or price <= 0:
        return jsonify({'success': False, 'error': 'Invalid data'})
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute('''INSERT INTO products (name, credit_cost_per_day, price_per_day, key_type, custom_key_pattern)
                     VALUES (%s, %s, %s, %s, %s)''', (name, credits, price, key_type, pattern))
        conn.commit()
        return jsonify({'success': True})
    except Exception:
        return jsonify({'success': False, 'error': 'Product name already exists'})
    finally:
        conn.close()

@app.route('/admin/edit_product', methods=['POST'])
@admin_required
def edit_product():
    data    = request.get_json()
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute('''UPDATE products SET name=%s, credit_cost_per_day=%s, price_per_day=%s, key_type=%s, custom_key_pattern=%s
                     WHERE id=%s''',
                  (data.get('name'), float(data.get('credit_cost_per_day', 0)),
                   float(data.get('price_per_day', 0)), data.get('key_type'),
                   data.get('custom_key_pattern') or None, data.get('product_id')))
        conn.commit()
        return jsonify({'success': True})
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)})
    finally:
        conn.close()

@app.route('/admin/delete_product', methods=['POST'])
@admin_required
def delete_product():
    data = request.get_json()
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute("DELETE FROM products WHERE id = %s", (data.get('product_id'),))
        conn.commit()
        return jsonify({'success': True})
    finally:
        conn.close()

@app.route('/admin/toggle_product', methods=['POST'])
@admin_required
def toggle_product():
    data = request.get_json()
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute("UPDATE products SET is_active = %s WHERE id = %s",
                  (data.get('is_active', True), data.get('product_id')))
        conn.commit()
        return jsonify({'success': True})
    finally:
        conn.close()

# ============================================
# ADMIN — KEY TYPE MANAGEMENT
# ============================================

@app.route('/admin/add_key_type', methods=['POST'])
@admin_required
def add_key_type():
    data = request.get_json()
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute('''INSERT INTO key_types (type_name, pattern, description) VALUES (%s, %s, %s)''',
                  (data.get('type_name'), data.get('pattern'), data.get('description')))
        conn.commit()
        return jsonify({'success': True})
    except Exception:
        return jsonify({'success': False, 'error': 'Type name already exists'})
    finally:
        conn.close()

@app.route('/admin/get_key_types')
@admin_required
def get_key_types():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM key_types ORDER BY type_name")
    types = c.fetchall()
    conn.close()
    return jsonify({'success': True, 'key_types': types})

# ============================================
# ADMIN — USER MANAGEMENT
# ============================================

@app.route('/admin/add_credits', methods=['POST'])
@admin_required
def add_credits():
    data    = request.get_json()
    username= data.get('username')
    credits = float(data.get('credits', 0))
    if credits <= 0:
        return jsonify({'success': False, 'error': 'Invalid amount'})
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute("UPDATE users SET credits = credits + %s WHERE username = %s", (credits, username))
        conn.commit()
        return jsonify({'success': True})
    finally:
        conn.close()

@app.route('/admin/delete_user', methods=['POST'])
@admin_required
def delete_user():
    data     = request.get_json()
    username = data.get('username')
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute("DELETE FROM licenses WHERE username = %s", (username,))
        c.execute("DELETE FROM payments WHERE username = %s", (username,))
        c.execute("DELETE FROM users WHERE username = %s AND role != 'admin'", (username,))
        conn.commit()
        return jsonify({'success': True})
    finally:
        conn.close()

@app.route('/admin/delete_key', methods=['POST'])
@admin_required
def delete_key():
    data = request.get_json()
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute("DELETE FROM licenses WHERE id = %s", (data.get('license_id'),))
        conn.commit()
        return jsonify({'success': True})
    finally:
        conn.close()

# ============================================
# HWID RESET
# ============================================

@app.route('/hwid_reset', methods=['POST'])
@login_required
def hwid_reset():
    data       = request.get_json()
    license_id = data.get('license_id')
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute("UPDATE licenses SET last_reset = %s WHERE id = %s AND username = %s",
                  (datetime.now(), license_id, session['username']))
        conn.commit()
        return jsonify({'success': True})
    finally:
        conn.close()

@app.route('/hwid_reset_all', methods=['POST'])
@login_required
def hwid_reset_all():
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute("UPDATE licenses SET last_reset = %s WHERE username = %s",
                  (datetime.now(), session['username']))
        conn.commit()
        return jsonify({'success': True})
    finally:
        conn.close()

# ============================================
# CRYPTO ORDER API
# ============================================

@app.route('/api/create_crypto_order', methods=['POST'])
@login_required
def create_crypto_order():
    data     = request.get_json()
    amount   = data.get('amount')
    currency = data.get('currency', 'USDT')
    network  = data.get('network', 'BSC')
    allowed_amounts = [10, 20, 30, 50, 100]
    if amount not in allowed_amounts:
        return jsonify({'success': False, 'error': 'Invalid amount'})
    try:
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        resp = requests.post("https://binance.digamber.in/api/orders",
                             json={'amount': float(amount), 'currency': currency, 'network': network},
                             headers=headers, timeout=30)
        if resp.status_code == 200:
            order_data = resp.json()
            credits = amount * USD_TO_INR * CREDIT_RATE
            conn = get_db_connection()
            c = conn.cursor()
            try:
                c.execute('''INSERT INTO payments (username, payment_method, order_id, amount, credits_added, status, date)
                             VALUES (%s, %s, %s, %s, %s, %s, %s)''',
                          (session['username'], 'binance', order_data.get('id'),
                           amount * USD_TO_INR, credits, 'pending', datetime.now()))
                conn.commit()
            finally:
                conn.close()
            return jsonify({'success': True, 'order_id': order_data.get('id'),
                            'qr_code': order_data.get('qr_code_base64'),
                            'address': order_data.get('deposit_address'),
                            'amount_crypto': order_data.get('unique_amount'),
                            'expires_at': order_data.get('expires_at')})
        return jsonify({'success': False, 'error': f'Gateway error: {resp.status_code}'})
    except Exception as e:
        logging.error(f"Crypto order error: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/check_crypto_order/<order_id>')
@login_required
def check_crypto_order(order_id):
    try:
        headers = {'Accept': 'application/json', 'User-Agent': 'Mozilla/5.0'}
        resp = requests.get(f"https://binance.digamber.in/api/orders/{order_id}",
                            headers=headers, timeout=30)
        if resp.status_code == 200:
            order_data = resp.json()
            status = order_data.get('status', 'PENDING').upper()
            if status == 'COMPLETED':
                conn = get_db_connection()
                try:
                    c = conn.cursor()
                    # ✅ FIX #15: Atomic update — only credit if still pending
                    c.execute('''UPDATE payments SET status='approved', approved_date=%s
                                 WHERE order_id=%s AND status='pending'
                                 RETURNING username, credits_added, amount''',
                              (datetime.now(), order_id))
                    row = c.fetchone()
                    if row:
                        c.execute('''UPDATE users SET credits=credits+%s, total_recharged=total_recharged+%s
                                     WHERE username=%s''',
                                  (row['credits_added'], row['amount'], row['username']))
                        conn.commit()
                        return jsonify({'success': True, 'status': 'completed'})
                finally:
                    conn.close()  # ✅ FIX #16: was missing conn.close() in completed path
            return jsonify({'success': True, 'status': status.lower()})
        return jsonify({'success': True, 'status': 'pending'})
    except Exception as e:
        logging.error(f"Check order error: {e}")
        return jsonify({'success': True, 'status': 'pending'})

# ============================================
# STATIC / MISC ROUTES
# ============================================

@app.route('/<path:filename>')
def static_files(filename):
    # ✅ FIX: Only allow specific safe extensions + block path traversal
    ALLOWED = ('.js', '.html', '.txt', '.xml', '.css', '.ico', '.png', '.jpg', '.gif', '.webp')
    # Block any path traversal attempts
    if '..' in filename or filename.startswith('/'):
        return redirect(url_for('index'))
    if filename.endswith(ALLOWED):
        return send_from_directory('static', filename)
    return redirect(url_for('index'))

@app.route('/robots.txt')
def robots_txt():
    return send_from_directory('static', 'robots.txt', mimetype='text/plain')

@app.route('/sw.js')
def service_worker():
    return send_from_directory('static', 'sw.js', mimetype='application/javascript')

@app.route('/privacy')
def privacy():
    return render_template('privacy.html', telegram_support=TELEGRAM_SUPPORT_LINK, whatsapp_channel=WHATSAPP_CHANNEL)

@app.route('/terms')
def terms():
    return render_template('terms.html', telegram_support=TELEGRAM_SUPPORT_LINK, whatsapp_channel=WHATSAPP_CHANNEL)

@app.route('/about')
def about():
    return render_template('about.html', telegram_support=TELEGRAM_SUPPORT_LINK, whatsapp_channel=WHATSAPP_CHANNEL)

@app.route('/home')
def home():
    return redirect(url_for('index'))

@app.route('/premium')
@login_required
def access_panel():
    return render_template('premium.html', telegram_support=TELEGRAM_SUPPORT_LINK, whatsapp_channel=WHATSAPP_CHANNEL)

# ============================================
# ERROR HANDLERS
# ============================================

@app.errorhandler(404)
def not_found_error(e):
    return render_template('error.html', error="Page not found",
                           telegram_support=TELEGRAM_SUPPORT_LINK,
                           whatsapp_channel=WHATSAPP_CHANNEL), 404

@app.errorhandler(500)
def internal_error(e):
    return render_template('error.html', error="Internal Server Error",
                           telegram_support=TELEGRAM_SUPPORT_LINK,
                           whatsapp_channel=WHATSAPP_CHANNEL), 500

# ============================================
# MAIN
# ============================================

if __name__ == '__main__':
    port  = int(os.getenv('PORT', 5000))
    debug = bool(os.getenv('FLASK_DEBUG'))
    app.run(host='0.0.0.0', port=port, debug=debug)
