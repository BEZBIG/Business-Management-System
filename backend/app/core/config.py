"""Конфигурация приложения: значения читаются из переменных окружения или .env."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Настройки приложения, загружаемые из окружения."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    environment: str = "dev"

    database_url: str

    db_pool_size: int = 10
    db_max_overflow: int = 5

    redis_url: str

    rabbitmq_url: str


settings = Settings()  # type: ignore[call-arg]  # noqa: S106
