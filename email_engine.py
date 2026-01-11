import imaplib
import smtplib
import email
from email.header import decode_header
from email.mime.text import MIMEText
import logging
import os

logger = logging.getLogger(__name__)

# ==========================================
# CONFIGURATION
# ==========================================
# Placeholder: To be filled by User
EMAIL_USER = os.getenv("JARVIS_EMAIL_USER", "")
EMAIL_PASS = os.getenv("JARVIS_EMAIL_PASS", "")

IMAP_SERVER = "imap.gmail.com"
SMTP_SERVER = "smtp.gmail.com"

# ==========================================
# READ EMAILS (IMAP)
# ==========================================
def fetch_unread_emails(limit=5):
    """Fetches top N unread emails."""
    if not EMAIL_USER or not EMAIL_PASS:
        return ["⚠️ Email credentials not configured."]
        
    try:
        # Connect
        mail = imaplib.IMAP4_SSL(IMAP_SERVER)
        mail.login(EMAIL_USER, EMAIL_PASS)
        mail.select("inbox")
        
        # Search Unread
        status, messages = mail.search(None, "UNSEEN")
        if status != "OK": return ["No unread emails."]
        
        email_ids = messages[0].split()
        if not email_ids: return ["You're all caught up! No unread mails."]
        
        latest_ids = email_ids[-limit:]
        summaries = []
        
        for e_id in reversed(latest_ids):
            _, msg_data = mail.fetch(e_id, "(RFC822)")
            for response_part in msg_data:
                if isinstance(response_part, tuple):
                    msg = email.message_from_bytes(response_part[1])
                    
                    # Subject
                    subject, encoding = decode_header(msg["Subject"])[0]
                    if isinstance(subject, bytes):
                        subject = subject.decode(encoding if encoding else "utf-8")
                        
                    # Sender
                    sender = msg.get("From")
                    
                    summaries.append(f"📩 **{sender}**: {subject}")
                    
        mail.close()
        mail.logout()
        return summaries
        
    except Exception as e:
        logger.error(f"Email Fetch Error: {e}")
        return [f"❌ Error fetching emails: {str(e)}"]

# ==========================================
# SEND EMAILS (SMTP)
# ==========================================
def send_email(to_email, subject, body):
    """Sends a text email."""
    if not EMAIL_USER or not EMAIL_PASS:
        return False
        
    try:
        msg = MIMEText(body)
        msg['Subject'] = subject
        msg['From'] = EMAIL_USER
        msg['To'] = to_email
        
        with smtplib.SMTP_SSL(SMTP_SERVER, 465) as smtp:
            smtp.login(EMAIL_USER, EMAIL_PASS)
            smtp.send_message(msg)
            
        logger.info(f"📧 Email sent to {to_email}")
        return True
        
    except Exception as e:
        logger.error(f"Email Send Error: {e}")
        return False
