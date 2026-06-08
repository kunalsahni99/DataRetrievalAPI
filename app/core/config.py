from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # ── Azure AD ──────────────────────────────────────────────────────────────
    AZURE_TENANT_ID: str
    AZURE_CLIENT_ID: str
    AZURE_CLIENT_SECRET: str

    # ── Database ──────────────────────────────────────────────────────────────
    # SQLite for lab — zero setup, file-based.
    # Swap to postgresql+psycopg2://... for production, no other code changes needed.
    DATABASE_URL: str = "sqlite:///./m365_data.db"

    # ── Graph API ─────────────────────────────────────────────────────────────
    GRAPH_BASE_URL: str = "https://graph.microsoft.com/v1.0"
    GRAPH_SCOPES: list[str] = ["https://graph.microsoft.com/.default"]

    # ── Retry / pagination ────────────────────────────────────────────────────
    GRAPH_MAX_RETRIES: int = 3
    GRAPH_RETRY_BACKOFF_BASE: int = 5  # seconds; doubles on each retry if Retry-After absent
    GRAPH_PAGE_SIZE: int = 999         # Graph's max for /users

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


@lru_cache()
def get_settings() -> Settings:
    return Settings()
