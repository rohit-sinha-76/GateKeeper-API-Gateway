from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "GateKeeper API Gateway"
    DEBUG: bool = False
    ENV: str = "development"

    # Redis Configuration
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_SOCKET_TIMEOUT: float = 2.0
    REDIS_CONNECT_TIMEOUT: float = 2.0

    # Security & Authentication
    API_KEY_HEADER_NAME: str = "X-API-Key"
    ADMIN_API_KEY_HEADER_NAME: str = "X-Admin-Key"
    ADMIN_API_KEY: str = "admin-secret-gatekeeper-key"

    # Tiered Rate Limiting (Fixed Window with Atomic Redis Lua Script)
    RATE_LIMIT_WINDOW_SECONDS: int = 60
    RATE_LIMIT_DEFAULT_TIER: str = "free"
    RATE_LIMIT_TIERS: dict[str, int] = {
        "free": 60,       # 60 requests / minute
        "premium": 600,   # 600 requests / minute
        "internal": 6000, # 6000 requests / minute
    }

    # Gateway / HTTP Connection Pool Settings
    GATEWAY_TIMEOUT_SECONDS: float = 10.0
    UPSTREAM_URL: str = "http://localhost:8001"
    HTTP_MAX_KEEPALIVE_CONNECTIONS: int = 100
    HTTP_MAX_CONNECTIONS: int = 500
    HTTP_KEEPALIVE_EXPIRY_SECONDS: float = 30.0

    # Circuit Breaker Settings
    CIRCUIT_BREAKER_FAILURE_THRESHOLD: int = 5
    CIRCUIT_BREAKER_RECOVERY_SECONDS: int = 15
    CIRCUIT_BREAKER_WINDOW_SECONDS: int = 30

    # Security Headers & Middleware
    CORS_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:8000"]
    ALLOWED_HOSTS: list[str] = ["localhost", "127.0.0.1", "test", "*"]
    RATE_LIMIT_WHITELIST_IPS: list[str] = ["127.0.0.1", "::1"]

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


settings = Settings()
