import asyncio
import os

import resend

RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
EMAIL_FROM = os.environ.get("EMAIL_FROM", "Hive <noreply@hive.rllm-project.com>")
APP_URL = os.environ.get("APP_URL", "http://localhost:3000")


async def send_verification_email(to: str, token: str):
    link = f"{APP_URL}/auth/verify?token={token}"
    if not RESEND_API_KEY:
        print(f"[email] RESEND_API_KEY not set. Would send to {to}: {link}")
        return
    resend.api_key = RESEND_API_KEY
    params = {
        "from": EMAIL_FROM,
        "to": [to],
        "subject": "Verify your Hive email",
        "html": (
            f'<p>Click the link below to verify your email:</p>'
            f'<p><a href="{link}">Verify email</a></p>'
            f'<p>This link expires in 24 hours.</p>'
            f'<p style="color:#888;font-size:12px">If you didn\'t create a Hive account, ignore this email.</p>'
        ),
    }
    await asyncio.to_thread(resend.Emails.send, params)
