"""Pydantic-схемы для домена аутентификации: запросы и ответы.

Строгая валидация пароля (D-04): минимум 12 символов + верхний/нижний регистр + цифра + спецсимвол.
password_hash намеренно исключён из всех ответных схем (T-02-09).
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, EmailStr, Field, field_validator

# Политика пароля D-04: ≥12 символов, обязательны a-z, A-Z, 0-9, спецсимвол.
PASSWORD_PATTERN = re.compile(
    r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[!@#$%^&*()\-_=+\[\]{};':\"\\|,.<>/?`~]).{12,}$"
)


def _validate_password_strength(v: str) -> str:
    """Проверяет соответствие пароля политике D-04."""
    if not PASSWORD_PATTERN.match(v):
        raise ValueError(
            "Password must be at least 12 characters and contain uppercase, "
            "lowercase, digit, and special character"
        )
    return v


class RegisterRequest(BaseModel):
    """Запрос регистрации нового пользователя. Роль задаётся сервером (D-10)."""

    email: EmailStr
    password: Annotated[str, Field(min_length=12)]

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        """Валидирует сложность пароля по политике D-04."""
        return _validate_password_strength(v)


class LoginRequest(BaseModel):
    """Запрос входа с email и паролем."""

    email: EmailStr
    password: str


class LoginResponse(BaseModel):
    """Ответ на успешный вход: JWT access-токен."""

    access_token: str
    token_type: str = "bearer"  # noqa: S105


class UserMeResponse(BaseModel):
    """Профиль текущего пользователя. Без password_hash (T-02-09)."""

    id: uuid.UUID
    email: str
    role: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}  # для ORM-объектов SQLAlchemy


class UserUpdateRequest(BaseModel):
    """Обновление профиля пользователя. Роль клиент не задаёт (D-10)."""

    email: EmailStr | None = None


class PasswordChangeRequest(BaseModel):
    """Запрос смены пароля. Требует верификации текущего пароля (D-05)."""

    current_password: str
    new_password: Annotated[str, Field(min_length=12)]

    @field_validator("new_password")
    @classmethod
    def validate_new_password_strength(cls, v: str) -> str:
        """Валидирует новый пароль по политике D-04."""
        return _validate_password_strength(v)
