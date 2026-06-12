"""Transactional email via Resend."""
import logging

import httpx

import config

logger = logging.getLogger(__name__)

RESEND_ENDPOINT = "https://api.resend.com/emails"


async def send_magic_link(to_email: str, link: str) -> bool:
    """Send a magic-login link. Returns True on success.

    If RESEND_API_KEY is unset (e.g. local dev), logs the link instead of
    sending so the flow is still testable.
    """
    if not config.RESEND_API_KEY:
        logger.warning("RESEND_API_KEY unset — magic link for %s: %s", to_email, link)
        return True

    html = f"""\
<div style="font-family:system-ui,sans-serif;max-width:480px;margin:auto">
  <h2>Sign in to Album Ranker</h2>
  <p>Click the button below to sign in. This link expires in
     {config.MAGIC_LINK_TTL_MIN} minutes and can be used once.</p>
  <p><a href="{link}"
        style="display:inline-block;padding:12px 20px;background:#1DB954;
               color:#fff;text-decoration:none;border-radius:8px">
     Sign in</a></p>
  <p style="color:#666;font-size:13px">Or paste this link into your browser:<br>
     <a href="{link}" style="color:#1DB954;word-break:break-all">{link}</a></p>
  <p style="color:#666;font-size:13px">If you didn't request this, ignore this email.</p>
</div>"""

    payload = {
        "from": config.MAIL_FROM,
        "to": [to_email],
        "subject": "Your Album Ranker sign-in link",
        "html": html,
    }
    headers = {"Authorization": f"Bearer {config.RESEND_API_KEY}"}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(RESEND_ENDPOINT, json=payload, headers=headers)
        if r.status_code >= 400:
            logger.error("Resend send failed %s: %s", r.status_code, r.text)
            return False
        return True
    except httpx.HTTPError as e:
        logger.error("Resend request error: %s", e)
        return False
