from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

load_dotenv()


class Config(BaseSettings):
    PORT: int = 8000

    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/simustratum"
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 10

    # Aurora PostgreSQL IAM auth — when DB_HOST is set, the engine authenticates
    # with a short-lived IAM token instead of DATABASE_URL's static password.
    # Leave DB_HOST blank (the default) to keep using DATABASE_URL as-is.
    DB_HOST: Optional[str] = None
    AWS_REGION: Optional[str] = None
    DB_USERNAME: str = "postgres"
    DB_NAME: str = "postgres"
    DB_PORT: int = 5432

    ALLOWED_ORIGINS: Optional[str] = None

    JWT_SECRET_KEY: str = ""
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_EXPIRE_MINUTES: int = 15
    JWT_REFRESH_EXPIRE_DAYS: int = 30

    GOOGLE_CLIENT_ID: Optional[str] = None

    ANTHROPIC_API_KEY: str = ""
    GEMINI_API_KEY: str = ""

    QDRANT_URL: str = "http://localhost:6333"
    QDRANT_API_KEY: Optional[str] = None
    QDRANT_COLLECTION: str = "session_documents"

    CLOUDINARY_URL: Optional[str] = None

    DOCS_AUTH_USERNAME: Optional[str] = None
    DOCS_AUTH_PASSWORD: Optional[str] = None

    # Password reset
    PASSWORD_RESET_TOKEN_EXPIRE_MINUTES: int = 30
    # Fallback base URL for the reset link, only used when a request carries
    # neither an Origin nor a Referer header (e.g. a non-browser client).
    FRONTEND_URL: Optional[str] = None

    # Stripe billing
    STRIPE_SECRET_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""
    STRIPE_PRICE_ID_NGN: str = ""
    STRIPE_PRICE_ID_USD: str = ""

    # Outbound email (fastapi-mail / SMTP)
    MAIL_USERNAME: Optional[str] = None
    MAIL_PASSWORD: Optional[str] = None
    MAIL_FROM: str = "no-reply@simustratum.app"
    MAIL_FROM_NAME: str = "Simustratum"
    MAIL_PORT: int = 587
    MAIL_SERVER: Optional[str] = None
    MAIL_STARTTLS: bool = True
    MAIL_SSL_TLS: bool = False
    MAIL_USE_CREDENTIALS: bool = True
    MAIL_VALIDATE_CERTS: bool = True

    model_config = SettingsConfigDict(
        env_file=".env", case_sensitive=True, env_file_encoding="utf-8"
    )


config = Config()
