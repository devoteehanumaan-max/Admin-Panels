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

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', secrets.token_hex(32))
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_PERMANENT'] = False
app.config['SESSION_USE_SIGNER'] = True
bcrypt = Bcrypt(app)

# Logging setup
logging.basicConfig(level=logging.DEBUG)

# ============================================
# DATABASE CONNECTION
# ============================================

EXTERNAL_DATABASE_URL = os.getenv('EXTERNAL_DATABASE_URL', 'postgresql://admin_panels_user:kRkEd8Zr8wCqJlXUNsnlNvgBqQOgHthi@dpg-d6ts46juibrs73eo0750-a.oregon-postgres.render.com/admin_panels')
INTERNAL_DATABASE_URL = os.getenv('INTERNAL_DATABASE_URL', 'postgresql://admin_panels_user:kRkEd8Zr8wCqJlXUNsnlNvgBqQOgHthi@dpg-d6ts46juibrs73eo0750-a/admin_panels')

def is_running_on_render():
    return os.getenv('RENDER', False) or os.getenv('RENDER_EXTERNAL_URL', False)

def get_database_url():
    if is_running_on_render():
        logging.info("✅ Using INTERNAL database URL")
        return INTERNAL_DATABASE_URL
    else:
        logging.info("✅ Using EXTERNAL database URL")
        return EXTERNAL_DATABASE_URL

def get_db_connection():
    primary_url = get_database_url()
    try:
        conn = psycopg2.connect(primary_url, connect_timeout=10, cursor_factory=RealDictCursor)
        return conn
    except Exception as e:
        logging.error(f"❌ Primary DB failed: {e}")
        fallback_url = EXTERNAL_DATABASE_URL if primary_url == INTERNAL_DATABASE_URL else INTERNAL_DATABASE_URL
        try:
            conn = psycopg2.connect(fallback_url, connect_timeout=10, cursor_factory=RealDictCursor)
            logging.info("✅ Fallback connection successful!")
            return conn
        except Exception as e2:
            logging.error(f"❌ Fallback also failed: {e2}")
            raise Exception("Database connection failed")

def init_db():
    try:
        conn = get_db_connection()
        c = conn.cursor()
        
        # Users table
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
        
        # Products table
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
        
        # Licenses table
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
        
        # Payments table
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
        
        # Custom key types table
        c.execute('''
            CREATE TABLE IF NOT EXISTS key_types (
                id SERIAL PRIMARY KEY,
                type_name VARCHAR(50) UNIQUE NOT NULL,
                pattern TEXT NOT NULL,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Notifications table (NEW)
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
        
        # Insert default key types
        default_key_types = [
            ('fluorite', 'RANDOM16', '16 characters random'),
            ('gbox', 'RANDOM16', '16 characters random'),
            ('drip', 'DIGITS10', '10 digits'),
            ('hg', 'HG-{RANDOM6}', 'HG-XXXXXX format'),
            ('brmod', 'USER8\\nPASS4', 'Username + Password'),
            ('lkteam', 'LKTEAM-{RANDOM6}', 'LKTEAM-XXXXXX'),
            ('strict', 'STRICT-{DIGITS8}', 'STRICT-8 digits'),
            ('spotify', 'EMAIL8@temp.com\\nPASS12', 'Email + Password'),
            ('standard', 'KEY-{RANDOM4}-{RANDOM4}', 'KEY-XXXX-XXXX')
        ]
        
        for type_name, pattern, desc in default_key_types:
            try:
                c.execute('''
                    INSERT INTO key_types (type_name, pattern, description)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (type_name) DO NOTHING
                ''', (type_name, pattern, desc))
            except:
                pass
        
        # Insert default admin
        hashed = bcrypt.generate_password_hash('620300').decode('utf-8')
        try:
            c.execute('''
                INSERT INTO users (username, password, role, credits)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (username) DO NOTHING
            ''', ('thedigamber', hashed, 'admin', 10000))
        except:
            pass
        
        # Insert default products
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
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (name) DO NOTHING
                ''', (name, credits, price, key_type))
            except:
                pass
        
        conn.commit()
        conn.close()
        logging.info("✅ Database initialized successfully!")
        return True
    except Exception as e:
        logging.error(f"❌ Database initialization error: {e}")
        return False

init_db()

# ============================================
# ADD MISSING COLUMNS
# ============================================

def add_missing_columns():
    try:
        conn = get_db_connection()
        c = conn.cursor()
        
        # Check and add discord_id column
        c.execute("""
            SELECT column_name FROM information_schema.columns 
            WHERE table_name='users' AND column_name='discord_id'
        """)
        if not c.fetchone():
            c.execute("ALTER TABLE users ADD COLUMN discord_id VARCHAR(50) UNIQUE")
            logging.info("✅ Added discord_id column")
        
        # Check and add discord_joined_at column
        c.execute("""
            SELECT column_name FROM information_schema.columns 
            WHERE table_name='users' AND column_name='discord_joined_at'
        """)
        if not c.fetchone():
            c.execute("ALTER TABLE users ADD COLUMN discord_joined_at TIMESTAMP")
            logging.info("✅ Added discord_joined_at column")
        
        # Check and add rejection_reason column
        c.execute("""
            SELECT column_name FROM information_schema.columns 
            WHERE table_name='payments' AND column_name='rejection_reason'
        """)
        if not c.fetchone():
            c.execute("ALTER TABLE payments ADD COLUMN rejection_reason TEXT")
            logging.info("✅ Added rejection_reason column")
        
        # Check and add expiry_time column
        c.execute("""
            SELECT column_name FROM information_schema.columns 
            WHERE table_name='payments' AND column_name='expiry_time'
        """)
        if not c.fetchone():
            c.execute("ALTER TABLE payments ADD COLUMN expiry_time TIMESTAMP")
            logging.info("✅ Added expiry_time column")
        
        # Check and add approved_date column
        c.execute("""
            SELECT column_name FROM information_schema.columns 
            WHERE table_name='payments' AND column_name='approved_date'
        """)
        if not c.fetchone():
            c.execute("ALTER TABLE payments ADD COLUMN approved_date TIMESTAMP")
            logging.info("✅ Added approved_date column")
        
        # Check and add approved_by column
        c.execute("""
            SELECT column_name FROM information_schema.columns 
            WHERE table_name='payments' AND column_name='approved_by'
        """)
        if not c.fetchone():
            c.execute("ALTER TABLE payments ADD COLUMN approved_by VARCHAR(100)")
            logging.info("✅ Added approved_by column")
        
        # Check and add binance_data column
        c.execute("""
            SELECT column_name FROM information_schema.columns 
            WHERE table_name='payments' AND column_name='binance_data'
        """)
        if not c.fetchone():
            c.execute("ALTER TABLE payments ADD COLUMN binance_data TEXT")
            logging.info("✅ Added binance_data column")
        
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logging.error(f"❌ Error adding columns: {e}")
        return False

add_missing_columns()

# ============================================
# CONSTANTS - UPDATED (WhatsApp Channel Added)
# ============================================

CREDIT_RATE = float(os.getenv('CREDIT_RATE', 0.5))
MINIMUM_RECHARGE = int(os.getenv('MIN_RECHARGE', 1000))
UPI_ID = os.getenv('UPI_ID', 'prabhu84@ptaxis')
UPI_NAME = os.getenv('UPI_NAME', 'Digamber Raj')

# ============================================
# SUPPORT LINKS - UPDATED
# ============================================
TELEGRAM_SUPPORT_LINK = os.getenv('TELEGRAM_SUPPORT_LINK', 'https://t.me/SMGrowMarthqofc')
WHATSAPP_CHANNEL = os.getenv('WHATSAPP_CHANNEL', 'https://whatsapp.com/channel/0029Vb8933MC6ZvoqBiPVq2h')
USD_TO_INR = 98
BINANCE_ADDRESS = '1143351874'

# ============================================
# DISCORD CONFIGURATION
# ============================================
DISCORD_BOT_TOKEN = os.getenv('DISCORD_BOT_TOKEN')
DISCORD_GUILD_ID = os.getenv('DISCORD_GUILD_ID', '1344323930923601992')
DISCORD_INVITE_LINK = os.getenv('DISCORD_INVITE_LINK', 'https://discord.gg/ATK3JcG7rB')

# ============================================
# DISCORD VERIFICATION - WITH CACHING
# ============================================

discord_cache = {}
CACHE_DURATION = 300

def check_discord_membership(discord_user_id):
    discord_user_id = str(discord_user_id).strip()
    
    if discord_user_id in discord_cache:
        cache_time, result = discord_cache[discord_user_id]
        if time.time() - cache_time < CACHE_DURATION:
            logging.info(f"✅ Using cached result for {discord_user_id}")
            return result
    
    logging.info(f"🔍 Discord Bot Token configured: {'Yes' if DISCORD_BOT_TOKEN else 'No'}")
    logging.info(f"🔍 Discord Guild ID: {DISCORD_GUILD_ID}")
    
    if not DISCORD_BOT_TOKEN or not DISCORD_GUILD_ID:
        logging.error("❌ Discord Bot Token or Guild ID not configured!")
        if app.debug:
            logging.warning("⚠️ Development mode: Bypassing Discord check")
            return True
        return False
    
    if not discord_user_id.isdigit():
        logging.error(f"❌ Invalid Discord ID format: {discord_user_id}")
        return False
    
    url = f"https://discord.com/api/v10/guilds/{DISCORD_GUILD_ID}/members/{discord_user_id}"
    headers = {"Authorization": f"Bot {DISCORD_BOT_TOKEN}"}
    
    try:
        logging.info(f"🔍 Checking Discord membership for user: {discord_user_id}")
        response = requests.get(url, headers=headers, timeout=10)
        logging.info(f"🔍 Discord API Response Status: {response.status_code}")
        
        if response.status_code == 200:
            logging.info(f"✅ Discord user {discord_user_id} is a member")
            discord_cache[discord_user_id] = (time.time(), True)
            return True
        elif response.status_code == 404:
            logging.warning(f"❌ Discord user {discord_user_id} is NOT a member")
            discord_cache[discord_user_id] = (time.time(), False)
            return False
        else:
            discord_cache[discord_user_id] = (time.time(), True)
            return True
    except Exception as e:
        logging.error(f"❌ Discord API error: {str(e)}")
        discord_cache[discord_user_id] = (time.time(), True)
        return True

# ============================================
# ULTRA DISCOUNT ENGINE
# ============================================

def calculate_discounted_credits(base_credit_per_day, days):
    print(f"🔥 DISCOUNT DEBUG - Base: {base_credit_per_day}, Days: {days}")
    
    if days == 1:
        result = base_credit_per_day * 1.0
    elif days == 3:
        result = base_credit_per_day * 1.5
    elif days == 7:
        result = base_credit_per_day * 2.0
    elif days == 15:
        result = base_credit_per_day * 3.0
    elif days == 30:
        result = base_credit_per_day * 4.0
    elif days == 60:
        result = base_credit_per_day * 5.0
    elif days == 90:
        result = base_credit_per_day * 6.0
    else:
        std_days = [1, 3, 7, 15, 30, 60, 90]
        std_mult = [1.0, 1.5, 2.0, 3.0, 4.0, 5.0, 6.0]
        
        if days < 1:
            result = base_credit_per_day
        elif days > 90:
            extra = (days - 90) / 30 * 0.5
            result = base_credit_per_day * (6.0 + extra)
        else:
            for i in range(len(std_days)-1):
                if std_days[i] < days < std_days[i+1]:
                    ratio = (days - std_days[i]) / (std_days[i+1] - std_days[i])
                    mult = std_mult[i] + ratio * (std_mult[i+1] - std_mult[i])
                    result = base_credit_per_day * mult
                    break
            else:
                result = base_credit_per_day * days
    
    print(f"🔥 DISCOUNT RESULT: {result}")
    return result

# ============================================
# API ENDPOINT TO GET DISCOUNTED PRICE
# ============================================

@app.route('/api/discounted_price', methods=['POST'])
def api_discounted_price():
    data = request.get_json()
    product_id = data.get('product_id')
    days = int(data.get('days', 1))
    
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT credit_cost_per_day FROM products WHERE id = %s", (product_id,))
    product = c.fetchone()
    conn.close()
    
    if not product:
        return jsonify({'success': False, 'error': 'Product not found'})
    
    base = float(product['credit_cost_per_day'])
    total = calculate_discounted_credits(base, days)
    
    return jsonify({
        'success': True,
        'total_credits': float(total),
        'original_total': float(base * days),
        'savings': float(round((base * days) - total, 2))
    })

# ============================================
# KEY GENERATOR CLASS
# ============================================

class KeyGenerator:
    def __init__(self):
        self.generators = {
            'fluorite': self._generate_fluorite,
            'gbox': self._generate_gbox,
            'drip': self._generate_drip,
            'hg': self._generate_hg,
            'brmod': self._generate_brmod,
            'lkteam': self._generate_lkteam,
            'strict': self._generate_strict,
            'spotify': self._generate_spotify,
            'standard': self._generate_standard
        }
    
    def generate_key(self, key_type, custom_pattern=None):
        if custom_pattern:
            return self._generate_from_pattern(custom_pattern)
        generator = self.generators.get(key_type, self._generate_standard)
        return generator()
    
    def _generate_from_pattern(self, pattern):
        result = pattern
        placeholders = {
            'RANDOM4': lambda: ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(4)),
            'RANDOM6': lambda: ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(6)),
            'RANDOM8': lambda: ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(8)),
            'RANDOM10': lambda: ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(10)),
            'RANDOM12': lambda: ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(12)),
            'RANDOM16': lambda: ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(16)),
            'DIGITS4': lambda: ''.join(secrets.choice(string.digits) for _ in range(4)),
            'DIGITS6': lambda: ''.join(secrets.choice(string.digits) for _ in range(6)),
            'DIGITS8': lambda: ''.join(secrets.choice(string.digits) for _ in range(8)),
            'DIGITS10': lambda: ''.join(secrets.choice(string.digits) for _ in range(10)),
            'USER4': lambda: ''.join(secrets.choice(string.ascii_lowercase) for _ in range(4)),
            'USER6': lambda: ''.join(secrets.choice(string.ascii_lowercase) for _ in range(6)),
            'USER8': lambda: ''.join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(8)),
            'PASS4': lambda: ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(4)),
            'PASS6': lambda: ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(6)),
            'PASS8': lambda: ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(8)),
            'PASS12': lambda: ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(12)),
            'DATE': lambda: datetime.now().strftime('%Y%m%d'),
            'TIME': lambda: datetime.now().strftime('%H%M%S'),
            'YEAR': lambda: datetime.now().strftime('%Y'),
            'MONTH': lambda: datetime.now().strftime('%m'),
            'DAY': lambda: datetime.now().strftime('%d')
        }
        
        for placeholder in re.findall(r'\{([^}]+)\}', result):
            if placeholder in placeholders:
                result = result.replace(f'{{{placeholder}}}', placeholders[placeholder]())
        
        return result
    
    def _generate_fluorite(self):
        return ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(16))
    
    def _generate_gbox(self):
        return ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(16))
    
    def _generate_drip(self):
        return ''.join(secrets.choice(string.digits) for _ in range(10))
    
    def _generate_hg(self):
        rand = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(6))
        return f"HG-{rand}"
    
    def _generate_brmod(self):
        username = ''.join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(8))
        password = ''.join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(4))
        return f"User: {username}\nPass: {password}"
    
    def _generate_lkteam(self):
        rand = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(6))
        return f"LKTEAM-{rand}"
    
    def _generate_strict(self):
        digits = ''.join(secrets.choice(string.digits) for _ in range(8))
        return f"STRICT-{digits}"
    
    def _generate_spotify(self):
        username = ''.join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(8))
        password = ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(12))
        return f"Username: {username}@temp.com\nPassword: {password}"
    
    def _generate_standard(self):
        part1 = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(4))
        part2 = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(4))
        return f"KEY-{part1}-{part2}"

key_gen = KeyGenerator()

# ============================================
# BINANCE API CLASS
# ============================================

class BinanceAPI:
    def __init__(self):
        self.base_url = os.getenv('BINANCE_API_URL', 'https://binance-verifier.onrender.com')
        self.timeout = 30
    
    def _request(self, endpoint, method='GET', data=None):
        try:
            url = self.base_url + endpoint
            headers = {'Content-Type': 'application/json'}
            
            if method == 'GET':
                response = requests.get(url, headers=headers, timeout=self.timeout)
            else:
                response = requests.post(url, headers=headers, json=data, timeout=self.timeout)
            
            if response.status_code == 200:
                return response.json()
            else:
                logging.error(f"Binance API error: {response.status_code}")
                return {'success': False, 'error': f'HTTP {response.status_code}'}
        except Exception as e:
            logging.error(f"Binance API error: {e}")
            return {'success': False, 'error': str(e)}
    
    def create_order(self, amount, email=None):
        try:
            payload = {
                'amount': float(amount),
                'customerEmail': email or f"user{int(time.time())}@temp.com"
            }
            result = self._request('/api/create-order', 'POST', payload)
            if result and result.get('success'):
                return result
            return {
                'success': True,
                'orderId': f"ORD{int(time.time())}{random.randint(100,999)}",
                'amount': amount,
                'status': 'pending'
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def check_order(self, order_id):
        try:
            result = self._request(f'/api/check/{order_id}')
            if result:
                return result
            return {'success': True, 'status': 'pending', 'orderId': order_id}
        except:
            return {'success': True, 'status': 'pending', 'orderId': order_id}
    
    def cancel_order(self, order_id):
        try:
            result = self._request(f'/api/cancel/{order_id}', 'POST')
            return result if result else {'success': True, 'message': 'Order cancelled'}
        except Exception as e:
            logging.error(f"Cancel order API error: {e}")
            return {'success': False, 'error': str(e)}
    
    def get_address(self, order_id):
        return {'address': BINANCE_ADDRESS}
    
    def get_qr(self, order_id):
        return self._request(f'/api/qr/{order_id}')

binance_api = BinanceAPI()

# ============================================
# HELPER FUNCTIONS
# ============================================

def generate_upi_qr(amount):
    try:
        upi_url = f"upi://pay?pa={UPI_ID}&pn={UPI_NAME}&am={amount}&cu=INR"
        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(upi_url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buffered = BytesIO()
        img.save(buffered, format="PNG")
        return base64.b64encode(buffered.getvalue()).decode()
    except Exception as e:
        logging.error(f"QR Error: {e}")
        return None

def format_datetime(dt):
    if dt is None:
        return 'N/A'
    if hasattr(dt, 'strftime'):
        return dt.strftime('%Y-%m-%d %H:%M')
    if isinstance(dt, str):
        return dt[:16]
    return str(dt)

# ============================================
# NOTIFICATION ROUTES (NEW)
# ============================================

@app.route('/api/notifications')
def get_notifications():
    if 'username' not in session:
        return jsonify({'success': False, 'error': 'Not logged in'})
    
    conn = get_db_connection()
    c = conn.cursor()
    
    username = session['username']
    
    # Get unread notifications for this user
    c.execute('''
        SELECT * FROM notifications 
        WHERE (is_global = TRUE OR target_user = %s)
        AND read_by NOT LIKE %s
        ORDER BY created_at DESC
        LIMIT 50
    ''', (username, f'%{username}%'))
    
    notifications = c.fetchall()
    conn.close()
    
    return jsonify({'success': True, 'notifications': notifications})

@app.route('/api/notifications/mark_read', methods=['POST'])
def mark_notification_read():
    if 'username' not in session:
        return jsonify({'success': False, 'error': 'Not logged in'})
    
    data = request.get_json()
    notification_id = data.get('notification_id')
    username = session['username']
    
    conn = get_db_connection()
    c = conn.cursor()
    
    c.execute('SELECT read_by FROM notifications WHERE id = %s', (notification_id,))
    notif = c.fetchone()
    
    if notif:
        read_list = notif['read_by'] or ''
        if username not in read_list:
            new_read = read_list + ',' + username if read_list else username
            c.execute('UPDATE notifications SET read_by = %s WHERE id = %s', (new_read, notification_id))
            conn.commit()
    
    conn.close()
    return jsonify({'success': True})

@app.route('/admin/send_notification', methods=['POST'])
def send_notification():
    if 'username' not in session or session.get('role') != 'admin':
        return jsonify({'success': False, 'error': 'Unauthorized'})
    
    data = request.get_json()
    title = data.get('title', 'Announcement')
    message = data.get('message', '')
    target_user = data.get('target_user')  # None = all users, or specific username
    is_global = target_user is None or target_user == ''
    
    if not message:
        return jsonify({'success': False, 'error': 'Message required'})
    
    conn = get_db_connection()
    c = conn.cursor()
    
    c.execute('''
        INSERT INTO notifications (title, message, target_user, is_global, created_by)
        VALUES (%s, %s, %s, %s, %s)
    ''', (title, message, target_user if not is_global else None, is_global, session['username']))
    
    conn.commit()
    conn.close()
    
    return jsonify({'success': True, 'message': 'Notification sent'})

@app.route('/admin/get_users_list')
def get_users_list():
    if 'username' not in session or session.get('role') != 'admin':
        return jsonify({'success': False, 'error': 'Unauthorized'})
    
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT username FROM users WHERE role != 'admin' ORDER BY username")
    users = c.fetchall()
    conn.close()
    
    return jsonify({'success': True, 'users': [u['username'] for u in users]})

# ============================================
# AUTH ROUTES
# ============================================

@app.route('/')
def index():
    if 'username' in session:
        if session.get('role') == 'admin':
            return redirect(url_for('admin_dashboard'))
        return redirect(url_for('user_dashboard'))
    return redirect(url_for('login'))

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
            session['role'] = user['role']
            session['credits'] = float(user['credits']) if user['credits'] else 0
            session['user_id'] = user['id']
            
            if user['role'] == 'admin':
                return redirect(url_for('admin_dashboard'))
            return redirect(url_for('user_dashboard'))
        
        return render_template('login.html', error='Invalid credentials')
    
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        confirm = request.form.get('confirm_password', '')
        discord_id = request.form.get('discord_id', '').strip()
        
        if not username or not password or not discord_id:
            return render_template('register.html', 
                                 error='Username, Password, and Discord ID are required',
                                 discord_invite=DISCORD_INVITE_LINK,
                                 whatsapp_channel=WHATSAPP_CHANNEL,
                                 telegram_support=TELEGRAM_SUPPORT_LINK)
        
        if password != confirm:
            return render_template('register.html', 
                                 error='Passwords do not match',
                                 discord_invite=DISCORD_INVITE_LINK,
                                 whatsapp_channel=WHATSAPP_CHANNEL,
                                 telegram_support=TELEGRAM_SUPPORT_LINK)
        
        if len(password) < 6:
            return render_template('register.html', 
                                 error='Password must be at least 6 characters',
                                 discord_invite=DISCORD_INVITE_LINK,
                                 whatsapp_channel=WHATSAPP_CHANNEL,
                                 telegram_support=TELEGRAM_SUPPORT_LINK)
        
        logging.info(f"🔍 Attempting Discord verification for user: {discord_id}")
        is_member = check_discord_membership(discord_id)
        
        if not is_member:
            return render_template('register.html', 
                                 error=f'❌ You must join our Discord server first! Join here: {DISCORD_INVITE_LINK}',
                                 discord_invite=DISCORD_INVITE_LINK,
                                 whatsapp_channel=WHATSAPP_CHANNEL,
                                 telegram_support=TELEGRAM_SUPPORT_LINK)
        
        logging.info(f"✅ Discord verification passed for user: {discord_id}")
        
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
            logging.info(f"✅ User registered successfully: {username}")
            return redirect(url_for('login'))
        except Exception as e:
            conn.close()
            logging.error(f"❌ Registration error: {e}")
            if 'duplicate key' in str(e):
                return render_template('register.html', 
                                     error='Username or Discord ID already exists',
                                     discord_invite=DISCORD_INVITE_LINK,
                                     whatsapp_channel=WHATSAPP_CHANNEL,
                                     telegram_support=TELEGRAM_SUPPORT_LINK)
            return render_template('register.html', 
                                 error='Registration failed. Please try again.',
                                 discord_invite=DISCORD_INVITE_LINK,
                                 whatsapp_channel=WHATSAPP_CHANNEL,
                                 telegram_support=TELEGRAM_SUPPORT_LINK)
    
    return render_template('register.html', 
                         discord_invite=DISCORD_INVITE_LINK,
                         whatsapp_channel=WHATSAPP_CHANNEL,
                         telegram_support=TELEGRAM_SUPPORT_LINK)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# ============================================
# USER DASHBOARD
# ============================================

@app.route('/dashboard')
def user_dashboard():
    if 'username' not in session or session.get('role') != 'user':
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    c = conn.cursor()
    
    c.execute("SELECT * FROM users WHERE username = %s", (session['username'],))
    user = c.fetchone()
    
    if not user:
        session.clear()
        conn.close()
        return redirect(url_for('login'))
    
    session['credits'] = float(user['credits'])
    
    c.execute("SELECT * FROM products WHERE is_active = TRUE ORDER BY name")
    products = c.fetchall()
    
    c.execute('''
        SELECT * FROM licenses 
        WHERE username = %s 
        ORDER BY expiry_date DESC 
        LIMIT 50
    ''', (session['username'],))
    licenses = c.fetchall()
    
    c.execute('''
        SELECT * FROM payments 
        WHERE username = %s 
        ORDER BY date DESC 
        LIMIT 20
    ''', (session['username'],))
    payments = c.fetchall()
    
    conn.close()
    
    return render_template('dashboard.html',
                         user=user,
                         products=products,
                         licenses=licenses,
                         payments=payments,
                         format_datetime=format_datetime,
                         telegram_support=TELEGRAM_SUPPORT_LINK,
                         whatsapp_channel=WHATSAPP_CHANNEL)

# ============================================
# KEY GENERATION
# ============================================

@app.route('/generate_key', methods=['POST'])
def generate_key_route():
    if 'username' not in session:
        return jsonify({'success': False, 'error': 'Not logged in'})
    
    data = request.get_json()
    product_id = data.get('product_id')
    days = int(data.get('days', 1))
    
    conn = get_db_connection()
    c = conn.cursor()
    
    c.execute("SELECT * FROM products WHERE id = %s", (product_id,))
    product = c.fetchone()
    
    if not product:
        conn.close()
        return jsonify({'success': False, 'error': 'Product not found'})
    
    base_credit = float(product['credit_cost_per_day'])
    total_credits = calculate_discounted_credits(base_credit, days)
    
    c.execute("SELECT credits FROM users WHERE username = %s", (session['username'],))
    result = c.fetchone()
    user_credits = result['credits']
    
    if float(user_credits) < float(total_credits):
        conn.close()
        return jsonify({'success': False, 'error': f'Need {total_credits} credits'})
    
    key = key_gen.generate_key(product['key_type'], product.get('custom_key_pattern'))
    expiry = datetime.now() + timedelta(days=days)
    
    new_credits = float(user_credits) - float(total_credits)
    c.execute('UPDATE users SET credits = %s WHERE username = %s',
             (new_credits, session['username']))
    
    c.execute('''
        INSERT INTO licenses 
        (key, username, product_name, days, total_credits, expiry_date, status)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    ''', (key, session['username'], product['name'], days, float(total_credits),
          expiry, 'active'))
    
    conn.commit()
    conn.close()
    
    session['credits'] = new_credits
    
    return jsonify({
        'success': True, 
        'key': key,
        'original_price': float(base_credit * days),
        'final_price': float(total_credits),
        'savings': float(round((base_credit * days) - total_credits, 2))
    })

# ============================================
# PAYMENT ROUTES
# ============================================

@app.route('/payment')
def payment_page():
    if 'username' not in session:
        return redirect(url_for('login'))
    
    return render_template('payment.html',
                         min_recharge=MINIMUM_RECHARGE,
                         credit_rate=CREDIT_RATE,
                         upi_id=UPI_ID,
                         usd_to_inr=USD_TO_INR,
                         binance_address=BINANCE_ADDRESS,
                         telegram_support=TELEGRAM_SUPPORT_LINK,
                         whatsapp_channel=WHATSAPP_CHANNEL)

@app.route('/payment/upi', methods=['GET', 'POST'])
def upi_payment():
    if 'username' not in session:
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        utr = request.form.get('utr', '').strip()
        amount = float(request.form.get('amount', 0))
        
        if amount < MINIMUM_RECHARGE:
            qr = generate_upi_qr(MINIMUM_RECHARGE)
            return render_template('upi_payment.html',
                                 error=f'Minimum amount is ₹{MINIMUM_RECHARGE}',
                                 qr_code=qr,
                                 min_recharge=MINIMUM_RECHARGE,
                                 credit_rate=CREDIT_RATE,
                                 upi_id=UPI_ID,
                                 usd_to_inr=USD_TO_INR,
                                 binance_address=BINANCE_ADDRESS,
                                 telegram_support=TELEGRAM_SUPPORT_LINK,
                                 whatsapp_channel=WHATSAPP_CHANNEL)
        
        if not utr or len(utr) != 12 or not utr.isdigit():
            qr = generate_upi_qr(amount)
            return render_template('upi_payment.html',
                                 error='Please enter a valid 12-digit UTR',
                                 qr_code=qr,
                                 amount=amount,
                                 min_recharge=MINIMUM_RECHARGE,
                                 credit_rate=CREDIT_RATE,
                                 upi_id=UPI_ID,
                                 usd_to_inr=USD_TO_INR,
                                 binance_address=BINANCE_ADDRESS,
                                 telegram_support=TELEGRAM_SUPPORT_LINK,
                                 whatsapp_channel=WHATSAPP_CHANNEL)
        
        credits = amount * CREDIT_RATE
        
        conn = get_db_connection()
        c = conn.cursor()
        try:
            c.execute('''
                INSERT INTO payments 
                (username, payment_method, utr, amount, credits_added, status, date)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            ''', (session['username'], 'upi', utr, amount, credits, 'pending',
                  datetime.now()))
            conn.commit()
            conn.close()
            
            qr = generate_upi_qr(amount)
            return render_template('upi_payment.html',
                                 success=f'Payment submitted! ₹{amount} = {credits} credits pending approval.',
                                 qr_code=qr,
                                 amount=amount,
                                 min_recharge=MINIMUM_RECHARGE,
                                 credit_rate=CREDIT_RATE,
                                 upi_id=UPI_ID,
                                 usd_to_inr=USD_TO_INR,
                                 binance_address=BINANCE_ADDRESS,
                                 telegram_support=TELEGRAM_SUPPORT_LINK,
                                 whatsapp_channel=WHATSAPP_CHANNEL)
        except:
            conn.close()
            qr = generate_upi_qr(amount)
            return render_template('upi_payment.html',
                                 error='UTR already exists!',
                                 qr_code=qr,
                                 amount=amount,
                                 min_recharge=MINIMUM_RECHARGE,
                                 credit_rate=CREDIT_RATE,
                                 upi_id=UPI_ID,
                                 usd_to_inr=USD_TO_INR,
                                 binance_address=BINANCE_ADDRESS,
                                 telegram_support=TELEGRAM_SUPPORT_LINK,
                                 whatsapp_channel=WHATSAPP_CHANNEL)
    
    qr_code = generate_upi_qr(MINIMUM_RECHARGE)
    return render_template('upi_payment.html',
                         qr_code=qr_code,
                         amount=MINIMUM_RECHARGE,
                         min_recharge=MINIMUM_RECHARGE,
                         credit_rate=CREDIT_RATE,
                         upi_id=UPI_ID,
                         usd_to_inr=USD_TO_INR,
                         binance_address=BINANCE_ADDRESS,
                         telegram_support=TELEGRAM_SUPPORT_LINK,
                         whatsapp_channel=WHATSAPP_CHANNEL)

@app.route('/payment/binance', methods=['GET', 'POST'])
def binance_payment():
    if 'username' not in session:
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        amount_inr = float(request.form.get('amount', 0))
        
        if amount_inr < MINIMUM_RECHARGE:
            return render_template('binance_payment.html',
                                 error=f'Minimum ₹{MINIMUM_RECHARGE}',
                                 min_recharge=MINIMUM_RECHARGE,
                                 credit_rate=CREDIT_RATE,
                                 usd_to_inr=USD_TO_INR,
                                 binance_address=BINANCE_ADDRESS,
                                 telegram_support=TELEGRAM_SUPPORT_LINK,
                                 whatsapp_channel=WHATSAPP_CHANNEL)
        
        amount_usd = round(amount_inr / USD_TO_INR, 2)
        
        result = binance_api.create_order(amount_usd, session['username'])
        
        if result and result.get('success'):
            order_id = result.get('orderId')
            credits = amount_inr * CREDIT_RATE
            expiry_time = datetime.now() + timedelta(minutes=10)
            
            conn = get_db_connection()
            c = conn.cursor()
            c.execute('''
                INSERT INTO payments 
                (username, payment_method, order_id, amount, credits_added, status, date, expiry_time, binance_data)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ''', (session['username'], 'binance', order_id, amount_inr, credits, 'pending',
                  datetime.now(),
                  expiry_time,
                  json.dumps(result)))
            conn.commit()
            conn.close()
            
            return render_template('binance_payment.html',
                                 order_id=order_id,
                                 amount_inr=amount_inr,
                                 amount_usd=amount_usd,
                                 credits=credits,
                                 binance_address=BINANCE_ADDRESS,
                                 min_recharge=MINIMUM_RECHARGE,
                                 credit_rate=CREDIT_RATE,
                                 usd_to_inr=USD_TO_INR,
                                 telegram_support=TELEGRAM_SUPPORT_LINK,
                                 whatsapp_channel=WHATSAPP_CHANNEL)
        else:
            return render_template('binance_payment.html',
                                 error='Unable to create Binance order. Please try UPI.',
                                 min_recharge=MINIMUM_RECHARGE,
                                 credit_rate=CREDIT_RATE,
                                 usd_to_inr=USD_TO_INR,
                                 binance_address=BINANCE_ADDRESS,
                                 telegram_support=TELEGRAM_SUPPORT_LINK,
                                 whatsapp_channel=WHATSAPP_CHANNEL)
    
    return render_template('binance_payment.html',
                         min_recharge=MINIMUM_RECHARGE,
                         credit_rate=CREDIT_RATE,
                         usd_to_inr=USD_TO_INR,
                         binance_address=BINANCE_ADDRESS,
                         telegram_support=TELEGRAM_SUPPORT_LINK,
                         whatsapp_channel=WHATSAPP_CHANNEL)

@app.route('/payment/binance/check/<order_id>')
def check_binance_payment(order_id):
    if 'username' not in session:
        return jsonify({'success': False, 'error': 'Not logged in'})
    
    result = binance_api.check_order(order_id)
    
    if result and result.get('status') == 'completed':
        conn = get_db_connection()
        c = conn.cursor()
        
        c.execute("SELECT * FROM payments WHERE order_id = %s", (order_id,))
        payment = c.fetchone()
        
        if payment and payment['status'] == 'pending':
            c.execute('''
                UPDATE payments SET status = 'approved', approved_date = %s
                WHERE order_id = %s
            ''', (datetime.now(), order_id))
            
            c.execute('''
                UPDATE users 
                SET credits = credits + %s, total_recharged = total_recharged + %s
                WHERE username = %s
            ''', (float(payment['credits_added']), float(payment['amount']), session['username']))
            
            conn.commit()
            conn.close()
            
            return jsonify({
                'success': True,
                'status': 'completed',
                'credited': True,
                'credits': float(payment['credits_added'])
            })
        conn.close()
    
    status = result.get('status', 'pending') if result else 'pending'
    return jsonify({'success': True, 'status': status})

@app.route('/payment/binance/cleanup/<order_id>', methods=['POST'])
def cleanup_binance_order(order_id):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("DELETE FROM payments WHERE order_id = %s AND status = 'pending'", (order_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/generate_payment_qr', methods=['POST'])
def generate_payment_qr():
    if 'username' not in session:
        return jsonify({'success': False, 'error': 'Not logged in'})
    
    data = request.get_json()
    amount = float(data.get('amount', MINIMUM_RECHARGE))
    
    if amount < MINIMUM_RECHARGE:
        return jsonify({'success': False, 'error': f'Minimum amount is ₹{MINIMUM_RECHARGE}'})
    
    qr_code = generate_upi_qr(amount)
    credits = amount * CREDIT_RATE
    
    return jsonify({
        'success': True,
        'qr_code': qr_code,
        'amount': amount,
        'credits': round(credits, 1)
    })

# ============================================
# ADMIN DASHBOARD
# ============================================

@app.route('/admin')
def admin_dashboard():
    if 'username' not in session or session.get('role') != 'admin':
        return redirect(url_for('login'))
    
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
    
    c.execute('''
        SELECT * FROM payments 
        ORDER BY CASE status WHEN 'pending' THEN 1 ELSE 2 END, date DESC
    ''')
    payments = c.fetchall()
    
    c.execute("SELECT * FROM licenses ORDER BY expiry_date DESC LIMIT 100")
    licenses = c.fetchall()
    
    c.execute("SELECT * FROM products ORDER BY name")
    products = c.fetchall()
    
    c.execute("SELECT * FROM key_types ORDER BY type_name")
    key_types = c.fetchall()
    
    conn.close()
    
    return render_template('admin.html',
                         users=users,
                         payments=payments,
                         licenses=licenses,
                         products=products,
                         key_types=key_types,
                         total_users=total_users,
                         total_revenue=total_revenue,
                         total_credits_sold=total_credits_sold,
                         pending_payments=pending_payments,
                         active_keys=active_keys,
                         format_datetime=format_datetime,
                         binance_address=BINANCE_ADDRESS,
                         telegram_support=TELEGRAM_SUPPORT_LINK,
                         whatsapp_channel=WHATSAPP_CHANNEL)

# ============================================
# ADMIN - PAYMENT ACTIONS
# ============================================

@app.route('/admin/approve_payment', methods=['POST'])
def approve_payment():
    if 'username' not in session or session.get('role') != 'admin':
        return jsonify({'success': False, 'error': 'Unauthorized'})
    
    data = request.get_json()
    payment_id = data.get('payment_id')
    
    if not payment_id:
        return jsonify({'success': False, 'error': 'Payment ID required'})
    
    conn = None
    try:
        conn = get_db_connection()
        c = conn.cursor()
        
        c.execute("SELECT * FROM payments WHERE id = %s", (payment_id,))
        payment = c.fetchone()
        
        if not payment:
            return jsonify({'success': False, 'error': 'Payment not found'})
        
        c.execute('''
            UPDATE payments 
            SET status = 'approved', approved_date = %s, approved_by = %s, rejection_reason = NULL
            WHERE id = %s
        ''', (datetime.now(), session['username'], payment_id))
        
        c.execute('''
            UPDATE users 
            SET credits = credits + %s, total_recharged = total_recharged + %s
            WHERE username = %s
        ''', (float(payment['credits_added']), float(payment['amount']), payment['username']))
        
        conn.commit()
        return jsonify({'success': True, 'message': 'Payment approved'})
        
    except Exception as e:
        logging.error(f"Approve payment error: {e}")
        return jsonify({'success': False, 'error': str(e)})
    finally:
        if conn:
            conn.close()

@app.route('/admin/reject_payment', methods=['POST'])
def reject_payment():
    if 'username' not in session or session.get('role') != 'admin':
        return jsonify({'success': False, 'error': 'Unauthorized'})
    
    data = request.get_json()
    payment_id = data.get('payment_id')
    reason = data.get('reason', 'Payment rejected by admin')
    
    if not payment_id:
        return jsonify({'success': False, 'error': 'Payment ID required'})
    
    conn = None
    try:
        conn = get_db_connection()
        c = conn.cursor()
        
        c.execute("SELECT * FROM payments WHERE id = %s", (payment_id,))
        payment = c.fetchone()
        
        if not payment:
            return jsonify({'success': False, 'error': 'Payment not found'})
        
        c.execute('''
            UPDATE payments 
            SET status = 'rejected', rejection_reason = %s, approved_by = %s
            WHERE id = %s
        ''', (reason, session['username'], payment_id))
        
        conn.commit()
        return jsonify({'success': True, 'message': 'Payment rejected'})
        
    except Exception as e:
        logging.error(f"Reject payment error: {e}")
        return jsonify({'success': False, 'error': str(e)})
    finally:
        if conn:
            conn.close()

@app.route('/admin/cancel_binance_order', methods=['POST'])
def cancel_binance_order():
    if 'username' not in session or session.get('role') != 'admin':
        return jsonify({'success': False, 'error': 'Unauthorized'})
    
    data = request.get_json()
    order_id = data.get('order_id')
    
    if not order_id:
        return jsonify({'success': False, 'error': 'Order ID required'})
    
    conn = None
    try:
        binance_result = binance_api.cancel_order(order_id)
        
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("DELETE FROM payments WHERE order_id = %s", (order_id,))
        conn.commit()
        
        return jsonify({
            'success': True, 
            'message': 'Order cancelled and deleted',
            'binance_response': binance_result
        })
        
    except Exception as e:
        logging.error(f"Cancel order error: {e}")
        return jsonify({'success': False, 'error': str(e)})
    finally:
        if conn:
            conn.close()

# ============================================
# ADMIN - PRODUCT MANAGEMENT
# ============================================

@app.route('/admin/add_product', methods=['POST'])
def add_product():
    if 'username' not in session or session.get('role') != 'admin':
        return jsonify({'success': False, 'error': 'Unauthorized'})
    
    data = request.get_json()
    name = data.get('name', '').strip()
    credits = float(data.get('credit_cost_per_day', 0))
    price = float(data.get('price_per_day', 0))
    key_type = data.get('key_type', 'standard')
    custom_pattern = data.get('custom_key_pattern')
    
    if not name or credits <= 0 or price <= 0:
        return jsonify({'success': False, 'error': 'Invalid data'})
    
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute('''
            INSERT INTO products (name, credit_cost_per_day, price_per_day, key_type, custom_key_pattern)
            VALUES (%s, %s, %s, %s, %s)
        ''', (name, credits, price, key_type, custom_pattern))
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    except:
        conn.close()
        return jsonify({'success': False, 'error': 'Product name exists'})

@app.route('/admin/edit_product', methods=['POST'])
def edit_product():
    if 'username' not in session or session.get('role') != 'admin':
        return jsonify({'success': False, 'error': 'Unauthorized'})
    
    data = request.get_json()
    product_id = data.get('product_id')
    name = data.get('name')
    credits = float(data.get('credit_cost_per_day', 0))
    price = float(data.get('price_per_day', 0))
    key_type = data.get('key_type')
    custom_pattern = data.get('custom_key_pattern')
    
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''
        UPDATE products 
        SET name = %s, credit_cost_per_day = %s, price_per_day = %s, 
            key_type = %s, custom_key_pattern = %s
        WHERE id = %s
    ''', (name, credits, price, key_type, custom_pattern, product_id))
    conn.commit()
    conn.close()
    
    return jsonify({'success': True})

@app.route('/admin/delete_product', methods=['POST'])
def delete_product():
    if 'username' not in session or session.get('role') != 'admin':
        return jsonify({'success': False, 'error': 'Unauthorized'})
    
    data = request.get_json()
    product_id = data.get('product_id')
    
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("DELETE FROM products WHERE id = %s", (product_id,))
    conn.commit()
    conn.close()
    
    return jsonify({'success': True})

@app.route('/admin/toggle_product', methods=['POST'])
def toggle_product():
    if 'username' not in session or session.get('role') != 'admin':
        return jsonify({'success': False, 'error': 'Unauthorized'})
    
    data = request.get_json()
    product_id = data.get('product_id')
    is_active = data.get('is_active', True)
    
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("UPDATE products SET is_active = %s WHERE id = %s", (is_active, product_id))
    conn.commit()
    conn.close()
    
    return jsonify({'success': True})

# ============================================
# ADMIN - KEY TYPE MANAGEMENT
# ============================================

@app.route('/admin/add_key_type', methods=['POST'])
def add_key_type():
    if 'username' not in session or session.get('role') != 'admin':
        return jsonify({'success': False, 'error': 'Unauthorized'})
    
    data = request.get_json()
    type_name = data.get('type_name')
    pattern = data.get('pattern')
    description = data.get('description')
    
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute('''
            INSERT INTO key_types (type_name, pattern, description)
            VALUES (%s, %s, %s)
        ''', (type_name, pattern, description))
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    except:
        conn.close()
        return jsonify({'success': False, 'error': 'Type name exists'})

@app.route('/admin/get_key_types')
def get_key_types():
    if 'username' not in session or session.get('role') != 'admin':
        return jsonify({'success': False, 'error': 'Unauthorized'})
    
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM key_types ORDER BY type_name")
    types = c.fetchall()
    conn.close()
    
    return jsonify({'success': True, 'key_types': types})

# ============================================
# ADMIN - USER MANAGEMENT
# ============================================

@app.route('/admin/add_credits', methods=['POST'])
def add_credits():
    if 'username' not in session or session.get('role') != 'admin':
        return jsonify({'success': False, 'error': 'Unauthorized'})
    
    data = request.get_json()
    username = data.get('username')
    credits = float(data.get('credits', 0))
    
    if credits <= 0:
        return jsonify({'success': False, 'error': 'Invalid amount'})
    
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''
        UPDATE users SET credits = credits + %s WHERE username = %s
    ''', (credits, username))
    conn.commit()
    conn.close()
    
    return jsonify({'success': True})

@app.route('/admin/delete_user', methods=['POST'])
def delete_user():
    if 'username' not in session or session.get('role') != 'admin':
        return jsonify({'success': False, 'error': 'Unauthorized'})
    
    data = request.get_json()
    username = data.get('username')
    
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("DELETE FROM licenses WHERE username = %s", (username,))
    c.execute("DELETE FROM payments WHERE username = %s", (username,))
    c.execute("DELETE FROM users WHERE username = %s AND role != 'admin'", (username,))
    conn.commit()
    conn.close()
    
    return jsonify({'success': True})

@app.route('/admin/delete_key', methods=['POST'])
def delete_key():
    if 'username' not in session or session.get('role') != 'admin':
        return jsonify({'success': False, 'error': 'Unauthorized'})
    
    data = request.get_json()
    license_id = data.get('license_id')
    
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("DELETE FROM licenses WHERE id = %s", (license_id,))
    conn.commit()
    conn.close()
    
    return jsonify({'success': True})

# ============================================
# HWID RESET
# ============================================

@app.route('/hwid_reset', methods=['POST'])
def hwid_reset():
    if 'username' not in session:
        return jsonify({'success': False, 'error': 'Not logged in'})
    
    data = request.get_json()
    license_id = data.get('license_id')
    
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''
        UPDATE licenses SET last_reset = %s 
        WHERE id = %s AND username = %s
    ''', (datetime.now(), license_id, session['username']))
    conn.commit()
    conn.close()
    
    return jsonify({'success': True})

@app.route('/hwid_reset_all', methods=['POST'])
def hwid_reset_all():
    if 'username' not in session:
        return jsonify({'success': False, 'error': 'Not logged in'})
    
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''
        UPDATE licenses SET last_reset = %s 
        WHERE username = %s
    ''', (datetime.now(), session['username']))
    conn.commit()
    conn.close()
    
    return jsonify({'success': True})

# ============================================
# ROBOTS.TXT
# ============================================

@app.route('/robots.txt')
def robots_txt():
    return send_from_directory('static', 'robots.txt', mimetype='text/plain')

# ============================================
# ERROR HANDLERS
# ============================================

@app.errorhandler(500)
def internal_error(error):
    return render_template('error.html', error="Internal Server Error",
                         telegram_support=TELEGRAM_SUPPORT_LINK,
                         whatsapp_channel=WHATSAPP_CHANNEL), 500

@app.errorhandler(404)
def not_found_error(error):
    return render_template('error.html', error="Page not found",
                         telegram_support=TELEGRAM_SUPPORT_LINK,
                         whatsapp_channel=WHATSAPP_CHANNEL), 404

# ============================================
# PRIVACY & TERMS ROUTES
# ============================================

@app.route('/privacy')
def privacy():
    return render_template('privacy.html', 
                         telegram_support=TELEGRAM_SUPPORT_LINK,
                         whatsapp_channel=WHATSAPP_CHANNEL)

@app.route('/terms')
def terms():
    return render_template('terms.html',
                         telegram_support=TELEGRAM_SUPPORT_LINK,
                         whatsapp_channel=WHATSAPP_CHANNEL)

# ============================================
# ABOUT PAGE ROUTE
# ============================================

@app.route('/about')
def about():
    return render_template('about.html',
                         telegram_support=TELEGRAM_SUPPORT_LINK,
                         whatsapp_channel=WHATSAPP_CHANNEL)

@app.route('/home')
def home():
    return render_template('index.html')

# ============================================
# MAIN
# ============================================

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
