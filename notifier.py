import os
import smtplib
import requests
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

load_dotenv()

def get_secret(key: str, default: str = None) -> str:
    # 1. Environment variable (.env)
    val = os.getenv(key)
    if val:
        return val
    # 2. Streamlit Cloud Secrets fallback
    try:
        import streamlit as st
        return st.secrets.get(key, default)
    except Exception:
        return default

GMAIL_SENDER = get_secret("GMAIL_SENDER")
GMAIL_APP_PASSWORD = get_secret("GMAIL_APP_PASSWORD")
GMAIL_RECIPIENT = get_secret("GMAIL_RECIPIENT")
TELEGRAM_BOT_TOKEN = get_secret("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = get_secret("TELEGRAM_CHAT_ID")

def send_email_alert(subject: str, message: str) -> tuple[bool, str]:
    sender = get_secret("GMAIL_SENDER")
    pwd = get_secret("GMAIL_APP_PASSWORD")
    recipient = get_secret("GMAIL_RECIPIENT")
    if not (sender and pwd and recipient):
        return False, "Gmail environment variables missing"
    
    clean_pwd = pwd.replace(" ", "")
    msg = MIMEMultipart()
    msg["From"] = f"Syndicate Terminal <{sender}>"
    msg["To"] = recipient
    msg["Subject"] = subject
    msg.attach(MIMEText(message, "plain"))
    
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(sender, clean_pwd)
            server.sendmail(sender, recipient, msg.as_string())
        return True, f"Dispatched email to {recipient}"
    except Exception as exc:
        return False, f"Email delivery failed: {exc}"

def send_telegram_alert(message: str) -> tuple[bool, str]:
    token = get_secret("TELEGRAM_BOT_TOKEN")
    chat_id = get_secret("TELEGRAM_CHAT_ID")
    if not (token and chat_id):
        return False, "Telegram token or chat ID not configured"
    
    endpoint = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown"
    }
    try:
        resp = requests.post(endpoint, json=payload, timeout=8)
        if resp.status_code == 200:
            return True, "Dispatched Telegram broadcast"
        return False, f"Telegram API error HTTP {resp.status_code}: {resp.text}"
    except Exception as exc:
        return False, f"Telegram request failed: {exc}"

def dispatch_wager_alert(sport: str, pick: str, book: str, odds: int, stake: float, ev: float = None):
    ev_str = f"\n*Model Edge:* +{ev:.1f}% EV" if ev is not None else ""
    odds_str = f"+{odds}" if odds > 0 else str(odds)
    
    tg_text = (
        f"🎯 *SYNDICATE WAGER LOCKED*\n\n"
        f"*League:* `{sport}`\n"
        f"*Selection:* *{pick}*\n"
        f"*Sportsbook:* {book}\n"
        f"*Locked Price:* `{odds_str}`\n"
        f"*Allocated Stake:* `{stake:.2f}u`"
        f"{ev_str}\n"
        f"*Status:* `PENDING`"
    )
    
    email_subject = f"🎯 [Syndicate Executed] {sport} | {pick} ({odds_str}) for {stake:.2f}u"
    email_body = (
        f"Syndicate Execution Confirmed:\n\n"
        f"Sport / League: {sport}\n"
        f"Selection: {pick}\n"
        f"Sportsbook: {book}\n"
        f"Locked Odds: {odds_str}\n"
        f"Staked Allocation: {stake:.2f} units\n"
        f"Status: PENDING\n"
    )
    
    e_ok, e_msg = send_email_alert(email_subject, email_body)
    t_ok, t_msg = send_telegram_alert(tg_text)
    
    return {"email": (e_ok, e_msg), "telegram": (t_ok, t_msg)}
