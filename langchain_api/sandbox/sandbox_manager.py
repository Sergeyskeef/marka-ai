"""
SandboxManager - менеджер песочницы для безопасного выполнения команд
"""

import asyncio
import logging
import shlex
import os
import ast
import re
import shutil
from pathlib import Path
from typing import Any, Iterable
from dataclasses import dataclass
from datetime import datetime

# Импортируем Event Bus
try:
    from core.event_bus import event_bus, EventTypes
    EVENT_BUS_AVAILABLE = True
except ImportError:
    EVENT_BUS_AVAILABLE = False

logger = logging.getLogger(__name__)


@dataclass
class CommandResult:
    """Результат выполнения команды"""
    success: bool
    output: str
    error: str | None = None
    return_code: int | None = None
    execution_time: float = 0.0
    command: str = ""


@dataclass
class Sandbox:
    """Конфигурация песочницы"""
    id: str
    working_dir: str
    timeout: int = 60
    max_output_size: int = 1024 * 1024  # 1MB
    allowed_commands: list[str] | None = None
    blocked_modules: list[str] | None = None


class SandboxManager:
    """Менеджер песочницы"""

    def __init__(self):
        self.sandboxes: dict[str, Sandbox] = {}
        self.command_history: list[CommandResult] = []
        self.default_timeout = 60
        self.default_max_output = 1024 * 1024  # 1MB
        
        # Белый список разрешенных shell команд
        self.allowed_shell_commands = {
            'echo', 'printf', 'date', 'pwd', 'whoami',
            'ls', 'dir', 'find', 'grep', 'sed', 'awk',
            'sort', 'uniq', 'wc', 'head', 'tail', 'cat',
            'python', 'python3', 'pip', 'pip3', 'npm', 'node',
            'git', 'curl', 'wget',  # для загрузки зависимостей
            'mkdir', 'touch', 'mv', 'cp', 'rm',  # файловые операции
            'cd', 'export', 'source',  # навигация
        }
        
        # Опасные паттерны в командах
        self.dangerous_patterns = [
            r'rm\s+-rf\s+/',  # rm -rf /
            r'rm\s+.*\s+/',   # rm что-то /
            r'>\s*/dev/.*',   # перенаправление в /dev/
            r'/etc/passwd',   # системные файлы
            r'/etc/shadow',
            r'sudo\s+',       # повышение привилегий
            r'su\s+',
            r'chmod\s+777',   # опасные права
            r'docker\s+',     # управление контейнерами
            r'systemctl',     # управление сервисами
            r'service\s+',
            r'kill\s+-9',     # убийство процессов
            r'pkill',
            r'nc\s+-l',       # сетевые утилиты
            r'nmap',
            r'telnet',
            r'ssh\s+',
        ]
        
        # Список заблокированных модулей Python
        self.default_blocked_modules = [
            "os.system",
            "subprocess",
            "__import__('os').system",
            "eval",
            "exec",
            "compile",
            "__import__",
            "open",
        ]
        
        # Список опасных AST узлов
        self.dangerous_ast_nodes = {
            'Import': ['os', 'sys', 'subprocess', 'importlib', '__builtin__', '__builtins__',
                      'socket', 'urllib', 'urllib2', 'urllib3', 'requests', 'httpx', 'aiohttp'],
            'ImportFrom': ['os', 'sys', 'subprocess', 'importlib', '__builtin__', '__builtins__',
                          'socket', 'urllib', 'urllib2', 'urllib3', 'requests', 'httpx', 'aiohttp'],
            'Call': ['eval', 'exec', 'compile', '__import__', 'open', 'file', 'input', 'raw_input',
                    'getattr', 'setattr', 'delattr', 'globals', 'locals', 'vars']
        }
        
        # Сетевые модули для блокировки
        self.network_modules = {'socket', 'urllib', 'urllib2', 'urllib3', 'requests', 'httpx', 'aiohttp'}
        
        # Опасные встроенные функции
        self.dangerous_builtins = {'eval', 'exec', 'compile', '__import__', 
                                  'getattr', 'setattr', 'delattr', 
                                  'globals', 'locals', 'vars'}

        # Создаем песочницу по умолчанию
        # Используем текущую директорию если /sandbox не существует
        sandbox_dir = "/sandbox" if os.path.exists("/sandbox") else "/workspace/sandbox_test"
        os.makedirs(sandbox_dir, exist_ok=True)
        self.create_sandbox("default", sandbox_dir)

        logger.info("✅ SandboxManager инициализирован с улучшенной безопасностью")

    def _resolve_sandbox_root(self) -> str:
        """Возвращает корень рабочей директории песочницы."""
        default = self.get_sandbox("default")
        return default.working_dir if default else ("/sandbox" if os.path.exists("/sandbox") else "/workspace/sandbox_test")

    def _detect_project_source(self, candidates: Iterable[str] | None = None) -> str | None:
        """Определяет доступный путь к исходникам проекта для копирования.

        Пытаемся найти директорию, где лежит проект. Предпочитаем корень,
        содержащий папку langchain_api.
        """
        search = list(candidates or [])
        if not search:
            search = [
                "/app",
                "/app/langchain_api",
                "/workspace/langchain_api",
                "/workspace",
                str(Path.cwd()),
            ]

        for base in search:
            try:
                if not base:
                    continue
                base_path = Path(base)
                if base_path.is_dir():
                    # Если это именно папка langchain_api — используем её родителя
                    if base_path.name == "langchain_api" and (base_path / "__init__.py").exists() or (base_path / "app").exists():
                        return str(base_path.parent)
                    # Если внутри есть langchain_api — отлично
                    if (base_path / "langchain_api").is_dir():
                        return str(base_path)
            except Exception:
                continue
        return None

    def copy_project_to_sandbox(
        self,
        source_candidates: Iterable[str] | None = None,
        dest_subdir: str = "app_copy",
        exclude_patterns: Iterable[str] | None = None,
    ) -> dict[str, Any]:
        """Копирует текущий проект в рабочую директорию песочницы безопасно (без shell).

        Args:
            source_candidates: Возможные исходные пути (корни проекта)
            dest_subdir: Подкаталог внутри песочницы для копии
            exclude_patterns: Паттерны для исключения файлов/директорий

        Returns:
            Словарь с результатом копирования
        """
        try:
            sandbox_root = self._resolve_sandbox_root()
            dest_root = Path(sandbox_root) / dest_subdir
            # Определяем источник
            source_root_str = self._detect_project_source(source_candidates)
            if not source_root_str:
                return {
                    "success": False,
                    "error": "Не удалось определить исходный путь проекта",
                    "sandbox_root": str(sandbox_root),
                }

            source_root = Path(source_root_str)

            # Эксклюды по умолчанию
            default_exclude = [
                ".git",
                "__pycache__",
                ".pytest_cache",
                "logs",
                "*.log",
                "*.db",
                "*.sqlite",
                "*.parquet",
                "*.ipynb",
                "*.graphml",
                "*.cache",
            ]
            patterns = list(exclude_patterns or []) or default_exclude

            # Готовим целевой каталог
            if dest_root.exists():
                # Аккуратно очищаем предыдущую копию
                shutil.rmtree(dest_root, ignore_errors=True)
            dest_root.mkdir(parents=True, exist_ok=True)

            def should_exclude(path: Path) -> bool:
                from fnmatch import fnmatch
                name = path.name
                rel = str(path.relative_to(source_root)) if path.is_relative_to(source_root) else name
                for pat in patterns:
                    if fnmatch(name, pat) or fnmatch(rel, pat):
                        return True
                return False

            files_copied = 0
            # Копируем только папку langchain_api и связанные корневые файлы (pyproject/requirements/docker-compose)
            items_to_copy = []
            if (source_root / "langchain_api").is_dir():
                items_to_copy.append((source_root / "langchain_api", dest_root / "langchain_api"))
            else:
                # fallback: копируем весь source_root
                items_to_copy.append((source_root, dest_root))

            important_root_files = [
                "pyproject.toml", "requirements.txt", "docker-compose.yml", "README.md"
            ]
            for fn in important_root_files:
                p = source_root / fn
                if p.exists() and not should_exclude(p):
                    (dest_root / fn).parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(p, dest_root / fn)
                    files_copied += 1

            for src, dst in items_to_copy:
                if src.is_file():
                    if not should_exclude(src):
                        dst.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(src, dst)
                        files_copied += 1
                    continue
                for root, dirs, files in os.walk(src):
                    root_path = Path(root)
                    # Фильтруем директории на месте, чтобы не заходить в исключенные
                    dirs[:] = [d for d in dirs if not should_exclude(root_path / d)]
                    rel_dir = root_path.relative_to(src)
                    target_dir = dst / rel_dir
                    target_dir.mkdir(parents=True, exist_ok=True)
                    for f in files:
                        sp = root_path / f
                        if should_exclude(sp):
                            continue
                        dp = target_dir / f
                        try:
                            shutil.copy2(sp, dp)
                            files_copied += 1
                        except Exception as ce:
                            logger.warning(f"Не удалось скопировать {sp} -> {dp}: {ce}")

            return {
                "success": True,
                "source": str(source_root),
                "destination": str(dest_root),
                "files_copied": files_copied,
            }
        except Exception as e:
            logger.error(f"Ошибка копирования проекта в песочницу: {e}")
            return {
                "success": False,
                "error": str(e),
            }

    def _check_shell_command(self, command: str) -> str | None:
        """Проверка shell команд на безопасность"""
        try:
            cmd_parts = shlex.split(command)
            if not cmd_parts:
                return "Пустая команда"
                
            base_cmd = cmd_parts[0]
            
            # Для путей типа /usr/bin/python берем последнюю часть
            if '/' in base_cmd:
                base_cmd = base_cmd.split('/')[-1]
            
            # Проверяем белый список
            if base_cmd not in self.allowed_shell_commands:
                return f"Команда '{base_cmd}' не в белом списке разрешенных команд"
                
            # Проверяем опасные паттерны
            for pattern in self.dangerous_patterns:
                if re.search(pattern, command, re.IGNORECASE):
                    return f"Обнаружен опасный паттерн: {pattern}"
                    
            return None
        except Exception as e:
            return f"Ошибка парсинга команды: {str(e)}"

    def create_sandbox(self, sandbox_id: str, working_dir: str, **kwargs) -> Sandbox:
        """Создает новую песочницу"""
        # Создаем директорию если не существует
        os.makedirs(working_dir, exist_ok=True)
        
        sandbox = Sandbox(
            id=sandbox_id,
            working_dir=working_dir,
            blocked_modules=kwargs.get('blocked_modules', self.default_blocked_modules),
            **{k: v for k, v in kwargs.items() if k != 'blocked_modules'}
        )
        self.sandboxes[sandbox_id] = sandbox
        logger.info(f"🏖️ Создана песочница: {sandbox_id} в {working_dir}")
        return sandbox

    def get_sandbox(self, sandbox_id: str = "default") -> Sandbox | None:
        """Возвращает песочницу по ID"""
        return self.sandboxes.get(sandbox_id)
    
    def _check_dangerous_code(self, command: str, sandbox: Sandbox) -> str | None:
        """Проверяет код на опасные операции"""
        if "python" in command and "-c" in command:
            # Извлекаем Python код из команды
            try:
                parts = shlex.split(command)
                if "-c" in parts:
                    code_idx = parts.index("-c") + 1
                    if code_idx < len(parts):
                        code = parts[code_idx]
                        
                        # Проверяем через AST
                        ast_error = self._check_python_ast(code)
                        if ast_error:
                            return ast_error
                        
                        # Проверяем на заблокированные модули (дополнительная проверка)
                        for blocked in sandbox.blocked_modules or []:
                            if blocked in code:
                                return f"Заблокированная операция: {blocked}"
            except Exception as e:
                return f"Ошибка парсинга команды: {str(e)}"
        
        return None
    
    def _check_python_ast(self, code: str) -> str | None:
        """Проверяет Python код через AST на наличие опасных операций"""
        try:
            tree = ast.parse(code)
            
            for node in ast.walk(tree):
                # Проверяем импорты
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name in self.dangerous_ast_nodes.get('Import', []):
                            return f"Заблокирован импорт модуля: {alias.name}"
                        # Проверяем сетевые модули
                        if alias.name in self.network_modules:
                            return f"Заблокирован сетевой модуль: {alias.name}"
                
                elif isinstance(node, ast.ImportFrom):
                    if node.module and node.module in self.dangerous_ast_nodes.get('ImportFrom', []):
                        return f"Заблокирован импорт из модуля: {node.module}"
                    # Проверяем сетевые модули
                    if node.module and node.module in self.network_modules:
                        return f"Заблокирован сетевой модуль: {node.module}"
                
                # Проверяем вызовы функций
                elif isinstance(node, ast.Call):
                    # Проверяем прямые вызовы
                    if isinstance(node.func, ast.Name):
                        if node.func.id in self.dangerous_ast_nodes.get('Call', []):
                            return f"Заблокирован вызов функции: {node.func.id}"
                        # Проверяем опасные встроенные функции
                        if node.func.id in self.dangerous_builtins:
                            return f"Заблокирована встроенная функция: {node.func.id}"
                    
                    # Проверяем вызовы атрибутов (например, os.system)
                    elif isinstance(node.func, ast.Attribute):
                        # Получаем полное имя (например, os.system)
                        full_name = []
                        current = node.func
                        while isinstance(current, ast.Attribute):
                            full_name.insert(0, current.attr)
                            current = current.value
                        if isinstance(current, ast.Name):
                            full_name.insert(0, current.id)
                            full_path = '.'.join(full_name)
                            
                            # Проверяем опасные вызовы
                            if full_path in ['os.system', 'os.popen', 'subprocess.call', 
                                           'subprocess.run', 'subprocess.Popen']:
                                return f"Заблокирован системный вызов: {full_path}"
                
                # Проверяем использование eval/exec в виде строк
                elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
                    if isinstance(node.value.func, ast.Name) and node.value.func.id in ['eval', 'exec']:
                        return f"Заблокировано использование: {node.value.func.id}"
            
            return None  # Код безопасен
            
        except SyntaxError as e:
            return f"Синтаксическая ошибка в Python коде: {str(e)}"
        except Exception as e:
            return f"Ошибка при анализе AST: {str(e)}"

    async def execute_command(self,
                            command: str,
                            sandbox_id: str = "default",
                            timeout: int | None = None) -> CommandResult:
        """Выполняет команду в песочнице"""
        sandbox = self.get_sandbox(sandbox_id)
        if not sandbox:
            return CommandResult(
                success=False,
                output="",
                error=f"Песочница {sandbox_id} не найдена",
                command=command
            )

        start_time = datetime.now()

        try:
            # Проверяем shell команды на безопасность
            if not command.startswith("python"):
                shell_error = self._check_shell_command(command)
                if shell_error:
                    result = CommandResult(
                        success=False,
                        output="",
                        error=shell_error,
                        command=command,
                        execution_time=(datetime.now() - start_time).total_seconds()
                    )
                    
                    # Публикуем событие о блокировке
                    if EVENT_BUS_AVAILABLE:
                        asyncio.create_task(event_bus.publish(
                            EventTypes.SANDBOX_BLOCKED,
                            {
                                "command": command,
                                "reason": shell_error,
                                "sandbox_id": sandbox_id
                            },
                            source="SandboxManager"
                        ))
                    
                    return result
            
            # Проверяем на опасные операции (Python код)
            danger_check = self._check_dangerous_code(command, sandbox)
            if danger_check:
                return CommandResult(
                    success=False,
                    output="",
                    error=danger_check,
                    command=command,
                    execution_time=(datetime.now() - start_time).total_seconds()
                )
            
            # Проверяем разрешенные команды
            if sandbox.allowed_commands:
                cmd_parts = shlex.split(command)
                if cmd_parts and cmd_parts[0] not in sandbox.allowed_commands:
                    return CommandResult(
                        success=False,
                        output="",
                        error=f"Команда {cmd_parts[0]} не разрешена в песочнице {sandbox_id}",
                        command=command
                    )

            # Правильно парсим команду с помощью shlex
            cmd_parts = shlex.split(command)
            
            # Выполняем команду
            process = await asyncio.create_subprocess_exec(
                *cmd_parts,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=sandbox.working_dir
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout or sandbox.timeout
                )
            except asyncio.TimeoutError:
                process.kill()
                return CommandResult(
                    success=False,
                    output="",
                    error=f"Команда превысила лимит времени ({timeout or sandbox.timeout}с)",
                    command=command,
                    execution_time=(datetime.now() - start_time).total_seconds()
                )

            execution_time = (datetime.now() - start_time).total_seconds()

            # Ограничиваем размер вывода
            output = stdout.decode('utf-8', errors='ignore')
            if len(output) > sandbox.max_output_size:
                output = output[:sandbox.max_output_size] + "\n... (вывод обрезан)"

            error_output = stderr.decode('utf-8', errors='ignore')

            result = CommandResult(
                success=process.returncode == 0,
                output=output,
                error=error_output if error_output else None,
                return_code=process.returncode,
                execution_time=execution_time,
                command=command
            )

            # Сохраняем в историю
            self.command_history.append(result)

            logger.info(f"🔧 Команда выполнена: {command} (код: {process.returncode}, время: {execution_time:.2f}с)")

            # Публикуем событие об успешном выполнении
            if EVENT_BUS_AVAILABLE:
                asyncio.create_task(event_bus.publish(
                    EventTypes.SANDBOX_EXECUTED,
                    {
                        "command": command,
                        "sandbox_id": sandbox_id,
                        "success": result.success,
                        "return_code": process.returncode,
                        "execution_time": execution_time,
                        "output_size": len(result.output)
                    },
                    source="SandboxManager"
                ))

            return result

        except Exception as e:
            execution_time = (datetime.now() - start_time).total_seconds()
            logger.error(f"❌ Ошибка выполнения команды {command}: {e}")

            return CommandResult(
                success=False,
                output="",
                error=str(e),
                command=command,
                execution_time=execution_time
            )

    def get_command_history(self, limit: int = 100) -> list[CommandResult]:
        """Возвращает историю команд"""
        return self.command_history[-limit:] if self.command_history else []

    def clear_history(self):
        """Очищает историю команд"""
        cleared_count = len(self.command_history)
        self.command_history.clear()
        logger.info(f"🧹 Очищена история команд: {cleared_count} записей")

    def get_sandbox_stats(self) -> dict[str, Any]:
        """Возвращает статистику песочницы"""
        return {
            "total_sandboxes": len(self.sandboxes),
            "total_commands": len(self.command_history),
            "successful_commands": len([c for c in self.command_history if c.success]),
            "failed_commands": len([c for c in self.command_history if not c.success]),
            "sandboxes": [s.id for s in self.sandboxes.values()]
        }
    
    def is_available(self) -> bool:
        """Проверяет доступность песочницы"""
        try:
            # Проверяем, что есть хотя бы одна песочница
            if not self.sandboxes:
                return False
            
            # Проверяем, что директория песочницы существует и доступна
            default_sandbox = self.get_sandbox("default")
            if default_sandbox and os.path.exists(default_sandbox.working_dir):
                return True
            
            return False
        except Exception as e:
            logger.error(f"Ошибка при проверке доступности песочницы: {e}")
            return False
