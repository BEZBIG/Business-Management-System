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

    # JWT (D-06/D-07)
    jwt_secret: str  # обязательное, без default — из env
    access_token_ttl: int = 900  # 15 минут в секундах
    refresh_token_ttl: int = 604800  # 7 дней в секундах

    # Первый суперпользователь — идемпотентный seed в lifespan (D-11)
    first_superuser_email: str = ""
    first_superuser_password: str = ""  # noqa: S105

    # SQLAdmin session signing через itsdangerous (D-14)
    admin_session_secret: str  # обязательное, без default — из env


settings = Settings()  # type: ignore[call-arg]  # noqa: S106
