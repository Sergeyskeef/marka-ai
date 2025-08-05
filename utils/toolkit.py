#!/usr/bin/env python3
"""
Tool Registry v2 - система регистрации и управления инструментами с Pydantic-схемами
"""

import json
import logging
import inspect
import subprocess
import tempfile
import os
import time
from typing import Any, Dict, List, Optional, Callable
from functools import wraps
from dataclasses import dataclass

from langchain_api.core.tools.schemas import (
    CodeExecutionIn, CodeExecutionOut,
    MemoryRetrieveIn, MemoryRetrieveOut,
    WebSearchIn, WebSearchOut,
    GraphSearchIn, GraphSearchOut,
    SummarizeIn, SummarizeOut,
    FileReadIn, FileReadOut,
    FileWriteIn, FileWriteOut,
)

logger = logging.getLogger(__name__)

@dataclass
class ToolDefinition:
    """Определение инструмента"""
    name: str
    description: str
    function: Callable
    input_schema: Any
    output_schema: Any
    category: str = "general"
    tags: List[str] = None
    
    def __post_init__(self):
        if self.tags is None:
            self.tags = []
    
    def to_dict(self) -> Dict[str, Any]:
        """Конвертация в словарь для сохранения"""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema.__name__ if self.input_schema else None,
            "output_schema": self.output_schema.__name__ if self.output_schema else None,
            "category": self.category,
            "tags": self.tags,
            "function_name": self.function.__name__,
            "module": self.function.__module__
        }

class ToolRegistry:
    """Реестр инструментов"""
    
    def __init__(self):
        self.tools: Dict[str, ToolDefinition] = {}
        self.categories: Dict[str, List[str]] = {}
        logger.info("🔧 ToolRegistry v2 инициализирован")
    
    def register_tool(self, tool_def: ToolDefinition) -> bool:
        """Регистрирует инструмент"""
        try:
            self.tools[tool_def.name] = tool_def
            
            # Добавляем в категорию
            if tool_def.category not in self.categories:
                self.categories[tool_def.category] = []
            self.categories[tool_def.category].append(tool_def.name)
            
            logger.info(f"✅ Зарегистрирован инструмент: {tool_def.name} ({tool_def.category})")
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка регистрации инструмента {tool_def.name}: {e}")
            return False
    
    def get_tool(self, name: str) -> Optional[ToolDefinition]:
        """Получает инструмент по имени"""
        return self.tools.get(name)
    
    def list_tools(self, category: Optional[str] = None) -> List[ToolDefinition]:
        """Список инструментов"""
        if category:
            tool_names = self.categories.get(category, [])
            return [self.tools[name] for name in tool_names if name in self.tools]
        return list(self.tools.values())
    
    def get_tools_dict(self) -> List[Dict[str, Any]]:
        """Возвращает список инструментов в виде словарей"""
        return [tool.to_dict() for tool in self.tools.values()]

# Глобальный экземпляр реестра
tool_registry = ToolRegistry()

# =====================================================
# Code Execution Tools
# =====================================================

def run_code(args: CodeExecutionIn) -> CodeExecutionOut:
    """Выполняет код в песочнице с валидацией через Pydantic"""
    start_time = time.time()
    
    # Предварительная обработка кода
    processed_code = _preprocess_code(args.code)
    
    try:
        # Создаем временный файл для кода
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(processed_code)
            temp_file = f.name
        
        # Выполняем код в песочнице
        result = subprocess.run(
            ['python', temp_file],
            capture_output=True,
            text=True,
            timeout=args.timeout,
            cwd='/sandbox'  # Рабочая директория песочницы
        )
        
        execution_time = time.time() - start_time
        
        # Собираем вывод
        stdout = result.stdout.strip()
        stderr = result.stderr.strip()
        
        # Формируем результат
        if stdout and stderr:
            output = f"STDOUT:\n{stdout}\n\nSTDERR:\n{stderr}"
        elif stdout:
            output = stdout
        elif stderr:
            output = f"STDERR:\n{stderr}"
        else:
            output = "(пусто)"
        
        # Очищаем временный файл
        try:
            os.unlink(temp_file)
        except:
            pass
        
        return CodeExecutionOut(
            output=output,
            error=None if result.returncode == 0 else stderr,
            execution_time=execution_time,
            exit_code=result.returncode
        )
        
    except subprocess.TimeoutExpired:
        execution_time = time.time() - start_time
        return CodeExecutionOut(
            output=f"❌ Превышено время выполнения ({args.timeout} сек)",
            error="Timeout exceeded",
            execution_time=execution_time,
            exit_code=-1
        )
    except Exception as e:
        execution_time = time.time() - start_time
        return CodeExecutionOut(
            output=f"❌ Ошибка выполнения: {str(e)}",
            error=str(e),
            execution_time=execution_time,
            exit_code=-1
        )

# =====================================================
# Memory Tools
# =====================================================

def search_memory(args: MemoryRetrieveIn) -> MemoryRetrieveOut:
    """Поиск в памяти с валидацией через Pydantic"""
    # TODO: Реализовать поиск через Graphiti API
    search_start = time.time()
    
    # Заглушка - в реальности здесь будет поиск через Graphiti
    memories = [
        {
            "id": "mem_001",
            "content": f"Найдено по запросу: {args.query}",
            "tags": args.tags or [],
            "created_at": "2025-08-01T18:00:00Z"
        }
    ]
    
    search_time = time.time() - search_start
    
    return MemoryRetrieveOut(
        memories=memories,
        total_found=len(memories),
        search_time=search_time
    )

# =====================================================
# Web Search Tools
# =====================================================

def web_search(args: WebSearchIn) -> WebSearchOut:
    """Поиск в интернете с валидацией через Pydantic"""
    # TODO: Реализовать веб-поиск
    return WebSearchOut(
        title="Результат поиска",
        url="https://example.com",
        snippet=f"Найдено по запросу: {args.query}",
        relevance_score=0.8
    )

# =====================================================
# Graph Search Tools
# =====================================================

def graph_search(args: GraphSearchIn) -> GraphSearchOut:
    """Поиск в графе знаний с валидацией через Pydantic"""
    # TODO: Реализовать поиск через Neo4j
    return GraphSearchOut(
        node_id="node_001",
        node_type="Concept",
        content=f"Найдено в графе: {args.query}",
        similarity_score=0.9,
        metadata={"source": "neo4j"}
    )

# =====================================================
# Summarization Tools
# =====================================================

def summarize_text(args: SummarizeIn) -> SummarizeOut:
    """Суммаризация с валидацией через Pydantic"""
    # TODO: Реализовать суммаризацию через LLM
    original_length = len(args.text)
    summary = f"Краткое содержание: {args.text[:args.max_length]}..."
    summary_length = len(summary)
    compression_ratio = max(0.0, 1 - (summary_length / original_length))
    
    return SummarizeOut(
        summary=summary,
        original_length=original_length,
        summary_length=summary_length,
        compression_ratio=compression_ratio
    )

# =====================================================
# File Operations Tools
# =====================================================

def read_file(args: FileReadIn) -> FileReadOut:
    """Чтение файла с валидацией через Pydantic"""
    try:
        with open(args.file_path, 'r', encoding=args.encoding) as f:
            content = f.read()
        
        file_size = len(content.encode(args.encoding))
        
        return FileReadOut(
            content=content,
            file_size=file_size,
            encoding=args.encoding,
            success=True
        )
    except Exception as e:
        return FileReadOut(
            content="",
            file_size=0,
            encoding=args.encoding,
            success=False
        )

def write_file(args: FileWriteIn) -> FileWriteOut:
    """Запись в файл с валидацией через Pydantic"""
    try:
        with open(args.file_path, args.mode, encoding=args.encoding) as f:
            f.write(args.content)
        
        bytes_written = len(args.content.encode(args.encoding))
        
        return FileWriteOut(
            success=True,
            bytes_written=bytes_written,
            file_path=args.file_path
        )
    except Exception as e:
        return FileWriteOut(
            success=False,
            bytes_written=0,
            file_path=args.file_path
        )

# =====================================================
# Utility Functions
# =====================================================

def get_tools_for_agent() -> List[Dict[str, Any]]:
    """Возвращает список инструментов для агента"""
    return tool_registry.get_tools_dict()

def _preprocess_code(code: str) -> str:
    """Предварительная обработка кода для исправления распространенных ошибок"""
    # Заменяем символы умножения и деления
    code = code.replace('×', '*')
    code = code.replace('÷', '/')
    code = code.replace('−', '-')  # длинное тире на обычный минус
    
    # Заменяем кавычки на стандартные
    code = code.replace('"', '"').replace('"', '"')
    code = code.replace(''', "'").replace(''', "'")
    
    # Исправляем print без скобок (для Python 2 совместимости)
    if 'print ' in code and '(' not in code.split('print ')[1][:10]:
        # Это сложная логика, лучше оставить как есть
        pass
    
    return code 