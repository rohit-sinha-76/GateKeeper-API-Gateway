from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "GateKeeper API Gateway"
    API_V1_STR: str = "/api/v1"
    DEBUG: bool = False
    ENV: str = "development"

    # Redis Configuration
    REDIS_URL: str = "redis://localhost:6379/0"

    # Security & Authentication
    API_KEY_HEADER_NAME: str = "X-API-Key"

    # Rate Limiting (Sliding Window)
    RATE_LIMIT_WINDOW_SECONDS: int = 60
    RATE_LIMIT_MAX_REQUESTS: int = 100

    # Gateway/Proxy Settings
    GATEWAY_TIMEOUT_SECONDS: float = 10.0
    UPSTREAM_URL: str = "http://localhost:8001"

    # Security Headers & Middleware
    CORS_ORIGINS: list[str] = ["*"]
    ALLOWED_HOSTS: list[str] = ["*"]
    RATE_LIMIT_WHITELIST_IPS: list[str] = ["127.0.0.1", "::1"]

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


settings = Settings()
