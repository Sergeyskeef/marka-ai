#!/usr/bin/env python3
"""
Скрипт для проверки работоспособности всех компонентов проекта
"""

import asyncio
import logging
import sys
import os
from typing import Dict, List, Any, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class ProjectValidator:
    """Валидатор всех компонентов проекта"""
    
    def __init__(self):
        self.results = {
            "memory": {},
            "tools": {},
            "api": {},
            "bot": {},
            "docker": {}
        }
        self.errors = []
    
    async def validate_all(self):
        """Запуск всех проверок"""
        logger.info("🚀 Начинаем полную проверку проекта...")
        
        # 1. Проверка системы памяти
        await self.validate_memory_chain()
        
        # 2. Проверка инструментов агента
        await self.validate_agent_tools()
        
        # 3. Проверка API endpoints
        await self.validate_api_endpoints()
        
        # 4. Проверка конфигурации Docker
        self.validate_docker_config()
        
        # 5. Проверка бота
        self.validate_bot_structure()
        
        # 6. Итоговый отчет
        self.print_report()
    
    async def validate_memory_chain(self):
        """Проверка цепочки работы памяти"""
        logger.info("\n🧠 ПРОВЕРКА СИСТЕМЫ ПАМЯТИ")
        
        try:
            # Проверка Neo4j Direct
            from app.memory.neo4j_direct import neo4j_client
            
            # Тест подключения
            await neo4j_client.connect()
            stats = await neo4j_client.get_memory_stats()
            
            self.results["memory"]["neo4j_direct"] = {
                "status": "✅ OK",
                "stats": stats
            }
            logger.info("✅ Neo4j Direct: Подключение успешно")
            
            await neo4j_client.close()
            
        except Exception as e:
            self.results["memory"]["neo4j_direct"] = {
                "status": "❌ FAIL",
                "error": str(e)
            }
            self.errors.append(f"Neo4j Direct: {e}")
        
        try:
            # Проверка AdvancedMemoryAdapter
            from app.memory.advanced_memory_adapter import AdvancedMemoryAdapter
            from core.memory.graphiti_adapter import graphiti_adapter
            
            adapter = AdvancedMemoryAdapter(graphiti_adapter)
            
            # Тест сохранения факта
            result = await adapter.save_fact(
                subject="test",
                predicate="is",
                object="validation",
                confidence=1.0
            )
            
            self.results["memory"]["advanced_adapter"] = {
                "status": "✅ OK",
                "test_fact": result
            }
            logger.info("✅ AdvancedMemoryAdapter: Работает корректно")
            
        except Exception as e:
            self.results["memory"]["advanced_adapter"] = {
                "status": "❌ FAIL",
                "error": str(e)
            }
            self.errors.append(f"AdvancedMemoryAdapter: {e}")
        
        try:
            # Проверка REAP цикла
            from app.learning.reap_cycle import reap_cycle
            
            # Проверяем инициализацию
            if hasattr(reap_cycle, 'memory'):
                self.results["memory"]["reap_cycle"] = {
                    "status": "✅ OK",
                    "initialized": True
                }
                logger.info("✅ REAP Cycle: Инициализирован")
            else:
                raise Exception("REAP cycle не инициализирован")
                
        except Exception as e:
            self.results["memory"]["reap_cycle"] = {
                "status": "❌ FAIL", 
                "error": str(e)
            }
            self.errors.append(f"REAP Cycle: {e}")
    
    async def validate_agent_tools(self):
        """Проверка всех инструментов агента"""
        logger.info("\n🔧 ПРОВЕРКА ИНСТРУМЕНТОВ АГЕНТА")
        
        tools_to_check = [
            ("memory_tools", "app.agents.memory_tools", "MEMORY_TOOLS"),
            ("advanced_memory_tools", "app.agents.advanced_memory_tools", "ADVANCED_MEMORY_TOOLS"),
            ("learning_tools", "app.agents.learning_tools", "LEARNING_TOOLS"),
            ("vector_search_tools", "app.agents.vector_search_tools", "VECTOR_SEARCH_TOOLS")
        ]
        
        for tool_name, module_path, export_name in tools_to_check:
            try:
                module = __import__(module_path, fromlist=[export_name])
                tools = getattr(module, export_name)
                
                self.results["tools"][tool_name] = {
                    "status": "✅ OK",
                    "count": len(tools),
                    "functions": [t.__name__ for t in tools]
                }
                logger.info(f"✅ {tool_name}: {len(tools)} инструментов")
                
            except Exception as e:
                self.results["tools"][tool_name] = {
                    "status": "❌ FAIL",
                    "error": str(e)
                }
                self.errors.append(f"{tool_name}: {e}")
    
    async def validate_api_endpoints(self):
        """Проверка API endpoints"""
        logger.info("\n🌐 ПРОВЕРКА API ENDPOINTS")
        
        # Проверяем наличие endpoint файлов в main.py
        try:
            with open("/workspace/main.py", "r") as f:
                content = f.read()
                
            endpoints_found = []
            
            # Проверяем наличие endpoints
            if "@app.get(\"/health\")" in content:
                endpoints_found.append("GET /health")
            if "@app.get(\"/memory/health\")" in content:
                endpoints_found.append("GET /memory/health")
            if "@app.post(\"/chat/ask\")" in content:
                endpoints_found.append("POST /chat/ask")
            if "@app.post(\"/chat/enhanced\")" in content:
                endpoints_found.append("POST /chat/enhanced")
                
            for endpoint in endpoints_found:
                self.results["api"][endpoint] = {
                    "status": "✅ Определен",
                    "found": True
                }
                logger.info(f"✅ {endpoint}: Найден в коде")
                
            # Проверяем импорты для enhanced_chat
            if "from app.agents.chat_handler import" in content and "enhanced_chat" in content:
                self.results["api"]["enhanced_chat_import"] = {
                    "status": "✅ OK",
                    "found": True
                }
                logger.info("✅ enhanced_chat импортирован корректно")
            else:
                self.results["api"]["enhanced_chat_import"] = {
                    "status": "❌ FAIL",
                    "found": False
                }
                self.errors.append("enhanced_chat не импортирован в main.py")
                
        except Exception as e:
            self.results["api"]["file_check"] = {
                "status": "❌ FAIL",
                "error": str(e)
            }
            self.errors.append(f"Проверка API: {e}")
    
    def validate_docker_config(self):
        """Проверка Docker конфигурации"""
        logger.info("\n🐳 ПРОВЕРКА DOCKER КОНФИГУРАЦИИ")
        
        files_to_check = [
            "/workspace/docker-compose.yml",
            "/workspace/Dockerfile",
            "/workspace/telegram_bot/Dockerfile",
            "/workspace/.env.example"
        ]
        
        for file_path in files_to_check:
            if os.path.exists(file_path):
                self.results["docker"][os.path.basename(file_path)] = "✅ Существует"
                logger.info(f"✅ {os.path.basename(file_path)}: Найден")
            else:
                self.results["docker"][os.path.basename(file_path)] = "❌ Отсутствует"
                self.errors.append(f"Файл {file_path} не найден")
    
    def validate_bot_structure(self):
        """Проверка структуры бота"""
        logger.info("\n🤖 ПРОВЕРКА TELEGRAM БОТА")
        
        bot_components = {
            "handlers": [
                "/workspace/telegram_bot/handlers/start.py",
                "/workspace/telegram_bot/handlers/chat.py",
                "/workspace/telegram_bot/handlers/base.py"
            ],
            "services": [
                "/workspace/telegram_bot/services/chat_service.py"
            ],
            "keyboards": [
                "/workspace/telegram_bot/keyboards/main_menu.py",
                "/workspace/telegram_bot/keyboards/feedback.py",
                "/workspace/telegram_bot/keyboards/memory_menu.py"
            ],
            "middleware": [
                "/workspace/telegram_bot/middleware/rate_limiter.py",
                "/workspace/telegram_bot/middleware/auth.py",
                "/workspace/telegram_bot/middleware/logging.py"
            ]
        }
        
        for component_type, files in bot_components.items():
            component_status = []
            for file_path in files:
                if os.path.exists(file_path):
                    component_status.append(f"✅ {os.path.basename(file_path)}")
                else:
                    component_status.append(f"❌ {os.path.basename(file_path)}")
                    self.errors.append(f"Bot {component_type}: {file_path} не найден")
            
            self.results["bot"][component_type] = component_status
            logger.info(f"📁 {component_type}: {len([s for s in component_status if '✅' in s])}/{len(files)} файлов")
    
    def print_report(self):
        """Вывод итогового отчета"""
        print("\n" + "="*60)
        print("📊 ИТОГОВЫЙ ОТЧЕТ ВАЛИДАЦИИ")
        print("="*60)
        
        # Статус компонентов
        print("\n🧠 СИСТЕМА ПАМЯТИ:")
        for component, status in self.results["memory"].items():
            if isinstance(status, dict) and "status" in status:
                print(f"  {component}: {status['status']}")
        
        print("\n🔧 ИНСТРУМЕНТЫ:")
        for tool, info in self.results["tools"].items():
            if isinstance(info, dict) and "status" in info:
                print(f"  {tool}: {info['status']} ({info.get('count', 0)} функций)")
        
        print("\n🌐 API ENDPOINTS:")
        for endpoint, info in self.results["api"].items():
            if isinstance(info, dict) and "status" in info:
                print(f"  {endpoint}: {info['status']}")
        
        print("\n🐳 DOCKER:")
        for file, status in self.results["docker"].items():
            print(f"  {file}: {status}")
        
        print("\n🤖 TELEGRAM БОТ:")
        for component, files in self.results["bot"].items():
            ok_count = len([f for f in files if '✅' in f])
            total_count = len(files)
            status = "✅" if ok_count == total_count else "⚠️"
            print(f"  {component}: {status} {ok_count}/{total_count}")
        
        # Итоговый статус
        print("\n" + "="*60)
        if not self.errors:
            print("✅ ВСЕ КОМПОНЕНТЫ РАБОТАЮТ КОРРЕКТНО!")
        else:
            print(f"⚠️ ОБНАРУЖЕНО ПРОБЛЕМ: {len(self.errors)}")
            print("\nОШИБКИ:")
            for error in self.errors[:10]:  # Показываем первые 10 ошибок
                print(f"  ❌ {error}")
            if len(self.errors) > 10:
                print(f"  ... и еще {len(self.errors) - 10} ошибок")
        print("="*60)


async def main():
    """Основная функция"""
    validator = ProjectValidator()
    await validator.validate_all()


if __name__ == "__main__":
    asyncio.run(main())