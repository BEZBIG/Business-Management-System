"""ConnectionManager: реестр WebSocket-соединений текущего воркера + Prometheus gauge."""

from __future__ import annotations

import structlog
from fastapi.websockets import WebSocket
from prometheus_client import Gauge

logger = structlog.get_logger(__name__)

# Gauge объявлен на module level — гарантирует однократную регистрацию при импорте (Pitfall 6).
# multiprocess_mode="livesum" — суммирует только живые воркеры; при рестарте воркера
# его счётчик не дрейфует (D-12).
WS_CONNECTIONS = Gauge(
    "teamflow_ws_active_connections",
    "Активные WebSocket-соединения на этом воркере",
    multiprocess_mode="livesum",
)


class ConnectionManager:
    """Реестр WebSocket-соединений текущего воркера.

    Хранит dict[user_id, set[WebSocket]] для поддержки мульти-девайс (D-06).
    Не расшаривается между процессами — координация между воркерами через Redis pub/sub.
    asyncio.Lock не нужен: один event loop на воркер, GIL + cooperative scheduling.
    """

    def __init__(self) -> None:
        """Инициализирует пустой реестр соединений."""
        self._connections: dict[str, set[WebSocket]] = {}

    def add(self, user_id: str, ws: WebSocket) -> None:
        """Регистрирует WebSocket-соединение для пользователя."""
        self._connections.setdefault(user_id, set()).add(ws)

    def remove(self, user_id: str, ws: WebSocket) -> None:
        """Удаляет WebSocket-соединение; если соединений не осталось — удаляет ключ."""
        conns = self._connections.get(user_id)
        if conns:
            conns.discard(ws)
            if not conns:
                del self._connections[user_id]

    def get(self, user_id: str) -> set[WebSocket]:
        """Возвращает множество активных соединений пользователя (пустое при miss)."""
        return self._connections.get(user_id, set())

    async def send_to_user(self, user_id: str, payload: dict) -> None:  # type: ignore[type-arg]
        """Fan-out: отправляет payload на все соединения пользователя на этом воркере.

        Мёртвые соединения (Exception при send_json) удаляются из реестра после цикла;
        один мёртвый клиент не прерывает доставку остальным (RT-03c, Pitfall 4).
        """
        dead: list[WebSocket] = []
        for ws in list(self.get(user_id)):  # копия set — безопасно при изменении
            try:
                await ws.send_json(payload)
            except Exception:  # noqa: BLE001
                logger.warning("ws_dead_connection_detected", user_id=user_id)
                dead.append(ws)
        for ws in dead:
            self.remove(user_id, ws)


# Singleton на воркер — импортируется всеми зависящими модулями (router, listener).
manager = ConnectionManager()
