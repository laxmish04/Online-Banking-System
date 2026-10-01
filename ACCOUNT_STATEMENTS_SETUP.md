# Account Statements Feature - Setup Guide

## Overview

The Account Statements feature allows users to:
- Generate account statements for custom date ranges
- Download statements as PDF
- Email statements to their registered email
- Print statements in a print-friendly format

## Installation

### 1. Install Required Packages

```bash
pip install -r requirements.txt
```

Or install individually:
```bash
pip install reportlab flask-mail
```

### 2. Email Configuration (Optional)

To enable email functionality, update the email settings in `app.py`:

```python
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'your_email@gmail.com'
app.config['MAIL_PASSWORD'] = 'your_app_password'
```

**For Gmail:**
- You need to use an "App Password" instead of your regular password
- Go to Google Account → Security → 2-Step Verification → App Passwords
- Generate an app password and use it in `MAIL_PASSWORD`

**For other email providers:**
- Update `MAIL_SERVER` and `MAIL_PORT` accordingly
- Common settings:
  - Outlook: `smtp-mail.outlook.com`, port 587
  - Yahoo: `smtp.mail.yahoo.com`, port 587

### 3. Environment Variables (Recommended)

For better security, use environment variables:

```python
import os
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')
```

Then set them in your environment:
```bash
export MAIL_USERNAME=your_email@gmail.com
export MAIL_PASSWORD=your_app_password
```

## Features

### 1. Generate Statement
- Select start and end date
- View transactions for the selected period
- See summary statistics (opening balance, closing balance, credits, debits)

### 2. Download PDF
- Click "Download PDF" button
- Statement is generated as a professional PDF document
- Includes:
  - Account holder information
  - Statement period
  - Summary statistics
  - Complete transaction list with running balance

### 3. Email Statement
- Click "Email Statement" button
- Statement is sent as PDF attachment to user's registered email
- Email includes a professional message

### 4. Print Statement
- Click "Print Statement" button
- Opens print-friendly version in new window
- Optimized for printing with proper formatting
- Use browser's print dialog (Ctrl+P / Cmd+P)

## Usage

1. **Access Statements**: Click "Statements" from dashboard or navigate to `/statements`

2. **Generate Statement**:
   - Select start date and end date
   - Click "Generate Statement"
   - View transactions and summary

3. **Download PDF**:
   - After generating statement, click "Download PDF"
   - PDF file will be downloaded to your computer

4. **Email Statement**:
   - After generating statement, click "Email Statement"
   - Statement will be sent to your registered email address
   - Make sure your email is configured in the app settings

5. **Print Statement**:
   - After generating statement, click "Print Statement"
   - Print-friendly page opens in new window
   - Use browser print dialog to print

## Notes

- **PDF Generation**: Requires `reportlab` package. If not installed, PDF download will be disabled.
- **Email Functionality**: Requires `flask-mail` package and proper email configuration. If not configured, email feature will be disabled.
- **Print Feature**: Works without any additional packages - uses browser's print functionality.
- **Date Range**: Maximum recommended range is 1 year for best performance.
- **Transactions**: All transactions within the date range are included in the statement.

## Troubleshooting

### PDF Not Generating
- Make sure `reportlab` is installed: `pip install reportlab`
- Check console for error messages
- Verify you have write permissions

### Email Not Sending
- Check email configuration in `app.py`
- Verify SMTP credentials are correct
- For Gmail, use App Password, not regular password
- Check firewall/network settings
- Review console logs for error messages

### Print Not Working
- Use a modern browser (Chrome, Firefox, Edge)
- Check browser print settings
- Ensure pop-ups are allowed for the site

## Future Enhancements

- Monthly/quarterly/yearly statement auto-generation
- Scheduled email statements
- Multiple statement formats (CSV, Excel)
- Statement archiving
- Custom statement templates

