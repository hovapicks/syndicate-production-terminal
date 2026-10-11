import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import requests

def send_telegram_alert(bot_token: str, chat_id: str, message: str) -> bool:
    """Dispatches a formatted Markdown alert directly to Telegram."""
    if not bot_token or not chat_id:
        print("[Notifier] Telegram credentials missing, skipping dispatch.")
        return False
        
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown"
    }
    try:
        res = requests.post(url, json=payload, timeout=8)
        res.raise_for_status()
        return True
    except Exception as e:
        print(f"[Notifier] Telegram dispatch failed: {e}")
        return False

def send_email_dossier(sender: str, app_password: str, recipient: str, subject: str, html_body: str) -> bool:
    """Dispatches the daily executive HTML dossier via Gmail SMTP."""
    if not sender or not app_password or not recipient:
        print("[Notifier] Email credentials missing, skipping dispatch.")
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = recipient

    part = MIMEText(html_body, "html")
    msg.attach(part)

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(sender, app_password)
            server.sendmail(sender, recipient, msg.as_string())
        return True
    except Exception as e:
        print(f"[Notifier] Email dispatch failed: {e}")
        return False
