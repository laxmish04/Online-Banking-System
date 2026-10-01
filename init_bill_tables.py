#!/usr/bin/env python3
"""
Script to initialize bill payment tables in the database.
Run this script if you encounter database errors with bill payments.
"""

import mysql.connector
from mysql.connector import pooling

# Database configuration - update these to match your app.py settings
DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': 'root',
    'database': 'online_banking'
}

def init_bill_tables():
    """Initialize bill payment tables."""
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cur = conn.cursor()
        
        print("Creating bill payment tables...")
        
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
        print("✓ Created saved_billers table")
        
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
        print("✓ Created bill_payments table")
        
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
        print("✓ Created recurring_payments table")
        
        conn.commit()
        print("\n✅ All bill payment tables created successfully!")
        return True
        
    except mysql.connector.Error as e:
        print(f"\n❌ Error: {e}")
        if conn:
            conn.rollback()
        return False
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        return False
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()

if __name__ == '__main__':
    print("=" * 50)
    print("Bill Payment Tables Initialization Script")
    print("=" * 50)
    print(f"\nConnecting to database: {DB_CONFIG['database']}")
    print("Make sure to update DB_CONFIG in this script if your credentials differ.\n")
    
    if init_bill_tables():
        print("\nYou can now use the bill payments feature!")
    else:
        print("\nFailed to create tables. Please check:")
        print("1. Database credentials are correct")
        print("2. Database 'online_banking' exists")
        print("3. 'users' table exists")
        print("4. You have proper permissions")

