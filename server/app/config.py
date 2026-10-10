"""Application configuration using Pydantic Settings."""

from functools import lru_cache
from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Application settings with environment variable support."""

    model_config = SettingsConfigDict(
        env_file=(str(BASE_DIR / ".env"), ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    MONGODB_URI: str = Field(
        default="mongodb://127.0.0.1:27017",
        description="MongoDB connection string URI",
    )
    DATABASE_NAME: str = Field(
        default="devmemory",
        description="MongoDB database name",
    )
    API_HOST: str = Field(
        default="127.0.0.1",
        description="Host to bind the API server",
    )
    API_PORT: int = Field(
        default=8000,
        description="Port to bind the API server",
    )
    FRONTEND_ORIGIN: str = Field(
        default="http://localhost:5173",
        description="CORS allowed origin for the React dashboard",
    )
    MONGODB_SERVER_SELECTION_TIMEOUT_MS: int = Field(
        default=2000,
        description="Server selection timeout for MongoDB in milliseconds",
    )


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings instance."""
    return Settings()
