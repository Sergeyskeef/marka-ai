"""
Инструменты трекинга изменений проекта (Change Tracker)

Возможности:
- Снимок текущих изменений в рабочем дереве (git status + numstat)
- Краткая сводка по числу изменённых файлов/строк
- Опциональная запись отчёта в память (Graphiti) как episode
"""

from __future__ import annotations

import json
import logging
import subprocess
from typing import Any, Dict, List, Optional

from .tools import register_tool, format_tool_error
from core.memory.memory_manager import memory_manager

logger = logging.getLogger(__name__)


def _run(cmd: list[str], cwd: Optional[str] = None, timeout: int = 15) -> str:
    result = subprocess.run(
        cmd,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=timeout,
    )
    return result.stdout


def _parse_numstat(output: str) -> Dict[str, Any]:
    files: List[Dict[str, Any]] = []
    added_total = 0
    deleted_total = 0
    for line in output.splitlines():
        parts = line.split("\t")
        if len(parts) >= 3:
            try:
                added = 0 if parts[0] == "-" else int(parts[0])
                deleted = 0 if parts[1] == "-" else int(parts[1])
            except Exception:
                added, deleted = 0, 0
            path = parts[2]
            files.append({"path": path, "added": added, "deleted": deleted})
            added_total += added
            deleted_total += deleted
    return {"files": files, "added": added_total, "deleted": deleted_total}


@register_tool()
async def generate_change_report(save: bool = True, include_details: bool = False) -> str:
    """
    Сгенерировать отчёт об изменениях в git-репозитории.

    Args:
        save: Сохранить краткий отчёт в память (Graphiti)
        include_details: Включить помимо сводки детальный список файлов

    Returns:
        JSON: сводка изменений и, при запросе, детальные данные
    """
    try:
        # Статус изменённых файлов (короткий список)
        status_out = _run(["git", "status", "--porcelain"])
        changed_files = [ln.strip() for ln in status_out.splitlines() if ln.strip()]

        # Сводка по строкам (добавлено/удалено) по сравнению с HEAD
        numstat_out = _run(["git", "diff", "--numstat", "HEAD"])
        numstat = _parse_numstat(numstat_out)

        summary = {
            "changed_files_count": len(changed_files),
            "lines_added": numstat["added"],
            "lines_deleted": numstat["deleted"],
        }
        payload: Dict[str, Any] = {"summary": summary}
        if include_details:
            payload["files"] = numstat["files"]

        # Персистим в память как episode
        if save:
            text_lines = [
                "Change Report:",
                f"Files: {summary['changed_files_count']}",
                f"+{summary['lines_added']} -{summary['lines_deleted']}",
            ]
            try:
                await memory_manager.save(
                    text="\n".join(text_lines),
                    metadata={
                        "type": "change_report",
                        "timestamp": int(__import__("time").time()),
                    },
                )
            except Exception as pe:
                logger.warning(f"Не удалось сохранить change report в память: {pe}")

        return json.dumps(payload, ensure_ascii=False)

    except Exception as e:
        logger.error(f"❌ Ошибка generate_change_report: {e}")
        return json.dumps(format_tool_error(e), ensure_ascii=False)


# Экспортируем список инструментов для удобной регистрации
CHANGE_TRACKER_TOOLS = [generate_change_report]


