"""
Application configuration via pydantic-settings.

All settings are read from environment variables or .env file.
No secrets are hardcoded — values come from the environment (D-05, D-06, T-01-02).
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Application environment: dev | prod
    environment: str = "dev"

    # PostgreSQL — required, no default (must be in env)
    database_url: str

    # Connection pool (D-13): conservative defaults, tuned in Phase 7
    db_pool_size: int = 10
    db_max_overflow: int = 5

    # Redis
    redis_url: str

    # RabbitMQ
    rabbitmq_url: str


# Module-level singleton; imported everywhere as `from app.core.config import settings`
settings = Settings()
