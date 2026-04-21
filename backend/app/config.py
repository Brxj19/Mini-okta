"""Application configuration using Pydantic Settings."""

from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://localhost:5432/idp"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # JWT / RSA Keys
    RSA_PRIVATE_KEY_PATH: str = "secrets/private.pem"
    RSA_PUBLIC_KEY_PATH: str = "secrets/public.pem"
    ISSUER_URL: str = "http://localhost:8000"
    ADMIN_CONSOLE_URL: str = "http://localhost:3000"
    ID_TOKEN_LIFETIME: int = 3600
    ACCESS_TOKEN_LIFETIME: int = 3600
    BROWSER_SSO_TTL_SECONDS: int = 43200

    # Admin seed
    ADMIN_EMAIL: str = "admin@internal.com"
    ADMIN_SECRET: str = "changeme_admin_secret!"

    # SMTP
    SMTP_HOST: str = "localhost"
    SMTP_PORT: int = 1025
    SMTP_USER: str = ""
    SMTP_PASS: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = "noreply@internal.com"
    SMTP_USE_TLS: bool = False
    SMTP_STARTTLS: bool = False
    SMTP_TIMEOUT_SECONDS: int = 30
    EMAIL_MAX_ATTEMPTS: int = 3
    EMAIL_RETRY_BACKOFF_SECONDS: int = 60
    EMAIL_VERIFICATION_OTP_TTL_MINUTES: int = 10

    # Password and onboarding policy
    PASSWORD_MAX_AGE_DAYS: int = 90
    PASSWORD_EXPIRY_GRACE_DAYS: int = 7
    PASSWORD_SETUP_TOKEN_TTL_HOURS: int = 72
    INVITATION_LINK_TTL_HOURS: int = 72

    # Feature flags
    RATE_LIMIT_ENABLED: bool = True
    ACCESS_TOKENS_ENABLED: bool = True
    REFRESH_TOKENS_ENABLED: bool = True

    # Billing / payments
    PAYMENTS_PROVIDER: str = "demo"
    BILLING_CURRENCY: str = "INR"
    SUBSCRIPTION_CYCLE_DAYS: int = 30
    RAZORPAY_KEY_ID: str = ""
    RAZORPAY_KEY_SECRET: str = ""
    SOFT_DELETE_RETENTION_DAYS: int = 90

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": True,
    }


settings = Settings()
