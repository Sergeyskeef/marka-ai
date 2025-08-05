"""
SandboxManager - менеджер песочницы для безопасного выполнения команд
"""

import asyncio
import logging
import shlex
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any

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
    timeout: int = 30
    max_output_size: int = 1024 * 1024  # 1MB
    allowed_commands: list[str] | None = None
    blocked_modules: list[str] | None = None


class SandboxManager:
    """Менеджер песочницы"""

    def __init__(self):
        self.sandboxes: dict[str, Sandbox] = {}
        self.command_history: list[CommandResult] = []
        self.default_timeout = 30
        self.default_max_output = 1024 * 1024  # 1MB
        
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

        # Создаем песочницу по умолчанию
        # Используем текущую директорию если /sandbox не существует
        sandbox_dir = "/sandbox" if os.path.exists("/sandbox") else "/workspace/sandbox_test"
        os.makedirs(sandbox_dir, exist_ok=True)
        self.create_sandbox("default", sandbox_dir)

        logger.info("✅ SandboxManager инициализирован")

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
                        
                        # Проверяем на заблокированные модули
                        for blocked in sandbox.blocked_modules or []:
                            if blocked in code:
                                return f"Заблокированная операция: {blocked}"
            except Exception:
                pass
        
        return None

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
            # Проверяем на опасные операции
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
