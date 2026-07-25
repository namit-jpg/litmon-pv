from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Resolve .env from monorepo root or api dir
_ROOT = Path(__file__).resolve().parents[4]
_API = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # Later files override earlier ones — keep real .env last so it wins over .env.example
        env_file=(
            str(_ROOT / ".env.example"),
            str(_API / ".env"),
            str(_ROOT / ".env"),
        ),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "sqlite:///./litmon.db"
    jwt_secret: str = "dev-secret-change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 480

    ncbi_email: str = "dev@example.com"
    ncbi_api_key: str = ""
    ncbi_tool: str = "litmon-pv"
    ncbi_base_url: str = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

    llm_api_key: str = ""
    llm_base_url: str = "https://api.x.ai/v1"
    llm_model: str = "grok-2-latest"
    llm_mock: bool = True

    app_env: str = "development"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    auto_clear_qc_sample_rate: float = 0.10
    log_level: str = "INFO"

    # Notifications (SLA breach etc.) — disabled by default; logs always
    notify_email_enabled: bool = False
    notify_smtp_host: str = ""
    notify_smtp_port: int = 587
    notify_smtp_tls: bool = True
    notify_smtp_user: str = ""
    notify_smtp_password: str = ""
    notify_from: str = "litmon-pv@localhost"
    notify_to: str = ""

    # Version stamps logged on every score
    prompt_version: str = "v1.0.0"
    ruleset_version: str = "v1.0.0"
    threshold_version: str = "v1.0.0"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
