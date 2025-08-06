# 📊 Анализ системы памяти проекта Марк

## 🔍 Текущее состояние

### ✅ Что реально работает:

1. **GraphitiMemoryAdapter** (`core/memory/graphiti_adapter.py`)
   - HTTP-клиент для работы с Graphiti Memory API
   - Используется как основной механизм памяти
   - Поддерживает кеширование через Redis
   - Имеет семафор для контроля параллелизма

2. **Graphiti Service** 
   - Отдельный сервис на `http://graphiti:7878`
   - Neo4j как backend для векторного поиска
   - Поддерживает операции: add_episodes, search, get_all_episodes

3. **MemoryManager** (`core/memory/memory_manager.py`)
   - Центральный менеджер памяти
   - Использует graphiti_adapter для операций
   - Методы: add_episode, search_episodes

### ⚠️ Устаревшие компоненты (не используются):

1. **Weaviate** - полностью удален из проекта:
   - В docker-compose.yml закомментирован
   - В requirements.txt закомментирован langchain-weaviate
   - НО: в `marka_passport.json` все еще указан Weaviate как storage

2. **MultiLayerMemory** - старая система с типами памяти:
   - Memory, Experience, Insight, Persona, UserFacts, ChatGPTMemory
   - Эти типы описаны в паспорте, но НЕ используются в текущей реализации
   - GraphitiMemory работает с единым типом "episodes"

3. **EnhancedMemory** (`core/memory/enhanced_memory.py`)
   - Используется только в тестах и reflection модуле
   - Не интегрирован в основной поток

### 📁 Неиспользуемые файлы:

1. `/workspace/memory/graphiti_memory.py` - дубликат адаптера
2. `/workspace/core/memory/base_memory.py` - используется только в enhanced_memory
3. `/workspace/core/memory/schema.py` - старая схема для Weaviate?

## 🎯 Рекомендации:

1. **Обновить marka_passport.json**:
   - Заменить "storage": "Weaviate" на "storage": "GraphitiMemory"
   - Упростить типы памяти до реально используемых

2. **Оставить как есть**:
   - enhanced_memory.py - может пригодиться в будущем
   - base_memory.py - базовый класс для расширения

3. **НЕ трогать**:
   - Старые файлы памяти - для обратной совместимости
   - weaviate_tools (если есть) - уже не используется

## 📊 Реальная архитектура памяти:

```
FastAPI (main.py)
    ↓
MemoryManager (memory_manager.py)
    ↓
GraphitiMemoryAdapter (graphiti_adapter.py)
    ↓ HTTP
Graphiti Service (:7878)
    ↓
Neo4j (векторный поиск + граф)
```

## ✅ Вывод:

Система памяти работает через GraphitiMemory + Neo4j. Многослойная память с разными типами (Memory, Experience, Insight и т.д.) - это legacy от Weaviate, сейчас не используется. Все работает через единый тип "episodes" в Graphiti.