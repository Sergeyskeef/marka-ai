"""
Утилиты для проекта
"""

from .id_generator import id_generator, IDType, IDGenerator
from . import fallback_queue

__all__ = ['id_generator', 'IDType', 'IDGenerator', 'fallback_queue']
