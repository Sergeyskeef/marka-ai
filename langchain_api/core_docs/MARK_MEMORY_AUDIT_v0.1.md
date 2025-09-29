# Аудит памяти — v0.1 (инициализация)

Документ описывает текущее состояние подсистемы памяти, риски и план улучшений.

## 1) Что есть сейчас
- **GraphitiMemoryAdapter** (`core/memory/graphiti_adapter.py`) — HTTP-клиент к Graphiti/Neo4j; создаёт `Episode`, публикует события в event bus, частично инвалидация кеша.
- **MemoryManager** (`core/memory/memory_manager.py`) — фасад с методами `add_episode/save/search_episodes/hybrid_search/list/get/health_check`. В `hybrid_search` вычисляется эмбеддинг запроса через OpenAI и передаётся как `filters[query_embedding]`.
- **HybridSearchEngine** (`core/memory/hybrid_search.py`) — пока выполняет keyword-поиск через Graphiti + опциональный косинусный реранк по эмбеддингу, если он найден в metadata элементов.
- **EnhancedMemory** (`core/memory/enhanced_memory.py`) — in-memory реализация для тестов рефлексии/инсайтов.
- **Neo4jDirect** (`app/memory/neo4j_direct.py`) — прямые запросы к Neo4j (используются точечно).

## 2) Наблюдаемые дельты/риски
1. **Отсутствует единый контракт/поток хранения**: местами запись/чтение идут разными путями (Graphiti HTTP vs Neo4j direct). Нет явных хуков `pre_store/post_retrieve/consolidate/distill`.
2. **Эмбеддинги для элементов не сохраняются**: HybridSearch ожидает `metadata.embedding`, но `create_episode` не пишет эмбеддинг (нет расчёта и поля). Из-за этого гибридность ограничена keyword-слоем.
3. **Ассимиляция опыта**: нет регулярной консолидации эпизодов в инсайты/навыки (правила срабатывания, расписание).
4. **Explainability (xtrace)**: отсутствует трек «что из памяти использовано» в ответах.
5. **Политики секретов**: при `compose config`/логах возможна утечка env; нужна централизованная редакция (маскирование).
6. **Тестовое покрытие**: есть unit-тесты для EnhancedMemory, но нет интеграционных тестов сквозного потока `store→search→consolidate` с Graphiti/Neo4j.

## 3) Цели M1 (память+объяснимость)
- Единый фасад **MemoryService** с контрактом: `store`, `retrieve`, `hybrid_search`, `consolidate`, `distill`, `link`, `health`.
- Поддержка эмбеддингов: расчёт при `store` (OpenAI или локально) и сохранение в metadata для элементов.
- Мини-конвейер REAP: post-answer → self-eval → insight → `store`.
- `xtrace` в ответе: `summary`, `steps`, `used_memory` (id/preview/score).
- Интеграционные тесты: фикстуры Graphiti/Neo4j, сценарии записи/поиска/консолидации.

## 4) План работ (первые итерации)
1. **Спецификация и слой MemoryService** (фасад над Graphiti):
   - Модуль `core/memory/service.py`: интерфейсы и адаптеры.
   - Хуки: `pre_store` (редакция секретов/нормализация), `post_store` (инвалидация кеша/ссылки), `post_retrieve` (маркировка источников), `consolidate`, `distill`.
2. **Эмбеддинги при записи**:
   - Модуль `core/memory/embeddings.py` с драйвером (OpenAI `text-embedding-3-small` и плагины под локальные).
   - `GraphitiAdapter.create_episode` — доп. поле `embedding` в properties/metadata.
3. **HybridSearch улучшенный**:
   - Rerank по косинусу на всех элементах, если есть и у запроса, и у элемента.
   - Фоллбек, если нет эмбеддингов.
4. **Consolidation/Distill**:
   - Простые правила: после N эпизодов по одной теме — свёртка в инсайт/факт/навык.
   - Метки и связи в графе (`INSPIRES`, `PRODUCES`, `RELATES_TO`).
5. **xtrace**:
   - Обёртка ответа: `xtrace.summary/steps/used_memory`.
6. **Тесты**:
   - Unit + интеграционные (mock Graphiti API).

## 5) Definition of Done (память)
- [ ] Сквозные тесты: `store→retrieve/hybrid→consolidate→distill` проходят.
- [ ] Эмбеддинги сохраняются и участвуют в поиске.
- [ ] xtrace содержит `used_memory` (id/preview/score).
- [ ] Политики маскирования секретов включены.
- [ ] Документация и примеры кода обновлены.

## 6) Следующие шаги (операционно)
- Подготовить `MemoryService` спецификацию и каркас модулей.
- Включить запись эмбеддингов в Graphiti через адаптер.
- Добавить интеграционные тесты.

— v0.1, 2025-09-28
