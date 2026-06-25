"""WebSocket-эндпоинт /ws с JWT-аутентификацией через Sec-WebSocket-Protocol.

Вся цепочка проверок выполняется ДО accept():
decode → exp → type=="access" → jti-ревокация в Redis → is_active.
user_id берётся только из token.sub — спуфинг структурно невозможен (D-05).
"""

from __future__ import annotations

import jwt
import structlog
from fastapi import APIRouter
from fastapi.websockets import WebSocketDisconnect
from starlette.websockets import WebSocket

from app.auth.models import User
from app.auth.security import decode_access_token
from app.core.redis_client import redis_client
from app.db.engine import async_session_factory
from app.realtime.manager import WS_CONNECTIONS, manager

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["realtime"])


@router.websocket("/ws")
async def ws_endpoint(websocket: WebSocket) -> None:
    """WebSocket push-канал. Аутентификация через Sec-WebSocket-Protocol (D-03).

    Цепочка проверок ДО accept (зеркалит get_current_user из auth/dependencies.py):
    1. Наличие bearer.<jwt> в subprotocols → 4008
    2. Подпись JWT и exp → 4008
    3. type == "access" → 4008
    4. jti в Redis revocation-set → 4008 (RT-01c)
    5. Пользователь существует и is_active → 4008 (D-04)

    После успешных проверок: accept(subprotocol="bearer"), add в ConnectionManager,
    WS_CONNECTIONS.inc(). Push-only цикл: ждём disconnect.
    try/finally гарантирует remove + dec при любом обрыве (D-12, RT-03b).
    """
    # --- Шаг 1: извлечь токен из subprotocols ДО accept ---
    subprotocols: list[str] = websocket["subprotocols"]
    token: str | None = next(
        (p[len("bearer.") :] for p in subprotocols if p.startswith("bearer.")),
        None,
    )

    if token is None:
        await websocket.close(code=4008, reason="Missing bearer token")
        return

    # --- Шаг 2: декодировать и верифицировать подпись/exp ---
    try:
        payload = decode_access_token(token)
    except jwt.ExpiredSignatureError:
        await websocket.close(code=4008, reason="Token expired")
        return
    except jwt.InvalidTokenError:
        await websocket.close(code=4008, reason="Invalid token")
        return

    # --- Шаг 3: проверить тип токена ---
    if payload.get("type") != "access":
        await websocket.close(code=4008, reason="Wrong token type")
        return

    # --- Шаг 4: проверить jti-ревокацию в Redis ---
    # WR-01: токен без jti обходит revocation-check (ключ "jti:" не создаётся при logout).
    # Отклоняем явно — валидный токен обязан содержать jti.
    jti = payload.get("jti")
    if not jti:
        await websocket.close(code=4008, reason="Invalid token")
        return
    if await redis_client.exists(f"jti:{jti}"):
        await websocket.close(code=4008, reason="Token revoked")
        return

    # --- Шаг 5: проверить пользователя и is_active в БД (D-04) ---
    # WR-02: payload["sub"] → KeyError при отсутствии sub; используем .get() с явной проверкой.
    raw_sub = payload.get("sub")
    if not raw_sub:
        await websocket.close(code=4008, reason="Invalid token")
        return
    user_id = str(raw_sub)
    async with async_session_factory() as session:
        user: User | None = await session.get(User, user_id)
        if user is None or not user.is_active:
            await websocket.close(code=4008, reason="User inactive")
            return

    # --- Все проверки пройдены: принять соединение ---
    await websocket.accept(subprotocol="bearer")
    manager.add(user_id, websocket)
    WS_CONNECTIONS.inc()

    log = logger.bind(user_id=user_id)
    log.info("ws_connected")

    # --- Push-only цикл: ждём disconnect ---
    try:
        while True:
            # Клиент ничего не присылает; ждём разрыва соединения.
            await websocket.receive_text()
    except WebSocketDisconnect:
        log.info("ws_disconnected")
    except Exception as exc:  # noqa: BLE001
        log.warning("ws_error", error=str(exc))
    finally:
        # Гарантированная очистка при любом исходе — gauge не дрейфует (D-12)
        manager.remove(user_id, websocket)
        WS_CONNECTIONS.dec()
