## [2025-05-09] Интеграция RUBRIC, исправление proxy и обновление схемы памяти

### Краткое описание:
В рамках улучшения архитектуры RAG-агента были внедрены автоматическая критика (RUBRIC), поддержка новых полей в памяти, а также устранены ошибки с прокси для httpx.Client.

### Основные шаги:
- В класс Memory (Weaviate) добавлены поля: rubric_score, rubric_summary, rubric_justification (init_schema.py)
- needs_reflection, rubric_score, rubric_summary, rubric_justification теперь поддерживаются на всех уровнях памяти (MultiLayerMemory, MemoryManager)
- Везде заменён параметр proxies на proxy при создании httpx.Client (utils, memory, rag, scripts)
- Исправлена логика передачи proxy: теперь всегда передаётся строка, а не словарь (ошибка AttributeError устранена)
- Перезапущены docker-контейнеры после всех изменений
- Пересоздана схема Weaviate с новыми полями (init_schema.py)
- Проведён локальный тест (local_test.py): ошибки с proxy устранены, LLM отвечает корректно
- Все изменения протестированы, ошибок не обнаружено

### Проблемы и решения:
- Ошибка AttributeError: 'dict' object has no attribute 'url' — исправлено, теперь proxy передаётся как строка
- Ошибка NameError: name 'http_client' is not defined — исправлено, область видимости переменной скорректирована

### Следующий шаг:
Интеграционное тестирование цепочки с сохранением RUBRIC-полей в Weaviate и автоматической критикой. 