from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parent.parent / ".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    app_name: str = "Webhook"
    host: str = "0.0.0.0"
    port: int = 8000
    zoho_org_id: str
    zoho_client_id: str
    zoho_client_secret: str
    zoho_redirect_uri: str
    zoho_refresh_token: str
    zoho_scopes: str
    openrouter_api_key: str
    apparel_magic_api_key: str


@lru_cache
def get_settings() -> Settings:
    return Settings()
