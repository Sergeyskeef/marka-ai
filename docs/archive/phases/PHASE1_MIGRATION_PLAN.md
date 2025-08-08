# 📋 ПЛАН МИГРАЦИИ НА OPENAI AGENTS SDK

**Фаза 1:** Миграция с LangChain на OpenAI Agents SDK  
**Цель:** Заменить LangChain на более простой и эффективный OpenAI Agents SDK

---

## 🔍 Анализ текущей ситуации

### Текущий стек:
- **LangChain 0.1.14** - устаревшая версия
- **langchain_openai 0.1.6** - обертка для OpenAI
- **openai-agents 0.2.4** - уже установлен, но не используется
- **simple_chat.py** - основная логика чата на LangChain

### Что нужно мигрировать:
1. **simple_chat.py** - основная логика общения
2. **Инструменты (tools)** - текущие функции на LangChain
3. **Память (memory)** - интеграция с Graphiti
4. **Промпты** - система управления промптами

---

## 🏗️ Архитектура на OpenAI Agents SDK

### 1. Базовая структура агента Марка

```python
# app/agents/mark_agent.py
from openai import AsyncOpenAI
from typing import List, Dict, Any
import json

class MarkAgent:
    def __init__(self, client: AsyncOpenAI, model: str = "gpt-4.1-mini"):
        self.client = client
        self.model = model
        self.tools = []
        
    async def chat(
        self, 
        message: str, 
        context: List[Dict[str, Any]] = None,
        tools: List[Any] = None
    ) -> str:
        """Основной метод общения"""
        messages = self._prepare_messages(message, context)
        
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            tools=tools or self.tools,
            tool_choice="auto" if tools else None
        )
        
        return await self._process_response(response)
```

### 2. Система инструментов (Tools)

```python
# app/agents/tools.py
from typing import Callable, Dict, Any
import json

def create_openai_tool(func: Callable) -> Dict[str, Any]:
    """Конвертер функции в OpenAI tool"""
    return {
        "type": "function",
        "function": {
            "name": func.__name__,
            "description": func.__doc__,
            "parameters": {
                "type": "object",
                "properties": extract_parameters(func),
                "required": extract_required_params(func)
            }
        }
    }

# Пример инструмента
async def search_memory(query: str, limit: int = 5) -> str:
    """Поиск информации в памяти агента"""
    results = await memory_manager.search_episodes(query, limit)
    return json.dumps(results, ensure_ascii=False)

async def save_to_memory(text: str, metadata: Dict[str, Any] = None) -> str:
    """Сохранение информации в память"""
    result = await memory_manager.save(text, metadata)
    return f"Сохранено в память: {result.get('id', 'unknown')}"
```

### 3. Интеграция с Graphiti

```python
# app/agents/memory_integration.py
from core.memory.memory_manager import memory_manager

class MemoryTools:
    @staticmethod
    async def search(query: str, limit: int = 5) -> List[Dict]:
        """Поиск в памяти через Graphiti"""
        return await memory_manager.search_episodes(query, limit)
    
    @staticmethod
    async def save(text: str, context: Dict = None) -> Dict:
        """Сохранение в память"""
        metadata = {
            "source": "agent_interaction",
            "timestamp": datetime.now().isoformat(),
            **context
        }
        return await memory_manager.save(text, metadata)
    
    @staticmethod
    async def get_context(user_id: str, limit: int = 10) -> List[Dict]:
        """Получение контекста пользователя"""
        # Гибридный поиск по user_id
        return await memory_manager.hybrid_search(
            query=f"user:{user_id}",
            user_id=user_id,
            k=limit
        )
```

---

## 📝 План реализации

### Шаг 1: Создание базового агента (День 1)
1. Создать директорию `app/agents/`
2. Реализовать `MarkAgent` класс
3. Настроить инициализацию с моделью `gpt-4.1-mini`
4. Добавить базовые методы chat и обработки

### Шаг 2: Миграция инструментов (День 2)
1. Конвертировать существующие tools в OpenAI формат
2. Создать декоратор `@openai_tool` для автоматической конвертации
3. Интегрировать memory_tools
4. Добавить sandbox_tools

### Шаг 3: Замена simple_chat (День 3)
1. Создать новый `app/agents/chat_handler.py`
2. Перенести логику из `simple_chat.py`
3. Использовать MarkAgent вместо LangChain
4. Сохранить обратную совместимость API

### Шаг 4: Интеграция с FastAPI (День 4)
1. Обновить эндпоинты в `main.py`
2. Заменить LangChain импорты
3. Настроить dependency injection для агента
4. Добавить middleware для трассировки

### Шаг 5: Тестирование и оптимизация (День 5)
1. Написать unit тесты для агента
2. Интеграционные тесты с Graphiti
3. Нагрузочное тестирование
4. Оптимизация производительности

---

## 🎯 Преимущества миграции

### До (LangChain):
```python
# Сложная цепочка вызовов
from langchain.chains import LLMChain
from langchain.prompts import PromptTemplate
from langchain_openai import ChatOpenAI

llm = ChatOpenAI(model="gpt-4.1-mini")
prompt = PromptTemplate(...)
chain = LLMChain(llm=llm, prompt=prompt)
result = await chain.arun({"input": message})
```

### После (OpenAI SDK):
```python
# Прямой вызов
response = await client.chat.completions.create(
    model="gpt-4.1-mini",
    messages=[{"role": "user", "content": message}],
    tools=tools
)
```

### Выигрыш:
- ✅ Меньше абстракций (-70% кода)
- ✅ Прямой контроль над API
- ✅ Нативная поддержка tools
- ✅ Лучшая производительность
- ✅ Проще отладка

---

## ⚠️ Риски и митигация

1. **Обратная совместимость**
   - Риск: Сломать существующие интеграции
   - Митигация: Adapter layer для старого API

2. **Потеря функциональности**
   - Риск: LangChain features могут быть нужны
   - Митигация: Поэтапная миграция с проверкой

3. **Интеграция с памятью**
   - Риск: Graphiti может не работать
   - Митигация: Тщательное тестирование

---

## 📊 Метрики успеха

- **Размер кода:** -50% (убираем LangChain abstractions)
- **Скорость ответа:** -30% (прямые вызовы)
- **Потребление памяти:** -40%
- **Простота кода:** 10/10 vs 5/10

---

*Следующий шаг: Начать с создания базового агента MarkAgent*