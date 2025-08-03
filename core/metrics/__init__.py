"""
Metrics package для системы метрик Марка
"""

from .outcome_logger import (
    OutcomeLogger,
    OutcomeStatus,
    ToolCallOutcome,
    outcome_logger
)

# Импорт metrics_manager из prometheus_metrics.py 
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from ..prometheus_metrics import metrics_manager

__all__ = [
    "OutcomeLogger",
    "OutcomeStatus", 
    "ToolCallOutcome",
    "outcome_logger",
    "metrics_manager"
]