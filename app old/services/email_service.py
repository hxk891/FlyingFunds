"""
Email service — Gmail SMTP by default.

Required environment variables:
    EMAIL_USER      your Gmail address          e.g. you@gmail.com
    EMAIL_PASSWORD  your Gmail App Password     (16-char, no spaces)
    APP_BASE_URL    base URL of your app        e.g. http://localhost:8000

To get a Gmail App Password:
  1. Google Account → Security → 2-Step Verification (must be ON)
  2. Security → App Passwords → Mail → Generate
  3. Copy the 16-char password into EMAIL_PASSWORD
"""

import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

EMAIL_USER     = os.getenv("EMAIL_USER", "")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD", "")
APP_BASE_URL   = os.getenv("APP_BASE_URL", "http://localhost:8000")

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587


def _send(to: str, subject: str, html: str) -> None:
    """Low-level send. Raises on failure."""
    if not EMAIL_USER or not EMAIL_PASSWORD:
        # Dev fallback — just print so the app doesn't crash
        print(f"\n[EMAIL DISABLED — set EMAIL_USER + EMAIL_PASSWORD]\nTo: {to}\nSubject: {subject}\n{html}\n")
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = f"FlyingFunds <{EMAIL_USER}>"
    msg["To"]      = to
    msg.attach(MIMEText(html, "html"))

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.ehlo()
        server.starttls()
        server.login(EMAIL_USER, EMAIL_PASSWORD)
        server.sendmail(EMAIL_USER, to, msg.as_string())


def send_password_reset(to: str, token: str) -> None:
    reset_url = f"{APP_BASE_URL}/reset-password?token={token}"
    html = f"""
    <div style="font-family:system-ui,sans-serif;max-width:480px;margin:0 auto;padding:32px;">
      <h2 style="font-size:22px;color:#0a0a0a;margin-bottom:8px;">Reset your password</h2>
      <p style="color:#555;font-size:15px;margin-bottom:24px;">
        We received a request to reset the password for your FlyingFunds account.
        Click the button below to choose a new password.
      </p>
      <a href="{reset_url}"
         style="display:inline-block;background:#0a0a0a;color:#fff;padding:12px 24px;
                border-radius:9px;text-decoration:none;font-size:15px;font-weight:600;">
        Reset password
      </a>
      <p style="color:#888;font-size:13px;margin-top:24px;">
        This link expires in <strong>1 hour</strong>. If you didn't request this, you can safely ignore this email.
      </p>
      <hr style="border:none;border-top:1px solid #eee;margin:24px 0;" />
      <p style="color:#bbb;font-size:12px;">FlyingFunds · your portfolio, your data</p>
    </div>
    """
    _send(to, "Reset your FlyingFunds password", html)


def send_welcome(to: str, username: str) -> None:
    html = f"""
    <div style="font-family:system-ui,sans-serif;max-width:480px;margin:0 auto;padding:32px;">
      <h2 style="font-size:22px;color:#0a0a0a;margin-bottom:8px;">Welcome to FlyingFunds, {username or 'there'} 👋</h2>
      <p style="color:#555;font-size:15px;">
        Your account is all set. Head to your dashboard to start tracking your portfolio.
      </p>
      <a href="{APP_BASE_URL}/dashboard"
         style="display:inline-block;background:#0a0a0a;color:#fff;padding:12px 24px;
                border-radius:9px;text-decoration:none;font-size:15px;font-weight:600;margin-top:16px;">
        Go to dashboard
      </a>
    </div>
    """
    _send(to, "Welcome to FlyingFunds", html)