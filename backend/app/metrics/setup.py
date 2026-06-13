"""Подключение метрик Prometheus и эндпоинта /metrics."""

from __future__ import annotations

from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator


def setup_metrics(app: FastAPI) -> None:
    """Подключает Prometheus-инструментатор к приложению и публикует /metrics.

    Вызывать до app.add_middleware().
    """
    Instrumentator().instrument(app).expose(app)
