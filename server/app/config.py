import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BASE_DIR.parent

# Load environment variables from .env files into os.environ,
# preserving existing environment variable precedence (override=False).
try:
    from dotenv import load_dotenv

    # 1. Check repository root .env
    load_dotenv(REPO_ROOT / ".env", override=False)
    # 2. Check server/.env
    load_dotenv(BASE_DIR / ".env", override=False)
except ImportError:
    pass


class Settings(BaseSettings):
    """Application settings with environment variable support."""

    model_config = SettingsConfigDict(
        env_file=(
            str(REPO_ROOT / ".env"),
            str(BASE_DIR / ".env"),
            ".env",
        ),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Groq AI Provider Configuration
    GROQ_API_KEY: Optional[str] = Field(
        default=None,
        description="Groq API key for cloud LLM inference",
    )
    GROQ_MODEL: str = Field(
        default="llama-3.3-70b-versatile",
        description="Groq model identifier",
    )
    GROQ_TIMEOUT_SECONDS: float = Field(
        default=30.0,
        description="Timeout in seconds for Groq API requests",
    )
    DEV_MEMORY_DISABLE_EXTERNAL_AI: Optional[str] = Field(
        default=None,
        description="Set to 1/true to disable external AI inference (forces offline mode)",
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
    PERFORMANCE_REGRESSION_PERCENT_THRESHOLD: float = Field(
        default=30.0,
        description="Percentage duration increase above baseline to flag as potential regression",
    )
    PERFORMANCE_REGRESSION_ABS_MS_THRESHOLD: float = Field(
        default=100.0,
        description="Absolute duration increase in ms above baseline to flag as potential regression",
    )
    PERFORMANCE_BASELINE_MIN_SAMPLES: int = Field(
        default=5,
        description="Minimum number of successful observations required to calculate a baseline",
    )

    def model_post_init(self, __context: Any) -> None:
        """Synchronize configuration to os.environ if not already present, preserving precedence."""
        if self.GROQ_API_KEY and not os.getenv("GROQ_API_KEY"):
            os.environ["GROQ_API_KEY"] = self.GROQ_API_KEY
        if self.GROQ_MODEL and not os.getenv("GROQ_MODEL"):
            os.environ["GROQ_MODEL"] = self.GROQ_MODEL
        if self.GROQ_TIMEOUT_SECONDS and not os.getenv("GROQ_TIMEOUT_SECONDS"):
            os.environ["GROQ_TIMEOUT_SECONDS"] = str(self.GROQ_TIMEOUT_SECONDS)


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings instance."""
    return Settings()


def clear_settings_cache() -> None:
    """Clear cached settings instance so next get_settings() reloads."""
    get_settings.cache_clear()
