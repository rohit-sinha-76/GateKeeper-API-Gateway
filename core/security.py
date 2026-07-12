from fastapi import HTTPException, Security
from fastapi.security.api_key import APIKeyHeader
from core.config import settings

# Simple in-memory API key store: key -> tier
API_KEYS: dict[str, str] = {
    "free-key-abc123": "free",
    "premium-key-xyz789": "premium",
}

api_key_header = APIKeyHeader(name=settings.API_KEY_HEADER_NAME, auto_error=False)


async def verify_api_key(api_key: str = Security(api_key_header)) -> str:
    """Validate the X-API-Key header. Returns the tier on success."""
    if not api_key or api_key not in API_KEYS:
        raise HTTPException(status_code=401, detail="Invalid or missing API key.")
    return API_KEYS[api_key]
