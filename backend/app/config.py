"""Application config loaded from .env via pydantic-settings."""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
    )

    # Database
    database_url: str = "postgresql+psycopg2://postgres:postgres@localhost:5432/reels"

    # Google Gemini
    gemini_api_key: str = ""

    # Pexels
    pexels_api_key: str = ""

    # Supabase
    supabase_url: str = ""
    supabase_service_role_key: str = ""
    supabase_bucket: str = "reels"

    # Make.com
    make_com_webhook_url: str = ""
    make_com_callback_secret: str = ""
    app_base_url: str = "http://localhost:8000"

    # CORS
    cors_origins: str = "http://localhost:3000"

    # Worker storage
    local_storage_dir: str = "./storage"

    # Mock mode — when True, POST /campaigns skips Make.com and simulates
    # the callback inline with stubbed data so you can test the full
    # backend pipeline (edge-tts + MoviePy + Supabase) without Make.com.
    mock_mode: bool = False

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
