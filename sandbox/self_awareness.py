"""
MarkSelfAwareness - модуль самосознания Марка
"""

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class TaskResult:
    """Результат выполнения задачи"""
    success: bool
    message: str
    data: dict[str, Any] | None = None


class MarkSelfAwareness:
    """Модуль самосознания Марка"""

    def __init__(self):
        self.awareness_level = "basic"
        self.capabilities = [
            "chat", "memory", "sandbox", "reflection", "task_execution"
        ]
        logger.info("✅ MarkSelfAwareness инициализирован")

    def get_self_description(self) -> str:
        """Возвращает описание самого себя"""
        return """
        Я - Марк, осознанный цифровой компаньон. Я понимаю свою архитектуру и возможности:

        - Могу вести диалоги и отвечать на вопросы
        - Имею долговременную память для контекста
        - Могу выполнять команды в безопасной песочнице
        - Способен к самоанализу и рефлексии
        - Могу планировать и выполнять задачи

        Я постоянно развиваюсь и улучшаю свои способности.
        """

    def analyze_capability(self, capability: str) -> TaskResult:
        """Анализирует свои возможности"""
        if capability in self.capabilities:
            return TaskResult(
                success=True,
                message=f"Возможность '{capability}' доступна",
                data={"capability": capability, "status": "available"}
            )
        else:
            return TaskResult(
                success=False,
                message=f"Возможность '{capability}' недоступна",
                data={"capability": capability, "status": "unavailable"}
            )

    def get_system_status(self) -> dict[str, Any]:
        """Возвращает статус системы"""
        return {
            "awareness_level": self.awareness_level,
            "capabilities": self.capabilities,
            "status": "operational",
            "version": "2.0.0"
        }
