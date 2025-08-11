run:
	uvicorn langchain_api.app.main:app --host 0.0.0.0 --port 8000 --reload

test:
	pytest -xvs

# Baseline Diagnostics для Марк v2
measure-baseline: ## Снятие базовых метрик перед оптимизациями
	@echo "🚀 Запуск Baseline Diagnostics для Марка v2..."
	@python3 benchmarks/p95_latency.py
	@python3 benchmarks/token_cost.py
	@echo "📊 Измерение success rate через pytest..."
	@pytest langchain_api/tests/benchmarks/ -v || echo "⚠️ Не все тесты прошли успешно"
	@echo "🧪 Измерение покрытия тестами..."
	@pytest --cov=langchain_api --cov-report=json:docs/metrics/coverage.json langchain_api/tests/benchmarks/ || echo "⚠️ Coverage не удалось измерить, но продолжаем"
	@echo "✅ Baseline metrics собраны в docs/metrics/"
	@ls -la docs/metrics/

# Цели для миграции данных Марк v2
export-weaviate: ## Экспорт данных из Weaviate в JSONL
	@echo "📤 Экспорт данных из Weaviate..."
	@python3 scripts/data_migration.py export --output docs/metrics/weaviate_export_$(shell date +%Y%m%d_%H%M%S).jsonl --report docs/metrics/export_report.json
	@echo "✅ Экспорт завершен"

import-graphiti: ## Импорт данных в GraphitiMemory
	@echo "📥 Импорт данных в GraphitiMemory..."
	@python3 scripts/data_migration.py import --input docs/metrics/weaviate_export_*.jsonl --report docs/metrics/import_report.json
	@echo "✅ Импорт завершен"

migrate-data: ## Полная миграция Weaviate → GraphitiMemory
	@echo "🚀 Полная миграция Weaviate → GraphitiMemory..."
	@python3 scripts/data_migration.py migrate --report docs/metrics/migration_report_$(shell date +%Y%m%d_%H%M%S).json
	@echo "✅ Миграция завершена"

validate-export: ## Валидация экспортированного файла
	@echo "🔍 Валидация экспортированного файла..."
	@python3 scripts/data_migration.py validate --file docs/metrics/weaviate_export_*.jsonl
	@echo "✅ Валидация завершена"



# Цели для интеграционного тестирования
test-integration: ## Интеграционные тесты GraphitiMemory + Rust Core
	@echo "🔗 Интеграционные тесты..."
	@pytest tests/integration/ -v
	@echo "✅ Интеграционные тесты завершены"

# Цели для A/B тестирования
test-ab: ## A/B тестирование GraphitiMemory vs Weaviate
	@echo "🧪 A/B тестирование памяти..."
	@python3 tests/ab_memory_test.py
	@echo "✅ A/B тестирование завершено"

# Цели для Q1 реализации
setup-q1: ## Настройка для Q1 реализации
	@echo "🚀 Настройка Q1 реализации..."
	@echo "📋 Проверка зависимостей..."
	@pip install -r requirements.txt
	@echo "🔧 Настройка GraphitiMemory..."
	@export GRAPHITI_MODE=shadow

	@echo "✅ Q1 настройка завершена"

clean-q1: ## Очистка временных файлов Q1
	@echo "🧹 Очистка временных файлов..."
	@rm -f docs/metrics/weaviate_export_*.jsonl
	@rm -f docs/metrics/*_report.json
	@rm -f migration.log
	@echo "✅ Очистка завершена"

help: ## Показать доступные команды
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'
