# Аудит инструментов, зависимостей и конфигураций (черновик)

## Зависимости (requirements)
- openai>=1.97.1 — OK (актуальная ветка 1.x, совместима)
- fastapi>=0.110 — OK
- httpx[http2]==0.27.2, h2 — OK
- neo4j>=5.23 — OK
- redis>=4.5 — OK
- prometheus_client==0.19.0 — OK
- pytest/pytest-asyncio/pytest-cov — OK
- ruff/black/mypy — присутствуют, нужны конфиги и CI job

Риски/заметки:
- Пины некоторых пакетов разнятся (tiktoken указан дважды: общий и фиксированная версия). Нужно унифицировать.
- Python 3.13 локально блокирует pip (PEP 668). Рекомендация: запуск через Docker Compose или Python 3.11.

## Конфигурации
- docker-compose.yml — описаны сервисы app, bot, graphiti, neo4j, redis, sandbox с лимитами ресурсов.
- .env.* — есть шаблоны, ensure REDIS_PASSWORD установлен.
- FastAPI — CORS * (можно ограничить в prod), Prometheus на /metrics, фоновые метрики RSS включены.

## Инструменты
- Health/Security/Load/Pre-production скрипты в langchain_api/scripts/* — OK
- Telegram бот — модульный, Dockerfile есть
- CI: .github/workflows/test-coverage.yml — запускает pytest+coverage, минимальный порог 50%

## Рекомендации
1) Привести requirements к единообразию: избежать дублирования tiktoken, проверить совместимость langchain версий.
2) Включить ruff/mypy в CI (workflow steps).
3) Ограничить CORS в prod, включить SECRET_KEY/SESSION настройки.
4) Добавить дашборд Grafana пример (docs/metrics/grafana.json) и экспортёры Neo4j/Redis.
5) Для локальной среды использовать `docker compose up -d`.