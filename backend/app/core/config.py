from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Tonie Finder API"
    environment: str = "dev"
    debug: bool = True

    host: str = "0.0.0.0"
    port: int = 8787

    database_url: str = "sqlite:///./tonie_finder.db"
    sqlite_path: str = "./tonie_finder.db"
    redis_url: str = "redis://localhost:6379/0"

    password_iterations: int = 120_000
    session_ttl_hours: int = 24 * 30

    auth_mode: str = "local"  # local | external
    auth_issuer: str = ""
    auth_audience: str = ""
    auth_jwks_url: str = ""
    auth_require_verified_email: bool = True

    market_cache_ttl_minutes: int = 360
    market_history_days: int = 180
    market_min_samples: int = 5
    market_min_effective_samples: float = 5.0
    market_price_min_eur: float = 3.0
    market_price_max_eur: float = 250.0
    market_outlier_iqr_factor: float = 1.8
    market_default_source_weight: float = 1.0
    market_source_weights: dict[str, float] = Field(
        default_factory=lambda: {
            "ebay_sold": 1.0,
            # Lower influence for classifieds/listing sources unless proven against sold data.
            "kleinanzeigen_listing": 0.35,
            "kleinanzeigen_offer": 0.35,
            "kleinanzeigen_sold_estimate": 0.45,
        }
    )

    market_auto_refresh_enabled: bool = False
    market_auto_refresh_interval_minutes: int = 10080
    market_auto_refresh_limit: int = 0
    market_auto_refresh_delay_ms: int = 200
    market_auto_refresh_max_items: int = 80

    ebay_api_enabled: bool = False
    ebay_env: str = "production"  # production | sandbox
    ebay_client_id: str = ""
    ebay_client_secret: str = ""
    ebay_oauth_scope: str = "https://api.ebay.com/oauth/api_scope"
    ebay_marketplace_id: str = "EBAY_DE"
    ebay_request_timeout_s: float = 15.0
    ebay_max_retries: int = 2
    ebay_api_shadow_mode: bool = True
    ebay_api_include_in_pricing: bool = False

    recognition_reference_dir: str = "./app/data/tonie_refs"
    recognition_index_path: str = "./app/data/tonie_reference_index.json"
    recognition_min_score: float = 0.72
    recognition_resolved_score: float = 0.90
    recognition_resolved_gap: float = 0.06

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()
