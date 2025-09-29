# План стратегии объединения веток

## Рекомендуемая стратегия: Поэтапное слияние

### Этап 1: Подготовка (КРИТИЧНО)
```bash
# 1. Создать резервную копию
git checkout main
git checkout -b backup/before-merge-$(date +%Y%m%d)

# 2. Проверить статус рабочей директории
git status
git stash  # если есть незакоммиченные изменения

# 3. Обновить main до последнего состояния
git checkout main
git pull origin main
```

### Этап 2: Слияние по приоритету

#### 2.1 Слияние `chore/memory-hardening` (ПРИОРИТЕТ: ВЫСОКИЙ)
**Причина:** Текущая ветка с важными изменениями безопасности
```bash
git checkout main
git checkout -b merge/memory-hardening
git merge chore/memory-hardening --no-ff
# Разрешить конфликты если есть
git checkout main
git merge merge/memory-hardening
git branch -d merge/memory-hardening
```

**Ожидаемые конфликты:**
- `docker-compose.yml` - вероятно
- `langchain_api/configs/redis.conf` - новый файл

#### 2.2 Слияние `feature/phase-3-reflexion` (ПРИОРИТЕТ: ВЫСОКИЙ)
**Причина:** Критически важные изменения архитектуры
```bash
git checkout main
git checkout -b merge/phase-3-reflexion
git merge feature/phase-3-reflexion --no-ff
# Разрешить конфликты
git checkout main
git merge merge/phase-3-reflexion
git branch -d merge/phase-3-reflexion
```

**Ожидаемые конфликты:**
- Множество файлов в `langchain_api/`
- Возможны конфликты в `docker-compose.yml`

#### 2.3 Слияние `agents_migration` (ПРИОРИТЕТ: СРЕДНИЙ)
**Причина:** Структурные изменения, но могут быть устаревшими
```bash
git checkout main
git checkout -b merge/agents-migration
git merge agents_migration --no-ff
# ВНИМАНИЕ: Возможны массивные конфликты
git checkout main
git merge merge/agents-migration
git branch -d merge/agents-migration
```

**Ожидаемые конфликты:**
- Практически все файлы в `langchain_api/`
- Конфигурационные файлы
- Документация

#### 2.4 Слияние `feature/agent-optimization-research` (ПРИОРИТЕТ: НИЗКИЙ)
**Причина:** Оптимизации, но не критичны
```bash
git checkout main
git checkout -b merge/agent-optimization
git merge feature/agent-optimization-research --no-ff
git checkout main
git merge merge/agent-optimization
git branch -d merge/agent-optimization
```

### Этап 3: Очистка и проверка

#### 3.1 Обработка неотслеживаемых файлов
```bash
# Добавить важные новые файлы
git add langchain_api/core/memory/embeddings.py
git add langchain_api/core/memory/facade_shim.py
git add langchain_api/core/memory/metadata.py
git add langchain_api/core/memory/service.py
git add langchain_api/core/memory/xtrace.py

# Добавить MCP файлы если нужны
git add mark_mcp/mark_mcp/docker_tools.py
git add mark_mcp/mark_mcp/mcp_server.py
git add mark_mcp/mark_mcp/metrics.py
git add mark_mcp/mark_mcp/models_memory.py
git add mark_mcp/mark_mcp/repo_tools.py

git commit -m "feat: add new memory and MCP components"
```

#### 3.2 Тестирование
```bash
# Запустить тесты
cd langchain_api
docker compose exec app python -m pytest tests/ -v

# Проверить основные функции
docker compose exec app python -c "import app.main; print('Import successful')"
```

#### 3.3 Финальная очистка
```bash
# Удалить устаревшие ветки (опционально)
git branch -d chore/memory-hardening
git branch -d feature/phase-3-reflexion
git branch -d agents_migration
git branch -d feature/agent-optimization-research

# Оставить только актуальные ветки
```

## Альтернативные стратегии

### Стратегия A: Массовое слияние
```bash
git checkout main
git checkout -b merge/all-branches
git merge chore/memory-hardening feature/phase-3-reflexion agents_migration feature/agent-optimization-research --no-ff
# Один большой merge commit со всеми изменениями
```

**Плюсы:** Быстро, один коммит
**Минусы:** Сложно разрешать конфликты, риск потери изменений

### Стратегия B: Селективное слияние
```bash
# Выбрать только критически важные файлы из каждой ветки
git checkout main
git checkout -b merge/selective
# Ручное копирование только нужных файлов
```

**Плюсы:** Полный контроль
**Минусы:** Трудоемко, можно пропустить важные изменения

## План разрешения конфликтов

### 1. docker-compose.yml
**Приоритет:** memory-hardening > phase-3-reflexion > agents_migration
**Стратегия:** Объединить все изменения вручную

### 2. langchain_api/
**Приоритет:** phase-3-reflexion > agents_migration > optimization-research
**Стратегия:** Использовать инструменты merge для сложных случаев

### 3. Конфигурационные файлы
**Приоритет:** memory-hardening > agents_migration
**Стратегия:** Объединить все настройки

## Команды для отката (если что-то пойдет не так)

```bash
# Вернуться к состоянию до слияния
git checkout backup/before-merge-$(date +%Y%m%d)
git checkout -b main-recovered
git branch -D main
git branch -m main-recovered main
```

## Чек-лист выполнения

- [ ] Создать резервную копию
- [ ] Обновить main до последнего состояния
- [ ] Слить chore/memory-hardening
- [ ] Слить feature/phase-3-reflexion
- [ ] Слить agents_migration
- [ ] Слить feature/agent-optimization-research
- [ ] Добавить неотслеживаемые файлы
- [ ] Запустить тесты
- [ ] Проверить работоспособность
- [ ] Удалить устаревшие ветки

## Временные оценки

- Подготовка: 15 минут
- Слияние chore/memory-hardening: 30 минут
- Слияние feature/phase-3-reflexion: 60 минут
- Слияние agents_migration: 90 минут
- Слияние feature/agent-optimization-research: 30 минут
- Тестирование и проверка: 45 минут

**Общее время:** ~4 часа

---

**Рекомендация:** Начать с поэтапного слияния, это самый безопасный подход.
