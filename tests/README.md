# Тесты проекта Марк

## Структура тестов

Тесты организованы по задачам из чек-листа Phase 3.H₂:

- `test_sandbox_e2e.py` - E2E тесты для Sandbox Runner (F-1)
- `test_sandbox_individual.py` - Индивидуальные тесты Sandbox (F-1)
- `test_tools_registry_f2.py` - Тесты Tools Registry (F-2)
- `test_sandbox_exec_f4.py` - Тесты /sandbox/exec endpoint (F-4)
- `test_feedback_api_f5.py` - Тесты Feedback API (F-5)
- `test_reflection_engine_f6.py` - Тесты Reflection Engine (F-6)
- `test_error_middleware_f8.py` - Тесты Error Middleware (F-8)

## Запуск тестов

### Все тесты
```bash
python3 -m pytest tests/
```

### Конкретный тест
```bash
python3 tests/test_sandbox_e2e.py
```

### С измерением покрытия
```bash
# Используйте скрипт
./scripts/check_coverage.sh

# Или напрямую
pytest --cov=. --cov-report=html --cov-report=term-missing
```

## Требования к покрытию

- **Минимальное покрытие**: 50%
- **Целевое покрытие**: 70%+
- **GitHub Action**: Автоматически проверяет покрытие при PR

## CI/CD

GitHub Action `.github/workflows/test-coverage.yml`:
- Запускается при push в main/develop и при PR
- Проверяет минимальное покрытие 50%
- Комментирует PR с результатами
- Сохраняет HTML отчет как артефакт

## Написание новых тестов

При добавлении новой функциональности:
1. Создайте тестовый файл `test_<feature>.py`
2. Покройте основные сценарии использования
3. Проверьте покрытие локально: `./scripts/check_coverage.sh`
4. Убедитесь, что покрытие не упало ниже 50%

## Маркеры pytest

- `@pytest.mark.slow` - медленные тесты
- `@pytest.mark.integration` - интеграционные тесты
- `@pytest.mark.unit` - юнит-тесты
- `@pytest.mark.e2e` - end-to-end тесты

Пропустить медленные тесты:
```bash
pytest -m "not slow"
```