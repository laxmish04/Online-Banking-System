-- Database schema for Bill Payments feature
-- Run these SQL commands in your MySQL database

-- Table for saving billers
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
);

-- Table for bill payment history
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
);

-- Table for recurring payments
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
);

