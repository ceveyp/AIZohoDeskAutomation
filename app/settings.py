from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field
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
    zoho_accounts_domain: str = "accounts.zoho.com"
    webhook_secret_token: str | None = None
    openrouter_api_key: str
    apparel_magic_api_key: str
    ii_hostname: str
    ii_product_search_api_key: str
    # Optional: if the search API returns a numeric score/similarity on each hit (higher = better match).
    product_search_min_confidence: float | None = None
    # Optional: minimum gap between 1st and 2nd hit scores (same scale as above) to avoid ambiguous matches.
    product_search_min_leader_gap: float | None = None
    google_client_id: str
    google_client_secret: str
    google_refresh_token: str

    # Optional Shopify Admin API (retail order-status when no AM customer match)
    shopify_access_token: str | None = Field(
        default=None,
        validation_alias=AliasChoices("SHOPIFY_ACCESS_TOKEN"),
    )
    shopify_shop: str | None = Field(
        default=None,
        validation_alias=AliasChoices("SHOPIFY_SHOP"),
    )
    shopify_api_version: str = Field(
        default="2025-04",
        validation_alias=AliasChoices("SHOPIFY_API_VERSION"),
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
