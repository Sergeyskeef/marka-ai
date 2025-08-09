#!/usr/bin/env python3
"""
Smoke тесты для Mark AI
Быстрая проверка критического функционала после деплоя
"""
import asyncio
import sys
import httpx
from openai import AsyncOpenAI
import redis.asyncio as redis
from neo4j import AsyncGraphDatabase
from colorama import Fore, Style, init

# Инициализация colorama
init(autoreset=True)

sys.path.append("/workspace")
from app.config import settings


class SmokeTests:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.tests = []
    
    def add_result(self, test_name: str, passed: bool, error: str = None):
        """Добавить результат теста"""
        if passed:
            self.passed += 1
            print(f"{Fore.GREEN}✅ {test_name}{Style.RESET_ALL}")
        else:
            self.failed += 1
            print(f"{Fore.RED}❌ {test_name}{Style.RESET_ALL}")
            if error:
                print(f"   {Fore.YELLOW}Ошибка: {error}{Style.RESET_ALL}")
        
        self.tests.append({
            "name": test_name,
            "passed": passed,
            "error": error
        })
    
    async def test_api_health(self):
        """Тест health эндпоинта"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get("http://localhost:8001/health")
                self.add_result(
                    "API Health Check",
                    response.status_code == 200 and response.json().get("status") == "healthy"
                )
        except Exception as e:
            self.add_result("API Health Check", False, str(e))
    
    async def test_chat_endpoint(self):
        """Тест chat эндпоинта"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "http://localhost:8001/api/chat",
                    json={"message": "Привет!", "user_id": "smoke_test"},
                    timeout=30.0
                )
                self.add_result(
                    "Chat Endpoint",
                    response.status_code == 200 and "response" in response.json()
                )
        except Exception as e:
            self.add_result("Chat Endpoint", False, str(e))
    
    async def test_redis_connection(self):
        """Тест подключения к Redis"""
        try:
            r = redis.from_url(settings.REDIS_URL)
            await r.ping()
            await r.close()
            self.add_result("Redis Connection", True)
        except Exception as e:
            self.add_result("Redis Connection", False, str(e))
    
    async def test_neo4j_connection(self):
        """Тест подключения к Neo4j"""
        try:
            driver = AsyncGraphDatabase.driver(
                settings.NEO4J_URI,
                auth=(settings.NEO4J_USERNAME, settings.NEO4J_PASSWORD)
            )
            async with driver.session() as session:
                result = await session.run("RETURN 1 as test")
                await result.single()
            await driver.close()
            self.add_result("Neo4j Connection", True)
        except Exception as e:
            self.add_result("Neo4j Connection", False, str(e))
    
    async def test_openai_api(self):
        """Тест OpenAI API"""
        try:
            client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
            response = await client.chat.completions.create(
                model=settings.OPENAI_MODEL,
                messages=[{"role": "user", "content": "test"}],
                max_tokens=5
            )
            self.add_result("OpenAI API", True)
        except Exception as e:
            self.add_result("OpenAI API", False, str(e))
    
    async def test_prompts_api(self):
        """Тест API промптов"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get("http://localhost:8001/api/prompts")
                self.add_result(
                    "Prompts API",
                    response.status_code == 200
                )
        except Exception as e:
            self.add_result("Prompts API", False, str(e))
    
    async def test_api_docs(self):
        """Тест документации API"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get("http://localhost:8001/docs")
                self.add_result(
                    "API Documentation",
                    response.status_code == 200
                )
        except Exception as e:
            self.add_result("API Documentation", False, str(e))
    
    async def test_metrics_endpoint(self):
        """Тест эндпоинта метрик"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get("http://localhost:8001/metrics")
                self.add_result(
                    "Prometheus Metrics",
                    response.status_code == 200 and "prompt_selections_total" in response.text
                )
        except Exception as e:
            self.add_result("Prometheus Metrics", False, str(e))
    
    async def run_all_tests(self):
        """Запуск всех smoke тестов"""
        print(f"\n{Fore.BLUE}🔥 SMOKE ТЕСТЫ MARK AI{Style.RESET_ALL}")
        print("="*50)
        
        # Запускаем тесты
        await self.test_api_health()
        await self.test_redis_connection()
        await self.test_neo4j_connection()
        await self.test_openai_api()
        await self.test_chat_endpoint()
        await self.test_prompts_api()
        await self.test_api_docs()
        await self.test_metrics_endpoint()
        
        # Итоги
        print("\n" + "="*50)
        print(f"{Fore.BLUE}ИТОГИ:{Style.RESET_ALL}")
        print(f"  ✅ Пройдено: {self.passed}")
        print(f"  ❌ Провалено: {self.failed}")
        print(f"  📊 Всего: {self.passed + self.failed}")
        
        success_rate = (self.passed / (self.passed + self.failed)) * 100 if (self.passed + self.failed) > 0 else 0
        
        if success_rate == 100:
            print(f"\n{Fore.GREEN}✅ ВСЕ ТЕСТЫ ПРОЙДЕНЫ!{Style.RESET_ALL}")
        elif success_rate >= 80:
            print(f"\n{Fore.YELLOW}⚠️  БОЛЬШИНСТВО ТЕСТОВ ПРОЙДЕНО ({success_rate:.0f}%){Style.RESET_ALL}")
        else:
            print(f"\n{Fore.RED}❌ КРИТИЧЕСКИЕ ТЕСТЫ НЕ ПРОЙДЕНЫ ({success_rate:.0f}%){Style.RESET_ALL}")
        
        # Возвращаем успех, если критические тесты пройдены
        critical_tests = ["API Health Check", "Redis Connection", "Neo4j Connection", "OpenAI API"]
        critical_passed = all(
            test["passed"] for test in self.tests 
            if test["name"] in critical_tests
        )
        
        if not critical_passed:
            print(f"\n{Fore.RED}❌ Критические компоненты не работают!{Style.RESET_ALL}")
        
        return critical_passed


async def main():
    tester = SmokeTests()
    success = await tester.run_all_tests()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())