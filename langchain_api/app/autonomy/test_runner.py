"""
Модуль для запуска и анализа тестов
"""

import logging
from typing import Dict, List, Any, Optional
import re
import json

from app.agents.mark_agent import MarkAgent
from sandbox.sandbox_manager import SandboxManager

logger = logging.getLogger(__name__)


class TestRunner:
    """
    Запускатель тестов
    
    Способности:
    - Запуск unit тестов
    - Запуск интеграционных тестов
    - Анализ результатов тестирования
    - Генерация отчетов о покрытии
    - Автоматическое исправление простых ошибок
    """
    
    def __init__(self, mark_agent: MarkAgent):
        """
        Инициализация запускателя тестов
        
        Args:
            mark_agent: Агент для анализа результатов
        """
        self.agent = mark_agent
        self.sandbox = SandboxManager()
        logger.info("🧪 TestRunner инициализирован")
    
    async def run_tests(
        self,
        test_path: str = "tests/",
        verbose: bool = False,
        coverage: bool = True
    ) -> Dict[str, Any]:
        """
        Запустить тесты
        
        Args:
            test_path: Путь к тестам
            verbose: Подробный вывод
            coverage: Измерять покрытие кода
            
        Returns:
            Результаты тестирования
        """
        try:
            logger.info(f"🚀 Запуск тестов: {test_path}")
            
            # Формируем команду pytest
            cmd_parts = ["pytest", test_path]
            
            if verbose:
                cmd_parts.append("-v")
            
            if coverage:
                cmd_parts.extend(["--cov=app", "--cov-report=json"])
            
            # Добавляем вывод в JSON для парсинга
            cmd_parts.append("--json-report")
            cmd_parts.append("--json-report-file=/tmp/test_report.json")
            
            cmd = " ".join(cmd_parts)
            
            # Запускаем тесты в песочнице
            result = await self.sandbox.execute_command(cmd)
            
            # Парсим результаты
            test_results = await self._parse_test_results(result)
            
            # Анализируем ошибки
            if test_results["failed"] > 0:
                test_results["error_analysis"] = await self._analyze_failures(test_results)
            
            # Получаем отчет о покрытии
            if coverage:
                coverage_result = await self._get_coverage_report()
                test_results["coverage"] = coverage_result
            
            return test_results
            
        except Exception as e:
            logger.error(f"❌ Ошибка запуска тестов: {str(e)}")
            return {
                "status": "error",
                "error": str(e),
                "passed": 0,
                "failed": 0,
                "skipped": 0
            }
    
    async def run_specific_test(
        self,
        test_file: str,
        test_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Запустить конкретный тест
        
        Args:
            test_file: Путь к файлу с тестом
            test_name: Имя конкретного теста (опционально)
            
        Returns:
            Результат теста
        """
        try:
            logger.info(f"🎯 Запуск теста: {test_file}::{test_name or ''}")
            
            # Формируем команду
            test_path = test_file
            if test_name:
                test_path += f"::{test_name}"
            
            cmd = f"pytest {test_path} -v --tb=short"
            
            # Запускаем
            result = await self.sandbox.execute_command(cmd)
            
            # Парсим результат
            return await self._parse_single_test_result(result)
            
        except Exception as e:
            logger.error(f"❌ Ошибка запуска теста: {str(e)}")
            return {
                "status": "error",
                "error": str(e)
            }
    
    async def fix_test_errors(
        self,
        test_results: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Попытаться исправить ошибки в тестах
        
        Args:
            test_results: Результаты тестирования с ошибками
            
        Returns:
            Результаты исправления
        """
        try:
            logger.info("🔧 Попытка исправить ошибки тестов")
            
            fixes_applied = []
            
            for failure in test_results.get("failures", []):
                # Анализируем тип ошибки
                error_type = self._classify_error(failure["error"])
                
                if error_type == "import_error":
                    fix_result = await self._fix_import_error(failure)
                elif error_type == "assertion_error":
                    fix_result = await self._fix_assertion_error(failure)
                elif error_type == "attribute_error":
                    fix_result = await self._fix_attribute_error(failure)
                else:
                    fix_result = {
                        "status": "skip",
                        "reason": f"Неизвестный тип ошибки: {error_type}"
                    }
                
                fixes_applied.append({
                    "test": failure["test"],
                    "error_type": error_type,
                    "fix_result": fix_result
                })
            
            # Перезапускаем тесты после исправлений
            if any(f["fix_result"]["status"] == "fixed" for f in fixes_applied):
                logger.info("🔄 Перезапуск тестов после исправлений")
                new_results = await self.run_tests(test_results.get("test_path", "tests/"))
                
                return {
                    "status": "completed",
                    "fixes_applied": fixes_applied,
                    "new_results": new_results
                }
            
            return {
                "status": "no_fixes",
                "fixes_attempted": fixes_applied
            }
            
        except Exception as e:
            logger.error(f"❌ Ошибка при исправлении тестов: {str(e)}")
            return {
                "status": "error",
                "error": str(e)
            }
    
    async def _parse_test_results(self, raw_output: Dict[str, Any]) -> Dict[str, Any]:
        """Парсить результаты тестов"""
        output = raw_output.get("output", "")
        
        # Базовые метрики
        results = {
            "status": "success" if raw_output.get("exit_code") == 0 else "failed",
            "passed": 0,
            "failed": 0,
            "skipped": 0,
            "errors": 0,
            "duration": 0,
            "failures": []
        }
        
        # Парсим summary line
        summary_match = re.search(
            r'(\d+) passed(?:, (\d+) failed)?(?:, (\d+) skipped)?(?:, (\d+) error)?.*in ([\d.]+)s',
            output
        )
        
        if summary_match:
            results["passed"] = int(summary_match.group(1))
            results["failed"] = int(summary_match.group(2) or 0)
            results["skipped"] = int(summary_match.group(3) or 0)
            results["errors"] = int(summary_match.group(4) or 0)
            results["duration"] = float(summary_match.group(5))
        
        # Парсим детали ошибок
        if results["failed"] > 0 or results["errors"] > 0:
            results["failures"] = self._extract_failures(output)
        
        # Пытаемся загрузить JSON отчет
        try:
            json_report = await self.sandbox.execute_command("cat /tmp/test_report.json")
            if json_report.get("exit_code") == 0:
                report_data = json.loads(json_report["output"])
                results["detailed_report"] = report_data
        except:
            pass
        
        return results
    
    def _extract_failures(self, output: str) -> List[Dict[str, Any]]:
        """Извлечь информацию об ошибках"""
        failures = []
        
        # Парсим FAILURES секцию
        failure_sections = re.findall(
            r'FAILED (.*?) - (.*?)(?=FAILED|=|$)',
            output,
            re.DOTALL
        )
        
        for test_name, error_text in failure_sections:
            failures.append({
                "test": test_name.strip(),
                "error": error_text.strip(),
                "traceback": self._extract_traceback(error_text)
            })
        
        return failures
    
    def _extract_traceback(self, error_text: str) -> List[str]:
        """Извлечь traceback из текста ошибки"""
        lines = error_text.split('\n')
        traceback = []
        
        for line in lines:
            if line.strip().startswith('File "'):
                traceback.append(line.strip())
        
        return traceback
    
    async def _analyze_failures(self, test_results: Dict[str, Any]) -> Dict[str, Any]:
        """Анализировать причины провала тестов"""
        failures = test_results.get("failures", [])
        
        if not failures:
            return {"analysis": "Нет ошибок для анализа"}
        
        # Формируем промпт для анализа
        analysis_prompt = f"""
        Проанализируй следующие ошибки тестов и предложи решения:
        
        {json.dumps(failures, indent=2, ensure_ascii=False)}
        
        Для каждой ошибки определи:
        1. Тип ошибки
        2. Вероятную причину
        3. Предлагаемое решение
        4. Код для исправления (если применимо)
        """
        
        response = await self.agent.generate_response(
            analysis_prompt,
            temperature=0.3
        )
        
        return {
            "analysis": response,
            "failure_count": len(failures),
            "common_issues": self._identify_common_issues(failures)
        }
    
    def _identify_common_issues(self, failures: List[Dict[str, Any]]) -> List[str]:
        """Идентифицировать общие проблемы"""
        issues = []
        
        import_errors = sum(1 for f in failures if "ImportError" in f["error"])
        if import_errors > 0:
            issues.append(f"Import errors: {import_errors}")
        
        assertion_errors = sum(1 for f in failures if "AssertionError" in f["error"])
        if assertion_errors > 0:
            issues.append(f"Assertion failures: {assertion_errors}")
        
        attribute_errors = sum(1 for f in failures if "AttributeError" in f["error"])
        if attribute_errors > 0:
            issues.append(f"Attribute errors: {attribute_errors}")
        
        return issues
    
    async def _get_coverage_report(self) -> Dict[str, Any]:
        """Получить отчет о покрытии кода"""
        try:
            # Читаем JSON отчет о покрытии
            coverage_json = await self.sandbox.execute_command("cat coverage.json")
            
            if coverage_json.get("exit_code") == 0:
                coverage_data = json.loads(coverage_json["output"])
                
                # Извлекаем ключевые метрики
                total_coverage = coverage_data.get("totals", {}).get("percent_covered", 0)
                
                return {
                    "total_coverage": total_coverage,
                    "files": coverage_data.get("files", {}),
                    "summary": f"Общее покрытие: {total_coverage:.1f}%"
                }
            
        except Exception as e:
            logger.error(f"Ошибка получения покрытия: {str(e)}")
        
        return {"total_coverage": 0, "summary": "Покрытие недоступно"}
    
    def _classify_error(self, error_text: str) -> str:
        """Классифицировать тип ошибки"""
        if "ImportError" in error_text or "ModuleNotFoundError" in error_text:
            return "import_error"
        elif "AssertionError" in error_text:
            return "assertion_error"
        elif "AttributeError" in error_text:
            return "attribute_error"
        elif "TypeError" in error_text:
            return "type_error"
        elif "ValueError" in error_text:
            return "value_error"
        else:
            return "unknown"
    
    async def _fix_import_error(self, failure: Dict[str, Any]) -> Dict[str, Any]:
        """Попытаться исправить ошибку импорта"""
        # Извлекаем имя модуля
        module_match = re.search(r"No module named '(\w+)'", failure["error"])
        if module_match:
            module_name = module_match.group(1)
            
            # Пытаемся установить модуль
            install_result = await self.sandbox.execute_command(f"pip install {module_name}")
            
            if install_result.get("exit_code") == 0:
                return {"status": "fixed", "action": f"Установлен модуль {module_name}"}
        
        return {"status": "failed", "reason": "Не удалось определить модуль"}
    
    async def _fix_assertion_error(self, failure: Dict[str, Any]) -> Dict[str, Any]:
        """Попытаться исправить ошибку assertion"""
        # Это сложнее автоматизировать, используем агента
        fix_prompt = f"""
        Тест провалился с AssertionError:
        {failure['error']}
        
        Предложи исправление для теста или кода.
        """
        
        response = await self.agent.generate_response(fix_prompt)
        
        return {
            "status": "suggestion",
            "suggestion": response
        }
    
    async def _fix_attribute_error(self, failure: Dict[str, Any]) -> Dict[str, Any]:
        """Попытаться исправить ошибку атрибута"""
        # Аналогично assertion error
        return await self._fix_assertion_error(failure)
    
    async def _parse_single_test_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Парсить результат одного теста"""
        output = result.get("output", "")
        
        if result.get("exit_code") == 0:
            return {
                "status": "passed",
                "output": output
            }
        else:
            return {
                "status": "failed",
                "output": output,
                "error": self._extract_error_from_output(output)
            }
    
    def _extract_error_from_output(self, output: str) -> str:
        """Извлечь сообщение об ошибке из вывода"""
        # Ищем секцию с ошибкой
        error_match = re.search(r'E\s+(.*?)(?=\n[A-Z]|\n=|$)', output, re.DOTALL)
        if error_match:
            return error_match.group(1).strip()
        return "Неизвестная ошибка"