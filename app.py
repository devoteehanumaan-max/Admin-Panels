from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash, send_from_directory
from flask_bcrypt import Bcrypt
import sqlite3
import secrets
import string
import random
from datetime import datetime, timedelta
import os
import qrcode
from io import BytesIO
import base64
import traceback

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_PERMANENT'] = False
app.config['SESSION_USE_SIGNER'] = True
bcrypt = Bcrypt(app)

# Credit conversion rate
CREDIT_RATE = 0.5
MINIMUM_RECHARGE = 1000

# UPI Details
UPI_ID = "prabhu84@ptaxis"
UPI_NAME = "Digamber Raj"

# Support Links
WHATSAPP_LINK = "https://wa.me/message/IGTHSKO23KP4H1"
TELEGRAM_CHANNEL = "https://t.me/growmarthq"

def get_db_connection():
    """Get database connection with row factory"""
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initialize database with all tables"""
    try:
        conn = get_db_connection()
        c = conn.cursor()
        
        # Users table
        c.execute('''CREATE TABLE IF NOT EXISTS users
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      username TEXT UNIQUE NOT NULL,
                      password TEXT NOT NULL,
                      role TEXT DEFAULT 'user',
                      credits REAL DEFAULT 0,
                      total_recharged REAL DEFAULT 0,
                      created_at TEXT DEFAULT CURRENT_TIMESTAMP)''')
        
        # Products table
        c.execute('''CREATE TABLE IF NOT EXISTS products
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      name TEXT UNIQUE NOT NULL,
                      credit_cost_per_day REAL NOT NULL,
                      price_per_day REAL NOT NULL,
                      key_type TEXT DEFAULT 'standard',
                      is_active BOOLEAN DEFAULT 1,
                      created_at TEXT DEFAULT CURRENT_TIMESTAMP)''')
        
        # Licenses table
        c.execute('''CREATE TABLE IF NOT EXISTS licenses
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      key TEXT UNIQUE NOT NULL,
                      username TEXT NOT NULL,
                      product_name TEXT NOT NULL,
                      days INTEGER NOT NULL,
                      total_credits REAL NOT NULL,
                      expiry_date TEXT NOT NULL,
                      status TEXT DEFAULT 'active',
                      last_reset TEXT,
                      created_at TEXT DEFAULT CURRENT_TIMESTAMP)''')
        
        # Payments table
        c.execute('''CREATE TABLE IF NOT EXISTS payments
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      username TEXT NOT NULL,
                      utr TEXT UNIQUE NOT NULL,
                      amount REAL NOT NULL,
                      credits_added REAL DEFAULT 0,
                      status TEXT DEFAULT 'pending',
                      date TEXT NOT NULL,
                      approved_date TEXT,
                      approved_by TEXT)''')
        
        # Insert default admin if not exists - CHANGED HERE
        c.execute("SELECT * FROM users WHERE username = 'thedigamber'")
        if not c.fetchone():
            hashed_password = bcrypt.generate_password_hash('620300').decode('utf-8')
            c.execute("INSERT INTO users (username, password, role, credits) VALUES (?, ?, ?, ?)",
                      ('thedigamber', hashed_password, 'admin', 10000))
            print("✅ Admin user created: thedigamber / 620300")
        
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
        
        for product in default_products:
            try:
                c.execute("INSERT INTO products (name, credit_cost_per_day, price_per_day, key_type) VALUES (?, ?, ?, ?)",
                         product)
            except sqlite3.IntegrityError:
                pass
        
        conn.commit()
        conn.close()
        print("✅ Database initialized successfully")
        
    except Exception as e:
        print(f"❌ Database initialization error: {str(e)}")
        traceback.print_exc()

# Initialize database
init_db()

def generate_upi_qr(amount):
    """Generate UPI QR code"""
    try:
        upi_url = f"upi://pay?pa={UPI_ID}&pn={UPI_NAME}&am={amount}&cu=INR"
        
        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(upi_url)
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        
        buffered = BytesIO()
        img.save(buffered, format="PNG")
        img_str = base64.b64encode(buffered.getvalue()).decode()
        
        return img_str
    except Exception as e:
        print(f"QR Generation Error: {e}")
        return None

# Key generation functions
def generate_fluorite_key():
    alphabet = string.ascii_uppercase + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(16))

def generate_gbox_key():
    alphabet = string.ascii_uppercase + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(16))

def generate_drip_key():
    return ''.join(secrets.choice(string.digits) for _ in range(10))

def generate_hg_key():
    alphabet = string.ascii_uppercase + string.digits
    random_part = ''.join(secrets.choice(alphabet) for _ in range(6))
    return f"HG-{random_part}"

def generate_brmod_credentials():
    username = ''.join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(8))
    password = ''.join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(4))
    return f"User: {username}\nPass: {password}"

def generate_lkteam_key():
    alphabet = string.ascii_uppercase + string.digits
    random_part = ''.join(secrets.choice(alphabet) for _ in range(6))
    return f"LKTEAM-{random_part}"

def generate_strict_key():
    digits = ''.join(secrets.choice(string.digits) for _ in range(8))
    return f"STRICT-{digits}"

def generate_spotify_credentials():
    username = ''.join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(8))
    password = ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(12))
    return f"Username: {username}@temp.com\nPassword: {password}"

def generate_key_by_type(key_type):
    generators = {
        'fluorite': generate_fluorite_key,
        'gbox': generate_gbox_key,
        'drip': generate_drip_key,
        'hg': generate_hg_key,
        'brmod': generate_brmod_credentials,
        'lkteam': generate_lkteam_key,
        'strict': generate_strict_key,
        'spotify': generate_spotify_credentials,
        'standard': generate_fluorite_key
    }
    generator = generators.get(key_type, generate_fluorite_key)
    return generator()

# Error handler for 500 errors
@app.errorhandler(500)
def internal_error(error):
    return render_template('error.html', error="Internal Server Error. Please try again."), 500

@app.errorhandler(404)
def not_found_error(error):
    return render_template('error.html', error="Page not found."), 404

# Routes
@app.route('/')
def index():
    try:
        if 'username' in session:
            if session.get('role') == 'admin':
                return redirect(url_for('admin_dashboard'))
            return redirect(url_for('user_dashboard'))
        return redirect(url_for('login'))
    except Exception as e:
        print(f"Index Error: {e}")
        return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    try:
        if request.method == 'POST':
            username = request.form.get('username', '').strip()
            password = request.form.get('password', '')
            
            if not username or not password:
                return render_template('login.html', error='Username and password required')
            
            conn = get_db_connection()
            c = conn.cursor()
            c.execute("SELECT * FROM users WHERE username = ?", (username,))
            user = c.fetchone()
            conn.close()
            
            if user and bcrypt.check_password_hash(user[2], password):
                session.clear()
                session['username'] = user[1]
                session['role'] = user[3]
                session['credits'] = float(user[4]) if user[4] else 0
                session['user_id'] = user[0]
                session.permanent = False
                
                print(f"✅ Login successful: {username}, Role: {user[3]}")
                
                if user[3] == 'admin':
                    return redirect(url_for('admin_dashboard'))
                return redirect(url_for('user_dashboard'))
            
            return render_template('login.html', error='Invalid credentials')
        
        return render_template('login.html')
        
    except Exception as e:
        print(f"Login Error: {e}")
        traceback.print_exc()
        return render_template('login.html', error='Server error. Please try again.')

@app.route('/register', methods=['GET', 'POST'])
def register():
    try:
        if request.method == 'POST':
            username = request.form.get('username', '').strip()
            password = request.form.get('password', '')
            confirm_password = request.form.get('confirm_password', '')
            
            if not username or not password:
                return render_template('register.html', error='Username and password required')
            
            if password != confirm_password:
                return render_template('register.html', error='Passwords do not match')
            
            if len(password) < 6:
                return render_template('register.html', error='Password must be at least 6 characters')
            
            hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
            
            conn = get_db_connection()
            c = conn.cursor()
            try:
                c.execute("INSERT INTO users (username, password, role, credits) VALUES (?, ?, ?, ?)",
                         (username, hashed_password, 'user', 0))
                conn.commit()
                conn.close()
                return redirect(url_for('login'))
            except sqlite3.IntegrityError:
                conn.close()
                return render_template('register.html', error='Username already exists')
        
        return render_template('register.html')
        
    except Exception as e:
        print(f"Register Error: {e}")
        return render_template('register.html', error='Server error. Please try again.')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/dashboard')
def user_dashboard():
    try:
        if 'username' not in session or session.get('role') != 'user':
            return redirect(url_for('login'))
        
        conn = get_db_connection()
        c = conn.cursor()
        
        # Get user data
        c.execute("SELECT * FROM users WHERE username = ?", (session['username'],))
        user = c.fetchone()
        
        if not user:
            session.clear()
            conn.close()
            return redirect(url_for('login'))
        
        session['credits'] = float(user[4]) if user[4] else 0
        
        # Get active products
        c.execute("SELECT * FROM products WHERE is_active = 1 ORDER BY name")
        products = c.fetchall()
        
        # Get user's licenses
        c.execute("""SELECT * FROM licenses WHERE username = ? 
                     ORDER BY expiry_date DESC LIMIT 50""", (session['username'],))
        licenses = c.fetchall()
        
        # Get pending payments
        c.execute("""SELECT * FROM payments WHERE username = ? AND status = 'pending' 
                     ORDER BY date DESC""", (session['username'],))
        pending_payments = c.fetchall()
        
        conn.close()
        
        return render_template('dashboard.html', 
                             user=user, 
                             products=products, 
                             licenses=licenses, 
                             pending_payments=pending_payments,
                             min_recharge=MINIMUM_RECHARGE, 
                             credit_rate=CREDIT_RATE,
                             whatsapp_link=WHATSAPP_LINK, 
                             telegram_channel=TELEGRAM_CHANNEL)
    
    except Exception as e:
        print(f"Dashboard Error: {e}")
        traceback.print_exc()
        return render_template('error.html', error="Error loading dashboard"), 500

@app.route('/admin')
def admin_dashboard():
    try:
        if 'username' not in session or session.get('role') != 'admin':
            return redirect(url_for('login'))
        
        conn = get_db_connection()
        c = conn.cursor()
        
        # Stats
        c.execute("SELECT COUNT(*) FROM users WHERE role = 'user'")
        total_users = c.fetchone()[0] or 0
        
        c.execute("SELECT IFNULL(SUM(amount), 0) FROM payments WHERE status = 'approved'")
        total_revenue = c.fetchone()[0] or 0
        
        c.execute("SELECT IFNULL(SUM(credits_added), 0) FROM payments WHERE status = 'approved'")
        total_credits_sold = c.fetchone()[0] or 0
        
        c.execute("SELECT COUNT(*) FROM payments WHERE status = 'pending'")
        pending_payments = c.fetchone()[0] or 0
        
        c.execute("SELECT COUNT(*) FROM licenses WHERE status = 'active'")
        active_keys = c.fetchone()[0] or 0
        
        # All users
        c.execute("SELECT * FROM users WHERE role != 'admin' ORDER BY credits DESC")
        users = c.fetchall()
        
        # All payments
        c.execute("""SELECT * FROM payments ORDER BY 
                     CASE status WHEN 'pending' THEN 1 ELSE 2 END, date DESC""")
        payments = c.fetchall()
        
        # All licenses
        c.execute("SELECT * FROM licenses ORDER BY expiry_date DESC LIMIT 100")
        licenses = c.fetchall()
        
        # All products
        c.execute("SELECT * FROM products ORDER BY name")
        products = c.fetchall()
        
        conn.close()
        
        return render_template('admin.html', 
                             users=users, 
                             payments=payments,
                             licenses=licenses, 
                             products=products,
                             total_users=total_users, 
                             total_revenue=total_revenue,
                             total_credits_sold=total_credits_sold,
                             pending_payments=pending_payments, 
                             active_keys=active_keys,
                             whatsapp_link=WHATSAPP_LINK, 
                             telegram_channel=TELEGRAM_CHANNEL)
    
    except Exception as e:
        print(f"Admin Dashboard Error: {e}")
        traceback.print_exc()
        return render_template('error.html', error="Error loading admin dashboard"), 500

@app.route('/calculate_price', methods=['POST'])
def calculate_price():
    try:
        if 'username' not in session:
            return jsonify({'success': False, 'error': 'Not logged in'})
        
        data = request.get_json()
        product_id = data.get('product_id')
        days = int(data.get('days', 1))
        
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT * FROM products WHERE id = ?", (product_id,))
        product = c.fetchone()
        conn.close()
        
        if not product:
            return jsonify({'success': False, 'error': 'Product not found'})
        
        total_credits = float(product[2]) * days
        total_price = float(product[3]) * days
        
        return jsonify({
            'success': True,
            'total_credits': round(total_credits, 1),
            'total_price': round(total_price, 2)
        })
        
    except Exception as e:
        print(f"Calculate Price Error: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/generate_key', methods=['POST'])
def generate_key_route():
    try:
        if 'username' not in session:
            return jsonify({'success': False, 'error': 'Not logged in'})
        
        data = request.get_json()
        product_id = data.get('product_id')
        days = int(data.get('days', 1))
        
        conn = get_db_connection()
        c = conn.cursor()
        
        c.execute("SELECT * FROM products WHERE id = ?", (product_id,))
        product = c.fetchone()
        
        if not product:
            conn.close()
            return jsonify({'success': False, 'error': 'Product not found'})
        
        total_credits = float(product[2]) * days
        
        c.execute("SELECT credits FROM users WHERE username = ?", (session['username'],))
        user_credits = c.fetchone()
        
        if not user_credits or user_credits[0] < total_credits:
            conn.close()
            return jsonify({'success': False, 'error': f'Insufficient credits. Need {total_credits} credits'})
        
        # Generate key
        key = generate_key_by_type(product[4])
        expiry_date = datetime.now() + timedelta(days=days)
        
        # Deduct credits
        c.execute("UPDATE users SET credits = credits - ? WHERE username = ?",
                 (total_credits, session['username']))
        
        # Save license
        c.execute("""INSERT INTO licenses 
                     (key, username, product_name, days, total_credits, expiry_date, status)
                     VALUES (?, ?, ?, ?, ?, ?, ?)""",
                 (key, session['username'], product[1], days, total_credits, 
                  expiry_date.strftime('%Y-%m-%d %H:%M:%S'), 'active'))
        
        conn.commit()
        conn.close()
        
        session['credits'] = session.get('credits', 0) - total_credits
        
        return jsonify({'success': True, 'key': key})
        
    except Exception as e:
        print(f"Generate Key Error: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/payment', methods=['GET', 'POST'])
def payment():
    try:
        if 'username' not in session:
            return redirect(url_for('login'))
        
        if request.method == 'POST':
            utr = request.form.get('utr', '').strip()
            amount = float(request.form.get('amount', 0))
            
            if amount < MINIMUM_RECHARGE:
                return render_template('payment.html', 
                                     error=f'Minimum recharge amount is ₹{MINIMUM_RECHARGE}',
                                     min_recharge=MINIMUM_RECHARGE,
                                     credit_rate=CREDIT_RATE,
                                     upi_id=UPI_ID,
                                     whatsapp_link=WHATSAPP_LINK,
                                     telegram_channel=TELEGRAM_CHANNEL)
            
            if not utr or len(utr) != 12 or not utr.isdigit():
                return render_template('payment.html', 
                                     error='Please enter a valid 12-digit UTR number',
                                     min_recharge=MINIMUM_RECHARGE,
                                     credit_rate=CREDIT_RATE,
                                     upi_id=UPI_ID,
                                     whatsapp_link=WHATSAPP_LINK,
                                     telegram_channel=TELEGRAM_CHANNEL)
            
            credits_to_add = amount * CREDIT_RATE
            
            conn = get_db_connection()
            c = conn.cursor()
            
            try:
                c.execute("""INSERT INTO payments 
                             (username, utr, amount, credits_added, status, date)
                             VALUES (?, ?, ?, ?, ?, ?)""",
                         (session['username'], utr, amount, credits_to_add, 'pending',
                          datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
                conn.commit()
                conn.close()
                
                qr_code = generate_upi_qr(amount)
                
                return render_template('payment.html', 
                                     success=f'Payment request submitted! ₹{amount} = {credits_to_add} credits pending approval.',
                                     qr_code=qr_code,
                                     amount=amount,
                                     min_recharge=MINIMUM_RECHARGE,
                                     credit_rate=CREDIT_RATE,
                                     upi_id=UPI_ID,
                                     whatsapp_link=WHATSAPP_LINK,
                                     telegram_channel=TELEGRAM_CHANNEL)
                                     
            except sqlite3.IntegrityError:
                conn.close()
                return render_template('payment.html', 
                                     error='UTR already exists! Please use a different UTR.',
                                     min_recharge=MINIMUM_RECHARGE,
                                     credit_rate=CREDIT_RATE,
                                     upi_id=UPI_ID,
                                     whatsapp_link=WHATSAPP_LINK,
                                     telegram_channel=TELEGRAM_CHANNEL)
        
        # GET request
        qr_code = generate_upi_qr(MINIMUM_RECHARGE)
        
        return render_template('payment.html', 
                             qr_code=qr_code,
                             min_recharge=MINIMUM_RECHARGE,
                             credit_rate=CREDIT_RATE,
                             upi_id=UPI_ID,
                             whatsapp_link=WHATSAPP_LINK,
                             telegram_channel=TELEGRAM_CHANNEL)
    
    except Exception as e:
        print(f"Payment Error: {e}")
        traceback.print_exc()
        return render_template('error.html', error="Payment system error"), 500

@app.route('/generate_payment_qr', methods=['POST'])
def generate_payment_qr():
    try:
        if 'username' not in session:
            return jsonify({'success': False, 'error': 'Not logged in'})
        
        data = request.get_json()
        amount = float(data.get('amount', MINIMUM_RECHARGE))
        
        if amount < MINIMUM_RECHARGE:
            return jsonify({'success': False, 'error': f'Minimum amount is ₹{MINIMUM_RECHARGE}'})
        
        qr_code = generate_upi_qr(amount)
        credits_to_add = amount * CREDIT_RATE
        
        return jsonify({
            'success': True,
            'qr_code': qr_code,
            'amount': amount,
            'credits': round(credits_to_add, 1),
            'upi_id': UPI_ID
        })
        
    except Exception as e:
        print(f"Generate QR Error: {e}")
        return jsonify({'success': False, 'error': str(e)})

# Admin routes
@app.route('/admin/approve_payment', methods=['POST'])
def approve_payment():
    try:
        if 'username' not in session or session.get('role') != 'admin':
            return jsonify({'success': False, 'error': 'Unauthorized'})
        
        data = request.get_json()
        payment_id = data.get('payment_id')
        
        conn = get_db_connection()
        c = conn.cursor()
        
        c.execute("SELECT * FROM payments WHERE id = ?", (payment_id,))
        payment = c.fetchone()
        
        if not payment:
            conn.close()
            return jsonify({'success': False, 'error': 'Payment not found'})
        
        # Update payment status
        c.execute("""UPDATE payments SET status = 'approved', approved_date = ?, approved_by = ? 
                     WHERE id = ?""", 
                 (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), session['username'], payment_id))
        
        # Add credits to user
        c.execute("UPDATE users SET credits = credits + ?, total_recharged = total_recharged + ? WHERE username = ?",
                 (float(payment[4]), float(payment[3]), payment[1]))
        
        conn.commit()
        conn.close()
        
        return jsonify({'success': True})
        
    except Exception as e:
        print(f"Approve Payment Error: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/admin/reject_payment', methods=['POST'])
def reject_payment():
    try:
        if 'username' not in session or session.get('role') != 'admin':
            return jsonify({'success': False, 'error': 'Unauthorized'})
        
        data = request.get_json()
        payment_id = data.get('payment_id')
        
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("UPDATE payments SET status = 'rejected' WHERE id = ?", (payment_id,))
        conn.commit()
        conn.close()
        
        return jsonify({'success': True})
        
    except Exception as e:
        print(f"Reject Payment Error: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/admin/add_credits', methods=['POST'])
def add_credits():
    try:
        if 'username' not in session or session.get('role') != 'admin':
            return jsonify({'success': False, 'error': 'Unauthorized'})
        
        data = request.get_json()
        username = data.get('username')
        credits = float(data.get('credits', 0))
        
        if credits <= 0:
            return jsonify({'success': False, 'error': 'Invalid credit amount'})
        
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("UPDATE users SET credits = credits + ? WHERE username = ?", (credits, username))
        conn.commit()
        conn.close()
        
        return jsonify({'success': True})
        
    except Exception as e:
        print(f"Add Credits Error: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/admin/delete_user', methods=['POST'])
def delete_user():
    try:
        if 'username' not in session or session.get('role') != 'admin':
            return jsonify({'success': False, 'error': 'Unauthorized'})
        
        data = request.get_json()
        username = data.get('username')
        
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("DELETE FROM users WHERE username = ? AND role != 'admin'", (username,))
        c.execute("DELETE FROM licenses WHERE username = ?", (username,))
        c.execute("DELETE FROM payments WHERE username = ?", (username,))
        conn.commit()
        conn.close()
        
        return jsonify({'success': True})
        
    except Exception as e:
        print(f"Delete User Error: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/admin/delete_key', methods=['POST'])
def delete_key():
    try:
        if 'username' not in session or session.get('role') != 'admin':
            return jsonify({'success': False, 'error': 'Unauthorized'})
        
        data = request.get_json()
        license_id = data.get('license_id')
        
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("DELETE FROM licenses WHERE id = ?", (license_id,))
        conn.commit()
        conn.close()
        
        return jsonify({'success': True})
        
    except Exception as e:
        print(f"Delete Key Error: {e}")
        return jsonify({'success': False, 'error': str(e)})

# Product management
@app.route('/admin/add_product', methods=['POST'])
def add_product():
    try:
        if 'username' not in session or session.get('role') != 'admin':
            return jsonify({'success': False, 'error': 'Unauthorized'})
        
        data = request.get_json()
        name = data.get('name', '').strip()
        credit_cost_per_day = float(data.get('credit_cost_per_day', 0))
        price_per_day = float(data.get('price_per_day', 0))
        key_type = data.get('key_type', 'standard')
        
        if not name or credit_cost_per_day <= 0 or price_per_day <= 0:
            return jsonify({'success': False, 'error': 'Invalid product data'})
        
        conn = get_db_connection()
        c = conn.cursor()
        
        try:
            c.execute("""INSERT INTO products (name, credit_cost_per_day, price_per_day, key_type)
                         VALUES (?, ?, ?, ?)""", (name, credit_cost_per_day, price_per_day, key_type))
            conn.commit()
            conn.close()
            return jsonify({'success': True})
        except sqlite3.IntegrityError:
            conn.close()
            return jsonify({'success': False, 'error': 'Product name already exists'})
            
    except Exception as e:
        print(f"Add Product Error: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/admin/edit_product', methods=['POST'])
def edit_product():
    try:
        if 'username' not in session or session.get('role') != 'admin':
            return jsonify({'success': False, 'error': 'Unauthorized'})
        
        data = request.get_json()
        product_id = data.get('product_id')
        name = data.get('name', '').strip()
        credit_cost_per_day = float(data.get('credit_cost_per_day', 0))
        price_per_day = float(data.get('price_per_day', 0))
        key_type = data.get('key_type', 'standard')
        
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("""UPDATE products SET name = ?, credit_cost_per_day = ?, price_per_day = ?, key_type = ?
                     WHERE id = ?""", (name, credit_cost_per_day, price_per_day, key_type, product_id))
        conn.commit()
        conn.close()
        
        return jsonify({'success': True})
        
    except Exception as e:
        print(f"Edit Product Error: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/admin/toggle_product', methods=['POST'])
def toggle_product():
    try:
        if 'username' not in session or session.get('role') != 'admin':
            return jsonify({'success': False, 'error': 'Unauthorized'})
        
        data = request.get_json()
        product_id = data.get('product_id')
        is_active = int(data.get('is_active', 1))
        
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("UPDATE products SET is_active = ? WHERE id = ?", (is_active, product_id))
        conn.commit()
        conn.close()
        
        return jsonify({'success': True})
        
    except Exception as e:
        print(f"Toggle Product Error: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/admin/delete_product', methods=['POST'])
def delete_product():
    try:
        if 'username' not in session or session.get('role') != 'admin':
            return jsonify({'success': False, 'error': 'Unauthorized'})
        
        data = request.get_json()
        product_id = data.get('product_id')
        
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("DELETE FROM products WHERE id = ?", (product_id,))
        conn.commit()
        conn.close()
        
        return jsonify({'success': True})
        
    except Exception as e:
        print(f"Delete Product Error: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/hwid_reset', methods=['POST'])
def hwid_reset():
    try:
        if 'username' not in session:
            return jsonify({'success': False, 'error': 'Not logged in'})
        
        data = request.get_json()
        license_id = data.get('license_id')
        
        conn = get_db_connection()
        c = conn.cursor()
        
        c.execute("SELECT * FROM licenses WHERE id = ? AND username = ?", 
                 (license_id, session['username']))
        license = c.fetchone()
        
        if not license:
            conn.close()
            return jsonify({'success': False, 'error': 'License not found'})
        
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        c.execute("UPDATE licenses SET last_reset = ? WHERE id = ?", 
                 (current_time, license_id))
        
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'message': 'HWID reset successful'})
        
    except Exception as e:
        print(f"HWID Reset Error: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/hwid_reset_all', methods=['POST'])
def hwid_reset_all():
    try:
        if 'username' not in session:
            return jsonify({'success': False, 'error': 'Not logged in'})
        
        conn = get_db_connection()
        c = conn.cursor()
        
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        c.execute("UPDATE licenses SET last_reset = ? WHERE username = ?", 
                 (current_time, session['username']))
        
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'message': 'All HWIDs reset successfully'})
        
    except Exception as e:
        print(f"HWID Reset All Error: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/get_products')
def get_products():
    try:
        if 'username' not in session:
            return jsonify({'success': False, 'error': 'Not logged in'})
        
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT * FROM products WHERE is_active = 1 ORDER BY name")
        products = c.fetchall()
        conn.close()
        
        return jsonify({'success': True, 'products': [dict(p) for p in products]})
        
    except Exception as e:
        print(f"Get Products Error: {e}")
        return jsonify({'success': False, 'error': str(e)})

# Error page template
@app.route('/error')
def error_page():
    error = request.args.get('error', 'Unknown error occurred')
    return render_template('error.html', error=error)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
