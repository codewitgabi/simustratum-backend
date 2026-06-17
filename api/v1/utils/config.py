from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

load_dotenv()


class Config(BaseSettings):
    PORT: int = 8000

    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/simustratum"
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 10

    ALLOWED_ORIGINS: Optional[str] = None

    JWT_SECRET_KEY: str = ""
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_EXPIRE_MINUTES: int = 15
    JWT_REFRESH_EXPIRE_DAYS: int = 30

    GOOGLE_CLIENT_ID: Optional[str] = None

    ANTHROPIC_API_KEY: str = ""
    GEMINI_API_KEY: str = ""

    DOCS_AUTH_USERNAME: Optional[str] = None
    DOCS_AUTH_PASSWORD: Optional[str] = None

    model_config = SettingsConfigDict(
        env_file=".env", case_sensitive=True, env_file_encoding="utf-8"
    )


config = Config()
