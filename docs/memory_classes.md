# MemoryClass: архитектура, структура и сценарии

## Общая идея
MemoryClass — универсальный интерфейс для работы с коллекциями памяти (Memory, Experience, Insight, Persona, UserFacts, ChatGPTMemory и др.) в проекте Mark AI. Все операции (insert, search, snapshot) реализуются через обёртки, зарегистрированные в едином реестре.

## Интерфейс MemoryClass
- insert(data: dict) -> str
- search(query: str, limit: int = 3) -> list[dict]
- link(source_id: str, target_id: str) -> None
- snapshot() -> dict
- to_dict() -> dict

## Сценарии использования
- Вся работа с памятью (retrieval, анализ, снапшоты) идёт через MemoryClass-обёртки, а не напрямую через Weaviate SDK.
- Для добавления новой коллекции — реализовать обёртку, зарегистрировать в реестре, добавить тесты по шаблону.
- Логирование всех действий критика (анализ, подъём, ошибка, snapshot) через CriticLogMemoryWrapper
- Поиск и анализ логов критика для аудита, отладки, автоматизации

## Примеры коллекций и их структуры
### Memory
- sender: str
- message: str
- timestamp: str (RFC3339)
- importance: float
- session_id: str
- tags: list[str]

### Experience
- summary: str
- source_ids: list[str]
- timestamp: str
- session_id: str
- elevated: bool
- manual_elevate: bool  # ручной подъём, участвует в автоматизации инсайтов

> Если manual_elevate=True и elevated=False, Experience будет автоматически поднят в инсайт при следующей автоматизации.

### Insight
- insight: str
- source_ids: list[str]
- timestamp: str

### Persona
- name: str
- description: str
- traits: str
- timestamp: str

### UserFacts
- user_id: str
- key: str
- value: str
- confidence: float
- timestamp: str

### ChatGPTMemory
- text: str
- timestamp: str
- session_id: str
- user_id: str  # сохраняется для новых данных, не используется для поиска

### CriticLog
- action: str (тип действия: анализ, подъём, ошибка, snapshot)
- details: str (подробности, json/dict в строке)
- timestamp: str
- session_id: str
- status: str (success/error)
- error_message: str
- source_ids: list[str] (ссылки на объекты Experience/Insight/Memory)

## Пример использования
```python
mm = MemoryManager()
wrapper = mm.memory_registry.get("Experience")
data = {"summary": "Q: ...", "source_ids": ["id1"], "timestamp": mm._get_rfc3339_timestamp(), "session_id": "..."}
id = wrapper.insert(data)
results = wrapper.search("ключевое слово")
snap = wrapper.snapshot()
```

---
# Retrieval-блок: структура, лимиты, fallback

## Порядок и приоритеты классов
1. Document
2. Insight
3. Experience
4. ChatGPTMemory
5. Memory

## Лимиты
- Не более 3-4 объектов на класс
- Всего не более 10 retrieval-объектов в prompt

## Fallback
- Если retrieval пустой — брать из Memory

## Формат retrieval-блока
```
--- DOCUMENT ---
...
--- INSIGHT ---
...
--- EXPERIENCE ---
...
--- CHATGPTMEMORY ---
...
--- MEMORY ---
...
```

## Вставка в prompt
- retrieval-блок вставляется после system prompt (Persona), до истории диалога

---
# Шаблон для новых MemoryClass-обёрток и тестов
- Копировать структуру существующих обёрток (см. memory_manager.py)
- Для тестов — использовать шаблон из test_memoryclass_wrappers.py
- Все тесты запускать внутри Docker-контейнера app

---
# Контрольные точки
- Все коллекции работают через MemoryClass
- Retrieval, snapshot, анализ — только через обёртки
- Все функции покрыты тестами
- Документация актуальна и обновляется при изменениях архитектуры 

## ⚠️ Стратегия user_id (глобальный режим)
- В retrieval и поиске фильтрация по user_id не используется, все данные доступны глобально.
- user_id сохраняется только для новых данных (например, Telegram chat_id), чтобы в будущем можно было перейти к мульти-пользовательскому режиму без миграции.
- В тестах и примерах не используйте фильтрацию по user_id.
- Для перехода к мульти-пользовательскому режиму потребуется только добавить фильтрацию по user_id в retrieval.
--- 