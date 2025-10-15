# metrics.py - система метрик и аудита для MCP инструментов
import time
import json
import os
from datetime import datetime
from typing import Dict, Any, Optional
from pathlib import Path

from .config import settings


class MetricsCollector:
    def __init__(self, audit_file: Optional[str] = None):
        self.audit_file = audit_file or settings.audit_log_file
        self.audit_dir = Path(self.audit_file).parent
        self.audit_dir.mkdir(parents=True, exist_ok=True)
    
    def log_tool_call(self, tool_name: str, args: Dict[str, Any], 
                     result: Dict[str, Any], duration_ms: int):
        """Логирует вызов инструмента для аудита"""
        audit_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "tool": tool_name,
            "args_hash": self._hash_args(args),
            "duration_ms": duration_ms,
            "exit_code": result.get("rc", result.get("exit_code", -1)),
            "stdout_size": len(result.get("stdout", "")),
            "stderr_size": len(result.get("stderr", "")),
            "success": result.get("rc", result.get("exit_code", -1)) == 0
        }
        
        # Записываем в аудит-файл
        try:
            with open(self.audit_file, "a") as f:
                f.write(json.dumps(audit_entry) + "\n")
        except Exception as e:
            print(f"Failed to write audit log: {e}")
    
    def _hash_args(self, args: Dict[str, Any]) -> str:
        """Создает хеш аргументов для аудита (без секретов)"""
        safe_args = {}
        for k, v in args.items():
            if k.lower() in ['token', 'password', 'secret', 'key']:
                safe_args[k] = "***"
            else:
                safe_args[k] = str(v)[:100]  # ограничиваем длину
        return str(hash(json.dumps(safe_args, sort_keys=True)))

# Глобальный коллектор метрик
_metrics = MetricsCollector()

def track_tool_call(tool_name: str):
    """Декоратор для отслеживания вызовов инструментов"""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            start_time = time.time()
            
            # Собираем аргументы для аудита
            audit_args = {}
            if args:
                audit_args["args"] = [str(arg)[:100] for arg in args]
            if kwargs:
                audit_args.update({k: str(v)[:100] for k, v in kwargs.items()})
            
            try:
                result = await func(*args, **kwargs)
                duration_ms = int((time.time() - start_time) * 1000)
                
                # Логируем успешный вызов
                _metrics.log_tool_call(tool_name, audit_args, result, duration_ms)
                
                return result
            except Exception as e:
                duration_ms = int((time.time() - start_time) * 1000)
                
                # Логируем ошибку
                error_result = {
                    "rc": -1,
                    "error": str(e),
                    "stdout": "",
                    "stderr": str(e)
                }
                _metrics.log_tool_call(tool_name, audit_args, error_result, duration_ms)
                
                raise
        return wrapper
    return decorator
