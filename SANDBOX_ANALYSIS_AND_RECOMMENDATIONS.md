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

## 🎯 Заключение

Текущая реализация песочницы имеет серьезные проблемы безопасности, которые необходимо устранить в первую очередь. После исправления критических уязвимостей следует сосредоточиться на улучшении архитектуры и пользовательского опыта.

Предложенный план действий позволит создать безопасную, масштабируемую и удобную систему для выполнения кода в изолированной среде.