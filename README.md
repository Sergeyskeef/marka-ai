# Marka - AI-Powered Development Assistant

[![build](https://github.com/marka-ai/marka/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/marka-ai/marka/actions/workflows/ci.yml)

## Описание
Marka - это интеллектуальный ассистент для разработки, построенный на базе LangChain API. Система предоставляет инструменты для анализа кода, управления задачами и автоматизации процессов разработки.

## Технологический стек
- **Framework**: Python (FastAPI)
- **Build Tool**: Docker Compose
- **Language**: Python 3.8+
- **Storage**: SQLite/PostgreSQL
- **Testing**: pytest
- **Linting**: ruff

## Быстрый старт

### Запуск через Docker Compose
```bash
cd langchain_api
docker-compose up -d
```

### Запуск тестов
```bash
docker-compose exec app python -m pytest -v
```

## Структура проекта
- `langchain_api/` - основной код приложения
- `tests/` - тесты
- `docs/` - документация
- `scripts/` - вспомогательные скрипты

## Статус разработки
- **Phase**: MVP-Spine (MVP-2 частично завершён)
- **Current Focus**: CI зелёный (249 passed, 0 failed)
- **Next**: MVP-1 Tool-Registry, MVP-2.5 Graphiti-Neo4j backend 