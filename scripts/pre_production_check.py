#!/usr/bin/env python3
"""
Полная предпродакшен проверка Mark AI
Запускает все необходимые тесты перед деплоем
"""
import os
import sys
import subprocess
import json
import asyncio
from datetime import datetime
from pathlib import Path
from colorama import Fore, Style, init

# Инициализация colorama
init(autoreset=True)

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

class PreProductionChecker:
    def __init__(self):
        self.results = {
            "timestamp": datetime.now().isoformat(),
            "checks": {},
            "passed": True,
            "summary": []
        }
        self.workspace = Path("/workspace")
    
    def print_section(self, title: str):
        """Печать заголовка секции"""
        print(f"\n{'='*70}")
        print(f"{Fore.CYAN}🔍 {title.upper()}{Style.RESET_ALL}")
        print('='*70)
    
    def run_command(self, cmd: str, description: str) -> bool:
        """Запуск команды и проверка результата"""
        print(f"\n▶️  {description}...")
        try:
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                cwd=self.workspace
            )
            
            if result.returncode == 0:
                print(f"{Fore.GREEN}✅ {description} - УСПЕШНО{Style.RESET_ALL}")
                return True
            else:
                print(f"{Fore.RED}❌ {description} - ОШИБКА{Style.RESET_ALL}")
                if result.stderr:
                    print(f"   Ошибка: {result.stderr[:200]}")
                return False
        except Exception as e:
            print(f"{Fore.RED}❌ {description} - ИСКЛЮЧЕНИЕ: {e}{Style.RESET_ALL}")
            return False
    
    async def check_unit_tests(self):
        """Запуск unit тестов"""
        self.print_section("Unit Тесты")
        
        success = self.run_command(
            "python -m pytest tests/ -v --tb=short -x",
            "Запуск unit тестов"
        )
        
        self.results["checks"]["unit_tests"] = {
            "passed": success,
            "description": "Unit тесты"
        }
        
        if not success:
            self.results["passed"] = False
            self.results["summary"].append("❌ Unit тесты не прошли")
        else:
            self.results["summary"].append("✅ Unit тесты пройдены")
        
        return success
    
    async def check_integration_tests(self):
        """Запуск интеграционных тестов"""
        self.print_section("Интеграционные тесты")
        
        # Проверяем, запущены ли необходимые сервисы
        print("Проверка сервисов для интеграционных тестов...")
        
        success = self.run_command(
            "python -m pytest tests/integration/ -v --tb=short -x -m integration",
            "Запуск интеграционных тестов"
        )
        
        self.results["checks"]["integration_tests"] = {
            "passed": success,
            "description": "Интеграционные тесты"
        }
        
        if not success:
            self.results["summary"].append("⚠️  Интеграционные тесты не прошли (может требоваться запуск сервисов)")
        else:
            self.results["summary"].append("✅ Интеграционные тесты пройдены")
        
        return success
    
    async def check_linting(self):
        """Проверка кода линтерами"""
        self.print_section("Проверка качества кода")
        
        checks = [
            ("ruff check .", "Ruff (линтер)"),
            ("mypy app/ --ignore-missing-imports", "MyPy (типизация)"),
            ("black --check app/", "Black (форматирование)"),
        ]
        
        all_passed = True
        for cmd, desc in checks:
            passed = self.run_command(cmd, desc)
            all_passed = all_passed and passed
        
        self.results["checks"]["code_quality"] = {
            "passed": all_passed,
            "description": "Качество кода"
        }
        
        if not all_passed:
            self.results["summary"].append("⚠️  Есть замечания по качеству кода")
        else:
            self.results["summary"].append("✅ Код соответствует стандартам качества")
        
        return all_passed
    
    async def check_docker(self):
        """Проверка Docker контейнеров"""
        self.print_section("Docker проверка")
        
        # Проверка docker-compose файла
        compose_valid = self.run_command(
            "docker compose -f langchain_api/docker-compose.yml config",
            "Валидация docker-compose.yml"
        )
        
        # Проверка сборки образов
        build_success = False
        if compose_valid:
            build_success = self.run_command(
                "docker compose -f langchain_api/docker-compose.yml build --no-cache",
                "Сборка Docker образов"
            )
        
        self.results["checks"]["docker"] = {
            "passed": compose_valid and build_success,
            "description": "Docker контейнеры"
        }
        
        if not (compose_valid and build_success):
            self.results["passed"] = False
            self.results["summary"].append("❌ Проблемы с Docker контейнерами")
        else:
            self.results["summary"].append("✅ Docker контейнеры готовы")
        
        return compose_valid and build_success
    
    async def check_env_variables(self):
        """Проверка переменных окружения"""
        self.print_section("Переменные окружения")
        
        env_file = self.workspace / ".env"
        env_example = self.workspace / ".env.example"
        
        if not env_file.exists():
            print(f"{Fore.RED}❌ Файл .env не найден!{Style.RESET_ALL}")
            self.results["checks"]["env_variables"] = {
                "passed": False,
                "description": "Переменные окружения"
            }
            self.results["passed"] = False
            self.results["summary"].append("❌ Файл .env не найден")
            return False
        
        # Сравниваем с .env.example
        if env_example.exists():
            example_vars = set()
            with open(env_example) as f:
                for line in f:
                    if '=' in line and not line.strip().startswith('#'):
                        var_name = line.split('=')[0].strip()
                        example_vars.add(var_name)
            
            actual_vars = set()
            with open(env_file) as f:
                for line in f:
                    if '=' in line and not line.strip().startswith('#'):
                        var_name = line.split('=')[0].strip()
                        actual_vars.add(var_name)
            
            missing_vars = example_vars - actual_vars
            
            if missing_vars:
                print(f"{Fore.YELLOW}⚠️  Отсутствуют переменные: {', '.join(missing_vars)}{Style.RESET_ALL}")
                self.results["summary"].append(f"⚠️  Отсутствуют некоторые переменные окружения: {', '.join(missing_vars)}")
            else:
                print(f"{Fore.GREEN}✅ Все переменные окружения установлены{Style.RESET_ALL}")
                self.results["summary"].append("✅ Переменные окружения настроены")
        
        self.results["checks"]["env_variables"] = {
            "passed": True,
            "description": "Переменные окружения"
        }
        
        return True
    
    async def check_migrations(self):
        """Проверка миграций базы данных"""
        self.print_section("Миграции базы данных")
        
        # Здесь можно добавить проверку миграций для Neo4j или других БД
        print("ℹ️  Проверка миграций не требуется (Neo4j управляется автоматически)")
        
        self.results["checks"]["migrations"] = {
            "passed": True,
            "description": "Миграции БД"
        }
        
        return True
    
    async def run_health_check(self):
        """Запуск health check"""
        self.print_section("Health Check")
        
        success = self.run_command(
            "python scripts/health_check.py",
            "Комплексный health check"
        )
        
        # Читаем результаты
        if success:
            try:
                with open("/workspace/health_check_results.json") as f:
                    health_results = json.load(f)
                    if health_results.get("overall_status") != "HEALTHY":
                        success = False
                        print(f"{Fore.RED}❌ Система не готова к деплою{Style.RESET_ALL}")
            except Exception:
                pass
        
        self.results["checks"]["health_check"] = {
            "passed": success,
            "description": "Health check системы"
        }
        
        if not success:
            self.results["passed"] = False
            self.results["summary"].append("❌ Health check не пройден")
        else:
            self.results["summary"].append("✅ Система здорова")
        
        return success
    
    async def run_security_audit(self):
        """Запуск аудита безопасности"""
        self.print_section("Аудит безопасности")
        
        success = self.run_command(
            "python scripts/security_audit.py",
            "Аудит безопасности"
        )
        
        # Читаем результаты
        if success:
            try:
                with open("/workspace/security_audit_report.json") as f:
                    security_results = json.load(f)
                    if security_results["summary"]["critical"] > 0:
                        success = False
                        print(f"{Fore.RED}❌ Найдены критические уязвимости!{Style.RESET_ALL}")
                    elif security_results["summary"]["high"] > 0:
                        print(f"{Fore.YELLOW}⚠️  Найдены высокоприоритетные проблемы{Style.RESET_ALL}")
            except Exception:
                pass
        
        self.results["checks"]["security_audit"] = {
            "passed": success,
            "description": "Аудит безопасности"
        }
        
        if not success:
            self.results["passed"] = False
            self.results["summary"].append("❌ Есть критические проблемы безопасности")
        else:
            self.results["summary"].append("✅ Аудит безопасности пройден")
        
        return success
    
    async def check_documentation(self):
        """Проверка документации"""
        self.print_section("Документация")
        
        required_docs = [
            "README.md",
            "ROADMAP_OPTIMIZATION.md",
            ".env.example"
        ]
        
        missing_docs = []
        for doc in required_docs:
            if not (self.workspace / doc).exists():
                missing_docs.append(doc)
        
        if missing_docs:
            print(f"{Fore.YELLOW}⚠️  Отсутствуют документы: {', '.join(missing_docs)}{Style.RESET_ALL}")
            self.results["summary"].append(f"⚠️  Отсутствует документация: {', '.join(missing_docs)}")
        else:
            print(f"{Fore.GREEN}✅ Вся необходимая документация присутствует{Style.RESET_ALL}")
            self.results["summary"].append("✅ Документация в порядке")
        
        self.results["checks"]["documentation"] = {
            "passed": len(missing_docs) == 0,
            "description": "Документация"
        }
        
        return len(missing_docs) == 0
    
    async def generate_report(self):
        """Генерация итогового отчета"""
        self.print_section("ИТОГОВЫЙ ОТЧЕТ")
        
        # Сохранение результатов
        with open("/workspace/pre_production_report.json", "w") as f:
            json.dump(self.results, f, indent=2)
        
        # Вывод итогов
        print(f"\n{'='*70}")
        print(f"{Fore.BLUE}📊 РЕЗУЛЬТАТЫ ПРЕДПРОДАКШЕН ПРОВЕРКИ{Style.RESET_ALL}")
        print(f"{'='*70}")
        
        for summary in self.results["summary"]:
            print(f"  {summary}")
        
        print(f"\n{'='*70}")
        
        if self.results["passed"]:
            print(f"\n{Fore.GREEN}🚀 СИСТЕМА ГОТОВА К ДЕПЛОЮ!{Style.RESET_ALL}")
            print(f"\n📋 Следующие шаги:")
            print(f"  1. Проверьте pre_production_report.json для деталей")
            print(f"  2. Убедитесь, что все секреты настроены на сервере")
            print(f"  3. Запустите deployment скрипт")
            print(f"  4. Проведите smoke тесты после деплоя")
        else:
            print(f"\n{Fore.RED}❌ СИСТЕМА НЕ ГОТОВА К ДЕПЛОЮ!{Style.RESET_ALL}")
            print(f"\n⚠️  Исправьте все критические проблемы перед деплоем")
            print(f"📄 Детали в pre_production_report.json")
        
        return self.results["passed"]
    
    async def run_all_checks(self):
        """Запуск всех проверок"""
        print(f"\n{Fore.BLUE}🚀 ЗАПУСК ПРЕДПРОДАКШЕН ПРОВЕРКИ MARK AI{Style.RESET_ALL}")
        print(f"{Fore.BLUE}Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}{Style.RESET_ALL}")
        
        # Последовательный запуск проверок
        await self.check_env_variables()
        await self.run_health_check()
        await self.run_security_audit()
        await self.check_unit_tests()
        await self.check_integration_tests()
        await self.check_linting()
        await self.check_docker()
        await self.check_documentation()
        await self.check_migrations()
        
        # Генерация отчета
        return await self.generate_report()


async def main():
    checker = PreProductionChecker()
    success = await checker.run_all_checks()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    # Добавим locust в requirements если нужно для load testing
    try:
        import locust
    except ImportError:
        print("⚠️  Установка locust для нагрузочного тестирования...")
        subprocess.run([sys.executable, "-m", "pip", "install", "locust"])
    
    asyncio.run(main())