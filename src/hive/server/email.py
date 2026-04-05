import asyncio
import os

import httpx

RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
EMAIL_FROM = "Hive <noreply@hive.rllm-project.com>"


def _send_sync(to: str, subject: str, body_text: str, body_html: str = ""):
    if not RESEND_API_KEY:
        print(f"[email] RESEND_API_KEY not set. Would send to {to}: {subject}")
        return
    resp = httpx.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {RESEND_API_KEY}"},
        json={
            "from": EMAIL_FROM,
            "to": [to],
            "subject": subject,
            "text": body_text,
            "html": body_html or body_text,
        },
        timeout=15,
    )
    if resp.status_code not in (200, 201):
        raise RuntimeError(f"Resend API error {resp.status_code}: {resp.text}")


async def send_password_reset_code(to: str, code: str):
    subject = f"Your Hive password reset code: {code}"
    body_text = f"Your password reset code is: {code}\n\nThis code expires in 10 minutes. If you didn't request this, ignore this email."
    body_html = (
        f'<p>Your password reset code is:</p>'
        f'<p style="font-size:32px;font-weight:bold;letter-spacing:4px;margin:16px 0">{code}</p>'
        f'<p>This code expires in 10 minutes.</p>'
        f'<p style="color:#888;font-size:12px">If you didn\'t request a password reset, ignore this email.</p>'
    )
    await asyncio.to_thread(_send_sync, to, subject, body_text, body_html)


async def send_verification_code(to: str, code: str):
    subject = f"Your Hive verification code: {code}"
    body_text = f"Your verification code is: {code}\n\nThis code expires in 10 minutes."
    body_html = (
        f'<p>Your verification code is:</p>'
        f'<p style="font-size:32px;font-weight:bold;letter-spacing:4px;margin:16px 0">{code}</p>'
        f'<p>This code expires in 10 minutes.</p>'
        f'<p style="color:#888;font-size:12px">If you didn\'t create a Hive account, ignore this email.</p>'
    )
    await asyncio.to_thread(_send_sync, to, subject, body_text, body_html)
