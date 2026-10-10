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

    # Voyage AI & Embedding Provider Configuration
    VOYAGE_API_KEY: Optional[str] = Field(
        default=None,
        description="Voyage AI API key for dense embedding generation",
    )
    VOYAGE_EMBEDDING_MODEL: str = Field(
        default="voyage-code-4",
        description="Voyage AI embedding model identifier",
    )
    VOYAGE_EMBEDDINGS_URL: str = Field(
        default="https://api.voyageai.com/v1/embeddings",
        description="Voyage AI API endpoint for embeddings",
    )
    # OpenAI & Alternative Embedding Provider Configuration
    OPENAI_API_KEY: Optional[str] = Field(
        default=None,
        description="OpenAI API key for dense embedding generation",
    )
    OPENAI_EMBEDDING_MODEL: str = Field(
        default="text-embedding-3-small",
        description="OpenAI embedding model identifier",
    )
    DEVMEMORY_EMBEDDING_PROVIDER: Optional[str] = Field(
        default="voyage",
        description="Configured embedding provider: voyage, auto, dense, or deterministic",
    )
    DEVMEMORY_VECTOR_DIMENSION: Optional[int] = Field(
        default=None,
        description="Configured vector dimension (1024 for voyage-code-4, 1536 for text-embedding-3-small, 128 for deterministic)",
    )
    MONGODB_VECTOR_FIELD: str = Field(
        default="embedding",
        description="Document field where embedding vector is persisted",
    )

    def model_post_init(self, __context: Any) -> None:
        """Synchronize configuration to os.environ if not already present, preserving precedence."""
        if self.GROQ_API_KEY and not os.getenv("GROQ_API_KEY"):
            os.environ["GROQ_API_KEY"] = self.GROQ_API_KEY
        if self.GROQ_MODEL and not os.getenv("GROQ_MODEL"):
            os.environ["GROQ_MODEL"] = self.GROQ_MODEL
        if self.GROQ_TIMEOUT_SECONDS and not os.getenv("GROQ_TIMEOUT_SECONDS"):
            os.environ["GROQ_TIMEOUT_SECONDS"] = str(self.GROQ_TIMEOUT_SECONDS)
        if self.VOYAGE_API_KEY and not os.getenv("VOYAGE_API_KEY"):
            os.environ["VOYAGE_API_KEY"] = self.VOYAGE_API_KEY
        if self.VOYAGE_EMBEDDING_MODEL and not os.getenv("VOYAGE_EMBEDDING_MODEL"):
            os.environ["VOYAGE_EMBEDDING_MODEL"] = self.VOYAGE_EMBEDDING_MODEL
        if self.VOYAGE_EMBEDDINGS_URL and not os.getenv("VOYAGE_EMBEDDINGS_URL"):
            os.environ["VOYAGE_EMBEDDINGS_URL"] = self.VOYAGE_EMBEDDINGS_URL
        if self.OPENAI_API_KEY and not os.getenv("OPENAI_API_KEY"):
            os.environ["OPENAI_API_KEY"] = self.OPENAI_API_KEY
        if self.OPENAI_EMBEDDING_MODEL and not os.getenv("OPENAI_EMBEDDING_MODEL"):
            os.environ["OPENAI_EMBEDDING_MODEL"] = self.OPENAI_EMBEDDING_MODEL
        if self.DEVMEMORY_EMBEDDING_PROVIDER and not os.getenv("DEVMEMORY_EMBEDDING_PROVIDER"):
            os.environ["DEVMEMORY_EMBEDDING_PROVIDER"] = self.DEVMEMORY_EMBEDDING_PROVIDER
        if self.DEVMEMORY_VECTOR_DIMENSION is not None and not os.getenv("DEVMEMORY_VECTOR_DIMENSION"):
            os.environ["DEVMEMORY_VECTOR_DIMENSION"] = str(self.DEVMEMORY_VECTOR_DIMENSION)
        if self.MONGODB_VECTOR_FIELD and not os.getenv("MONGODB_VECTOR_FIELD"):
            os.environ["MONGODB_VECTOR_FIELD"] = self.MONGODB_VECTOR_FIELD


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings instance."""
    return Settings()


def clear_settings_cache() -> None:
    """Clear cached settings instance so next get_settings() reloads."""
    get_settings.cache_clear()
