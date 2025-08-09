#!/usr/bin/env python3
"""
Комплексный health check для предпродакшен проверки
"""
import asyncio
import sys
import os
import httpx
import redis.asyncio as redis
from openai import AsyncOpenAI
from neo4j import AsyncGraphDatabase
import psutil
import json
from datetime import datetime
from colorama import Fore, Style, init

# Инициализация colorama для цветного вывода
init(autoreset=True)

# Добавляем путь к проекту
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings


class HealthChecker:
    def __init__(self):
        self.results = {
            "timestamp": datetime.now().isoformat(),
            "checks": {},
            "overall_status": "HEALTHY",
            "warnings": [],
            "errors": []
        }
    
    def print_header(self, title: str):
        """Печать заголовка секции"""
        print(f"\n{'='*60}")
        print(f"{Fore.CYAN}{title}{Style.RESET_ALL}")
        print('='*60)
    
    def print_status(self, service: str, status: str, details: str = ""):
        """Печать статуса сервиса"""
        if status == "OK":
            status_color = Fore.GREEN
            icon = "✅"
        elif status == "WARNING":
            status_color = Fore.YELLOW
            icon = "⚠️"
        else:
            status_color = Fore.RED
            icon = "❌"
        
        print(f"{icon} {service:<30} [{status_color}{status:<7}{Style.RESET_ALL}] {details}")
    
    async def check_system_resources(self):
        """Проверка системных ресурсов"""
        self.print_header("СИСТЕМНЫЕ РЕСУРСЫ")
        
        # CPU
        cpu_percent = psutil.cpu_percent(interval=1)
        cpu_status = "OK" if cpu_percent < 80 else "WARNING" if cpu_percent < 90 else "ERROR"
        self.print_status("CPU Usage", cpu_status, f"{cpu_percent:.1f}%")
        
        # Memory
        memory = psutil.virtual_memory()
        mem_status = "OK" if memory.percent < 80 else "WARNING" if memory.percent < 90 else "ERROR"
        self.print_status("Memory Usage", mem_status, f"{memory.percent:.1f}%")
        
        # Disk
        disk = psutil.disk_usage('/')
        disk_status = "OK" if disk.percent < 80 else "WARNING" if disk.percent < 90 else "ERROR"
        self.print_status("Disk Usage", disk_status, f"{disk.percent:.1f}%")
        
        self.results["checks"]["system"] = {
            "cpu": {"percent": cpu_percent, "status": cpu_status},
            "memory": {"percent": memory.percent, "status": mem_status},
            "disk": {"percent": disk.percent, "status": disk_status}
        }
    
    async def check_redis(self):
        """Проверка Redis"""
        self.print_header("REDIS")
        
        try:
            r = redis.from_url(settings.REDIS_URL)
            await r.ping()
            
            # Проверяем память Redis
            info = await r.info("memory")
            used_memory_mb = info.get("used_memory", 0) / 1024 / 1024
            
            # Проверяем ключи
            keys_count = await r.dbsize()
            
            await r.close()
            
            self.print_status("Redis Connection", "OK", f"Keys: {keys_count}, Memory: {used_memory_mb:.1f}MB")
            self.results["checks"]["redis"] = {
                "status": "OK",
                "keys": keys_count,
                "memory_mb": used_memory_mb
            }
        except Exception as e:
            self.print_status("Redis Connection", "ERROR", str(e))
            self.results["checks"]["redis"] = {"status": "ERROR", "error": str(e)}
            self.results["overall_status"] = "UNHEALTHY"
    
    async def check_neo4j(self):
        """Проверка Neo4j"""
        self.print_header("NEO4J")
        
        try:
            driver = AsyncGraphDatabase.driver(
                settings.NEO4J_URI,
                auth=(settings.NEO4J_USERNAME, settings.NEO4J_PASSWORD)
            )
            
            async with driver.session() as session:
                # Проверяем подключение
                result = await session.run("RETURN 1 as test")
                await result.single()
                
                # Считаем узлы
                result = await session.run("MATCH (n) RETURN count(n) as count")
                node_count = (await result.single())["count"]
                
                # Считаем связи
                result = await session.run("MATCH ()-[r]->() RETURN count(r) as count")
                rel_count = (await result.single())["count"]
            
            await driver.close()
            
            self.print_status("Neo4j Connection", "OK", f"Nodes: {node_count}, Relations: {rel_count}")
            self.results["checks"]["neo4j"] = {
                "status": "OK",
                "nodes": node_count,
                "relations": rel_count
            }
        except Exception as e:
            self.print_status("Neo4j Connection", "ERROR", str(e))
            self.results["checks"]["neo4j"] = {"status": "ERROR", "error": str(e)}
            self.results["overall_status"] = "UNHEALTHY"
    
    async def check_openai(self):
        """Проверка OpenAI API"""
        self.print_header("OPENAI API")
        
        try:
            client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
            
            # Проверяем доступность модели
            response = await client.chat.completions.create(
                model=settings.OPENAI_MODEL,
                messages=[{"role": "user", "content": "test"}],
                max_tokens=5
            )
            
            # Проверяем embeddings
            embedding_response = await client.embeddings.create(
                model=settings.OPENAI_EMBEDDING_MODEL,
                input="test"
            )
            
            self.print_status("OpenAI API", "OK", f"Model: {settings.OPENAI_MODEL}")
            self.print_status("Embeddings API", "OK", f"Model: {settings.OPENAI_EMBEDDING_MODEL}")
            
            self.results["checks"]["openai"] = {
                "status": "OK",
                "model": settings.OPENAI_MODEL,
                "embedding_model": settings.OPENAI_EMBEDDING_MODEL
            }
        except Exception as e:
            self.print_status("OpenAI API", "ERROR", str(e))
            self.results["checks"]["openai"] = {"status": "ERROR", "error": str(e)}
            self.results["overall_status"] = "UNHEALTHY"
    
    async def check_graphiti(self):
        """Проверка Graphiti"""
        self.print_header("GRAPHITI")
        
        try:
            async with httpx.AsyncClient() as client:
                # Health check
                response = await client.get(f"{settings.GRAPHITI_URL}/health")
                
                if response.status_code == 200:
                    self.print_status("Graphiti Service", "OK", f"URL: {settings.GRAPHITI_URL}")
                    self.results["checks"]["graphiti"] = {"status": "OK"}
                else:
                    self.print_status("Graphiti Service", "ERROR", f"Status: {response.status_code}")
                    self.results["checks"]["graphiti"] = {
                        "status": "ERROR",
                        "status_code": response.status_code
                    }
        except Exception as e:
            self.print_status("Graphiti Service", "ERROR", str(e))
            self.results["checks"]["graphiti"] = {"status": "ERROR", "error": str(e)}
            self.results["overall_status"] = "UNHEALTHY"
    
    async def check_api_endpoints(self):
        """Проверка API эндпоинтов"""
        self.print_header("API ENDPOINTS")
        
        endpoints = [
            ("/", "Root"),
            ("/health", "Health"),
            ("/api/chat", "Chat API"),
            ("/api/prompts", "Prompts API"),
            ("/docs", "API Documentation")
        ]
        
        try:
            async with httpx.AsyncClient() as client:
                for endpoint, name in endpoints:
                    try:
                        response = await client.get(f"http://localhost:8001{endpoint}")
                        status = "OK" if response.status_code < 400 else "ERROR"
                        self.print_status(name, status, f"Status: {response.status_code}")
                    except Exception as e:
                        self.print_status(name, "ERROR", "Not accessible")
                        if endpoint == "/":
                            self.results["warnings"].append("FastAPI server might not be running")
        except Exception as e:
            self.results["warnings"].append(f"Could not check API endpoints: {str(e)}")
    
    async def check_configuration(self):
        """Проверка конфигурации"""
        self.print_header("CONFIGURATION")
        
        critical_vars = [
            "OPENAI_API_KEY",
            "NEO4J_URI",
            "NEO4J_USERNAME",
            "NEO4J_PASSWORD",
            "REDIS_URL",
            "GRAPHITI_URL",
            "TELEGRAM_BOT_TOKEN"
        ]
        
        missing = []
        for var in critical_vars:
            value = getattr(settings, var, None)
            if not value or value.startswith("your-"):
                missing.append(var)
                self.print_status(var, "ERROR", "Not configured")
            else:
                # Скрываем значения для безопасности
                masked = value[:4] + "****" if len(value) > 4 else "****"
                self.print_status(var, "OK", f"Set ({masked})")
        
        if missing:
            self.results["errors"].append(f"Missing configuration: {', '.join(missing)}")
            self.results["overall_status"] = "UNHEALTHY"
    
    async def check_file_permissions(self):
        """Проверка прав доступа к файлам"""
        self.print_header("FILE PERMISSIONS")
        
        dirs_to_check = [
            "/workspace/data",
            "/workspace/data/prompts",
            "/workspace/logs",
            "/workspace/sandbox"
        ]
        
        for dir_path in dirs_to_check:
            if os.path.exists(dir_path):
                if os.access(dir_path, os.W_OK):
                    self.print_status(dir_path, "OK", "Writable")
                else:
                    self.print_status(dir_path, "ERROR", "Not writable")
                    self.results["warnings"].append(f"{dir_path} is not writable")
            else:
                self.print_status(dir_path, "WARNING", "Does not exist")
                os.makedirs(dir_path, exist_ok=True)
    
    async def run_all_checks(self):
        """Запуск всех проверок"""
        print(f"\n{Fore.BLUE}🔍 MARK AI - ПРЕДПРОДАКШЕН HEALTH CHECK{Style.RESET_ALL}")
        print(f"{Fore.BLUE}Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}{Style.RESET_ALL}")
        
        await self.check_system_resources()
        await self.check_configuration()
        await self.check_redis()
        await self.check_neo4j()
        await self.check_openai()
        await self.check_graphiti()
        await self.check_api_endpoints()
        await self.check_file_permissions()
        
        # Итоговый статус
        self.print_header("ИТОГОВЫЙ СТАТУС")
        
        if self.results["overall_status"] == "HEALTHY":
            print(f"\n{Fore.GREEN}✅ СИСТЕМА ГОТОВА К ДЕПЛОЮ!{Style.RESET_ALL}")
        else:
            print(f"\n{Fore.RED}❌ ОБНАРУЖЕНЫ КРИТИЧЕСКИЕ ПРОБЛЕМЫ!{Style.RESET_ALL}")
        
        if self.results["warnings"]:
            print(f"\n{Fore.YELLOW}⚠️  Предупреждения:{Style.RESET_ALL}")
            for warning in self.results["warnings"]:
                print(f"  - {warning}")
        
        if self.results["errors"]:
            print(f"\n{Fore.RED}❌ Ошибки:{Style.RESET_ALL}")
            for error in self.results["errors"]:
                print(f"  - {error}")
        
        # Сохраняем результаты
        with open("/workspace/health_check_results.json", "w") as f:
            json.dump(self.results, f, indent=2)
        
        print(f"\n📊 Результаты сохранены в health_check_results.json")
        
        return self.results["overall_status"] == "HEALTHY"


async def main():
    checker = HealthChecker()
    success = await checker.run_all_checks()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())