"""
alerts.py — Email notifications (optional)

Set ALERT_EMAIL, ALERT_EMAIL_PASSWORD, NOTIFY_EMAIL in .env to enable.
"""

import os
import smtplib
import traceback
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

SMTP_HOST          = "smtp.gmail.com"
SMTP_PORT          = 587
ALERT_EMAIL        = os.getenv("ALERT_EMAIL", "")
ALERT_PASSWORD     = os.getenv("ALERT_EMAIL_PASSWORD", "")
NOTIFY_EMAIL       = os.getenv("NOTIFY_EMAIL", "")


def _send_email(subject: str, body: str):
    if not ALERT_EMAIL or not ALERT_PASSWORD or not NOTIFY_EMAIL:
        return  # Silently skip if not configured
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = ALERT_EMAIL
        msg["To"]      = NOTIFY_EMAIL
        msg.attach(MIMEText(body, "plain"))
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(ALERT_EMAIL, ALERT_PASSWORD)
            server.sendmail(ALERT_EMAIL, NOTIFY_EMAIL, msg.as_string())
        print(f"  ✓ Alert sent to {NOTIFY_EMAIL}")
    except Exception as e:
        print(f"  ⚠ Email alert failed: {e}")


def send_failure_alert(error: Exception, video_id: str = None, step: str = None):
    now     = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    subject = f"Animal Reels Pipeline Failed — {now}"
    body    = f"Time: {now}\nVideo ID: {video_id or 'N/A'}\nError: {str(error)}\n\n{traceback.format_exc()}"
    _send_email(subject, body)


def send_daily_summary(videos_generated: int, videos_posted: int, failures: int, video_titles: list):
    now     = datetime.utcnow().strftime("%Y-%m-%d")
    subject = f"Animal Reels Daily Summary — {now}"
    titles  = "\n".join([f"  - {t}" for t in video_titles]) if video_titles else "  None"
    body    = f"Date: {now}\nGenerated: {videos_generated}\nPosted: {videos_posted}\nFailed: {failures}\n\nVideos:\n{titles}"
    _send_email(subject, body)
