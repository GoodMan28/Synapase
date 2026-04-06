"""
Project-75A — Configuration
Pydantic Settings for environment-driven configuration.
"""

from pydantic_settings import BaseSettings
from pydantic import Field
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment variables / .env file."""

    # ── LLM ──
    # Supports multiple keys separated by '|' for round-robin random selection.
    # Example: GOOGLE_API_KEY=key1|key2|key3
    GOOGLE_API_KEY: str = Field(..., description="Google AI Studio API key(s), pipe-separated")
    GEMINI_MODEL: str = Field(default="gemini-3.1-flash-lite-preview", description="Gemini model identifier")
    GEMINI_TEMPERATURE: float = Field(default=0.4, description="LLM temperature for generation")
    GEMINI_MAX_OUTPUT_TOKENS: int = Field(default=4096, description="Max output tokens per LLM call")

    # ── ChromaDB ──
    CHROMA_PERSIST_DIR: str = Field(default="./chroma_data", description="ChromaDB persistent storage dir")

    # ── ArXiv ──
    ARXIV_MAX_RESULTS: int = Field(default=5, description="Max papers per ArXiv search query")
    ARXIV_RATE_LIMIT_SECONDS: float = Field(default=3.0, description="Delay between ArXiv API calls")

    # ── Agent Pipeline ──
    MAX_REVISIONS: int = Field(default=2, description="Max auditor revision cycles before forced approval")

    # ── Server ──
    LOG_LEVEL: str = Field(default="INFO", description="Logging level")
    CORS_ORIGINS: list[str] = Field(
        default=["http://localhost:5173", "http://127.0.0.1:5173"],
        description="Allowed CORS origins",
    )

    model_config = {
        "env_file": "../.env",
        "env_file_encoding": "utf-8",
        "case_sensitive": True,
    }

    @property
    def api_keys(self) -> list[str]:
        """Return the list of API keys parsed from the pipe-separated string."""
        return [k.strip() for k in self.GOOGLE_API_KEY.split("|") if k.strip()]


@lru_cache()
def get_settings() -> Settings:
    """Cached singleton — parsed once on first call."""
    return Settings()
