<div align="center">

# 🌊 TeamFlow

### Business Management System

**Внутрикорпоративная платформа для управления командами: задачи, встречи, общий календарь и AI-помощник в одном месте.**

[![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.136-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-2.0-D71F00?logo=sqlalchemy&logoColor=white)](https://www.sqlalchemy.org/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![Redis](https://img.shields.io/badge/Redis-7-FF4438?logo=redis&logoColor=white)](https://redis.io/)
[![RabbitMQ](https://img.shields.io/badge/RabbitMQ-3.13-FF6600?logo=rabbitmq&logoColor=white)](https://www.rabbitmq.com/)
[![React](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=black)](https://react.dev/)
[![License](https://img.shields.io/badge/license-internal-lightgrey)](#)

</div>

---

## ✨ О проекте

**TeamFlow** — это async-платформа для управления командной работой, спроектированная под высокую нагрузку (цель — до **10 000** одновременных пользователей).

> **Core Value:** команда видит полную картину работы в одном месте — задачи, встречи и календарь, — а AI-помощник снимает рутину планирования и ежедневно подсвечивает каждому сотруднику, что важно сегодня.

---

## 🚀 Возможности

| | Возможность | Описание |
|:--:|:--|:--|
| 👥 | **Команды и пользователи** | Управление участниками, ролями и составом команд |
| ✅ | **Задачи** | Постановка, отслеживание и оценка работы |
| 📅 | **Встречи и календарь** | Общий календарь, видеовстречи через Jitsi Meet |
| 🤖 | **AI-помощник** | Ежедневные дайджесты и помощь в планировании на Groq API |
| 🔔 | **Реал-тайм** | Мгновенные уведомления через WebSocket / SSE |
| 📊 | **Наблюдаемость** | Метрики Prometheus и дашборды Grafana |

---

## 🛠️ Технологический стек

### Backend

| Технология | Версия | Назначение |
|:--|:--|:--|
| **Python** | 3.12 | Рантайм (лучшая async-производительность) |
| **FastAPI** | 0.136 | ASGI web-фреймворк (async/await, OpenAPI, SSE) |
| **SQLAlchemy** | 2.0 + asyncpg | Полностью async ORM |
| **Alembic** | 1.18 | Миграции БД (async-пайплайн) |
| **FastStream** | 0.7 | Фоновые задачи поверх RabbitMQ |
| **PostgreSQL** | 16 | Основная БД |
| **Redis** | 7 | Кэш, сессии, pub/sub для реал-тайма |
| **RabbitMQ** | 3.13 | Брокер фоновых задач |
| **structlog** | — | Структурированное JSON-логирование |
| **PyJWT + pwdlib** | — | JWT-аутентификация и хеширование паролей (Argon2) |

### Frontend

| Технология | Версия | Назначение |
|:--|:--|:--|
| **React** | 19 | UI-фреймворк |
| **TypeScript** | 5.7 | Типобезопасность |
| **Vite** | 8 | Сборка и dev-сервер |
| **TanStack Query / Router** | 5 / 1 | Серверное состояние и типизированный роутинг |
| **Zustand** | 5 | Клиентское состояние |
| **shadcn/ui + Tailwind** | — | UI-компоненты |
| **FullCalendar** | 6 | Календарь (месяц/неделя/день) |

### Инфраструктура и инструменты

`Docker Compose` · `uv` · `ruff` · `mypy` · `pytest` · `pre-commit` · `GitHub Actions` · `Prometheus` · `Grafana` · `Jitsi Meet`

---

## 📦 Структура проекта

```
Business-Management-System/
├── backend/                    # Async FastAPI бэкенд
│   ├── app/
│   │   ├── core/               # Конфиг, логирование, middleware, брокер, Redis
│   │   ├── db/                 # Engine, сессии, ORM-база (TimestampMixin)
│   │   ├── health/             # Эндпоинты /health/live и /health/ready
│   │   ├── metrics/            # Инструментатор Prometheus
│   │   └── main.py             # Точка входа ASGI-приложения
│   ├── alembic/                # Async-миграции (baseline 0001)
│   ├── tests/                  # pytest + httpx (async)
│   └── pyproject.toml          # Зависимости (пиннинг через uv)
├── frontend/                   # SPA на React 19 + TypeScript (планируется)
├── docker-compose.yml          # PostgreSQL + Redis + RabbitMQ + app
└── README.md
```

---

## ⚡ Быстрый старт

### Требования

- [Docker](https://www.docker.com/) и Docker Compose
- [uv](https://github.com/astral-sh/uv) (менеджер пакетов Python)
- Python 3.12

### Запуск через Docker Compose

```bash
# 1. Скопировать переменные окружения
cp .env.example .env

# 2. Поднять весь стек (PostgreSQL 16 + Redis 7 + RabbitMQ 3.13 + app)
docker compose up -d

# 3. Применить миграции БД
docker compose exec app uv run alembic upgrade head

# 4. Проверить готовность
curl http://localhost:8000/health/ready
# → {"status":"ok","services":{"postgres":"ok","redis":"ok","rabbitmq":"ok"}}
```

### Локальная разработка backend

```bash
cd backend

# Установить зависимости в виртуальное окружение
uv sync

# Запустить dev-сервер с авто-перезагрузкой
uv run uvicorn app.main:app --reload

# Прогнать тесты и линтеры
uv run pytest
uv run ruff check .
uv run mypy .
```

---

## 🔗 Ключевые эндпоинты

| Метод | Путь | Назначение |
|:--|:--|:--|
| `GET` | `/health/live` | Liveness-проба (без I/O) |
| `GET` | `/health/ready` | Readiness: PostgreSQL + Redis + RabbitMQ |
| `GET` | `/metrics` | Метрики в формате Prometheus |
| `GET` | `/docs` | Интерактивная документация OpenAPI (Swagger UI) |

---

## 🏛️ Архитектурные принципы

- **Async-стек целиком** — FastAPI + SQLAlchemy 2.0 + asyncpg под нагрузку 10k пользователей.
- **`expire_on_commit=False`** на всех сессиях — защита от `MissingGreenlet` при сериализации.
- **`lazy="raise"`** на всех связях ORM — явный eager-loading, блокировка случайных async lazy-load.
- **`TIMESTAMPTZ`** на всех временных колонках — timezone-aware даты с первой миграции.
- **Redis pub/sub** как backplane реал-тайма — обязателен для multi-worker WebSocket/SSE.
- **Health-чеки и метрики** с первого коммита — наблюдаемость не добавляется задним числом.

---

<div align="center">

**TeamFlow** — сделано с ❤️ для продуктивных команд

</div>
