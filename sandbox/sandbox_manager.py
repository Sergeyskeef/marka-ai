"""
SandboxManager - менеджер песочницы для безопасного выполнения команд
"""

import logging
import subprocess
import asyncio
from typing import Dict, Any, Optional, List
from datetime import datetime
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class CommandResult:
    """Результат выполнения команды"""
    success: bool
    output: str
    error: Optional[str] = None
    return_code: Optional[int] = None
    execution_time: float = 0.0
    command: str = ""


@dataclass
class Sandbox:
    """Конфигурация песочницы"""
    id: str
    working_dir: str
    timeout: int = 30
    max_output_size: int = 1024 * 1024  # 1MB
    allowed_commands: Optional[List[str]] = None


class SandboxManager:
    """Менеджер песочницы"""
    
    def __init__(self):
        self.sandboxes: Dict[str, Sandbox] = {}
        self.command_history: List[CommandResult] = []
        self.default_timeout = 30
        self.default_max_output = 1024 * 1024  # 1MB
        
        # Создаем песочницу по умолчанию
        self.create_sandbox("default", "/sandbox")
        
        logger.info("✅ SandboxManager инициализирован")
    
    def create_sandbox(self, sandbox_id: str, working_dir: str, **kwargs) -> Sandbox:
        """Создает новую песочницу"""
        sandbox = Sandbox(
            id=sandbox_id,
            working_dir=working_dir,
            **kwargs
        )
        self.sandboxes[sandbox_id] = sandbox
        logger.info(f"🏖️ Создана песочница: {sandbox_id} в {working_dir}")
        return sandbox
    
    def get_sandbox(self, sandbox_id: str = "default") -> Optional[Sandbox]:
        """Возвращает песочницу по ID"""
        return self.sandboxes.get(sandbox_id)
    
    async def execute_command(self, 
                            command: str, 
                            sandbox_id: str = "default",
                            timeout: Optional[int] = None) -> CommandResult:
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
            # Проверяем разрешенные команды
            if sandbox.allowed_commands and command.split()[0] not in sandbox.allowed_commands:
                return CommandResult(
                    success=False,
                    output="",
                    error=f"Команда {command.split()[0]} не разрешена в песочнице {sandbox_id}",
                    command=command
                )
            
            # Выполняем команду
            process = await asyncio.create_subprocess_exec(
                *command.split(),
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
    
    def get_command_history(self, limit: int = 100) -> List[CommandResult]:
        """Возвращает историю команд"""
        return self.command_history[-limit:] if self.command_history else []
    
    def clear_history(self):
        """Очищает историю команд"""
        cleared_count = len(self.command_history)
        self.command_history.clear()
        logger.info(f"🧹 Очищена история команд: {cleared_count} записей")
    
    def get_sandbox_stats(self) -> Dict[str, Any]:
        """Возвращает статистику песочницы"""
        return {
            "total_sandboxes": len(self.sandboxes),
            "total_commands": len(self.command_history),
            "successful_commands": len([c for c in self.command_history if c.success]),
            "failed_commands": len([c for c in self.command_history if not c.success]),
            "sandboxes": [s.id for s in self.sandboxes.values()]
        } 