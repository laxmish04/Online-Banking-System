# app.py  — Flask + MySQL version

from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, make_response, send_file
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import random, string, hashlib
from datetime import datetime, timedelta
from io import BytesIO
import os

import mysql.connector
from mysql.connector import pooling

# PDF and Email imports (optional - will work without them but with limited functionality)
try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter, A4
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False
    print("Warning: reportlab not installed. PDF generation will be disabled. Install with: pip install reportlab")

try:
    from flask_mail import Mail, Message
    MAIL_AVAILABLE = True
except ImportError:
    MAIL_AVAILABLE = False
    print("Warning: flask-mail not installed. Email functionality will be disabled. Install with: pip install flask-mail")

app = Flask(__name__)
app.secret_key = 'your_secret_key'   # change in production

# Email configuration (optional - update with your SMTP settings)
if MAIL_AVAILABLE:
    app.config['MAIL_SERVER'] = 'smtp.gmail.com'
    app.config['MAIL_PORT'] = 587
    app.config['MAIL_USE_TLS'] = True
    app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME', 'your_email@gmail.com')
    app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD', 'your_app_password')
    mail = Mail(app)

# ---------- MySQL CONNECTION (update credentials here) ----------
pool = pooling.MySQLConnectionPool(
    pool_name="bankpool",
    pool_size=5,
    host="localhost",
    user="root",                 # <- or 'root'
    password="root",     # <- put your password
    database="online_banking",
    autocommit=False
)

def get_conn():
    return pool.get_connection()

# ------------------ DATABASE INITIALIZATION ------------------
def init_transaction_pin():
    """Initialize transaction PIN column in users table if it doesn't exist."""
    conn = get_conn()
    cur = conn.cursor()
    try:
        # Check if column exists
        cur.execute("""
            SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS 
            WHERE TABLE_SCHEMA = DATABASE() 
            AND TABLE_NAME = 'users' 
            AND COLUMN_NAME = 'transaction_pin'
        """)
        exists = cur.fetchone()[0] > 0
        
        if not exists:
            # Add transaction_pin column
            cur.execute("""
                ALTER TABLE users 
                ADD COLUMN transaction_pin VARCHAR(255) NULL
            """)
            conn.commit()
            print("✓ Transaction PIN column added to users table")
            return True
        return True
    except Exception as e:
        conn.rollback()
        print(f"Error initializing transaction PIN: {e}")
        return False
    finally:
        cur.close()
        conn.close()

def init_bill_tables():
    """Initialize bill payment tables if they don't exist."""
    conn = get_conn()
    cur = conn.cursor()
    try:
        # Create saved_billers table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS saved_billers (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id VARCHAR(8) NOT NULL,
                biller_category VARCHAR(50) NOT NULL,
                biller_name VARCHAR(255) NOT NULL,
                biller_code VARCHAR(50),
                account_number VARCHAR(100) NOT NULL,
                nickname VARCHAR(100),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                INDEX idx_user_id (user_id)
            )
        """)
        
        # Create bill_payments table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS bill_payments (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id VARCHAR(8) NOT NULL,
                biller_category VARCHAR(50) NOT NULL,
                biller_name VARCHAR(255) NOT NULL,
                biller_code VARCHAR(50),
                account_number VARCHAR(100) NOT NULL,
                amount DECIMAL(10, 2) NOT NULL,
                note TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                INDEX idx_user_id (user_id),
                INDEX idx_created_at (created_at)
            )
        """)
        
        # Create recurring_payments table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS recurring_payments (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id VARCHAR(8) NOT NULL,
                saved_biller_id INT NOT NULL,
                amount DECIMAL(10, 2) NOT NULL,
                frequency ENUM('weekly', 'monthly', 'quarterly', 'yearly') DEFAULT 'monthly',
                next_payment_date DATE NOT NULL,
                is_active TINYINT(1) DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (saved_biller_id) REFERENCES saved_billers(id) ON DELETE CASCADE,
                INDEX idx_user_id (user_id),
                INDEX idx_next_payment_date (next_payment_date)
            )
        """)
        
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f"Error initializing bill tables: {e}")
        return False
    finally:
        cur.close()
        conn.close()

# ------------------ SMALL HELPERS ------------------
admin_username = "admin"
admin_password = "admin123"

def generate_user_id() -> str:
    """Create an 8-digit id not already used in DB."""
    for _ in range(200):
        uid = ''.join(random.choices(string.digits, k=8))
        if not user_by_id(uid):
            return uid
    raise RuntimeError("Could not generate unique id")

def sha256(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()

def user_by_id(uid):
    conn = get_conn(); cur = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM users WHERE id=%s", (uid,))
    row = cur.fetchone()
    cur.close(); conn.close()
    return row

def user_by_username(username):
    conn = get_conn(); cur = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM users WHERE username=%s", (username,))
    row = cur.fetchone()
    cur.close(); conn.close()
    return row

def username_exists(username) -> bool:
    return user_by_username(username) is not None

def email_exists(email) -> bool:
    conn = get_conn(); cur = conn.cursor()
    cur.execute("SELECT 1 FROM users WHERE email=%s", (email,))
    ok = cur.fetchone() is not None
    cur.close(); conn.close()
    return ok

def create_user(uid, fullname, email, username, phone, password_hash):
    conn = get_conn(); cur = conn.cursor()
    cur.execute("""
        INSERT INTO users (id, fullname, email, username, phone, password_hash)
        VALUES (%s,%s,%s,%s,%s,%s)
    """, (uid, fullname, email, username, phone, password_hash))
    conn.commit(); cur.close(); conn.close()

def list_user_transactions(uid, limit=5):
    conn = get_conn(); cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT id, type AS action, amount, note, created_at AS timestamp
        FROM transactions
        WHERE user_id=%s
        ORDER BY created_at DESC
        LIMIT %s
    """, (uid, limit))
    rows = cur.fetchall()
    cur.close(); conn.close()
    return rows

def record_tx_and_update_balance(uid, ttype, amount, note=""):
    """Atomic: lock user, insert transaction, update balance."""
    conn = get_conn(); cur = conn.cursor()
    try:
        cur.execute("SELECT balance FROM users WHERE id=%s FOR UPDATE", (uid,))
        r = cur.fetchone()
        if not r:
            conn.rollback(); raise ValueError("User not found")
        bal = float(r[0])
        new_bal = bal + amount if ttype in ("credit","add_funds","loan_credited") else bal - amount
        if new_bal < 0:
            conn.rollback(); raise ValueError("Insufficient funds")

        cur.execute("""
            INSERT INTO transactions (user_id, type, amount, note)
            VALUES (%s,%s,%s,%s)
        """, (uid, ttype, amount, note))
        cur.execute("UPDATE users SET balance=%s WHERE id=%s", (new_bal, uid))
        conn.commit()
        return new_bal
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cur.close(); conn.close()

def create_loan(uid, loan_type, amount):
    conn = get_conn(); cur = conn.cursor()
    cur.execute("INSERT INTO loans (user_id, loan_type, amount) VALUES (%s,%s,%s)",
                (uid, loan_type, amount))
    conn.commit(); cur.close(); conn.close()

def list_loans():
    conn = get_conn(); cur = conn.cursor(dictionary=True)
    cur.execute("SELECT id, user_id, loan_type, amount, status, created_at FROM loans ORDER BY created_at DESC")
    rows = cur.fetchall()
    cur.close(); conn.close()
    return rows

def loan_by_id(loan_id):
    conn = get_conn(); cur = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM loans WHERE id=%s", (loan_id,))
    row = cur.fetchone()
    cur.close(); conn.close()
    return row

def update_loan_status(loan_id, status):
    conn = get_conn(); cur = conn.cursor()
    cur.execute("UPDATE loans SET status=%s WHERE id=%s", (status, loan_id))
    conn.commit(); cur.close(); conn.close()

# ------------------ BILL PAYMENT HELPERS ------------------
def get_biller_categories():
    """Return list of available biller categories."""
    return ['electricity', 'water', 'phone', 'internet', 'gas', 'insurance']

def get_billers_by_category(category):
    """Get billers for a specific category."""
    # Predefined billers for demo
    billers = {
        'electricity': [
            {'name': 'State Electricity Board', 'code': 'SEB001'},
            {'name': 'Power Grid Corporation', 'code': 'PGC001'},
            {'name': 'Green Energy Co', 'code': 'GEC001'}
        ],
        'water': [
            {'name': 'Municipal Water Supply', 'code': 'MWS001'},
            {'name': 'Water Works Department', 'code': 'WWD001'},
            {'name': 'Aqua Services', 'code': 'AQS001'}
        ],
        'phone': [
            {'name': 'Airtel', 'code': 'AIR001'},
            {'name': 'Jio', 'code': 'JIO001'},
            {'name': 'Vodafone', 'code': 'VOD001'},
            {'name': 'BSNL', 'code': 'BSN001'}
        ],
        'internet': [
            {'name': 'Broadband Services', 'code': 'BBS001'},
            {'name': 'FiberNet', 'code': 'FBN001'}
        ],
        'gas': [
            {'name': 'Gas Supply Co', 'code': 'GSC001'},
            {'name': 'LPG Services', 'code': 'LPG001'}
        ],
        'insurance': [
            {'name': 'Life Insurance Corp', 'code': 'LIC001'},
            {'name': 'Health Insurance Co', 'code': 'HIC001'}
        ]
    }
    return billers.get(category, [])

def get_user_saved_billers(uid):
    """Get all saved billers for a user."""
    try:
        conn = get_conn(); cur = conn.cursor(dictionary=True)
        cur.execute("""
            SELECT id, biller_category, biller_name, biller_code, account_number, nickname, created_at
            FROM saved_billers
            WHERE user_id=%s
            ORDER BY created_at DESC
        """, (uid,))
        rows = cur.fetchall()
        cur.close(); conn.close()
        return rows
    except mysql.connector.Error as e:
        if e.errno == 1146:  # Table doesn't exist
            init_bill_tables()
            return []
        raise

def save_biller(uid, biller_category, biller_name, biller_code, account_number, nickname=None):
    """Save a biller for the user."""
    conn = get_conn(); cur = conn.cursor()
    cur.execute("""
        INSERT INTO saved_billers (user_id, biller_category, biller_name, biller_code, account_number, nickname)
        VALUES (%s, %s, %s, %s, %s, %s)
    """, (uid, biller_category, biller_name, biller_code, account_number, nickname))
    conn.commit(); cur.close(); conn.close()

def get_saved_biller_by_id(biller_id, uid):
    """Get a saved biller by ID (ensuring it belongs to user)."""
    conn = get_conn(); cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT * FROM saved_billers WHERE id=%s AND user_id=%s
    """, (biller_id, uid))
    row = cur.fetchone()
    cur.close(); conn.close()
    return row

def delete_saved_biller(biller_id, uid):
    """Delete a saved biller."""
    conn = get_conn(); cur = conn.cursor()
    cur.execute("DELETE FROM saved_billers WHERE id=%s AND user_id=%s", (biller_id, uid))
    conn.commit(); cur.close(); conn.close()

def record_bill_payment(uid, biller_category, biller_name, biller_code, account_number, amount, note=""):
    """Record a bill payment transaction."""
    payment_note = f"Bill payment: {biller_name} ({biller_category}) - Account: {account_number}"
    if note:
        payment_note += f" - {note}"
    try:
        new_bal = record_tx_and_update_balance(uid, 'debit', amount, payment_note)
        
        # Also record in bill_payments table
        conn = get_conn(); cur = conn.cursor()
        cur.execute("""
            INSERT INTO bill_payments (user_id, biller_category, biller_name, biller_code, account_number, amount, note)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (uid, biller_category, biller_name, biller_code, account_number, amount, note))
        conn.commit(); cur.close(); conn.close()
        return new_bal
    except Exception as e:
        raise e

def get_bill_payment_history(uid, limit=None):
    """Get bill payment history for a user."""
    try:
        conn = get_conn(); cur = conn.cursor(dictionary=True)
        query = """
            SELECT id, biller_category, biller_name, biller_code, account_number, amount, note, created_at
            FROM bill_payments
            WHERE user_id=%s
            ORDER BY created_at DESC
        """
        if limit:
            query += " LIMIT %s"
            cur.execute(query, (uid, limit))
        else:
            cur.execute(query, (uid,))
        rows = cur.fetchall()
        cur.close(); conn.close()
        return rows
    except mysql.connector.Error as e:
        if e.errno == 1146:  # Table doesn't exist
            init_bill_tables()
            return []
        raise

def create_recurring_payment(uid, saved_biller_id, amount, frequency, next_payment_date):
    """Create a recurring payment schedule."""
    conn = get_conn(); cur = conn.cursor()
    cur.execute("""
        INSERT INTO recurring_payments (user_id, saved_biller_id, amount, frequency, next_payment_date, is_active)
        VALUES (%s, %s, %s, %s, %s, 1)
    """, (uid, saved_biller_id, amount, frequency, next_payment_date))
    conn.commit(); cur.close(); conn.close()

def get_user_recurring_payments(uid):
    """Get all recurring payments for a user."""
    try:
        conn = get_conn(); cur = conn.cursor(dictionary=True)
        cur.execute("""
            SELECT rp.id, rp.saved_biller_id, rp.amount, rp.frequency, rp.next_payment_date, rp.is_active, rp.created_at,
                   sb.biller_category, sb.biller_name, sb.biller_code, sb.account_number, sb.nickname
            FROM recurring_payments rp
            JOIN saved_billers sb ON rp.saved_biller_id = sb.id
            WHERE rp.user_id=%s
            ORDER BY rp.next_payment_date ASC
        """, (uid,))
        rows = cur.fetchall()
        cur.close(); conn.close()
        return rows
    except mysql.connector.Error as e:
        if e.errno == 1146:  # Table doesn't exist
            init_bill_tables()
            return []
        raise

def update_recurring_payment_next_date(recurring_id, next_date):
    """Update the next payment date for a recurring payment."""
    conn = get_conn(); cur = conn.cursor()
    cur.execute("""
        UPDATE recurring_payments SET next_payment_date=%s WHERE id=%s
    """, (next_date, recurring_id))
    conn.commit(); cur.close(); conn.close()

def toggle_recurring_payment(recurring_id, uid, is_active):
    """Enable/disable a recurring payment."""
    conn = get_conn(); cur = conn.cursor()
    cur.execute("""
        UPDATE recurring_payments SET is_active=%s WHERE id=%s AND user_id=%s
    """, (is_active, recurring_id, uid))
    conn.commit(); cur.close(); conn.close()

def delete_recurring_payment(recurring_id, uid):
    """Delete a recurring payment."""
    conn = get_conn(); cur = conn.cursor()
    cur.execute("DELETE FROM recurring_payments WHERE id=%s AND user_id=%s", (recurring_id, uid))
    conn.commit(); cur.close(); conn.close()

# ------------------ TRANSACTION PIN HELPERS ------------------
def set_transaction_pin(uid, pin):
    """Set or update transaction PIN for a user."""
    if not pin or len(pin) != 4 or not pin.isdigit():
        raise ValueError("PIN must be exactly 4 digits")
    
    # Hash the PIN for security
    pin_hash = generate_password_hash(pin)
    conn = get_conn(); cur = conn.cursor()
    cur.execute("UPDATE users SET transaction_pin=%s WHERE id=%s", (pin_hash, uid))
    conn.commit(); cur.close(); conn.close()

def verify_transaction_pin(uid, pin):
    """Verify transaction PIN for a user."""
    if not pin or len(pin) != 4 or not pin.isdigit():
        return False
    
    conn = get_conn(); cur = conn.cursor(dictionary=True)
    cur.execute("SELECT transaction_pin FROM users WHERE id=%s", (uid,))
    row = cur.fetchone()
    cur.close(); conn.close()
    
    if not row or not row.get('transaction_pin'):
        return False  # PIN not set
    
    return check_password_hash(row['transaction_pin'], pin)

def has_transaction_pin(uid):
    """Check if user has a transaction PIN set."""
    conn = get_conn(); cur = conn.cursor(dictionary=True)
    cur.execute("SELECT transaction_pin FROM users WHERE id=%s", (uid,))
    row = cur.fetchone()
    cur.close(); conn.close()
    
    return row and row.get('transaction_pin') is not None

# ------------------ ACCOUNT STATEMENT HELPERS ------------------
def get_statement_transactions(uid, start_date, end_date):
    """Get transactions for a date range."""
    conn = get_conn(); cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT type AS action, amount, note, created_at AS timestamp
        FROM transactions
        WHERE user_id=%s AND DATE(created_at) BETWEEN %s AND %s
        ORDER BY created_at ASC
    """, (uid, start_date, end_date))
    rows = cur.fetchall()
    cur.close(); conn.close()
    return rows

def calculate_statement_summary(transactions):
    """Calculate summary statistics for statement."""
    total_credits = 0.0
    total_debits = 0.0
    transaction_count = len(transactions)
    
    for tx in transactions:
        amount = float(tx['amount'])
        if tx['action'] in ('credit', 'add_funds', 'loan_credited'):
            total_credits += amount
        elif tx['action'] == 'debit':
            total_debits += amount
    
    opening_balance = 0.0
    closing_balance = 0.0
    
    if transactions:
        # Calculate opening balance (balance before first transaction)
        first_tx = transactions[0]
        first_amount = float(first_tx['amount'])
        if first_tx['action'] in ('credit', 'add_funds', 'loan_credited'):
            opening_balance = closing_balance - first_amount
        elif first_tx['action'] == 'debit':
            opening_balance = closing_balance + first_amount
        
        # Calculate closing balance
        running_balance = opening_balance
        for tx in transactions:
            amount = float(tx['amount'])
            if tx['action'] in ('credit', 'add_funds', 'loan_credited'):
                running_balance += amount
            elif tx['action'] == 'debit':
                running_balance -= amount
        closing_balance = running_balance
    
    return {
        'opening_balance': opening_balance,
        'closing_balance': closing_balance,
        'total_credits': total_credits,
        'total_debits': total_debits,
        'transaction_count': transaction_count
    }

def generate_pdf_statement(user, transactions, summary, start_date, end_date):
    """Generate PDF statement using reportlab."""
    if not PDF_AVAILABLE:
        raise Exception("PDF generation not available. Please install reportlab: pip install reportlab")
    
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=72, leftMargin=72, topMargin=72, bottomMargin=18)
    
    # Container for the 'Flowable' objects
    elements = []
    
    # Define styles
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=colors.HexColor('#1034a6'),
        spaceAfter=30,
        alignment=1  # Center
    )
    
    # Title
    title = Paragraph("Account Statement", title_style)
    elements.append(title)
    elements.append(Spacer(1, 0.2*inch))
    
    # Bank info
    bank_info = [
        ['OnlineBanking', ''],
        ['Account Statement', '']
    ]
    bank_table = Table(bank_info, colWidths=[4*inch, 2*inch])
    bank_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (0, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (0, 0), 16),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
    ]))
    elements.append(bank_table)
    elements.append(Spacer(1, 0.3*inch))
    
    # Account details
    account_data = [
        ['Account Holder:', user.get('fullname', 'N/A')],
        ['Account Number:', user.get('id', 'N/A')],
        ['Email:', user.get('email', 'N/A')],
        ['Phone:', user.get('phone', 'N/A')],
        ['Statement Period:', f"{start_date} to {end_date}"],
        ['Generated On:', datetime.now().strftime('%Y-%m-%d %H:%M:%S')]
    ]
    account_table = Table(account_data, colWidths=[2*inch, 4*inch])
    account_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f0f0f0')),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('GRID', (0, 0), (-1, -1), 1, colors.grey)
    ]))
    elements.append(account_table)
    elements.append(Spacer(1, 0.3*inch))
    
    # Summary
    summary_data = [
        ['Opening Balance', f"₹{summary['opening_balance']:.2f}"],
        ['Total Credits', f"₹{summary['total_credits']:.2f}"],
        ['Total Debits', f"₹{summary['total_debits']:.2f}"],
        ['Closing Balance', f"₹{summary['closing_balance']:.2f}"],
        ['No. of Transactions', str(summary['transaction_count'])]
    ]
    summary_table = Table(summary_data, colWidths=[3*inch, 3*inch])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1034a6')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 11),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ('TOPPADDING', (0, 0), (-1, -1), 10),
        ('GRID', (0, 0), (-1, -1), 1, colors.grey),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f9f9f9')])
    ]))
    elements.append(summary_table)
    elements.append(Spacer(1, 0.3*inch))
    
    # Transactions table
    if transactions:
        tx_data = [['Date', 'Type', 'Description', 'Debit', 'Credit', 'Balance']]
        running_balance = summary['opening_balance']
        
        for tx in transactions:
            date_str = tx['timestamp'].strftime('%Y-%m-%d')
            tx_type = tx['action'].replace('_', ' ').title()
            description = tx.get('note', '')[:50]  # Limit description length
            amount = float(tx['amount'])
            
            if tx['action'] in ('credit', 'add_funds', 'loan_credited'):
                debit = ''
                credit = f"₹{amount:.2f}"
                running_balance += amount
            else:
                debit = f"₹{amount:.2f}"
                credit = ''
                running_balance -= amount
            
            tx_data.append([date_str, tx_type, description, debit, credit, f"₹{running_balance:.2f}"])
        
        tx_table = Table(tx_data, colWidths=[0.8*inch, 1*inch, 2.2*inch, 1*inch, 1*inch, 1*inch])
        tx_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1034a6')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('ALIGN', (3, 1), (5, -1), 'RIGHT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('GRID', (0, 0), (-1, -1), 1, colors.grey),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f9f9f9')])
        ]))
        elements.append(tx_table)
    else:
        no_tx = Paragraph("No transactions found for the selected period.", styles['Normal'])
        elements.append(no_tx)
    
    elements.append(Spacer(1, 0.3*inch))
    
    # Footer
    footer = Paragraph(
        "<i>This is a computer-generated statement. No signature is required.</i><br/>"
        "<i>For queries, please contact support.</i>",
        styles['Normal']
    )
    elements.append(footer)
    
    # Build PDF
    doc.build(elements)
    buffer.seek(0)
    return buffer

def send_statement_email(user, pdf_buffer, start_date, end_date):
    """Send statement via email."""
    if not MAIL_AVAILABLE:
        raise Exception("Email functionality not available. Please install flask-mail: pip install flask-mail")
    
    try:
        msg = Message(
            subject=f'Account Statement - {start_date} to {end_date}',
            recipients=[user.get('email', '')],
            body=f"""
Dear {user.get('fullname', 'Customer')},

Please find attached your account statement for the period {start_date} to {end_date}.

Account Number: {user.get('id', 'N/A')}

If you have any questions, please contact our support team.

Best regards,
OnlineBanking Team
            """,
            sender=app.config['MAIL_USERNAME']
        )
        
        msg.attach(
            f'statement_{start_date}_{end_date}.pdf',
            'application/pdf',
            pdf_buffer.read()
        )
        
        mail.send(msg)
        return True
    except Exception as e:
        print(f"Error sending email: {e}")
        return False

# --------------- CONTEXT (inject current user) ---------------
@app.context_processor
def inject_user():
    if 'user_id' in session and session['user_id'] != "admin":
        return {'user': user_by_id(session['user_id'])}
    return {'user': None}

# ----------------------- ROUTES -----------------------
@app.route('/')
def home():
    return render_template('login.html')

# -------- Signup --------
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        fullname = request.form['fullname'].strip()
        email = request.form['email'].strip()
        username = request.form['username'].strip()
        phone = request.form['phone'].strip()
        password = request.form['password']
        confirm  = request.form['confirm']

        if password != confirm:
            flash('Passwords do not match!'); return render_template('signup.html')
        if username_exists(username):
            flash('Username already exists.'); return render_template('signup.html')
        if email_exists(email):
            flash('Email already exists.'); return render_template('signup.html')

        uid = generate_user_id()
        # store werkzeug hash (pbkdf2:sha256)
        create_user(uid, fullname, email, username, phone, generate_password_hash(password))
        flash('Account created! Please log in.')
        return redirect(url_for('home'))
    return render_template('signup.html')

# -------- Login --------
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']

        # Admin backdoor
        if username == admin_username and password == admin_password:
            session['user_id'] = "admin"
            session['is_admin'] = True
            return redirect(url_for('admin_panel'))

        u = user_by_username(username)
        if u and check_password_hash(u['password_hash'], password):
            session['user_id'] = u['id']
            session['is_admin'] = bool(u.get('is_admin', 0))
            return redirect(url_for('dashboard'))

        flash('Invalid credentials.')
    return render_template('login.html')

# -------- Dashboard --------
@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('home'))

    if session['user_id'] == "admin":
        return redirect(url_for('admin_panel'))

    user = user_by_id(session['user_id'])
    if not user:
        session.clear(); flash('Session expired. Please log in again.')
        return redirect(url_for('home'))

    user_transactions = list_user_transactions(user['id'], limit=5)

    # Build daily/monthly balance from full tx history
    conn = get_conn(); cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT type AS action, amount, created_at AS ts
        FROM transactions WHERE user_id=%s ORDER BY created_at ASC
    """, (user['id'],))
    all_tx = cur.fetchall()
    cur.close(); conn.close()

    running = 0.0
    daily_map, monthly_map = {}, {}

    for t in all_tx:
        action = t['action']
        amt = float(t['amount'])
        if action in ('credit','add_funds','loan_credited'):
            running += amt
        elif action == 'debit':
            running -= amt
        d = t['ts'].strftime('%Y-%m-%d')
        m = t['ts'].strftime('%Y-%m')
        daily_map[d] = running
        monthly_map[m] = running

    balance_daily = [{'date': d, 'balance': daily_map[d]} for d in sorted(daily_map)]
    balance_monthly = [{'date': m, 'balance': monthly_map[m]} for m in sorted(monthly_map)]

    return render_template('dashboard.html',
                           user=user,
                           user_transactions=user_transactions,
                           is_admin=session.get('is_admin'),
                           show_dropdown=True,
                           balance_daily=balance_daily,
                           balance_monthly=balance_monthly)

# -------- Logout --------
@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.')
    return redirect(url_for('home'))

# -------- Profile --------
@app.route('/profile')
def profile():
    if 'user_id' not in session or session['user_id'] == "admin":
        return redirect(url_for('home'))
    user = user_by_id(session['user_id'])
    if not user:
        session.clear(); flash('Session expired. Please log in again.')
        return redirect(url_for('home'))
    return render_template('profile.html', user=user, user_id=user['id'], show_dropdown=False)

# -------- Transaction PIN Management --------
@app.route('/pin/setup', methods=['GET', 'POST'])
def setup_pin():
    """Setup transaction PIN for first time."""
    if 'user_id' not in session or session['user_id'] == "admin":
        return redirect(url_for('home'))
    
    uid = session['user_id']
    user = user_by_id(uid)
    if not user:
        session.clear(); flash('Session expired. Please log in again.')
        return redirect(url_for('home'))
    
    if has_transaction_pin(uid):
        flash('You already have a transaction PIN set. Use change PIN to update it.')
        return redirect(url_for('change_pin'))
    
    if request.method == 'POST':
        pin = request.form.get('pin', '').strip()
        confirm_pin = request.form.get('confirm_pin', '').strip()
        
        if not pin or not confirm_pin:
            flash('Please enter PIN and confirm it.')
            return render_template('setup_pin.html', user=user)
        
        if pin != confirm_pin:
            flash('PINs do not match. Please try again.')
            return render_template('setup_pin.html', user=user)
        
        try:
            set_transaction_pin(uid, pin)
            flash('Transaction PIN set successfully!')
            return redirect(url_for('profile'))
        except ValueError as e:
            flash(str(e))
            return render_template('setup_pin.html', user=user)
    
    return render_template('setup_pin.html', user=user)

@app.route('/pin/change', methods=['GET', 'POST'])
def change_pin():
    """Change existing transaction PIN."""
    if 'user_id' not in session or session['user_id'] == "admin":
        return redirect(url_for('home'))
    
    uid = session['user_id']
    user = user_by_id(uid)
    if not user:
        session.clear(); flash('Session expired. Please log in again.')
        return redirect(url_for('home'))
    
    if not has_transaction_pin(uid):
        flash('You need to setup a transaction PIN first.')
        return redirect(url_for('setup_pin'))
    
    if request.method == 'POST':
        old_pin = request.form.get('old_pin', '').strip()
        new_pin = request.form.get('new_pin', '').strip()
        confirm_pin = request.form.get('confirm_pin', '').strip()
        
        if not old_pin or not new_pin or not confirm_pin:
            flash('Please fill all fields.')
            return render_template('change_pin.html', user=user)
        
        if not verify_transaction_pin(uid, old_pin):
            flash('Current PIN is incorrect.')
            return render_template('change_pin.html', user=user)
        
        if new_pin != confirm_pin:
            flash('New PINs do not match.')
            return render_template('change_pin.html', user=user)
        
        try:
            set_transaction_pin(uid, new_pin)
            flash('Transaction PIN changed successfully!')
            return redirect(url_for('profile'))
        except ValueError as e:
            flash(str(e))
            return render_template('change_pin.html', user=user)
    
    return render_template('change_pin.html', user=user)

# Confirm password route removed — profile editing no longer requires password confirmation.
# -------- Edit profile (GET) --------
@app.route('/edit_profile', methods=['GET'])
def edit_profile():
    if 'user_id' not in session or session['user_id'] == "admin":
        return redirect(url_for('home'))

    user = user_by_id(session['user_id'])
    if not user:
        session.clear(); flash('Session expired. Please log in again.')
        return redirect(url_for('home'))
    return render_template('edit_profile.html', user=user)

# -------- Update profile (POST) --------
@app.route('/update_profile', methods=['POST'])
def update_profile():
    if 'user_id' not in session or session['user_id'] == "admin":
        return redirect(url_for('home'))

    uid = session['user_id']
    fullname = request.form.get('fullname', '').strip()
    email    = request.form.get('email', '').strip()
    username = request.form.get('username', '').strip()
    phone    = request.form.get('phone', '').strip()
    new_pw   = request.form.get('new_password', '').strip()
    confirm  = request.form.get('confirm_new_password', '').strip()

    if not fullname or not email or not username or not phone:
        flash('All fields are required.')
        return redirect(url_for('edit_profile'))

    # uniqueness checks
    conn = get_conn(); cur = conn.cursor()
    cur.execute("SELECT 1 FROM users WHERE username=%s AND id<>%s", (username, uid))
    if cur.fetchone(): cur.close(); conn.close(); flash('Username already exists.'); return redirect(url_for('edit_profile'))
    conn.cmd_query  # keep connection alive (no-op)

    cur.execute("SELECT 1 FROM users WHERE email=%s AND id<>%s", (email, uid))
    if cur.fetchone(): cur.close(); conn.close(); flash('Email already exists.'); return redirect(url_for('edit_profile'))

    if new_pw:
        if new_pw != confirm:
            cur.close(); conn.close(); flash('New passwords do not match.'); return redirect(url_for('edit_profile'))
        if len(new_pw) < 6:
            cur.close(); conn.close(); flash('Password must be at least 6 characters long.'); return redirect(url_for('edit_profile'))
        cur.execute("""
            UPDATE users SET fullname=%s, email=%s, username=%s, phone=%s, password_hash=%s WHERE id=%s
        """, (fullname, email, username, phone, generate_password_hash(new_pw), uid))
    else:
        cur.execute("""
            UPDATE users SET fullname=%s, email=%s, username=%s, phone=%s WHERE id=%s
        """, (fullname, email, username, phone, uid))

    conn.commit()
    cur.close(); conn.close()
    flash('Profile updated successfully!')
    return redirect(url_for('profile'))

# -------- Balance --------
@app.route('/balance')
def balance():
    if 'user_id' not in session or session['user_id'] == "admin":
        return redirect(url_for('home'))
    user = user_by_id(session['user_id'])
    if not user:
        session.clear(); flash('Session expired. Please log in again.')
        return redirect(url_for('home'))
    return render_template('balance.html', user=user)

# -------- Transfer --------
@app.route('/transfer', methods=['GET', 'POST'])
def transfer():
    if 'user_id' not in session or session['user_id'] == "admin":
        return redirect(url_for('home'))

    sender = user_by_id(session['user_id'])
    if not sender:
        session.clear(); flash('Session expired. Please log in again.')
        return redirect(url_for('home'))

    if request.method == 'POST':
        receiver_username = request.form.get('receiver', '').strip()
        transaction_pin = request.form.get('transaction_pin', '').strip()
        
        try:
            amount = float(request.form.get('amount', '0'))
        except ValueError:
            amount = -1

        if amount <= 0:
            flash('Enter a valid positive amount.')
            return render_template('transfer.html', user=sender, has_pin=has_transaction_pin(sender['id']))

        # Verify transaction PIN if set
        if has_transaction_pin(sender['id']):
            if not transaction_pin:
                flash('Transaction PIN is required.')
                return render_template('transfer.html', user=sender, has_pin=True)
            if not verify_transaction_pin(sender['id'], transaction_pin):
                flash('Invalid transaction PIN.')
                return render_template('transfer.html', user=sender, has_pin=True)

        receiver = user_by_username(receiver_username)
        if not receiver:
            flash('Receiver not found.')
            return render_template('transfer.html', user=sender, has_pin=has_transaction_pin(sender['id']))

        try:
            # debit sender
            record_tx_and_update_balance(sender['id'], 'debit', amount, note=f'transfer to {receiver_username}')
            # credit receiver
            record_tx_and_update_balance(receiver['id'], 'credit', amount, note=f'transfer from {sender["username"]}')
            flash('Transfer successful!')
        except ValueError as e:
            flash(str(e))
        return redirect(url_for('dashboard'))

    return render_template('transfer.html', user=sender, has_pin=has_transaction_pin(sender['id']))

# -------- Legacy credit route -> redirect to /loan --------
@app.route('/credit', methods=['GET', 'POST'])
def credit():
    return redirect(url_for('loan'))

# -------- Add funds --------
@app.route('/add_funds', methods=['GET', 'POST'])
def add_funds():
    if 'user_id' not in session or session['user_id'] == "admin":
        return redirect(url_for('home'))

    user = user_by_id(session['user_id'])
    if not user:
        session.clear(); flash('Session expired. Please log in again.')
        return redirect(url_for('home'))

    if request.method == 'POST':
        try:
            amount = float(request.form.get('amount', '0'))
        except ValueError:
            amount = -1

        if amount <= 0:
            flash('Enter a valid positive amount.')
            return render_template('add_funds.html', user=user)

        try:
            new_bal = record_tx_and_update_balance(user['id'], 'add_funds', amount, note='self add funds')
            flash(f'Money added successfully! New balance: ₹{new_bal:.2f}')
        except ValueError as e:
            flash(str(e))
        return redirect(url_for('dashboard'))

    return render_template('add_funds.html', user=user)

# -------- Loan apply --------
@app.route('/loan', methods=['GET', 'POST'])
def loan():
    if 'user_id' not in session or session['user_id'] == "admin":
        return redirect(url_for('home'))

    uid = session['user_id']
    if request.method == 'POST':
        loan_type = request.form.get('loan_type', 'personal')
        try:
            amount = float(request.form.get('amount', '0'))
        except ValueError:
            amount = -1

        if amount <= 0:
            flash('Enter a valid positive amount.')
            return render_template('loan.html')

        create_loan(uid, loan_type, amount)
        flash('Loan application submitted!')
        return redirect(url_for('dashboard'))

    return render_template('loan.html')

# -------- Bill Payments --------
@app.route('/bills', methods=['GET'])
def bills():
    """Main bill payments page - shows categories and saved billers."""
    if 'user_id' not in session or session['user_id'] == "admin":
        return redirect(url_for('home'))
    
    uid = session['user_id']
    user = user_by_id(uid)
    if not user:
        session.clear(); flash('Session expired. Please log in again.')
        return redirect(url_for('home'))
    
    try:
        categories = get_biller_categories()
        saved_billers = get_user_saved_billers(uid)
        payment_history = get_bill_payment_history(uid, limit=5)
    except mysql.connector.Error as e:
        # Table doesn't exist, try to create it
        if e.errno == 1146:  # Table doesn't exist error
            flash('Initializing bill payments tables...')
            if init_bill_tables():
                flash('Bill payments tables created successfully! Please refresh the page.')
            else:
                flash('Error creating bill payments tables. Please run the SQL script manually.')
            return redirect(url_for('dashboard'))
        else:
            flash(f'Database error: {str(e)}. Please check your database connection.')
            return redirect(url_for('dashboard'))
    except Exception as e:
        flash(f'Error loading bill payments: {str(e)}')
        return redirect(url_for('dashboard'))
    
    return render_template('bills.html',
                         user=user,
                         categories=categories,
                         saved_billers=saved_billers,
                         payment_history=payment_history)

@app.route('/bills/pay', methods=['GET', 'POST'])
def pay_bill():
    """Pay a bill - either from saved biller or new payment."""
    if 'user_id' not in session or session['user_id'] == "admin":
        return redirect(url_for('home'))
    
    uid = session['user_id']
    user = user_by_id(uid)
    if not user:
        session.clear(); flash('Session expired. Please log in again.')
        return redirect(url_for('home'))
    
    if request.method == 'POST':
        saved_biller_id = request.form.get('saved_biller_id', '').strip()
        biller_category = request.form.get('biller_category', '').strip()
        biller_name = request.form.get('biller_name', '').strip()
        biller_code = request.form.get('biller_code', '').strip()
        account_number = request.form.get('account_number', '').strip()
        note = request.form.get('note', '').strip()
        transaction_pin = request.form.get('transaction_pin', '').strip()
        
        try:
            amount = float(request.form.get('amount', '0'))
        except ValueError:
            amount = -1
        
        if amount <= 0:
            flash('Enter a valid positive amount.')
            return redirect(url_for('bills'))
        
        if not biller_category or not biller_name or not account_number:
            flash('Please fill all required fields.')
            return redirect(url_for('bills'))
        
        # Verify transaction PIN if set
        if has_transaction_pin(uid):
            if not transaction_pin:
                flash('Transaction PIN is required.')
                return redirect(url_for('pay_bill'))
            if not verify_transaction_pin(uid, transaction_pin):
                flash('Invalid transaction PIN.')
                return redirect(url_for('pay_bill'))
        
        # If using saved biller, get details
        if saved_biller_id:
            saved_biller = get_saved_biller_by_id(saved_biller_id, uid)
            if saved_biller:
                biller_category = saved_biller['biller_category']
                biller_name = saved_biller['biller_name']
                biller_code = saved_biller['biller_code']
                account_number = saved_biller['account_number']
        
        try:
            new_bal = record_bill_payment(uid, biller_category, biller_name, biller_code, account_number, amount, note)
            flash(f'Bill payment successful! Paid ₹{amount:.2f} to {biller_name}. New balance: ₹{new_bal:.2f}')
        except ValueError as e:
            flash(str(e))
        
        return redirect(url_for('bills'))
    
    # GET request - show payment form
    saved_biller_id = request.args.get('saved_biller_id')
    categories = get_biller_categories()
    saved_billers = get_user_saved_billers(uid)
    
    saved_biller = None
    if saved_biller_id:
        saved_biller = get_saved_biller_by_id(saved_biller_id, uid)
    
    return render_template('pay_bill.html',
                         user=user,
                         categories=categories,
                         saved_billers=saved_billers,
                         saved_biller=saved_biller)

@app.route('/bills/add_biller', methods=['GET', 'POST'])
def add_biller():
    """Add a new biller to saved list."""
    if 'user_id' not in session or session['user_id'] == "admin":
        return redirect(url_for('home'))
    
    uid = session['user_id']
    user = user_by_id(uid)
    if not user:
        session.clear(); flash('Session expired. Please log in again.')
        return redirect(url_for('home'))
    
    if request.method == 'POST':
        biller_category = request.form.get('biller_category', '').strip()
        biller_name = request.form.get('biller_name', '').strip()
        biller_code = request.form.get('biller_code', '').strip()
        account_number = request.form.get('account_number', '').strip()
        nickname = request.form.get('nickname', '').strip()
        
        if not biller_category or not biller_name or not account_number:
            flash('Please fill all required fields.')
            return redirect(url_for('add_biller'))
        
        save_biller(uid, biller_category, biller_name, biller_code, account_number, nickname)
        flash(f'Biller "{biller_name}" saved successfully!')
        return redirect(url_for('bills'))
    
    categories = get_biller_categories()
    return render_template('add_biller.html', user=user, categories=categories)

@app.route('/bills/delete_biller', methods=['POST'])
def delete_biller():
    """Delete a saved biller."""
    if 'user_id' not in session or session['user_id'] == "admin":
        return redirect(url_for('home'))
    
    uid = session['user_id']
    biller_id = request.form.get('biller_id')
    
    if biller_id:
        delete_saved_biller(biller_id, uid)
        flash('Biller deleted successfully.')
    
    return redirect(url_for('bills'))

@app.route('/bills/history')
def bill_history():
    """View complete bill payment history."""
    if 'user_id' not in session or session['user_id'] == "admin":
        return redirect(url_for('home'))
    
    uid = session['user_id']
    user = user_by_id(uid)
    if not user:
        session.clear(); flash('Session expired. Please log in again.')
        return redirect(url_for('home'))
    
    payment_history = get_bill_payment_history(uid)
    return render_template('bill_history.html', user=user, payment_history=payment_history)

@app.route('/bills/recurring', methods=['GET', 'POST'])
def recurring_payments():
    """Manage recurring payments."""
    if 'user_id' not in session or session['user_id'] == "admin":
        return redirect(url_for('home'))
    
    uid = session['user_id']
    user = user_by_id(uid)
    if not user:
        session.clear(); flash('Session expired. Please log in again.')
        return redirect(url_for('home'))
    
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'create':
            saved_biller_id = request.form.get('saved_biller_id', '').strip()
            try:
                amount = float(request.form.get('amount', '0'))
            except ValueError:
                amount = -1
            frequency = request.form.get('frequency', 'monthly').strip()
            next_payment_date = request.form.get('next_payment_date', '').strip()
            
            if amount <= 0 or not saved_biller_id or not next_payment_date:
                flash('Please fill all required fields with valid values.')
                return redirect(url_for('recurring_payments'))
            
            create_recurring_payment(uid, saved_biller_id, amount, frequency, next_payment_date)
            flash('Recurring payment scheduled successfully!')
        
        elif action == 'toggle':
            recurring_id = request.form.get('recurring_id')
            is_active = request.form.get('is_active') == '1'
            if recurring_id:
                toggle_recurring_payment(recurring_id, uid, 1 if is_active else 0)
                flash('Recurring payment updated.')
        
        elif action == 'delete':
            recurring_id = request.form.get('recurring_id')
            if recurring_id:
                delete_recurring_payment(recurring_id, uid)
                flash('Recurring payment deleted.')
        
        return redirect(url_for('recurring_payments'))
    
    saved_billers = get_user_saved_billers(uid)
    recurring = get_user_recurring_payments(uid)
    
    return render_template('recurring_payments.html',
                         user=user,
                         saved_billers=saved_billers,
                         recurring_payments=recurring)

@app.route('/bills/get_billers', methods=['GET'])
def get_billers():
    """API endpoint to get billers for a category."""
    if 'user_id' not in session or session['user_id'] == "admin":
        return jsonify({'error': 'Unauthorized'}), 401
    
    category = request.args.get('category', '')
    billers = get_billers_by_category(category)
    return jsonify({'billers': billers})

# -------- Account Statements --------
@app.route('/statements', methods=['GET', 'POST'])
def statements():
    """Account statements page - generate statements for date ranges."""
    if 'user_id' not in session or session['user_id'] == "admin":
        return redirect(url_for('home'))
    
    uid = session['user_id']
    user = user_by_id(uid)
    if not user:
        session.clear(); flash('Session expired. Please log in again.')
        return redirect(url_for('home'))
    
    # Default date range (last 30 days)
    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=30)
    
    transactions = []
    summary = None
    
    if request.method == 'POST' or request.args.get('start_date'):
        start_date_str = request.form.get('start_date') or request.args.get('start_date', '')
        end_date_str = request.form.get('end_date') or request.args.get('end_date', '')
        
        if start_date_str and end_date_str:
            try:
                start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
                
                if start_date > end_date:
                    flash('Start date cannot be after end date.')
                    return render_template('statements.html', user=user, start_date=start_date_str, end_date=end_date_str)
                
                transactions = get_statement_transactions(uid, start_date, end_date)
                summary = calculate_statement_summary(transactions)
            except ValueError:
                flash('Invalid date format. Please use YYYY-MM-DD format.')
    
    return render_template('statements.html',
                         user=user,
                         transactions=transactions,
                         summary=summary,
                         start_date=start_date.strftime('%Y-%m-%d'),
                         end_date=end_date.strftime('%Y-%m-%d'))

@app.route('/statements/pdf', methods=['GET'])
def download_statement_pdf():
    """Download account statement as PDF."""
    if 'user_id' not in session or session['user_id'] == "admin":
        return redirect(url_for('home'))
    
    uid = session['user_id']
    user = user_by_id(uid)
    if not user:
        return redirect(url_for('home'))
    
    start_date_str = request.args.get('start_date', '')
    end_date_str = request.args.get('end_date', '')
    
    if not start_date_str or not end_date_str:
        flash('Please select a date range.')
        return redirect(url_for('statements'))
    
    try:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        
        transactions = get_statement_transactions(uid, start_date, end_date)
        summary = calculate_statement_summary(transactions)
        
        if not PDF_AVAILABLE:
            flash('PDF generation is not available. Please install reportlab: pip install reportlab')
            return redirect(url_for('statements'))
        
        pdf_buffer = generate_pdf_statement(user, transactions, summary, start_date_str, end_date_str)
        
        filename = f'statement_{user["id"]}_{start_date_str}_{end_date_str}.pdf'
        return send_file(
            pdf_buffer,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=filename
        )
    except Exception as e:
        flash(f'Error generating PDF: {str(e)}')
        return redirect(url_for('statements'))

@app.route('/statements/email', methods=['POST'])
def email_statement():
    """Email account statement to user."""
    if 'user_id' not in session or session['user_id'] == "admin":
        return redirect(url_for('home'))
    
    uid = session['user_id']
    user = user_by_id(uid)
    if not user:
        return redirect(url_for('home'))
    
    start_date_str = request.form.get('start_date', '')
    end_date_str = request.form.get('end_date', '')
    
    if not start_date_str or not end_date_str:
        flash('Please select a date range.')
        return redirect(url_for('statements'))
    
    if not user.get('email'):
        flash('Email address not found in your profile. Please update your profile.')
        return redirect(url_for('statements'))
    
    try:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        
        transactions = get_statement_transactions(uid, start_date, end_date)
        summary = calculate_statement_summary(transactions)
        
        if not PDF_AVAILABLE:
            flash('PDF generation is not available. Please install reportlab: pip install reportlab')
            return redirect(url_for('statements'))
        
        if not MAIL_AVAILABLE:
            flash('Email functionality is not available. Please install flask-mail: pip install flask-mail')
            return redirect(url_for('statements'))
        
        pdf_buffer = generate_pdf_statement(user, transactions, summary, start_date_str, end_date_str)
        
        if send_statement_email(user, pdf_buffer, start_date_str, end_date_str):
            flash(f'Statement sent successfully to {user.get("email")}!')
        else:
            flash('Error sending email. Please check email configuration.')
    except Exception as e:
        flash(f'Error sending statement: {str(e)}')
    
    return redirect(url_for('statements'))

@app.route('/statements/print', methods=['GET'])
def print_statement():
    """Print-friendly version of statement."""
    if 'user_id' not in session or session['user_id'] == "admin":
        return redirect(url_for('home'))
    
    uid = session['user_id']
    user = user_by_id(uid)
    if not user:
        return redirect(url_for('home'))
    
    start_date_str = request.args.get('start_date', '')
    end_date_str = request.args.get('end_date', '')
    
    if not start_date_str or not end_date_str:
        flash('Please select a date range.')
        return redirect(url_for('statements'))
    
    try:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        
        transactions = get_statement_transactions(uid, start_date, end_date)
        summary = calculate_statement_summary(transactions)
        
        return render_template('statement_print.html',
                             user=user,
                             transactions=transactions,
                             summary=summary,
                             start_date=start_date,
                             end_date=end_date)
    except Exception as e:
        flash(f'Error loading statement: {str(e)}')
        return redirect(url_for('statements'))

# -------- Admin panel --------
@app.route('/admin', methods=['GET', 'POST'])
def admin_panel():
    if not session.get('is_admin'):
        return redirect(url_for('home'))

    if request.method == 'POST':
        action = request.form.get('action')
        loan_id = request.form.get('loan_id')  # expect templates to send loan_id
        if loan_id and loan_id.isdigit():
            loan_id = int(loan_id)
            ln = loan_by_id(loan_id)
            if not ln or ln['status'] != 'pending':
                flash('Invalid or already processed loan.')
            else:
                if action == 'approve':
                    update_loan_status(loan_id, 'approved')
                    record_tx_and_update_balance(ln['user_id'], 'loan_credited', float(ln['amount']), note='loan approved')
                    flash('Loan approved and amount credited.')
                elif action == 'reject':
                    update_loan_status(loan_id, 'rejected')
                    flash('Loan rejected.')

    # Gather dashboard metrics
    conn = get_conn(); cur = conn.cursor(dictionary=True)
    cur.execute("SELECT id as user_id, username, email, is_admin, balance FROM users")
    users_table = cur.fetchall()
    cur.close(); conn.close()

    loans_view = list_loans()
    non_admin_users = [u for u in users_table if not u['is_admin']]
    total_users = len(non_admin_users)
    total_admins = len([u for u in users_table if u['is_admin']])
    pending_loans = len([l for l in loans_view if l['status'] == 'pending'])
    approved_loans = len([l for l in loans_view if l['status'] == 'approved'])
    total_user_balance = sum(float(u['balance']) for u in non_admin_users)

    sorted_users = sorted(non_admin_users, key=lambda u: float(u['balance']), reverse=True)[:8]
    chart_labels = [u['username'] for u in sorted_users]
    chart_values = [float(u['balance']) for u in sorted_users]

    return render_template(
        'admin.html',
        loans=loans_view,
        users={u['user_id']: u for u in users_table},   # keeps your template flexible
        users_table=users_table,
        total_users=total_users,
        total_admins=total_admins,
        pending_loans=pending_loans,
        approved_loans=approved_loans,
        total_user_balance=total_user_balance,
        chart_labels=chart_labels,
        chart_values=chart_values,
    )

# -------- History --------
@app.route('/history')
def txn_history():
    if 'user_id' not in session or session['user_id'] == "admin":
        return redirect(url_for('home'))
    uid = session['user_id']
    conn = get_conn(); cur = conn.cursor(dictionary=True)
    cur.execute("""
      SELECT type AS action, amount, note, created_at AS timestamp
      FROM transactions WHERE user_id=%s ORDER BY created_at DESC
    """, (uid,))
    user_txns = cur.fetchall()
    cur.close(); conn.close()
    return render_template('history.html', transactions=user_txns)

# -------- Analytics --------
@app.route('/analytics')
def analytics():
    if 'user_id' not in session:
        return redirect(url_for('home'))
    uid = session['user_id']

    conn = get_conn(); cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT type AS action, amount, created_at AS ts
        FROM transactions WHERE user_id=%s ORDER BY created_at ASC
    """, (uid,))
    rows = cur.fetchall()
    cur.close(); conn.close()

    # totals by action
    from collections import defaultdict
    totals = defaultdict(float)
    for r in rows:
        totals[r['action']] += float(r['amount'])

    # daily/monthly balances
    running = 0.0
    daily_map, monthly_map = {}, {}
    for r in rows:
        a = r['action']; amt = float(r['amount'])
        if a in ('credit','add_funds','loan_credited'):
            running += amt
        elif a == 'debit':
            running -= amt
        d = r['ts'].strftime('%Y-%m-%d'); m = r['ts'].strftime('%Y-%m')
        daily_map[d] = running; monthly_map[m] = running

    balance_daily = [{'date': d, 'balance': daily_map[d]} for d in sorted(daily_map)]
    balance_monthly = [{'date': m, 'balance': monthly_map[m]} for m in sorted(monthly_map)]

    labels = list(totals.keys())
    values = [totals[k] for k in labels]

    return render_template('analytics.html',
                           labels=labels, values=values,
                           balance_daily=balance_daily,
                           balance_monthly=balance_monthly)

# -------- Admin: per-user detail analytics --------
@app.route('/admin/user/<username>')
def admin_user_detail(username):
    if not session.get('is_admin'):
        return redirect(url_for('home'))
    u = user_by_username(username)
    if not u:
        flash('User not found'); return redirect(url_for('admin_panel'))

    uid = u['id']
    conn = get_conn(); cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT type AS action, amount FROM transactions WHERE user_id=%s
    """, (uid,))
    rows = cur.fetchall()
    cur.close(); conn.close()

    from collections import defaultdict
    totals = defaultdict(float)
    for r in rows:
        totals[r['action']] += float(r['amount'])
    labels = list(totals.keys()); values = [totals[k] for k in labels]

    return render_template('admin_user_detail.html', user=u, user_id=uid, labels=labels, values=values)

# -------- Admin: delete user --------
@app.route('/delete_user', methods=['POST'])
def delete_user():
    if not session.get('is_admin'):
        return redirect(url_for('home'))

    user_id = request.form.get('user_id')
    username = request.form.get('username')

    if not user_id or user_id == "admin":
        flash('Cannot delete admin account or invalid user.')
        return redirect(url_for('admin_panel'))

    conn = get_conn(); cur = conn.cursor()
    try:
        cur.execute("DELETE FROM recurring_payments WHERE user_id=%s", (user_id,))
        cur.execute("DELETE FROM saved_billers WHERE user_id=%s", (user_id,))
        cur.execute("DELETE FROM bill_payments WHERE user_id=%s", (user_id,))
        cur.execute("DELETE FROM transactions WHERE user_id=%s", (user_id,))
        cur.execute("DELETE FROM loans WHERE user_id=%s", (user_id,))
        cur.execute("DELETE FROM users WHERE id=%s", (user_id,))
        conn.commit()
        flash(f'User "{username}" has been deleted successfully.')
    except Exception as e:
        conn.rollback()
        flash(f'Error: {e}')
    finally:
        cur.close(); conn.close()

    return redirect(url_for('admin_panel'))

# -------- Blockchain Demo (UI) --------
@app.route('/blockchain_demo')
def blockchain_demo():
    if 'user_id' not in session or session['user_id'] == "admin":
        return redirect(url_for('home'))
    # Demo PoW blockchain built from this user's transactions
    DIFFICULTY = 2  # leading zeros

    class Transaction:
        def __init__(self, title, sender, receiver, amount):
            self.title = title
            self.sender = sender
            self.receiver = receiver
            self.amount = amount

    class Block:
        def __init__(self, index, transactions, previous_hash):
            self.index = index
            self.timestamp = datetime.now()
            self.transactions = transactions  # list[Transaction]
            self.previous_hash = previous_hash
            self.nonce = 0
            self.hash = self.calculate_hash()
            self.mine(DIFFICULTY)

        def calculate_hash(self):
            tx_string = '|'.join(f'{t.title}:{t.sender}->{t.receiver}:{t.amount}' for t in self.transactions)
            block_string = f"{self.index}{self.timestamp.timestamp()}{tx_string}{self.previous_hash}{self.nonce}"
            return hashlib.sha256(block_string.encode()).hexdigest()

        def mine(self, difficulty: int):
            prefix = '0' * difficulty
            while not self.hash.startswith(prefix):
                self.nonce += 1
                self.hash = self.calculate_hash()

    # Fetch user and transactions (chronological)
    uid = session['user_id']
    u = user_by_id(uid)
    me = u['username'] if u and u.get('username') else 'ME'
    conn = get_conn(); cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT type AS action, amount, note, created_at AS ts
        FROM transactions
        WHERE user_id=%s
        ORDER BY created_at ASC
    """, (uid,))
    rows = cur.fetchall()
    cur.close(); conn.close()

    chain = []
    # Genesis block with metadata only
    genesis_tx = Transaction("Account Opened", "SYSTEM", me, 0.00)
    genesis = Block(0, [genesis_tx], "0")
    chain.append(genesis)

    # Helpers
    def parse_note_target(note: str, prefix: str) -> str:
        if not note:
            return "UNKNOWN"
        n = note.strip()
        if n.lower().startswith(prefix):
            return n[len(prefix):].strip()
        return "UNKNOWN"

    # Build one-block-per-transaction from app data
    idx = 1
    for r in rows:
        action = r['action']
        amount = float(r['amount'])
        note = (r.get('note') or '').strip()
        ts = r['ts']

        if action == 'debit':
            receiver = parse_note_target(note.lower(), 'transfer to ')
            tx = Transaction("Transfer Out" if 'transfer to' in note.lower() else "Debit",
                             me, receiver if receiver != "UNKNOWN" else "MERCHANT",
                             amount)
        elif action == 'credit':
            sender_name = parse_note_target(note.lower(), 'transfer from ')
            tx = Transaction("Transfer In" if 'transfer from' in note.lower() else "Credit",
                             sender_name if sender_name != "UNKNOWN" else "SYSTEM",
                             me, amount)
        elif action == 'add_funds':
            tx = Transaction("Funds Added", "SYSTEM", me, amount)
        elif action == 'loan_credited':
            tx = Transaction("Loan Credit", "BANK", me, amount)
        else:
            tx = Transaction(action.title(), "SYSTEM", me, amount)

        b = Block(idx, [tx], chain[-1].hash)
        # use the real timestamp for display
        b.timestamp = ts
        chain.append(b)
        idx += 1

    # Prepare render data
    blocks = []
    for b in chain:
        blocks.append({
            'index': b.index,
            'time': b.timestamp.strftime('%d/%m/%Y, %H:%M:%S'),
            'tx_count': len(b.transactions),
            'nonce': b.nonce,
            'previous_hash': b.previous_hash,
            'hash': b.hash,
            'txs': [{
                'title': t.title,
                'from': t.sender,
                'to': t.receiver,
                'amount': t.amount
            } for t in b.transactions]
        })
    status = {
        'length': len(chain),
        'last_hash': chain[-1].hash[:8],
        'difficulty': DIFFICULTY
    }
    # Also flatten txs for a "Transaction History" section
    tx_history = []
    for b in chain:
        for t in b.transactions:
            tx_history.append({
                'title': t.title,
                'from': t.sender,
                'to': t.receiver,
                'amount': t.amount,
                'hash': b.hash[:8],
                'block_index': b.index,
                'date': b.timestamp.strftime('%d/%m/%Y'),
                'is_out': t.sender == me
            })

    # newest first for display
    blocks_sorted = sorted(blocks, key=lambda x: x['index'], reverse=True)
    tx_history_sorted = list(reversed(tx_history))  # earliest first like screenshot
    return render_template('blockchain.html',
                           blocks=blocks_sorted,
                           status=status,
                           tx_history=tx_history_sorted)

# -------------------- MAIN --------------------
if __name__ == '__main__':
    # Initialize bill payment tables on startup
    print("Initializing bill payment tables...")
    init_bill_tables()
    print("Bill payment tables ready!")
    app.run(debug=True)
