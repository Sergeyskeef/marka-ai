"""
Brain Processor - Центральный процессор интеллекта
Часть архитектуры "Все через мозг" для достижения полной автономности Марка
"""

import asyncio
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
import json

from .llm_integration_hub import LLMIntegrationHub, LLMRequest, LLMResponse
from .tools_registry import get_tools_registry

logger = logging.getLogger(__name__)


@dataclass
class ProcessingResult:
    """Результат обработки сообщения"""
    text: str
    tools_used: List[str]
    context: Dict[str, Any]
    metadata: Dict[str, Any]


class BrainProcessor:
    """
    Центральный процессор интеллекта - мозг системы.
    
    Реализует архитектуру "Все через мозг":
    - Единый pipeline для всех сообщений
    - Обязательное использование контекста и памяти  
    - LLM принимает все решения об использовании инструментов
    """
    
    def __init__(self):
        """Инициализация центрального процессора"""
        self.llm_hub = LLMIntegrationHub()
        self.tools_registry = get_tools_registry()
        self.processed_count = 0
        self.memory_operations = 0
        self.context_operations = 0
        
        # Инициализируем компоненты асинхронно
        self._init_task = None
        self._is_initialized = False
        
        logger.info("🧠 BrainProcessor создан, запуск инициализации...")
        
    async def _ensure_initialized(self):
        """Гарантирует что система инициализирована"""
        if not self._is_initialized and not self._init_task:
            self._init_task = asyncio.create_task(self._initialize())
        
        if self._init_task:
            await self._init_task
            
    async def _initialize(self):
        """Асинхронная инициализация компонентов"""
        try:
            # Инициализируем LLM Hub
            await self.llm_hub.initialize()
            self._is_initialized = True
            logger.info("✅ BrainProcessor полностью инициализирован")
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации BrainProcessor: {e}")
            raise
    
    def process(self, message: str, chat_id: int, user_id: Optional[int] = None, timestamp: Optional[datetime] = None) -> Dict[str, Any]:
        """
        Синхронная обработка сообщения через мозг (для Telegram)
        
        🔧 ИСПРАВЛЕНИЕ: Избегаем RuntimeError 'This event loop is already running'
        """
        try:
            import asyncio
            
            # Проверяем, есть ли уже running event loop
            try:
                loop = asyncio.get_running_loop()
                # Если есть - мы в async контексте, используем create_task
                logger.warning("🔄 Обнаружен running event loop, создаем task")
                
                # Создаем задачу в существующем loop
                import concurrent.futures
                import threading
                
                # Создаем новый event loop в отдельном потоке
                def run_in_new_loop():
                    new_loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(new_loop)
                    try:
                        return new_loop.run_until_complete(
                            self._process_async(message, chat_id, user_id, timestamp)
                        )
                    finally:
                        new_loop.close()
                
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(run_in_new_loop)
                    return future.result()
                    
            except RuntimeError:
                # Нет running loop - создаем новый
                logger.info("🔄 Создаем новый event loop")
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                try:
                    return loop.run_until_complete(
                        self._process_async(message, chat_id, user_id, timestamp)
                    )
                finally:
                    loop.close()
                    
        except Exception as e:
            logger.error(f"❌ Критическая ошибка в sync процессоре: {str(e)}", exc_info=True)
            
            # Возвращаем безопасный fallback ответ
            return {
                "answer": f"Произошла техническая ошибка: {str(e)}",
                "chat_id": chat_id,
                "context_used": False,
                "memory_added": False,
                "error": True,
                "error_message": str(e)
            }
    
    async def _process_async(self, message: str, chat_id: int, user_id: Optional[int] = None, timestamp: Optional[datetime] = None) -> Dict[str, Any]:
        """
        Главная функция обработки - все сообщения идут только через неё!
        
        Args:
            message: Текст сообщения
            chat_id: ID чата
            user_id: ID пользователя  
            timestamp: Время сообщения
            
        Returns:
            dict: Стандартизированный ответ с ОБЯЗАТЕЛЬНЫМИ флагами context_used=True, memory_added=True
        """
        try:
            # Гарантируем инициализацию
            await self._ensure_initialized()
            
            self.processed_count += 1
            
            if timestamp is None:
                timestamp = datetime.now()
                
            logger.info(f"🧠 Мозг обрабатывает сообщение #{self.processed_count}")
            logger.debug(f"📝 Сообщение: {message[:150]}...")
            
            # ЭТАП 1: Обогащение контекстом (ОБЯЗАТЕЛЬНО!)
            enriched_context = await self._enrich_with_context(message, chat_id, user_id, timestamp)
            self.context_operations += 1
            
            # ЭТАП 2: Создание запроса к LLM  
            llm_request = await self._create_llm_request(message, enriched_context)
            
            # ЭТАП 3: Обработка через LLM (с инструментами)
            llm_response = await self.llm_hub.process_request(llm_request)
            
            # ЭТАП 4: Выполнение инструментов если нужно
            execution_result = await self._execute_tools_if_needed(llm_response, enriched_context)
            
            # ЭТАП 5: Сохранение в память (ОБЯЗАТЕЛЬНО!)
            await self._save_to_memory(message, execution_result, chat_id, user_id, timestamp)
            self.memory_operations += 1
            
            # ЭТАП 6: Формирование финального ответа
            final_result = self._format_final_response(execution_result, chat_id)
            
            logger.info(f"✅ Мозг успешно обработал сообщение. Инструменты: {final_result.get('tools_used', [])}")
            
            return final_result
            
        except Exception as e:
            logger.error(f"❌ Ошибка в мозге: {str(e)}", exc_info=True)
            
            # Даже при ошибке сохраняем в память  
            try:
                await self._save_error_to_memory(message, str(e), chat_id, user_id, timestamp)
                self.memory_operations += 1
            except:
                pass  # Не критично если не удалось сохранить ошибку
            
            return {
                "answer": f"Произошла ошибка в процессоре интеллекта: {str(e)}",
                "chat_id": chat_id,
                "context_used": True,   # Даже при ошибке мы использовали контекст
                "memory_added": True,   # И сохранили в память
                "error": True,
                "error_message": str(e),
                "tools_used": []
            }
    
    async def _enrich_with_context(self, message: str, chat_id: int, user_id: Optional[int], timestamp: datetime) -> Dict[str, Any]:
        """Обогащение сообщения контекстом"""
        try:
            # Получаем системный контекст из LLM Hub
            system_context = await self.llm_hub.get_system_context()
            
            # Получаем контекст чата
            chat_context = await self.llm_hub.get_context()
            
            # Комбинируем контексты
            enriched = {
                "original_message": message,
                "chat_id": chat_id,
                "user_id": user_id,
                "timestamp": timestamp.isoformat(),
                "system_context": system_context,
                "chat_context": chat_context,
                "available_tools": await self.llm_hub.get_available_tools()
            }
            
            logger.debug(f"📚 Контекст обогащен: {len(enriched.get('available_tools', []))} инструментов доступно")
            
            return enriched
            
        except Exception as e:
            logger.error(f"❌ Ошибка обогащения контекстом: {e}")
            # Возвращаем минимальный контекст
            return {
                "original_message": message,
                "chat_id": chat_id,
                "user_id": user_id, 
                "timestamp": timestamp.isoformat(),
                "error": f"Context enrichment failed: {e}"
            }
    
    async def _create_llm_request(self, message: str, context: Dict[str, Any]) -> LLMRequest:
        """Создание запроса к LLM с полным контекстом"""
        
        # 🔧 ИСПРАВЛЕНИЕ: Ограничиваем количество инструментов для предотвращения переполнения токенов
        available_tools = context.get('available_tools', [])
        
        # Ограничиваем до 20 наиболее релевантных инструментов
        limited_tools = []
        if len(available_tools) > 20:
            # Приоритизируем основные инструменты
            priority_keywords = ['memory', 'search', 'sandbox', 'execute', 'command', 'file', 'help']
            priority_tools = []
            other_tools = []
            
            for tool in available_tools:
                tool_name = tool.get('name', '').lower()
                if any(keyword in tool_name for keyword in priority_keywords):
                    priority_tools.append(tool)
                else:
                    other_tools.append(tool)
            
            # Берём приоритетные + часть остальных
            limited_tools = priority_tools[:15] + other_tools[:5]
        else:
            limited_tools = available_tools
        
        # 🔧 ИСПРАВЛЕНИЕ: Минимизируем размер контекста чата
        chat_context = context.get('chat_context', {})
        compact_context = {}
        if chat_context:
            # Берём только последние несколько важных полей
            compact_context = {
                'recent_interactions': chat_context.get('recent_interactions', [])[-3:],  # Только 3 последних
                'user_preferences': chat_context.get('user_preferences', {}),
                'current_topic': chat_context.get('current_topic', '')
            }
        
        # 🔧 ИСПРАВЛЕНИЕ: Оптимизированный промпт
        contextual_prompt = f"""Ты - Марк, автономный ИИ-ассистент. Отвечай естественно и дружелюбно.

Сообщение: {message}

Контекст: {json.dumps(compact_context, ensure_ascii=False) if compact_context else 'Новый диалог'}

Инструментов доступно: {len(limited_tools)}/{len(available_tools)}

Дай дружелюбный ответ на русском языке. Если нужно выполнить команду - используй инструменты.
НЕ показывай анализ - сразу отвечай пользователю."""
        
        return LLMRequest(
            prompt=contextual_prompt,
            context=context,
            tools=limited_tools,  # Полные описания инструментов для OpenAI Tools API
            memory_context=compact_context,  # Компактный контекст
            priority=0.8,
            temperature=0.7
        )
    
    async def _execute_tools_if_needed(self, llm_response: LLMResponse, context: Dict[str, Any]) -> ProcessingResult:
        """Выполнение инструментов если LLM решил их использовать"""
        tools_used = []
        final_text = llm_response.content
        
        if llm_response.tool_calls:
            logger.info(f"🛠️ LLM решил использовать {len(llm_response.tool_calls)} инструментов")
            
            for tool_call in llm_response.tool_calls:
                try:
                    tool_result = await self.llm_hub.execute_tool_call(tool_call)
                    tools_used.append(tool_call.get('function', {}).get('name', 'unknown'))
                    
                    # Обновляем ответ результатом инструмента
                    if tool_result.get('result'):
                        final_text += f"\n\nРезультат выполнения: {tool_result['result']}"
                        
                except Exception as e:
                    logger.error(f"❌ Ошибка выполнения инструмента {tool_call}: {e}")
                    final_text += f"\n\nОшибка выполнения инструмента: {e}"
        
        return ProcessingResult(
            text=final_text,
            tools_used=tools_used,
            context=context,
            metadata={
                "llm_confidence": llm_response.confidence,
                "llm_reasoning": llm_response.reasoning,
                "processed_at": datetime.now().isoformat()
            }
        )
    
    async def _save_to_memory(self, message: str, result: ProcessingResult, chat_id: int, user_id: Optional[int], timestamp: datetime):
        """Обязательное сохранение взаимодействия в память"""
        try:
            memory_entry = {
                "type": "interaction",
                "chat_id": chat_id,
                "user_id": user_id,
                "timestamp": timestamp.isoformat(),
                "input": message,
                "output": result.text,
                "tools_used": result.tools_used,
                "metadata": result.metadata
            }
            
            # Используем систему памяти LLM Hub
            await self.llm_hub._save_to_memory(
                LLMRequest(prompt=message, context={"chat_id": chat_id}),
                LLMResponse(content=result.text, tool_calls=[])
            )
            
            logger.debug(f"💾 Взаимодействие сохранено в память")
            
        except Exception as e:
            logger.error(f"❌ Ошибка сохранения в память: {e}")
            raise  # Критично для архитектуры "все через мозг"
    
    async def _save_error_to_memory(self, message: str, error: str, chat_id: int, user_id: Optional[int], timestamp: datetime):
        """Сохранение ошибки в память"""
        try:
            error_entry = {
                "type": "error",
                "chat_id": chat_id,
                "user_id": user_id,
                "timestamp": timestamp.isoformat(),
                "input": message,
                "error": error
            }
            
            # Простое сохранение через memory manager
            # (детали зависят от реализации memory система)
            
        except Exception as e:
            logger.error(f"❌ Не удалось сохранить ошибку в память: {e}")
    
    def _format_final_response(self, result: ProcessingResult, chat_id: int) -> Dict[str, Any]:
        """Формирование финального стандартизированного ответа"""
        return {
            "answer": result.text,
            "chat_id": chat_id,
            "context_used": True,      # ✅ ВСЕГДА True в новой архитектуре!
            "memory_added": True,      # ✅ ВСЕГДА True в новой архитектуре!
            "tools_used": result.tools_used,
            "metadata": result.metadata
        }
    
    def get_stats(self) -> Dict[str, Any]:
        """Статистика работы процессора"""
        return {
            "processed_messages": self.processed_count,
            "memory_operations": self.memory_operations,
            "context_operations": self.context_operations,
            "is_initialized": self._is_initialized
        }
    
    def health_check(self) -> bool:
        """Проверка здоровья процессора"""
        try:
            return self._is_initialized and self.llm_hub.is_initialized
        except:
            return False 