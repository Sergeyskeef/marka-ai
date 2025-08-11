"""
Генератор кода для автономного агента
"""

import logging
from typing import Dict, List, Any, Optional
import re
import ast

from app.agents.mark_agent import MarkAgent
from app.memory.advanced_memory_adapter import AdvancedMemoryAdapter

logger = logging.getLogger(__name__)


class CodeGenerator:
    """
    Генератор кода
    
    Способности:
    - Генерация кода по описанию
    - Рефакторинг существующего кода
    - Создание тестов
    - Генерация документации
    - Анализ и улучшение кода
    """
    
    def __init__(self, mark_agent: MarkAgent, memory_adapter: AdvancedMemoryAdapter):
        """
        Инициализация генератора кода
        
        Args:
            mark_agent: Агент для генерации кода
            memory_adapter: Адаптер памяти для поиска примеров
        """
        self.agent = mark_agent
        self.memory = memory_adapter
        logger.info("💻 CodeGenerator инициализирован")
    
    async def generate_code(
        self, 
        description: str,
        language: str = "python",
        requirements: Optional[List[str]] = None,
        use_memory: bool = True
    ) -> Dict[str, Any]:
        """
        Сгенерировать код по описанию
        
        Args:
            description: Описание того, что должен делать код
            language: Язык программирования
            requirements: Дополнительные требования
            use_memory: Использовать ли примеры из памяти
            
        Returns:
            Сгенерированный код и метаинформация
        """
        try:
            logger.info(f"🚀 Генерация кода: {description[:100]}...")
            
            # Ищем похожие примеры в памяти
            examples = []
            if use_memory:
                examples = await self._find_similar_code_examples(description, language)
            
            # Формируем промпт
            generation_prompt = self._create_generation_prompt(
                description, language, requirements, examples
            )
            
            # Генерируем код
            response = await self.agent.generate_response(
                generation_prompt,
                use_tools=False,
                temperature=0.3
            )
            
            # Извлекаем код из ответа
            code = self._extract_code_from_response(response, language)
            
            # Валидируем код
            validation_result = await self._validate_code(code, language)
            
            # Сохраняем успешный код в память
            if validation_result["is_valid"]:
                await self._save_code_to_memory(code, description, language)
            
            return {
                "status": "success" if validation_result["is_valid"] else "warning",
                "code": code,
                "language": language,
                "validation": validation_result,
                "description": description
            }
            
        except Exception as e:
            logger.error(f"❌ Ошибка генерации кода: {str(e)}")
            return {
                "status": "error",
                "error": str(e),
                "code": ""
            }
    
    def _create_generation_prompt(
        self, 
        description: str,
        language: str,
        requirements: Optional[List[str]],
        examples: List[Dict]
    ) -> str:
        """Создать промпт для генерации кода"""
        
        examples_text = ""
        if examples:
            examples_text = "\n\nПримеры похожего кода из памяти:\n"
            for ex in examples[:2]:
                examples_text += f"\n```{language}\n{ex.get('code', '')}\n```\n"
        
        requirements_text = ""
        if requirements:
            requirements_text = "\n\nДополнительные требования:\n" + "\n".join(f"- {req}" for req in requirements)
        
        return f"""
        Напиши код на языке {language} для следующей задачи:
        
        {description}
        {requirements_text}
        {examples_text}
        
        Требования к коду:
        1. Код должен быть чистым, читаемым и хорошо структурированным
        2. Используй современные практики и паттерны
        3. Добавь необходимые комментарии и docstrings
        4. Обработай возможные ошибки
        5. Код должен быть готов к использованию
        
        Верни ТОЛЬКО код без дополнительных объяснений.
        """
    
    def _extract_code_from_response(self, response: str, language: str) -> str:
        """Извлечь код из ответа"""
        # Ищем код в markdown блоках
        code_pattern = rf"```{language}?\n(.*?)```"
        matches = re.findall(code_pattern, response, re.DOTALL)
        
        if matches:
            return matches[0].strip()
        
        # Если не нашли в блоках, пробуем найти код по отступам
        lines = response.split('\n')
        code_lines = []
        in_code = False
        
        for line in lines:
            if line.startswith('    ') or line.startswith('\t'):
                in_code = True
                code_lines.append(line)
            elif in_code and line.strip() == '':
                code_lines.append(line)
            elif in_code and not line.startswith(' '):
                break
        
        if code_lines:
            return '\n'.join(code_lines)
        
        # Если ничего не нашли, возвращаем весь ответ
        return response.strip()
    
    async def _validate_code(self, code: str, language: str) -> Dict[str, Any]:
        """Валидировать сгенерированный код"""
        validation_result = {
            "is_valid": True,
            "errors": [],
            "warnings": []
        }
        
        if language == "python":
            try:
                # Проверяем синтаксис Python
                ast.parse(code)
            except SyntaxError as e:
                validation_result["is_valid"] = False
                validation_result["errors"].append(f"Синтаксическая ошибка: {str(e)}")
            except Exception as e:
                validation_result["warnings"].append(f"Предупреждение при парсинге: {str(e)}")
        
        # Базовые проверки для всех языков
        if not code.strip():
            validation_result["is_valid"] = False
            validation_result["errors"].append("Код пустой")
        
        if len(code) < 10:
            validation_result["warnings"].append("Код слишком короткий")
        
        return validation_result
    
    async def refactor_code(
        self,
        file_path: str,
        improvements: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Рефакторинг существующего кода
        
        Args:
            file_path: Путь к файлу с кодом
            improvements: Список предлагаемых улучшений
            
        Returns:
            Отрефакторенный код
        """
        try:
            logger.info(f"🔧 Рефакторинг кода: {file_path}")
            
            # Читаем существующий код
            code_content = await self.agent.call_tool(
                "read_file",
                {"file_path": file_path}
            )
            
            if not code_content.get("content"):
                return {"status": "error", "error": "Не удалось прочитать файл"}
            
            original_code = code_content["content"]
            
            # Формируем промпт для рефакторинга
            refactor_prompt = f"""
            Проведи рефакторинг следующего кода:
            
            ```python
            {original_code}
            ```
            
            Улучшения для применения:
            {chr(10).join(f"- {imp}" for imp in (improvements or ["Общий рефакторинг"]))}
            
            Требования:
            1. Сохрани функциональность кода
            2. Улучши читаемость и структуру
            3. Следуй PEP 8 и лучшим практикам
            4. Добавь или улучши комментарии
            5. Оптимизируй производительность где возможно
            
            Верни только улучшенный код.
            """
            
            # Генерируем улучшенный код
            response = await self.agent.generate_response(
                refactor_prompt,
                temperature=0.2
            )
            
            refactored_code = self._extract_code_from_response(response, "python")
            
            # Сохраняем рефакторенный код
            save_result = await self.agent.call_tool(
                "write_file",
                {
                    "file_path": file_path,
                    "content": refactored_code
                }
            )
            
            return {
                "status": "success",
                "original_code": original_code,
                "refactored_code": refactored_code,
                "file_path": file_path,
                "improvements_applied": improvements or ["Общий рефакторинг"]
            }
            
        except Exception as e:
            logger.error(f"❌ Ошибка рефакторинга: {str(e)}")
            return {
                "status": "error",
                "error": str(e)
            }
    
    async def generate_tests(
        self,
        code_or_file: str,
        test_framework: str = "pytest"
    ) -> Dict[str, Any]:
        """
        Сгенерировать тесты для кода
        
        Args:
            code_or_file: Код или путь к файлу
            test_framework: Фреймворк для тестов (pytest, unittest)
            
        Returns:
            Сгенерированные тесты
        """
        try:
            logger.info(f"🧪 Генерация тестов с {test_framework}")
            
            # Определяем, это код или путь к файлу
            if code_or_file.endswith('.py'):
                # Это файл
                file_content = await self.agent.call_tool(
                    "read_file",
                    {"file_path": code_or_file}
                )
                code = file_content.get("content", "")
            else:
                code = code_or_file
            
            # Генерируем тесты
            test_prompt = f"""
            Напиши comprehensive тесты для следующего кода используя {test_framework}:
            
            ```python
            {code}
            ```
            
            Требования к тестам:
            1. Покрой все функции и методы
            2. Включи позитивные и негативные тест-кейсы
            3. Проверь граничные условия
            4. Используй моки где необходимо
            5. Добавь docstrings к тестам
            
            Верни только код тестов.
            """
            
            response = await self.agent.generate_response(
                test_prompt,
                temperature=0.2
            )
            
            tests_code = self._extract_code_from_response(response, "python")
            
            return {
                "status": "success",
                "tests": tests_code,
                "framework": test_framework
            }
            
        except Exception as e:
            logger.error(f"❌ Ошибка генерации тестов: {str(e)}")
            return {
                "status": "error",
                "error": str(e)
            }
    
    async def generate_documentation(
        self,
        target: str,
        format: str = "markdown"
    ) -> Dict[str, Any]:
        """
        Сгенерировать документацию
        
        Args:
            target: Путь к файлу или директории
            format: Формат документации (markdown, rst, html)
            
        Returns:
            Сгенерированная документация
        """
        try:
            logger.info(f"📚 Генерация документации в формате {format}")
            
            # Анализируем код
            analysis = await self.agent.call_tool(
                "analyze_code",
                {"file_path": target}
            )
            
            if not analysis or analysis.get("status") == "error":
                return {"status": "error", "error": "Не удалось проанализировать код"}
            
            # Генерируем документацию
            doc_prompt = f"""
            Создай подробную документацию в формате {format} для следующего кода:
            
            Анализ кода:
            {analysis}
            
            Требования к документации:
            1. Опиши назначение и основные возможности
            2. Приведи примеры использования
            3. Документируй все публичные API
            4. Добавь информацию об установке и настройке
            5. Включи раздел FAQ если применимо
            
            Формат: {format}
            """
            
            response = await self.agent.generate_response(
                doc_prompt,
                temperature=0.3
            )
            
            return {
                "status": "success",
                "documentation": response,
                "format": format,
                "target": target
            }
            
        except Exception as e:
            logger.error(f"❌ Ошибка генерации документации: {str(e)}")
            return {
                "status": "error",
                "error": str(e)
            }
    
    async def _find_similar_code_examples(self, description: str, language: str) -> List[Dict]:
        """Найти похожие примеры кода в памяти"""
        try:
            # Ищем в памяти
            similar = await self.memory.search_memories(
                query=f"code {language} {description}",
                memory_type="skill",
                limit=3
            )
            
            examples = []
            for mem in similar:
                if mem.get("metadata", {}).get("code"):
                    examples.append({
                        "code": mem["metadata"]["code"],
                        "description": mem.get("metadata", {}).get("description", ""),
                        "language": mem.get("metadata", {}).get("language", language)
                    })
            
            return examples
            
        except Exception as e:
            logger.error(f"❌ Ошибка поиска примеров: {str(e)}")
            return []
    
    async def _save_code_to_memory(self, code: str, description: str, language: str):
        """Сохранить успешный код в память"""
        try:
            await self.memory.save_skill(
                trigger=f"code_example_{language}_{description[:30]}",
                response_template=code,
                metadata={
                    "code": code,
                    "description": description,
                    "language": language,
                    "type": "code_example"
                }
            )
            logger.info("✅ Код сохранен в память")
        except Exception as e:
            logger.error(f"❌ Ошибка сохранения кода: {str(e)}")