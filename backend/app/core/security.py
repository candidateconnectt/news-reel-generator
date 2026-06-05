"""HMAC verification for Make.com → FastAPI webhooks."""
from __future__ import annotations

import hmac

from fastapi import HTTPException, Request, status

from app.config import settings


async def verify_webhook_secret(request: Request) -> None:
    """Verify X-Webhook-Secret header against the configured secret.

    In dev, if no secret is set, this is a no-op (with a warning logged at startup).
    In production, this MUST be configured.
    """
    expected = settings.make_com_callback_secret
    if not expected or expected.startswith("change-me"):
        # Dev mode: secret not configured. Accept the request but the user should know.
        return

    provided = request.headers.get("X-Webhook-Secret", "")
    if not hmac.compare_digest(provided, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook secret",
        )
