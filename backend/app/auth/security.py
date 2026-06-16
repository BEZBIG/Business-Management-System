"""Криптографические операции: хеширование паролей (Argon2id) и JWT encode/decode (HS256).

Модуль-синглтон: password_hasher создаётся один раз при импорте и переиспользуется
во всём приложении. Исключения JWT пробрасываются наверх — обработка в dependencies/router.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import jwt
from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher

from app.core.config import settings

# Синглтон — явный конструктор, детерминирован и тестируем.
# НЕ использовать PasswordHash.recommended() — создаёт свежий объект без контроля над хешером.
password_hasher = PasswordHash((Argon2Hasher(),))

# Алгоритм подписи JWT. Всегда список при decode — защита от подмены алгоритма.
ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    """Хеширует пароль через Argon2id-синглтон."""
    return password_hasher.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Верифицирует пароль против Argon2id-хеша."""
    return password_hasher.verify(plain_password, hashed_password)


def create_access_token(sub: str, role: str) -> str:
    """Создаёт JWT access-токен (HS256, 15 мин).

    Claims: sub, role, jti (uuid4.hex), iat, exp, type="access".
    Секрет берётся только из settings.jwt_secret (никогда не хранится в коде).
    """
    now = datetime.now(UTC)
    payload = {
        "sub": sub,
        "role": role,
        "jti": uuid.uuid4().hex,
        "iat": now,
        "exp": now + timedelta(seconds=settings.access_token_ttl),
        "type": "access",
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict[str, object]:
    """Декодирует и верифицирует JWT access-токен.

    ОБЯЗАТЕЛЬНО список algorithms=[ALGORITHM] — защита от подмены алгоритма.
    Бросает jwt.ExpiredSignatureError при истёкшем exp, jwt.InvalidTokenError при иных ошибках.
    """
    return jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])


def create_refresh_token(sub: str) -> str:
    """Создаёт JWT refresh-токен (HS256, 7 дней).

    Claims: sub, jti, iat, exp, type="refresh". Роль в refresh не включается.
    """
    now = datetime.now(UTC)
    payload = {
        "sub": sub,
        "jti": uuid.uuid4().hex,
        "iat": now,
        "exp": now + timedelta(seconds=settings.refresh_token_ttl),
        "type": "refresh",
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)


def decode_refresh_token(token: str) -> dict[str, object]:
    """Декодирует и верифицирует JWT refresh-токен.

    Бросает jwt.ExpiredSignatureError / jwt.InvalidTokenError при ошибках.
    """
    return jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])
