"""
FastStream RabbitBroker with connect_robust and fail_fast=False (D-14, criterion #5).

Design choices:
  - fail_fast=False: the application starts even if RabbitMQ is not yet available;
    aio-pika's connect_robust() retries automatically (T-03-03).
  - reconnect_interval=5.0: controls back-off between reconnect attempts;
    prevents a tight reconnect loop (Pitfall 7).
  - No queues declared here: digest/notifications queues are Phase 6+ scope (D-14).
  - No FastStream app created: FastStream(broker=...) API changed in 0.7.x;
    standalone broker is all that is needed in Phase 1 (Pitfall 4).

broker.start()  in lifespan → calls connect_robust() internally (Pattern 6).
broker.stop()   in lifespan → graceful AMQP channel/connection close.
"""

from __future__ import annotations

from faststream.rabbit import RabbitBroker

from app.core.config import settings

broker = RabbitBroker(
    url=settings.rabbitmq_url,
    fail_fast=False,  # do not crash on startup if broker is unavailable (Pitfall 7)
    reconnect_interval=5.0,  # seconds between reconnect attempts (T-03-03)
)
