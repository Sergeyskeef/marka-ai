# 🎯 Финальный план действий по развитию Марка

## 📌 Ключевые уточнения

1. **Проект уже существует** - дорабатываем, а не создаем с нуля
2. **GraphitiMemory вместо Weaviate** - Neo4j через Graphiti для векторного поиска
3. **Ограниченные ресурсы** - 2 CPU, 4GB RAM
4. **Docker Compose** - продолжаем использовать текущую инфраструктуру
5. **Один пользователь сейчас** - но архитектура для масштабирования до 100

## 🚨 Фаза 1: Критическая безопасность (1 день)

### 1.1 Белый список команд в SandboxManager
**Файл**: `/workspace/sandbox/sandbox_manager.py`
**Время**: 2 часа

```python
# В __init__ добавить:
self.allowed_shell_commands = {
    'echo', 'printf', 'date', 'pwd', 'whoami',
    'ls', 'dir', 'find', 'grep', 'sed', 'awk',
    'sort', 'uniq', 'wc', 'head', 'tail', 'cat',
    'python', 'python3', 'pip', 'npm', 'node'
}

# Новый метод:
def _check_shell_command(self, command: str) -> str | None:
    import shlex
    try:
        cmd_parts = shlex.split(command)
        base_cmd = cmd_parts[0].split('/')[-1] if cmd_parts else ""
        
        if base_cmd not in self.allowed_shell_commands:
            return f"Команда '{base_cmd}' не в белом списке"
            
        for pattern in self.dangerous_patterns:
            if re.search(pattern, command, re.IGNORECASE):
                return f"Обнаружен опасный паттерн: {pattern}"
                
        return None
    except Exception as e:
        return f"Ошибка парсинга команды: {str(e)}"

# В execute_command добавить:
if not command.startswith("python"):
    shell_error = self._check_shell_command(command)
    if shell_error:
        return CommandResult(
            success=False,
            output="",
            error=shell_error,
            command=command
        )
```

### 1.2 Расширить AST проверки
**Время**: 1 час

```python
# В dangerous_ast_nodes добавить:
self.network_modules = {'socket', 'urllib', 'requests', 'httpx', 'aiohttp'}
self.dangerous_builtins = {'eval', 'exec', 'compile', '__import__', 
                          'getattr', 'setattr', 'delattr', 
                          'globals', 'locals', 'vars'}

# В _check_dangerous_code расширить проверки
```

### 1.3 Тесты безопасности
**Файл**: `/workspace/tests/test_sandbox_security_enhanced.py`
**Время**: 1 час

## 🔥 Фаза 2: Система планирования (2-3 дня)

### 2.1 Полная реализация TaskPlanner
**Файл**: `/workspace/sandbox/task_planning_system.py`
**Время**: 4 часа

Заменить все заглушки на рабочий код:
- Использовать `get_llm_client()` из `langchain_api.core.llm`
- Интегрировать с `GraphitiMemoryAdapter` для сохранения планов
- Реализовать декомпозицию задач через LLM

### 2.2 API endpoints для планирования
**Файл**: `/workspace/main.py`
**Время**: 2 часа

```python
# После строки 187:
from langchain_api.sandbox.task_planning_system import TaskPlanner
task_planner = TaskPlanner()

# Новые endpoints:
@app.post("/plan/create", tags=["planning"])
async def create_plan(request: PlanRequest):
    plan = await task_planner.create_plan(request.goal, {
        "user_id": request.user_id,
        "chat_id": request.chat_id
    })
    return {"success": True, "plan": plan.to_dict()}

@app.get("/plan/{plan_id}/status", tags=["planning"])
async def get_plan_status(plan_id: str):
    return task_planner.get_plan_status(plan_id)

@app.post("/plan/{plan_id}/execute", tags=["planning"])
async def execute_plan(plan_id: str):
    return await task_planner.execute_plan(plan_id)
```

### 2.3 Обновить команды бота
**Файл**: `/workspace/telegram_bot/bot.py`
**Время**: 2 часа

1. **Заменить заглушку decompose_cmd** (строка 495):
```python
async def decompose_cmd(update, context):
    """Создает план выполнения задачи"""
    if not context.args:
        keyboard = [
            [InlineKeyboardButton("📝 Написать код", callback_data="plan:code")],
            [InlineKeyboardButton("🔧 Исправить баг", callback_data="plan:fix")],
            [InlineKeyboardButton("📚 Изучить тему", callback_data="plan:learn")]
        ]
        await update.message.reply_text(
            "🎯 Что планируем?",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    
    goal = ' '.join(context.args)
    msg = await update.message.reply_text("🤔 Создаю план...")
    
    # Вызов API
    response = await _post("/plan/create", {
        "goal": goal,
        "user_id": str(update.effective_user.id)
    })
    
    if response.status_code == 200:
        plan = response.json()["plan"]
        text = format_plan(plan)  # Форматирование плана
        
        keyboard = [
            [
                InlineKeyboardButton("▶️ Выполнить", callback_data=f"plan:exec:{plan['id']}"),
                InlineKeyboardButton("📊 Статус", callback_data=f"plan:status:{plan['id']}")
            ]
        ]
        
        await msg.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
```

2. **Исправить кнопку "👨‍💻 code"** (строка 975):
```python
{
    "name": "code_mode",
    "description": "Переключить в режим выполнения кода",
    "triggers": ["👨‍💻 code", "code mode", "/code"],
    "action": run_code_cmd,  # Вместо lambda
}
```

## ⚡ Фаза 3: Event Bus и интеграция (2 дня)

### 3.1 Создать Event Bus
**Файл**: `/workspace/core/event_bus.py`
**Время**: 3 часа

```python
import asyncio
import logging
from typing import Callable, Dict, List, Any
from collections import defaultdict
from datetime import datetime

logger = logging.getLogger(__name__)

class EventBus:
    def __init__(self):
        self.subscribers: Dict[str, List[Callable]] = defaultdict(list)
        self.event_history: List[Dict] = []
        
    def subscribe(self, event_type: str, handler: Callable):
        self.subscribers[event_type].append(handler)
        
    async def publish(self, event_type: str, data: Dict[str, Any], source: str = None):
        event = {
            "type": event_type,
            "data": data,
            "timestamp": datetime.now(),
            "source": source
        }
        
        self.event_history.append(event)
        
        # Вызываем обработчики
        for handler in self.subscribers[event_type]:
            try:
                await self._safe_call(handler, event)
            except Exception as e:
                logger.error(f"Handler error: {e}")
                
    async def _safe_call(self, handler, event):
        result = handler(event)
        if asyncio.iscoroutine(result):
            await result

# Глобальный экземпляр
event_bus = EventBus()
```

### 3.2 Интеграция с компонентами
**Время**: 3 часа

1. **GraphitiMemoryAdapter** - публиковать события:
   - `memory.stored` при сохранении
   - `memory.searched` при поиске

2. **SandboxManager** - публиковать события:
   - `sandbox.executed` при выполнении
   - `sandbox.blocked` при блокировке

3. **TaskPlanner** - публиковать события:
   - `plan.created` при создании
   - `plan.executed` при выполнении

## 💫 Фаза 4: Самосознание (1 день)

### 4.1 Расширить MarkSelfAwareness
**Файл**: `/workspace/sandbox/self_awareness.py`
**Время**: 3 часа

Добавить методы:
```python
def analyze_own_code(self, file_path: str) -> Dict[str, Any]:
    """Анализирует файл из проекта"""
    # AST анализ
    # Возврат функций, классов, зависимостей
    
def diagnose_error(self, error_type: str, error_message: str) -> Dict[str, Any]:
    """Диагностирует ошибку"""
    # Анализ типа ошибки
    # Поиск в коде
    # Предложение решений
```

### 4.2 Команды для бота
**Время**: 2 часа

Добавить в COMMANDS_REGISTRY:
```python
{
    "name": "/analyze",
    "description": "Анализировать файл проекта",
    "triggers": ["/analyze", "проанализируй файл"],
    "action": analyze_file_cmd,
},
{
    "name": "/diagnose", 
    "description": "Диагностировать ошибку",
    "triggers": ["/diagnose", "диагностика"],
    "action": diagnose_error_cmd,
}
```

## 📊 Метрики успеха

1. **Безопасность**: 0 успешных эксплойтов песочницы
2. **Планирование**: Планы сохраняются и выполняются
3. **Интеграция**: Компоненты общаются через Event Bus
4. **Самосознание**: Марк может анализировать свой код
5. **Производительность**: < 2 сек отклик, < 512MB на песочницу

## 🚀 Порядок выполнения

```bash
# День 1: Безопасность
1. Обновить SandboxManager ✓
2. Написать тесты ✓
3. Проверить все эксплойты ✓

# День 2-3: Планирование
4. Реализовать TaskPlanner ✓
5. Добавить API endpoints ✓
6. Обновить команды бота ✓

# День 4-5: Интеграция
7. Создать Event Bus ✓
8. Подключить компоненты ✓
9. Расширить самосознание ✓

# День 6: Финализация
10. Тестирование всей системы ✓
11. Оптимизация производительности ✓
12. Документация ✓
```

## ⚠️ Важные моменты

1. **Не ломаем существующее** - все изменения обратно совместимы
2. **GraphitiMemory работает** - не трогаем, только добавляем события
3. **Тестируем каждый шаг** - после каждого изменения запускаем тесты
4. **Коммитим часто** - маленькие атомарные коммиты

## 🎬 Начинаем!

```bash
cd /workspace
git checkout -b feature/security-and-planning
cd sandbox
# Начинаем с критической безопасности...
```

## 📁 Неиспользуемые модули (для справки)

По результатам анализа, следующие модули не используются активно, но оставлены для обратной совместимости:

1. **Память (legacy от Weaviate)**:
   - `/workspace/memory/graphiti_memory.py` - дубликат адаптера
   - `/workspace/core/memory/base_memory.py` - используется только в enhanced_memory
   - `/workspace/core/memory/enhanced_memory.py` - может пригодиться в будущем
   - `/workspace/core/memory/schema.py` - старая схема для Weaviate

2. **Типы памяти из marka_passport.json**:
   - Memory, Experience, Insight, Persona, UserFacts, ChatGPTMemory
   - Сейчас используется единый тип "episodes" в GraphitiMemory

3. **Возможные старые файлы**:
   - weaviate_tools/* (если существует)
   - Любые файлы с упоминанием weaviate в названии

**Рекомендация**: Не удалять эти файлы, они не мешают работе системы.