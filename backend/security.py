"""
Shared authentication dependencies.

`require_user` is the STRICT identity dependency for sensitive routes (integration
credentials, OAuth). Unlike main.get_current_user it never trusts a client-supplied
identity and has no "test-user" fallback in production.
"""
import os
import hmac
from typing import Optional

from fastapi import Header, HTTPException


def require_user(
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
    x_claritty_auth: Optional[str] = Header(None, alias="X-Claritty-Auth"),
) -> str:
    """
    Trusted per-user identity.

    Identity must come from CloudFront Lambda@Edge, which validates the user's JWT
    and injects X-User-Id plus the X-Claritty-Auth admission secret. We re-verify
    X-Claritty-Auth here (defense-in-depth) so a request that bypasses the edge —
    forging X-User-Id — cannot reach credential storage. Fail closed.
    """
    alb_secret = os.getenv("ALB_AUTH_SECRET", "")

    # Production: ALB_AUTH_SECRET is injected → require the edge-stamped header.
    if alb_secret:
        if not x_claritty_auth or not hmac.compare_digest(x_claritty_auth, alb_secret):
            raise HTTPException(
                status_code=403,
                detail="Request did not originate from the Claritty edge.",
            )
        if not x_user_id:
            raise HTTPException(status_code=401, detail="Authentication required.")
        return x_user_id

    # Local development only (no ALB secret AND explicitly non-production).
    if os.getenv("NODE_ENV", "").lower() in ("development", "dev", "local"):
        return x_user_id or "dev-user"

    # No edge secret and not dev → refuse rather than guess identity.
    raise HTTPException(status_code=401, detail="Authentication required.")
