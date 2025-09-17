"""
Система внутреннего диалога для Марка

Позволяет Марку:
- Показывать процесс мышления в Telegram
- Автоматически решать проблемы без подтверждений
- Обучаться на своих действиях
"""

from .manager import InternalDialogueManager
from .thinking_handler import ThinkingMessageHandler
from .auto_solver import AutoProblemSolver
from .dialogue_state import DialogueState

__all__ = [
    "InternalDialogueManager",
    "ThinkingMessageHandler", 
    "AutoProblemSolver",
    "DialogueState"
]
