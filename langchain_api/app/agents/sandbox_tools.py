"""
Инструменты для безопасного выполнения команд в песочнице
"""

import json
import logging
from typing import Optional

from .tools import register_tool, format_tool_error
from sandbox.sandbox_manager import SandboxManager

logger = logging.getLogger(__name__)


_SANDBOX = SandboxManager()


@register_tool()
async def run_in_sandbox(command: str, timeout: Optional[int] = 60) -> str:
    """
    Выполнить команду в изолированной песочнице с таймаутом и ограничениями.

    Args:
        command: Команда для выполнения (например, "python3 /sandbox/hello.py")
        timeout: Таймаут выполнения в секундах (по умолчанию 30)

    Returns:
        JSON с результатами: success, stdout, stderr, return_code, execution_time
    """
    try:
        if not _SANDBOX.is_available():
            return json.dumps({
                "success": False,
                "error": "Песочница недоступна"
            }, ensure_ascii=False)

        result = await _SANDBOX.execute_command(command=command, timeout=timeout)

        return json.dumps({
            "success": bool(result.success),
            "stdout": result.output,
            "stderr": result.error,
            "return_code": result.return_code,
            "execution_time": result.execution_time,
            "command": result.command,
        }, ensure_ascii=False)

    except Exception as e:
        logger.error(f"Ошибка run_in_sandbox: {e}")
        return json.dumps(format_tool_error(e), ensure_ascii=False)


@register_tool()
async def run_python_snippet(code: str, filename: str = "snippet.py", timeout: Optional[int] = 60) -> str:
    """
    Выполнить небольшой Python-фрагмент в песочнице.

    Код сохраняется в /sandbox/<filename> и запускается как python3 <file>.

    Args:
        code: Python код для выполнения
        filename: Имя файла в /sandbox
        timeout: Таймаут выполнения в секундах
    """
    try:
        import os

        # Гарантируем директорию
        workdir = "/sandbox" if os.path.exists("/sandbox") else "/workspace/sandbox_test"
        os.makedirs(workdir, exist_ok=True)

        # Безопасное имя файла
        safe_name = "".join(ch for ch in filename if ch.isalnum() or ch in ("_", "-", ".")) or "snippet.py"
        target = os.path.join(workdir, safe_name)

        with open(target, "w", encoding="utf-8") as f:
            f.write(code)

        # Запуск
        result = await _SANDBOX.execute_command(command=f"python3 {target}", timeout=timeout)

        return json.dumps({
            "success": bool(result.success),
            "stdout": result.output,
            "stderr": result.error,
            "return_code": result.return_code,
            "execution_time": result.execution_time,
            "file": target,
        }, ensure_ascii=False)

    except Exception as e:
        logger.error(f"Ошибка run_python_snippet: {e}")
        return json.dumps(format_tool_error(e), ensure_ascii=False)


SANDBOX_TOOLS = [
    run_in_sandbox,
    run_python_snippet,
]


@register_tool()
async def stage_project_in_sandbox(source_hints: list[str] | None = None, dest_subdir: str = "app_copy") -> str:
    """
    Скопировать проект в рабочую директорию песочницы безопасным способом.

    Args:
        source_hints: Список возможных корней проекта (например, ["/app", "/workspace"]).
        dest_subdir: Подкаталог в песочнице для копии (по умолчанию app_copy).

    Returns:
        JSON со статусом, источником, назначением и количеством скопированных файлов.
    """
    try:
        hints = source_hints or ["/app", "/workspace", "/workspace/langchain_api"]
        result = _SANDBOX.copy_project_to_sandbox(source_candidates=hints, dest_subdir=dest_subdir)
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        return json.dumps(format_tool_error(e), ensure_ascii=False)


SANDBOX_TOOLS.append(stage_project_in_sandbox)

