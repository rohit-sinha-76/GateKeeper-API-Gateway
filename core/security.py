import hmac
import hashlib
import time
import secrets
from dataclasses import dataclass
from fastapi import HTTPException, Security, status, Request
from fastapi.security.api_key import APIKeyHeader
from core.config import settings

@dataclass(frozen=True)
class ClientIdentity:
    api_key: str
    tier: str
    is_admin: bool = False


# Registered client API keys mapping: key -> tier
REGISTERED_API_KEYS: dict[str, str] = {
    "free-key-abc123": "free",
    "premium-key-xyz789": "premium",
    "internal-key-ops001": "internal",
}

api_key_header = APIKeyHeader(name=settings.API_KEY_HEADER_NAME, auto_error=False)
admin_key_header = APIKeyHeader(name=settings.ADMIN_API_KEY_HEADER_NAME, auto_error=False)


def create_admin_session_token() -> str:
    """Generate an HMAC-SHA256 signed session token for authenticated browser sessions."""
    timestamp = str(int(time.time()))
    sig = hmac.new(
        settings.ADMIN_API_KEY.encode("utf-8"),
        timestamp.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"{timestamp}.{sig}"


def verify_admin_session_token(token: str, max_age_seconds: int = 86400) -> bool:
    """Verify the authenticity and freshness of an admin session cookie token."""
    try:
        if not token or "." not in token:
            return False
        timestamp_str, sig = token.split(".", 1)
        ts = int(timestamp_str)
        if time.time() - ts > max_age_seconds:
            return False
        expected_sig = hmac.new(
            settings.ADMIN_API_KEY.encode("utf-8"),
            timestamp_str.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return secrets.compare_digest(sig, expected_sig)
    except Exception:
        return False


async def verify_api_key(api_key: str = Security(api_key_header)) -> ClientIdentity:
    """
    Validate the X-API-Key header with constant-time checking and return ClientIdentity.
    """
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing required API key header.",
            headers={"WWW-Authenticate": settings.API_KEY_HEADER_NAME},
        )

    matched_tier: str | None = None
    for registered_key, tier in REGISTERED_API_KEYS.items():
        if secrets.compare_digest(api_key, registered_key):
            matched_tier = tier
            break

    if not matched_tier:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key provided.",
            headers={"WWW-Authenticate": settings.API_KEY_HEADER_NAME},
        )

    return ClientIdentity(api_key=api_key, tier=matched_tier, is_admin=False)


async def verify_admin_key(
    request: Request,
    admin_key: str | None = Security(admin_key_header),
) -> ClientIdentity:
    """
    Validate administrator credentials via either:
    1. Direct X-Admin-Key header (for automated scripts / API / tests)
    2. HttpOnly admin_session cookie (for dashboard browser sessions)
    """
    # 1. Direct header verification
    if admin_key and secrets.compare_digest(admin_key, settings.ADMIN_API_KEY):
        return ClientIdentity(api_key=admin_key, tier="internal", is_admin=True)

    # 2. HttpOnly session cookie verification
    session_cookie = request.cookies.get("admin_session")
    if session_cookie and verify_admin_session_token(session_cookie):
        return ClientIdentity(api_key="session-authenticated", tier="internal", is_admin=True)

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Forbidden: Invalid or missing administrator credentials.",
        headers={"WWW-Authenticate": settings.ADMIN_API_KEY_HEADER_NAME},
    )
