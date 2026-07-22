import secrets
from dataclasses import dataclass
from fastapi import HTTPException, Security, status
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


async def verify_admin_key(admin_key: str = Security(admin_key_header)) -> ClientIdentity:
    """
    Validate the X-Admin-Key header for privileged administration operations.
    """
    if not admin_key or not secrets.compare_digest(admin_key, settings.ADMIN_API_KEY):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Invalid or missing administrator credentials.",
            headers={"WWW-Authenticate": settings.ADMIN_API_KEY_HEADER_NAME},
        )

    return ClientIdentity(api_key=admin_key, tier="internal", is_admin=True)

