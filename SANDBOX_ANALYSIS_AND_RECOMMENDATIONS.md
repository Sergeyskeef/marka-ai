# 🔍 Анализ песочницы и рекомендации по улучшению

## 📊 Резюме анализа

После глубокого анализа работы песочницы и связанных команд бота были выявлены следующие ключевые проблемы:

### 🚨 Критические проблемы безопасности (4 обнаружено)

1. **Недостаточная блокировка опасных команд**
   - Shell команды (`rm -rf /`, `cat /etc/passwd`) не блокируются
   - Сетевые операции (`wget`, `nc`) разрешены
   - Отсутствует белый список разрешенных команд

2. **Отсутствие изоляции на уровне Docker**
   - Нет ограничений capabilities
   - Отсутствует непривилегированный пользователь
   - Нет security profiles (AppArmor/SELinux)

## 🔧 Обнаруженные проблемы

### 1. Безопасность песочницы

**Текущее состояние:**
- ✅ Блокируются Python импорты: `os`, `sys`, `subprocess`
- ✅ Блокируются функции: `eval`, `exec`, `__import__`
- ❌ НЕ блокируются shell команды: `rm`, `cat`, `wget`, `nc`
- ❌ НЕ блокируются сетевые операции

**Риски:**
- Возможность удаления системных файлов
- Чтение конфиденциальной информации
- Загрузка и выполнение вредоносного кода
- Создание backdoor через сетевые соединения

### 2. Архитектура системы

**Проблемы:**
- Отсутствие директории `/sandbox` в runtime
- Синхронное выполнение команд блокирует API
- Нет системы очередей для длительных операций
- Отсутствует мониторинг и логирование выполнения

### 3. Пользовательский опыт

**Недостатки:**
- Нет подсветки синтаксиса в ответах
- Отсутствует история выполненных команд
- Примитивные сообщения об ошибках
- Нет индикации прогресса для длительных операций

## 📋 План действий

### 1. [КРИТИЧНО] Усиление безопасности песочницы (2-3 часа)

#### 1.1 Улучшить SandboxManager

```python
# Добавить в sandbox/sandbox_manager.py

class SandboxManager:
    def __init__(self):
        # Белый список безопасных shell команд
        self.allowed_shell_commands = {
            'echo', 'printf', 'date', 'pwd', 'whoami',
            'ls', 'dir', 'find', 'grep', 'sed', 'awk',
            'sort', 'uniq', 'wc', 'head', 'tail'
        }
        
        # Черный список опасных паттернов
        self.dangerous_patterns = [
            r'rm\s+-rf', r'rm\s+/', r'dd\s+if=',
            r'mkfs', r'format', r':(){ :|:& };:',  # fork bomb
            r'wget\s+http', r'curl\s+http', r'nc\s+-l',
            r'/etc/passwd', r'/etc/shadow', r'sudo',
            r'chmod\s+777', r'chown', r'kill\s+-9'
        ]

    def _check_shell_command(self, command: str) -> str | None:
        """Проверка shell команд на безопасность"""
        # Извлекаем первое слово команды
        cmd_parts = shlex.split(command)
        if not cmd_parts:
            return "Пустая команда"
            
        base_cmd = cmd_parts[0]
        
        # Проверяем белый список
        if base_cmd not in self.allowed_shell_commands:
            return f"Команда '{base_cmd}' не в белом списке"
            
        # Проверяем опасные паттерны
        for pattern in self.dangerous_patterns:
            if re.search(pattern, command, re.IGNORECASE):
                return f"Обнаружен опасный паттерн: {pattern}"
                
        return None
```

#### 1.2 Добавить проверку сетевых операций

```python
# Расширить dangerous_ast_nodes
self.dangerous_ast_nodes = {
    'Import': [
        'os', 'sys', 'subprocess', 'importlib', 
        'socket', 'urllib', 'requests', 'httpx',
        'ftplib', 'telnetlib', 'smtplib'
    ],
    'Call': [
        'eval', 'exec', 'compile', '__import__', 
        'open', 'file', 'input', 'raw_input',
        'globals', 'locals', 'vars', 'dir',
        'getattr', 'setattr', 'delattr', 'hasattr'
    ]
}
```

### 2. [ВЫСОКИЙ] Настройка Docker песочницы (3-4 часа)

#### 2.1 Создать Dockerfile для песочницы

```dockerfile
# Dockerfile.sandbox
FROM python:3.11-slim

# Создаем непривилегированного пользователя
RUN useradd -m -s /bin/bash -u 1000 sandbox && \
    mkdir -p /sandbox && \
    chown -R sandbox:sandbox /sandbox

# Устанавливаем только необходимые пакеты
RUN apt-get update && apt-get install -y \
    --no-install-recommends \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Копируем requirements
COPY requirements.txt /tmp/
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Переключаемся на непривилегированного пользователя
USER sandbox
WORKDIR /sandbox

# Ограничиваем сетевой доступ
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
```

#### 2.2 Обновить docker-compose.yml

```yaml
services:
  sandbox:
    build:
      context: .
      dockerfile: Dockerfile.sandbox
    volumes:
      - ./sandbox:/sandbox:rw
      - /tmp:/tmp:rw
    tmpfs:
      - /run:size=100M
      - /tmp:size=100M
    read_only: true
    security_opt:
      - no-new-privileges:true
      - seccomp:unconfined
    cap_drop:
      - ALL
    cap_add:
      - CHOWN
      - SETUID
      - SETGID
    mem_limit: 512m
    memswap_limit: 512m
    cpu_quota: 50000
    pids_limit: 100
    networks:
      - isolated
    
networks:
  isolated:
    driver: bridge
    internal: true
```

### 3. [СРЕДНИЙ] Улучшение UX бота (4-5 часов)

#### 3.1 Добавить подсветку синтаксиса

```python
# В telegram_bot/bot.py
from pygments import highlight
from pygments.lexers import PythonLexer, BashLexer, get_lexer_by_name
from pygments.formatters import TerminalFormatter

def format_code_output(code: str, language: str = 'python') -> str:
    """Форматирует код с подсветкой синтаксиса"""
    try:
        if language == 'python':
            lexer = PythonLexer()
        elif language in ['bash', 'shell']:
            lexer = BashLexer()
        else:
            lexer = get_lexer_by_name(language)
            
        return highlight(code, lexer, TerminalFormatter())
    except:
        return code
```

#### 3.2 Добавить историю команд

```python
# Добавить в bot.py
from collections import deque

class CommandHistory:
    def __init__(self, max_size=50):
        self.history = defaultdict(lambda: deque(maxlen=max_size))
    
    def add(self, user_id: int, command: str, result: str):
        self.history[user_id].append({
            'command': command,
            'result': result,
            'timestamp': datetime.now()
        })
    
    def get_last(self, user_id: int, n: int = 5):
        return list(self.history[user_id])[-n:]

# Глобальная история
command_history = CommandHistory()
```

#### 3.3 Улучшить inline кнопки

```python
def create_sandbox_keyboard() -> InlineKeyboardMarkup:
    """Создает клавиатуру для работы с песочницей"""
    keyboard = [
        [
            InlineKeyboardButton("📝 Python", callback_data="sandbox:python"),
            InlineKeyboardButton("🖥️ Shell", callback_data="sandbox:shell"),
            InlineKeyboardButton("📊 Статус", callback_data="sandbox:status")
        ],
        [
            InlineKeyboardButton("🔄 Синхронизация", callback_data="sandbox:sync"),
            InlineKeyboardButton("📜 История", callback_data="sandbox:history"),
            InlineKeyboardButton("🧹 Очистить", callback_data="sandbox:clear")
        ],
        [
            InlineKeyboardButton("❓ Помощь", callback_data="sandbox:help")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)
```

### 4. [НИЗКИЙ] Мониторинг и логирование (2-3 часа)

#### 4.1 Добавить метрики Prometheus

```python
# В core/metrics.py
from prometheus_client import Counter, Histogram, Gauge

# Метрики песочницы
sandbox_executions = Counter(
    'sandbox_executions_total',
    'Total number of sandbox executions',
    ['command_type', 'status']
)

sandbox_execution_time = Histogram(
    'sandbox_execution_duration_seconds',
    'Sandbox execution duration',
    ['command_type']
)

sandbox_active_sessions = Gauge(
    'sandbox_active_sessions',
    'Number of active sandbox sessions'
)
```

#### 4.2 Структурированное логирование

```python
import structlog

logger = structlog.get_logger()

# В SandboxManager
async def execute_command(self, command: str, **kwargs):
    start_time = time.time()
    
    logger.info(
        "sandbox_execution_started",
        command=command[:100],
        user_id=kwargs.get('user_id'),
        sandbox_id=kwargs.get('sandbox_id', 'default')
    )
    
    try:
        result = await self._execute(command, **kwargs)
        
        logger.info(
            "sandbox_execution_completed",
            command=command[:100],
            success=result.success,
            duration=time.time() - start_time,
            output_size=len(result.output)
        )
        
        return result
    except Exception as e:
        logger.error(
            "sandbox_execution_failed",
            command=command[:100],
            error=str(e),
            duration=time.time() - start_time
        )
        raise
```

## 🏆 Лучшие практики

### 1. Безопасность

1. **Принцип наименьших привилегий**
   - Запускать код от непривилегированного пользователя
   - Использовать только необходимые capabilities
   - Ограничить доступ к файловой системе

2. **Защита в глубину**
   - Проверка на уровне AST для Python
   - Белый список для shell команд
   - Изоляция на уровне Docker
   - Сетевая изоляция

3. **Аудит и мониторинг**
   - Логировать все выполненные команды
   - Отслеживать аномальное поведение
   - Регулярно проверять логи на подозрительную активность

### 2. Производительность

1. **Асинхронное выполнение**
   - Использовать очередь задач (Celery/RQ)
   - Не блокировать API длительными операциями
   - Показывать прогресс выполнения

2. **Управление ресурсами**
   - Установить лимиты CPU/Memory
   - Ограничить время выполнения
   - Очищать временные файлы

### 3. Масштабируемость

1. **Микросервисная архитектура**
   - Выделить песочницу в отдельный сервис
   - Использовать API Gateway
   - Реализовать service mesh

2. **Горизонтальное масштабирование**
   - Использовать Kubernetes для оркестрации
   - Настроить автомасштабирование
   - Распределить нагрузку

## 🚀 Следующие шаги

1. **Немедленно (сегодня):**
   - Исправить блокировку опасных shell команд
   - Добавить проверку сетевых операций
   - Создать тесты для проверки безопасности

2. **В течение недели:**
   - Настроить Docker с ограничениями
   - Реализовать белый список команд
   - Добавить структурированное логирование

3. **В течение месяца:**
   - Внедрить очередь задач
   - Создать отдельный микросервис для песочницы
   - Настроить мониторинг и алерты

## 📚 Полезные ресурсы

1. [Docker Security Best Practices](https://docs.docker.com/engine/security/)
2. [Python AST Security](https://docs.python.org/3/library/ast.html)
3. [OWASP Secure Coding Practices](https://owasp.org/www-project-secure-coding-practices-quick-reference-guide/)
4. [Linux Capabilities](https://man7.org/linux/man-pages/man7/capabilities.7.html)

## 🧠 Система планирования и самосознания

### Текущие проблемы

1. **Система планирования - заглушка**
   - Функции `create_task_plan`, `execute_task_plan` не реализованы
   - Планы не сохраняются в памяти
   - Нет интеграции с выполнением задач

2. **Изолированные компоненты (87 модулей)**
   - Многие модули не связаны между собой
   - Отсутствует единая шина событий
   - Нет централизованного управления возможностями

3. **Ограниченное самосознание**
   - Марк не может анализировать свой код
   - Не понимает зависимости между компонентами
   - Не может трассировать ошибки

### План интеграции системы планирования

#### 1. Реализация TaskPlanner (HIGH priority)

```python
# sandbox/task_planning_system.py
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from enum import Enum
import uuid

class TaskStatus(Enum):
    DRAFT = "draft"
    PLANNED = "planned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"

@dataclass
class SubTask:
    id: str
    description: str
    dependencies: List[str]
    estimated_time: int  # минуты
    status: TaskStatus = TaskStatus.DRAFT
    result: Optional[Dict[str, Any]] = None

@dataclass
class Plan:
    id: str
    goal: str
    subtasks: List[SubTask]
    status: TaskStatus = TaskStatus.DRAFT
    created_at: datetime
    updated_at: datetime
    metadata: Dict[str, Any] = field(default_factory=dict)

class TaskPlanner:
    def __init__(self, memory_manager, llm_client, event_bus):
        self.memory = memory_manager
        self.llm = llm_client
        self.event_bus = event_bus
        self.plans: Dict[str, Plan] = {}
        
    async def create_plan(self, goal: str, context: Dict[str, Any] = None) -> Plan:
        """Создает план для достижения цели"""
        # 1. Анализ цели с помощью LLM
        prompt = f"""
        Создай детальный план для достижения цели: {goal}
        
        Контекст: {context}
        
        Разбей задачу на подзадачи, определи зависимости и время.
        Формат ответа: JSON с полями subtasks, dependencies, time_estimates
        """
        
        response = await self.llm.generate(prompt)
        plan_data = self._parse_llm_response(response)
        
        # 2. Создание структуры плана
        plan = Plan(
            id=str(uuid.uuid4()),
            goal=goal,
            subtasks=self._create_subtasks(plan_data),
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
        
        # 3. Сохранение в памяти
        await self._save_to_memory(plan)
        
        # 4. Публикация события
        await self.event_bus.publish("plan_created", {
            "plan_id": plan.id,
            "goal": plan.goal,
            "subtasks_count": len(plan.subtasks)
        })
        
        self.plans[plan.id] = plan
        return plan
```

#### 2. Интеграция с ботом

```python
# telegram_bot/bot.py - добавить команды

async def plan_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Создает план для достижения цели"""
    if not context.args:
        keyboard = [
            [InlineKeyboardButton("📝 Написать статью", callback_data="plan:article")],
            [InlineKeyboardButton("🔧 Исправить баг", callback_data="plan:bugfix")],
            [InlineKeyboardButton("📚 Изучить тему", callback_data="plan:learn")],
            [InlineKeyboardButton("🏗️ Создать проект", callback_data="plan:project")]
        ]
        await update.message.reply_text(
            "Что планируем? Опишите цель или выберите шаблон:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    
    goal = ' '.join(context.args)
    
    # Показываем процесс планирования
    status_msg = await update.message.reply_text("🤔 Анализирую задачу...")
    
    # Создаем план через API
    response = await _post("/plan/create", {
        "goal": goal,
        "context": {
            "user_id": update.effective_user.id,
            "chat_id": update.effective_chat.id
        }
    })
    
    if response.status_code == 200:
        plan = response.json()
        
        # Форматируем план
        text = f"📋 **План: {plan['goal']}**\n\n"
        text += f"🆔 ID: `{plan['id']}`\n"
        text += f"📊 Подзадач: {len(plan['subtasks'])}\n\n"
        
        for i, task in enumerate(plan['subtasks'], 1):
            text += f"{i}. {task['description']}\n"
            text += f"   ⏱️ ~{task['estimated_time']} мин\n"
            if task['dependencies']:
                text += f"   🔗 Зависит от: {', '.join(task['dependencies'])}\n"
            text += "\n"
        
        # Кнопки действий
        keyboard = [
            [
                InlineKeyboardButton("▶️ Начать", callback_data=f"plan:start:{plan['id']}"),
                InlineKeyboardButton("📊 Статус", callback_data=f"plan:status:{plan['id']}")
            ],
            [
                InlineKeyboardButton("✏️ Изменить", callback_data=f"plan:edit:{plan['id']}"),
                InlineKeyboardButton("❌ Отменить", callback_data=f"plan:cancel:{plan['id']}")
            ]
        ]
        
        await status_msg.edit_text(
            text,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        await status_msg.edit_text("❌ Ошибка при создании плана")
```

#### 3. Расширение самосознания

```python
# sandbox/enhanced_self_awareness.py
import ast
import inspect
from pathlib import Path

class EnhancedSelfAwareness(MarkSelfAwareness):
    def __init__(self):
        super().__init__()
        self.code_map = self._build_code_map()
        self.dependency_graph = self._build_dependency_graph()
        
    def _build_code_map(self) -> Dict[str, Dict[str, Any]]:
        """Строит карту всего кода проекта"""
        code_map = {}
        
        for py_file in Path("/workspace").rglob("*.py"):
            if any(skip in str(py_file) for skip in ["__pycache__", "venv"]):
                continue
                
            try:
                with open(py_file, 'r') as f:
                    content = f.read()
                
                tree = ast.parse(content)
                
                code_map[str(py_file)] = {
                    "functions": self._extract_functions(tree),
                    "classes": self._extract_classes(tree),
                    "imports": self._extract_imports(tree),
                    "size": len(content),
                    "lines": content.count('\n')
                }
            except Exception as e:
                logger.error(f"Error parsing {py_file}: {e}")
                
        return code_map
    
    def analyze_capability(self, capability: str) -> TaskResult:
        """Анализирует возможность с учетом кода"""
        base_result = super().analyze_capability(capability)
        
        # Добавляем анализ кода
        if capability in self.capabilities:
            # Находим файлы, связанные с возможностью
            related_files = self._find_related_files(capability)
            
            analysis = {
                "capability": capability,
                "status": "available",
                "files": related_files,
                "entry_points": self._find_entry_points(capability),
                "dependencies": self._get_capability_dependencies(capability),
                "health": self._check_capability_health(capability)
            }
            
            return TaskResult(
                success=True,
                message=f"Детальный анализ возможности '{capability}'",
                data=analysis
            )
            
        return base_result
    
    def diagnose_error(self, error_message: str) -> Dict[str, Any]:
        """Диагностирует ошибку и предлагает решения"""
        diagnosis = {
            "error": error_message,
            "possible_causes": [],
            "affected_components": [],
            "suggested_fixes": []
        }
        
        # Анализ стека ошибки
        if "Traceback" in error_message:
            files = self._extract_files_from_traceback(error_message)
            diagnosis["affected_components"] = files
            
            # Анализ каждого файла
            for file in files:
                if file in self.code_map:
                    # Проверяем импорты
                    imports = self.code_map[file]["imports"]
                    diagnosis["possible_causes"].extend(
                        self._analyze_import_issues(imports)
                    )
        
        # Поиск похожих ошибок в истории
        similar_errors = self._find_similar_errors(error_message)
        if similar_errors:
            diagnosis["suggested_fixes"].extend(
                [e["fix"] for e in similar_errors if "fix" in e]
            )
        
        return diagnosis
```

### 4. Event Bus для связи компонентов

```python
# core/event_bus.py
from typing import Callable, Dict, List, Any
from collections import defaultdict
import asyncio
import logging

class EventBus:
    """Центральная шина событий для связи компонентов"""
    
    def __init__(self):
        self.subscribers: Dict[str, List[Callable]] = defaultdict(list)
        self.event_history: List[Dict[str, Any]] = []
        self.logger = logging.getLogger(__name__)
        
    def subscribe(self, event_type: str, handler: Callable, priority: int = 0):
        """Подписка на событие"""
        self.subscribers[event_type].append((priority, handler))
        # Сортируем по приоритету
        self.subscribers[event_type].sort(key=lambda x: x[0], reverse=True)
        self.logger.info(f"Subscribed {handler.__name__} to {event_type}")
        
    async def publish(self, event_type: str, data: Dict[str, Any]):
        """Публикация события"""
        event = {
            "type": event_type,
            "data": data,
            "timestamp": datetime.now(),
            "handlers_called": []
        }
        
        # Вызываем обработчики
        for priority, handler in self.subscribers[event_type]:
            try:
                await handler(data)
                event["handlers_called"].append(handler.__name__)
            except Exception as e:
                self.logger.error(f"Error in handler {handler.__name__}: {e}")
                
        self.event_history.append(event)
        
        # Ограничиваем историю
        if len(self.event_history) > 1000:
            self.event_history = self.event_history[-1000:]
            
    def get_event_stats(self) -> Dict[str, Any]:
        """Статистика событий"""
        stats = defaultdict(int)
        for event in self.event_history:
            stats[event["type"]] += 1
            
        return {
            "total_events": len(self.event_history),
            "event_types": dict(stats),
            "subscribers": {k: len(v) for k, v in self.subscribers.items()}
        }

# Глобальная шина событий
event_bus = EventBus()

# Регистрация обработчиков
event_bus.subscribe("plan_created", memory_manager.handle_plan_created)
event_bus.subscribe("task_completed", task_executor.handle_completion)
event_bus.subscribe("error_occurred", monitoring.handle_error)
```

## 🎯 Заключение

Для создания полноценного самосознающего бота Марка необходимо:

1. **Исправить критические проблемы безопасности песочницы** (2-3 часа)
2. **Реализовать систему планирования с сохранением в памяти** (4-5 часов)
3. **Создать Event Bus для связи всех компонентов** (3-4 часа)
4. **Расширить самосознание для анализа кода и ошибок** (5-6 часов)
5. **Интегрировать все компоненты через единую архитектуру** (1 неделя)

Предложенный план позволит создать:
- **Безопасную** систему выполнения кода
- **Интегрированную** архитектуру без изолированных модулей
- **Самосознающего** бота, понимающего свою структуру
- **Планирующего** ассистента с долговременной памятью

Общее время реализации: ~2-3 недели при полной занятости.