# Bill Payments Feature - Setup Instructions

## Database Setup

Before using the Bill Payments feature, you need to create the required database tables. Run the SQL commands in `database_schema_bills.sql` in your MySQL database.

### Steps:

1. Open your MySQL client (MySQL Workbench, phpMyAdmin, or command line)
2. Connect to your `online_banking` database
3. Run the SQL commands from `database_schema_bills.sql`

Or run this command:
```bash
mysql -u root -p online_banking < database_schema_bills.sql
```

## Features Included

### 1. **Pay Bills**
   - Pay utilities (electricity, water, phone, internet, gas, insurance)
   - Select from predefined billers or enter custom details
   - Instant payment processing
   - Payment confirmation and receipt

### 2. **Save Billers**
   - Save frequently used billers with account numbers
   - Add nicknames for easy identification
   - Quick access for future payments

### 3. **Recurring Payments**
   - Schedule automatic bill payments
   - Set frequency (weekly, monthly, quarterly, yearly)
   - Enable/disable scheduled payments
   - View all scheduled payments

### 4. **Payment History**
   - Complete history of all bill payments
   - Filter by date, category, or biller
   - View payment details and receipts

## Usage

1. **Access Bill Payments**: Click "Pay Bills" from the dashboard or navigate to `/bills`

2. **Pay a Bill**:
   - Click "Pay Bill" button
   - Select category (electricity, water, phone, etc.)
   - Choose biller from the list
   - Enter account number and amount
   - Confirm payment

3. **Save a Biller**:
   - Click "Add Biller"
   - Fill in biller details
   - Add a nickname (optional)
   - Save for quick access

4. **Schedule Recurring Payment**:
   - Go to "Recurring Payments"
   - Select a saved biller
   - Set amount, frequency, and next payment date
   - Enable/disable as needed

5. **View History**:
   - Click "History" to see all past payments
   - View payment details and dates

## Available Bill Categories

- **Electricity**: State Electricity Board, Power Grid Corporation, Green Energy Co
- **Water**: Municipal Water Supply, Water Works Department, Aqua Services
- **Phone**: Airtel, Jio, Vodafone, BSNL
- **Internet**: Broadband Services, FiberNet
- **Gas**: Gas Supply Co, LPG Services
- **Insurance**: Life Insurance Corp, Health Insurance Co

## Notes

- All bill payments are processed immediately
- Payments are recorded in both the transactions table and bill_payments table
- Recurring payments need to be processed manually (scheduler logic can be added later)
- Bill payments appear in the main transaction history as well

## Future Enhancements

- Automatic processing of recurring payments (cron job/scheduler)
- Email notifications for scheduled payments
- Bill reminders before due dates
- Payment receipts in PDF format
- Integration with real biller APIs

