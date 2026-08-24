import logging
import secrets
import subprocess
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Application
    APP_NAME: str = "WMS QuickStart"
    APP_VERSION: str = "0.2.0"
    APP_BUILD_SHA: str = ""
    DEBUG: bool = False
    # Dev convenience: create/patch schema at startup via create_all + inline DDL.
    # None = follow DEBUG. Production schema is owned by Alembic (docker-entrypoint.sh
    # runs `alembic upgrade head` before the server starts).
    AUTO_CREATE_SCHEMA: bool | None = None
    # Destructive ops/seed endpoints (/api/v1/maintenance/*). None = follow DEBUG.
    # Production keeps them off; set MAINTENANCE_API_ENABLED=true temporarily for
    # UAT bootstrap/cleanup runs (frontend/scripts/cleanup-production-test-data.mjs).
    MAINTENANCE_API_ENABLED: bool | None = None
    # New tenant registrations require platform-admin approval before login.
    REGISTRATION_APPROVAL_REQUIRED: bool = False
    API_V1_PREFIX: str = "/api/v1"
    APP_BASE_URL: str = "https://app.maxsmartwms.online"
    API_BASE_URL: str = "https://api.maxsmartwms.online"

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://wms:wms@localhost:5432/wms"
    # Per-worker pool. Production runs WEB_CONCURRENCY uvicorn workers, so total
    # connections = workers x (POOL_SIZE + MAX_OVERFLOW). Managed Postgres free
    # tiers cap around ~95 connections — keep headroom for migrations/psql.
    DATABASE_POOL_SIZE: int = 5
    DATABASE_MAX_OVERFLOW: int = 5

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # JWT / Auth
    JWT_SECRET_KEY: str = ""
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 480  # 8 hours for warehouse shifts

    # S3
    S3_BUCKET: str = "wms-quickstart-dev"
    S3_REGION: str = "us-east-1"

    # Shipping (EasyPost — unified UPS/FedEx/USPS)
    EASYPOST_API_KEY: str = ""  # sign up at easypost.com

    # Stripe
    STRIPE_SECRET_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""

    # Email
    EMAIL_PROVIDER: str = "auto"
    EMAIL_VERIFICATION_REQUIRED: bool = False
    EMAIL_FROM_EMAIL: str = ""
    RESEND_API_KEY: str = ""
    RESEND_FROM_EMAIL: str = ""
    BREVO_API_KEY: str = ""
    BREVO_FROM_EMAIL: str = ""
    SMTP2GO_API_KEY: str = ""
    SMTP2GO_FROM_EMAIL: str = ""
    MAILERSEND_API_KEY: str = ""
    MAILERSEND_FROM_EMAIL: str = ""
    POSTMARK_SERVER_TOKEN: str = ""
    POSTMARK_FROM_EMAIL: str = ""
    POSTMARK_MESSAGE_STREAM: str = "outbound"
    SENDGRID_API_KEY: str = ""
    SENDGRID_FROM_EMAIL: str = ""
    MAILGUN_API_KEY: str = ""
    MAILGUN_DOMAIN: str = ""
    MAILGUN_FROM_EMAIL: str = ""
    MAILGUN_API_BASE_URL: str = "https://api.mailgun.net"
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""  # Gmail App Password (16 chars)
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 465
    SMTP_FROM_EMAIL: str = ""

    # External agent team
    MINIMAX_API_KEY: str = ""
    MINIMAX_BASE_URL: str = "https://api.minimaxi.com/v1"
    MINIMAX_MODEL: str = "MiniMax-M1"
    QWEN_API_KEY: str = ""
    QWEN_BASE_URL: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    QWEN_MODEL: str = "qwen-max"
    KIMI_API_KEY: str = ""
    KIMI_BASE_URL: str = "https://api.moonshot.cn/v1"
    KIMI_MODEL: str = "moonshot-v1-8k"
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com"
    DEEPSEEK_MODEL: str = "deepseek-v4-flash"
    DEEPSEEK_WEB_SEARCH_ENABLED: bool = False
    WEB_SEARCH_PROVIDER: str = "tavily"
    WEB_SEARCH_MAX_RESULTS: int = 5
    TAVILY_API_KEY: str = ""
    TAVILY_BASE_URL: str = "https://api.tavily.com"

    # Deployment metadata
    RENDER_GIT_COMMIT: str = ""
    RENDER_GIT_BRANCH: str = ""
    RENDER_SERVICE_ID: str = ""

    # CORS
    CORS_ORIGINS: list[str] = [
        "http://localhost:5173",
        "http://localhost:3000",
        "https://app.maxsmartwms.online",
        "https://maxsmartwms.online",
        "capacitor://localhost",
        "ionic://localhost",
    ]


settings = Settings()


def _read_git_value(*args: str) -> str:
    try:
        repo_root = Path(__file__).resolve().parents[3]
        result = subprocess.run(
            ["git", *args],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
            timeout=2,
        )
        return result.stdout.strip()
    except Exception:
        return ""


if not settings.APP_BUILD_SHA:
    settings.APP_BUILD_SHA = _read_git_value("rev-parse", "--short", "HEAD")

if not settings.RENDER_GIT_BRANCH:
    settings.RENDER_GIT_BRANCH = _read_git_value("rev-parse", "--abbrev-ref", "HEAD")

# ─── Security enforcement ───
_INSECURE_DEFAULTS = {
    "",
    "CHANGE-ME-IN-PRODUCTION",
    "changeme",
    "secret",
    "dev-secret-change-in-production",
}

if settings.JWT_SECRET_KEY in _INSECURE_DEFAULTS:
    if settings.DEBUG:
        # Dev mode: auto-generate a random key and warn
        settings.JWT_SECRET_KEY = secrets.token_urlsafe(32)
        logging.warning(
            "JWT_SECRET_KEY not configured — using auto-generated random key. "
            "Sessions will not survive restarts. Set JWT_SECRET_KEY in .env for production."
        )
    else:
        # Production: refuse to start
        raise RuntimeError(
            "FATAL: JWT_SECRET_KEY is not set or has an insecure default value. "
            "Set a strong random JWT_SECRET_KEY in your environment before deploying. "
            'Generate one with: python -c "import secrets; print(secrets.token_urlsafe(32))"'
        )
