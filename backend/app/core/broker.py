"""FastStream RabbitBroker с fail_fast=False: приложение стартует даже при недоступном RabbitMQ."""

from __future__ import annotations

from faststream.rabbit import RabbitBroker

from app.core.config import settings

broker = RabbitBroker(
    url=settings.rabbitmq_url,
    fail_fast=False,
    reconnect_interval=5.0,
)
