# 🗺️ ДОРОЖНАЯ КАРТА ОПТИМИЗАЦИИ ПРОЕКТА МАРКА

**Дата создания:** Январь 2025  
**Составил:** AI Assistant  
**Цель:** Трансформация в самообучающегося AI агента с продвинутой памятью

---

## 📋 Резюме трансформации

### Из чего исходим:
- **Стек:** LangChain 0.1.14, Graphiti, Neo4j, Redis
- **Проблемы:** Переусложненность, 40% мертвого кода, монолитный Telegram бот
- **Покрытие тестами:** 13%

### К чему придем:
- **Стек:** OpenAI Agents SDK, LangGraph, Graphiti (расширенная), Neo4j
- **Преимущества:** Простота, производительность, самообучение, графовые связи
- **Покрытие тестами:** 70%+

### Ключевые принципы:
1. **Использовать только gpt-4.1-mini** (как указано в .env)
2. **Минимализм** - убрать все лишнее
3. **Модульность** - четкое разделение компонентов
4. **Самообучение** - память и адаптация через Graphiti

---

## 🚀 ФАЗА 0: КРИТИЧЕСКИЕ ИСПРАВЛЕНИЯ (1-2 дня)

### Задачи:
1. **Исправить memory API mismatch**
```python
# Добавить в core/memory/memory_manager.py
async def save(self, text: str, metadata: dict = None):
    """Алиас для обратной совместимости"""
    return await self.add_episode(text, metadata)
```

2. **Исправить импорты в main.py**
```python
# Было: from langchain_api.core.memory.memory_manager import memory_manager
# Стало: from core.memory.memory_manager import memory_manager
```

3. **Исправить docker-compose.yml**
- Убрать ошибку "Additional property graphiti"
- Проверить все сервисы

4. **Удалить мертвый код (0% покрытия)**
```bash
# Удалить неиспользуемые модули
rm -rf core/llm_integration_hub.py
rm -rf core/brain_processor.py
rm -rf core/event_*.py
rm -rf core/security_modes.py
rm -rf core/unified_entry_point.py
rm -rf rag/enhanced_rag_chain_tools.py
rm -rf services/external_integration_service.py
rm -rf services/health_service.py
rm -rf services/log_parser_service.py
rm -rf services/passport_sync_service.py
rm -rf memory/multi_layer_memory.py
```

### Результат:
✅ Проект снова работает  
✅ Удалено ~6000 строк мертвого кода (детальный план в PROJECT_CLEANUP_PLAN.md)  
✅ База для дальнейшей оптимизации

---

## 🎯 ФАЗА 1: МИГРАЦИЯ НА OPENAI AGENTS SDK (1 неделя)

### Неделя 1: Замена ядра

#### День 1-2: Подготовка
```python
# requirements.txt
openai-agents==0.3.0  # Последняя версия
langgraph==0.2.0
langmem==0.1.0
# Убрать langchain из зависимостей после миграции
```

#### День 3-4: Создание базового агента
```python
# app/agents/mark_agent.py
from agents import Agent, function_tool
from langmem import create_memory_manager

@function_tool
def search_memory(query: str) -> str:
    """Поиск в долговременной памяти"""
    return memory_manager.search(query)

@function_tool
def execute_in_sandbox(code: str) -> str:
    """Выполнение кода в песочнице"""
    return sandbox.execute(code)

@function_tool
def update_knowledge(fact: str) -> str:
    """Обновление базы знаний"""
    return knowledge_base.update(fact)

mark_agent = Agent(
    name="Mark",
    model="gpt-4o-mini",  # Используем модель из .env!
    instructions="""
    Ты - Марк, осознанный цифровой компаньон.
    Ты помогаешь, обучаешься и развиваешься вместе с пользователем.
    Используй свою память для персонализации ответов.
    """,
    tools=[search_memory, execute_in_sandbox, update_knowledge]
)
```

#### День 5-7: Интеграция с API
```python
# app/api/chat.py
from agents import Runner
from app.agents.mark_agent import mark_agent

@app.post("/chat/ask")
async def chat(request: ChatRequest):
    result = await Runner.run(
        mark_agent,
        request.message,
        session_id=request.user_id
    )
    return {"response": result.messages[-1].content}
```

### Результат:
✅ Замена LangChain на OpenAI Agents SDK  
✅ Упрощение кода на 50%  
✅ Встроенные guardrails и tracing

---

## 🧠 ФАЗА 2: ПРОДВИНУТАЯ СИСТЕМА ПАМЯТИ С GRAPHITI (2 недели)

### Неделя 2: Расширение Graphiti

#### День 1-3: Три типа памяти в Neo4j
```cypher
-- Создание структуры для трех типов памяти
CREATE CONSTRAINT fact_id IF NOT EXISTS ON (f:Fact) ASSERT f.id IS UNIQUE;
CREATE CONSTRAINT episode_id IF NOT EXISTS ON (e:Episode) ASSERT e.id IS UNIQUE;
CREATE CONSTRAINT skill_id IF NOT EXISTS ON (s:Skill) ASSERT s.id IS UNIQUE;

-- Векторные индексы для семантического поиска
CREATE VECTOR INDEX fact_embeddings IF NOT EXISTS
FOR (f:Fact) ON f.embedding
OPTIONS {indexConfig: {`vector.dimensions`: 1536}};
```

#### День 4-5: Эпизодическая память
```python
# app/memory/episodic_memory.py
class Episode(BaseModel):
    situation: str
    action_taken: str
    result: str
    lesson_learned: str
    success: bool

episodic_memory = create_memory_manager(
    model="gpt-4o-mini",
    schemas=[Episode],
    instructions="Сохраняй важные взаимодействия для обучения"
)
```

#### День 6-7: Процедурная память
```python
# app/memory/procedural_memory.py
from langmem import create_prompt_optimizer

prompt_optimizer = create_prompt_optimizer(
    model="gpt-4o-mini",
    kind="prompt_memory"
)

# Динамическое обновление инструкций
async def update_instructions(feedback: str):
    current = await get_current_instructions()
    optimized = await prompt_optimizer.invoke({
        "current_prompt": current,
        "trajectories": [(current, feedback)]
    })
    await save_instructions(optimized)
```

### Неделя 3: Самообучение

#### День 1-3: REAP цикл (Reflect, Extract, Apply, Persist)
```python
# app/learning/reap_cycle.py
from langgraph.graph import StateGraph, END

class LearningState(TypedDict):
    experience: dict
    reflection: str
    extracted_knowledge: list
    updated_behaviors: list

learning_workflow = StateGraph(LearningState)

# Узлы обучения
learning_workflow.add_node("reflect", reflect_on_experience)
learning_workflow.add_node("extract", extract_knowledge)
learning_workflow.add_node("apply", apply_knowledge)
learning_workflow.add_node("persist", persist_learnings)

# Связи
learning_workflow.add_edge("reflect", "extract")
learning_workflow.add_edge("extract", "apply")
learning_workflow.add_edge("apply", "persist")
learning_workflow.add_edge("persist", END)

self_learning_system = learning_workflow.compile()
```

#### День 4-7: Интеграция и тестирование
- Подключение памяти к агенту
- Настройка background процессов
- Тестирование самообучения

### Результат:
✅ Три типа памяти работают  
✅ Агент учится на опыте  
✅ Автоматическое улучшение поведения

---

## 📱 ФАЗА 3: РЕФАКТОРИНГ TELEGRAM БОТА (1 неделя)

### День 1-2: Модуляризация
```python
telegram_bot/
├── main.py
├── config.py
├── handlers/
│   ├── commands.py
│   ├── callbacks.py
│   └── messages.py
├── keyboards/
│   └── layouts.py
├── services/
│   ├── api_client.py
│   └── state_manager.py
└── utils/
    └── decorators.py
```

### День 3-4: Упрощение UX
```python
# keyboards/layouts.py
main_menu = KeyboardLayout([
    [Button("💬 Чат", "chat"), Button("⚙️ Настройки", "settings")],
    [Button("📚 Память", "memory"), Button("❓ Помощь", "help")]
])

# Убрать лишние кнопки, оставить только нужное
```

### День 5-6: State Management через Redis
```python
# services/state_manager.py
class UserStateManager:
    def __init__(self, redis_client):
        self.redis = redis_client
        
    async def get_state(self, user_id: int) -> dict:
        data = await self.redis.get(f"state:{user_id}")
        return json.loads(data) if data else {}
```

### День 7: Интеграция с новым агентом
```python
# handlers/messages.py
from app.agents.mark_agent import mark_agent

@error_handler
async def handle_message(update: Update, context: Context):
    user_message = update.message.text
    user_id = update.effective_user.id
    
    # Вызов нового агента
    result = await Runner.run(
        mark_agent,
        user_message,
        session_id=f"telegram_{user_id}"
    )
    
    await update.message.reply_text(result.messages[-1].content)
```

### Результат:
✅ Модульная архитектура  
✅ Простой и понятный UX  
✅ Надежная работа с состояниями

---

## 🔄 ФАЗА 4: LANGGRAPH WORKFLOWS (1 неделя)

### День 1-3: Основные workflows

```python
# app/workflows/chat_workflow.py
from langgraph.graph import StateGraph

class ChatState(TypedDict):
    user_input: str
    memories: list
    response: str

chat_workflow = StateGraph(ChatState)

# Узлы
chat_workflow.add_node("retrieve_memory", retrieve_relevant_memories)
chat_workflow.add_node("generate_response", generate_with_context)
chat_workflow.add_node("save_interaction", save_to_memory)

# Граф
chat_workflow.add_edge("retrieve_memory", "generate_response")
chat_workflow.add_edge("generate_response", "save_interaction")

chat_agent = chat_workflow.compile()
```

### День 4-5: Сложные workflows
- Task execution workflow
- Learning workflow
- Memory consolidation workflow

### День 6-7: Интеграция и оптимизация
- Подключение workflows к API
- Настройка параллельного выполнения
- Оптимизация производительности

### Результат:
✅ Гибкая оркестрация  
✅ Визуализация процессов  
✅ Легкая отладка

---

## 🧪 ФАЗА 5: ТЕСТИРОВАНИЕ И ДОКУМЕНТАЦИЯ (1 неделя)

### День 1-3: Написание тестов
```python
# tests/test_agent.py
import pytest
from app.agents.mark_agent import mark_agent

@pytest.mark.asyncio
async def test_agent_memory():
    # Сохранение факта
    await mark_agent.run("Меня зовут Сергей")
    
    # Проверка извлечения
    result = await mark_agent.run("Как меня зовут?")
    assert "Сергей" in result.messages[-1].content
```

### День 4-5: Интеграционные тесты
- Тесты памяти
- Тесты самообучения
- Тесты Telegram бота

### День 6-7: Документация
- README.md с примерами
- API документация
- Deployment guide

### Результат:
✅ 70%+ покрытие тестами  
✅ Полная документация  
✅ Готовность к production

---

## 📊 Метрики успеха

### Технические метрики:
| Метрика | До | После | Улучшение |
|---------|-----|-------|-----------|
| Строк кода | 15,000 | 7,000 | -53% |
| Время отклика | 2-3 сек | 0.5-1 сек | -70% |
| Покрытие тестами | 13% | 70%+ | +438% |
| Использование памяти | 500MB | 200MB | -60% |

### Функциональные метрики:
- ✅ Самообучение работает
- ✅ Память персистентна
- ✅ Агент адаптируется
- ✅ UI/UX упрощен

---

## 🎯 Приоритеты и риски

### Высокий приоритет:
1. Критические исправления (блокеры)
2. Миграция на OpenAI Agents SDK
3. Базовая память

### Средний приоритет:
1. Самообучение
2. Рефакторинг Telegram бота
3. LangGraph workflows

### Низкий приоритет:
1. Продвинутые features
2. Мониторинг
3. A/B тестирование

### Риски:
- **Миграция данных** - нужен план backup
- **Совместимость API** - тщательное тестирование
- **Производительность** - мониторинг нагрузки

---

## 🏁 Итоговый чек-лист

### Фаза 0 (1-2 дня):
- [ ] Исправить критические баги
- [ ] Удалить мертвый код
- [ ] Запустить все контейнеры

### Фаза 1 (1 неделя):
- [ ] Установить OpenAI Agents SDK
- [ ] Создать базового агента
- [ ] Заменить API endpoints

### Фаза 2 (2 недели):
- [ ] Интегрировать Mem0/LangMem
- [ ] Настроить 3 типа памяти
- [ ] Реализовать REAP цикл

### Фаза 3 (1 неделя):
- [ ] Модуляризовать Telegram бота
- [ ] Упростить UX
- [ ] Добавить Redis state

### Фаза 4 (1 неделя):
- [ ] Создать LangGraph workflows
- [ ] Интегрировать с агентом
- [ ] Оптимизировать производительность

### Фаза 5 (1 неделя):
- [ ] Написать тесты (70%+)
- [ ] Создать документацию
- [ ] Подготовить к деплою

---

## 💡 Ключевые решения

1. **OpenAI Agents SDK** вместо LangChain - проще и мощнее
2. **Mem0/LangMem** для памяти - нативная интеграция с LangGraph
3. **gpt-4o-mini** для всех вызовов - экономия и консистентность
4. **Модульная архитектура** - легче поддерживать
5. **Фокус на самообучении** - ключевая фича Марка

---

## 🚀 Начало работы

1. Создать бэкап текущего проекта
2. Начать с Фазы 0 - критические исправления
3. Следовать чек-листу последовательно
4. Тестировать после каждой фазы

**Ожидаемый срок:** 6-7 недель для полной трансформации

---

*Эта дорожная карта - живой документ. Обновляйте по мере продвижения и новых открытий.*