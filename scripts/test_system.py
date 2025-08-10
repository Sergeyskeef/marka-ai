#!/usr/bin/env python3
"""
System test script - tests all components
"""

import sys
import os
import asyncio
import logging
from typing import Dict, Any

# Add the workspace root to the Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def test_config():
    """Test configuration loading"""
    logger.info("🔧 Testing configuration...")
    try:
        from app.config import settings
        logger.info(f"✅ Config loaded successfully")
        logger.info(f"   - OpenAI Model: {settings.OPENAI_MODEL}")
        logger.info(f"   - Use Direct Neo4j: {settings.USE_DIRECT_NEO4J}")
        logger.info(f"   - Neo4j URI: {settings.NEO4J_URI}")
        return True
    except Exception as e:
        logger.error(f"❌ Config test failed: {e}")
        return False


async def test_neo4j_connection():
    """Test Neo4j database connection"""
    logger.info("🗄️ Testing Neo4j connection...")
    try:
        from app.memory import neo4j_client
        
        # Test connection
        await neo4j_client.connect()
        
        # Test simple query
        async with neo4j_client.driver.session() as session:
            result = await session.run("RETURN 1 as test")
            data = await result.single()
            if data['test'] == 1:
                logger.info("✅ Neo4j connection successful")
                return True
            else:
                logger.error("❌ Neo4j query returned unexpected result")
                return False
                
    except Exception as e:
        logger.error(f"❌ Neo4j connection failed: {e}")
        return False


async def test_memory_adapter():
    """Test memory adapter"""
    logger.info("🧠 Testing memory adapter...")
    try:
        from app.memory.advanced_memory_adapter import AdvancedMemoryAdapter
        from core.memory.graphiti_adapter import GraphitiMemoryAdapter
        from openai import AsyncOpenAI
        from app.config import settings
        
        # Create instances
        graphiti = GraphitiMemoryAdapter()
        openai_client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        adapter = AdvancedMemoryAdapter(graphiti, openai_client)
        
        logger.info("✅ Memory adapter created successfully")
        return True
        
    except Exception as e:
        logger.error(f"❌ Memory adapter test failed: {e}")
        return False


async def test_agent():
    """Test Mark agent"""
    logger.info("🤖 Testing Mark agent...")
    try:
        from app.agents.mark_agent import MarkAgent
        from openai import AsyncOpenAI
        from app.config import settings
        
        # Create agent
        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        agent = MarkAgent(
            client=client,
            model=settings.OPENAI_MODEL,
            temperature=settings.OPENAI_TEMPERATURE
        )
        
        logger.info("✅ Mark agent created successfully")
        return True
        
    except Exception as e:
        logger.error(f"❌ Agent test failed: {e}")
        return False


async def test_api_routes():
    """Test API route imports"""
    logger.info("🌐 Testing API routes...")
    try:
        from app.api.chat import router as chat_router
        from app.api.memory import router as memory_router
        from app.api.prompts_api import router as prompts_router
        
        logger.info("✅ All API routes imported successfully")
        return True
        
    except Exception as e:
        logger.error(f"❌ API routes test failed: {e}")
        return False


async def test_telegram_bot():
    """Test telegram bot imports"""
    logger.info("📱 Testing Telegram bot...")
    try:
        from telegram_bot.config import bot_config
        from telegram_bot.services import ChatService
        from telegram_bot.handlers.start import start_command
        from telegram_bot.handlers.chat import handle_text_message
        
        logger.info("✅ Telegram bot components imported successfully")
        return True
        
    except Exception as e:
        logger.error(f"❌ Telegram bot test failed: {e}")
        return False


async def main():
    """Run all tests"""
    logger.info("🚀 Starting system tests...")
    
    tests = [
        ("Configuration", test_config),
        ("Neo4j Connection", test_neo4j_connection),
        ("Memory Adapter", test_memory_adapter),
        ("Mark Agent", test_agent),
        ("API Routes", test_api_routes),
        ("Telegram Bot", test_telegram_bot),
    ]
    
    results = {}
    for test_name, test_func in tests:
        logger.info(f"\n{'='*50}")
        result = await test_func()
        results[test_name] = result
        logger.info(f"{'='*50}\n")
    
    # Summary
    logger.info("\n📊 TEST SUMMARY:")
    logger.info("=" * 50)
    
    passed = sum(1 for r in results.values() if r)
    total = len(results)
    
    for test_name, result in results.items():
        status = "✅ PASSED" if result else "❌ FAILED"
        logger.info(f"{test_name}: {status}")
    
    logger.info("=" * 50)
    logger.info(f"Total: {passed}/{total} tests passed")
    
    if passed == total:
        logger.info("🎉 All tests passed! System is ready.")
    else:
        logger.error("⚠️ Some tests failed. Please check the errors above.")
        
    # Close connections
    try:
        from app.memory import neo4j_client
        if neo4j_client.driver:
            await neo4j_client.close()
    except:
        pass


if __name__ == "__main__":
    asyncio.run(main())