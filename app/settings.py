from functools import lru_cache
import logging
import os
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_logger = logging.getLogger(__name__)


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

    # Product inquiry: false = only IT department (see ticket_webhook); true = all departments.
    product_inquiry_all_departments: bool = Field(
        default=False,
        validation_alias=AliasChoices(
            "product_inquiry_all_departments",
            "PRODUCT_INQUIRY_ALL_DEPARTMENTS",
        ),
    )

    # Optional LangSmith / LangChain tracing (sets LANGCHAIN_* env vars for LangChain agents).
    langsmith_tracing: bool = Field(
        default=False,
        validation_alias=AliasChoices(
            "LANGSMITH_TRACING",
            "LANGCHAIN_TRACING_V2",
        ),
    )
    langsmith_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "LANGSMITH_API_KEY",
            "LANGCHAIN_API_KEY",
        ),
    )
    langsmith_project: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "LANGSMITH_PROJECT",
            "LANGCHAIN_PROJECT",
        ),
    )
    langsmith_endpoint: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "LANGSMITH_ENDPOINT",
            "LANGCHAIN_ENDPOINT",
        ),
    )


def configure_langchain_tracing(settings: Settings) -> None:
    """
    LangChain reads LANGCHAIN_TRACING_V2 and LANGCHAIN_API_KEY at run time for LangSmith.
    Call once after Settings load (see get_settings).
    """
    if not settings.langsmith_tracing:
        return
    key = (settings.langsmith_api_key or "").strip()
    if not key:
        _logger.warning(
            "LangSmith tracing requested (LANGSMITH_TRACING) but no LANGSMITH_API_KEY / LANGCHAIN_API_KEY set"
        )
        return
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGCHAIN_API_KEY"] = key
    proj = (settings.langsmith_project or "").strip()
    if proj:
        os.environ["LANGCHAIN_PROJECT"] = proj
    endpoint = (settings.langsmith_endpoint or "").strip()
    if endpoint:
        os.environ["LANGCHAIN_ENDPOINT"] = endpoint.rstrip("/")
    _logger.info(
        "LangChain tracing enabled for LangSmith (project=%r endpoint_set=%s)",
        proj or "(default)",
        bool(endpoint),
    )


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    configure_langchain_tracing(settings)
    return settings
