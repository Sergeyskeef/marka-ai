#!/bin/bash

# Script to apply all fixes to the langchain_api directory
# Run this on your VM in the marka directory

echo "🔧 Applying all fixes to langchain_api..."

cd langchain_api || exit 1

# 1. Create missing API files
echo "📁 Creating missing API files..."

# Create chat.py
cat > app/api/chat.py << 'EOF'
"""
Chat API endpoints
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, Dict, Any
import logging

from openai import AsyncOpenAI
from app.agents.mark_agent import MarkAgent
from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()

# Request/Response models
class ChatRequest(BaseModel):
    message: str
    user_id: str
    session_id: Optional[str] = None
    context: Optional[Dict[str, Any]] = None

class ChatResponse(BaseModel):
    response: str
    session_id: str
    metadata: Optional[Dict[str, Any]] = None

# Global agent instance (in production, you might want to use dependency injection)
agent = None

async def get_agent():
    """Get or create agent instance"""
    global agent
    if agent is None:
        # Create OpenAI client
        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        # Create agent with the client
        agent = MarkAgent(
            client=client,
            model=settings.OPENAI_MODEL,
            temperature=settings.OPENAI_TEMPERATURE,
            max_tokens=settings.OPENAI_MAX_TOKENS
        )
    return agent

@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    agent_instance: MarkAgent = Depends(get_agent)
):
    """
    Process a chat message
    """
    try:
        logger.info(f"Processing chat request from user {request.user_id}")
        
        # Process the message through the agent
        result = await agent_instance.chat(
            message=request.message,
            user_id=request.user_id,
            chat_id=None,  # Could be mapped from session_id if needed
            context=None,  # Could be built from request.context
            use_tools=True
        )
        
        return ChatResponse(
            response=result.get("content", ""),
            session_id=request.session_id or "default",
            metadata=result.get("metadata")
        )
        
    except Exception as e:
        logger.error(f"Error processing chat request: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/chat/sessions/{user_id}")
async def get_user_sessions(user_id: str):
    """
    Get chat sessions for a user
    """
    try:
        # This would typically fetch from database
        # For now, return a placeholder
        return {
            "user_id": user_id,
            "sessions": []
        }
    except Exception as e:
        logger.error(f"Error fetching sessions: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/chat/sessions/{session_id}")
async def clear_session(session_id: str):
    """
    Clear a chat session
    """
    try:
        # This would typically clear session from database/cache
        return {"status": "success", "message": f"Session {session_id} cleared"}
    except Exception as e:
        logger.error(f"Error clearing session: {e}")
        raise HTTPException(status_code=500, detail=str(e))
EOF

# Create memory.py
cat > app/api/memory.py << 'EOF'
"""
Memory API endpoints
"""

from fastapi import APIRouter, HTTPException, Query, Depends
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime
import logging

from app.memory.advanced_memory_adapter import AdvancedMemoryAdapter
from app.memory.models import Fact, Episode, Skill, MemoryType, IDType, SearchResult
from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()

# Request/Response models
class MemorySearchRequest(BaseModel):
    query: str
    limit: Optional[int] = 10
    memory_types: Optional[List[str]] = None

class MemoryAddRequest(BaseModel):
    content: str
    memory_type: str  # "fact", "episode", or "skill"
    metadata: Optional[Dict[str, Any]] = None

class MemoryStatsResponse(BaseModel):
    total_facts: int
    total_episodes: int
    total_skills: int
    total_memories: int
    last_updated: Optional[datetime] = None

# Global memory adapter instance
memory_adapter = None

async def get_memory_adapter():
    """Get or create memory adapter instance"""
    global memory_adapter
    if memory_adapter is None:
        # Create GraphitiMemoryAdapter first
        from core.memory.graphiti_adapter import GraphitiMemoryAdapter
        from openai import AsyncOpenAI
        
        graphiti_adapter = GraphitiMemoryAdapter()
        openai_client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        
        # Create AdvancedMemoryAdapter with required dependencies
        memory_adapter = AdvancedMemoryAdapter(
            graphiti_adapter=graphiti_adapter,
            openai_client=openai_client
        )
    return memory_adapter

@router.post("/search")
async def search_memory(
    request: MemorySearchRequest,
    adapter: AdvancedMemoryAdapter = Depends(get_memory_adapter)
):
    """
    Search through memories
    """
    try:
        logger.info(f"Searching memory with query: {request.query}")
        
        # For now, we search episodes as the main search method
        # This can be expanded to search other memory types
        results = await adapter.graphiti.search_episodes(
            query=request.query,
            limit=request.limit
        )
        
        # Convert to list format if needed
        if isinstance(results, dict) and "episodes" in results:
            results = results["episodes"]
        
        return {
            "query": request.query,
            "results": results,
            "count": len(results) if isinstance(results, list) else 0
        }
        
    except Exception as e:
        logger.error(f"Error searching memory: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/add")
async def add_memory(
    request: MemoryAddRequest,
    adapter: AdvancedMemoryAdapter = Depends(get_memory_adapter)
):
    """
    Add a new memory
    """
    try:
        logger.info(f"Adding {request.memory_type} memory")
        
        if request.memory_type == "fact":
            # Parse fact from content (expecting format: "subject predicate object")
            parts = request.content.split(" ", 2)
            if len(parts) >= 3:
                memory = await adapter.save_fact(
                    subject=parts[0],
                    predicate=parts[1],
                    object=parts[2],
                    metadata=request.metadata
                )
            else:
                raise ValueError("Fact must be in format: 'subject predicate object'")
        elif request.memory_type == "episode":
            memory = await adapter.save_episode(
                content=request.content,
                participants=request.metadata.get("participants", []) if request.metadata else [],
                location=request.metadata.get("location", "unknown") if request.metadata else "unknown",
                metadata=request.metadata
            )
        elif request.memory_type == "skill":
            memory = await adapter.learn_skill(
                name=request.metadata.get("name", "skill") if request.metadata else "skill",
                description=request.content,
                implementation=request.metadata.get("implementation", "") if request.metadata else "",
                metadata=request.metadata
            )
        else:
            raise ValueError(f"Invalid memory type: {request.memory_type}")
        
        return {
            "status": "success",
            "memory_id": memory.get("id"),
            "memory_type": request.memory_type
        }
        
    except Exception as e:
        logger.error(f"Error adding memory: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/stats", response_model=MemoryStatsResponse)
async def get_memory_stats(
    adapter: AdvancedMemoryAdapter = Depends(get_memory_adapter)
):
    """
    Get memory statistics
    """
    try:
        stats = await adapter.get_memory_stats()
        
        return MemoryStatsResponse(
            total_facts=stats.get("facts", 0),
            total_episodes=stats.get("episodes", 0),
            total_skills=stats.get("skills", 0),
            total_memories=stats.get("total", 0),
            last_updated=stats.get("last_updated")
        )
        
    except Exception as e:
        logger.error(f"Error getting memory stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/recent")
async def get_recent_memories(
    limit: int = Query(10, le=100),
    memory_type: Optional[str] = None,
    adapter: AdvancedMemoryAdapter = Depends(get_memory_adapter)
):
    """
    Get recent memories
    """
    try:
        # For now, return empty list as this method doesn't exist yet
        # TODO: Implement get_recent method in AdvancedMemoryAdapter
        return {
            "memories": [],
            "count": 0,
            "message": "This endpoint is not yet implemented"
        }
        
    except Exception as e:
        logger.error(f"Error getting recent memories: {e}")
        raise HTTPException(status_code=500, detail=str(e))
EOF

# 2. Create memory __init__.py
echo "📁 Creating app/memory/__init__.py..."
cat > app/memory/__init__.py << 'EOF'
"""
Memory system components
"""

from .neo4j_direct import Neo4jDirectClient
from .advanced_memory_adapter import AdvancedMemoryAdapter
from .models import Fact, Episode, Skill, MemoryType, IDType, SearchResult

# Create singleton instance
neo4j_client = Neo4jDirectClient()

__all__ = [
    'Neo4jDirectClient',
    'AdvancedMemoryAdapter', 
    'Fact',
    'Episode',
    'Skill',
    'MemoryType',
    'IDType',
    'SearchResult',
    'neo4j_client'
]
EOF

# 3. Fix app/main.py to include the routers
echo "🔧 Fixing app/main.py..."
cat > app/main.py << 'EOF'
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os
import sys

# Добавляем путь к корню проекта
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.api.chat import router as chat_router
from app.api.memory import router as memory_router
from app.api.prompts_api import register_prompts_api

app = FastAPI(title="Mark AI API", version="1.0.0")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(chat_router, prefix="/api", tags=["chat"])
app.include_router(memory_router, prefix="/api/memory", tags=["memory"])
register_prompts_api(app)

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "mark-ai"}

@app.get("/")
async def root():
    return {"message": "Mark AI API", "version": "1.0.0"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
EOF

# 4. Fix app/config.py pydantic import
echo "🔧 Fixing app/config.py..."
sed -i 's/from pydantic import BaseSettings/from pydantic_settings import BaseSettings/' app/config.py

# 5. Update requirements.txt
echo "📦 Updating requirements.txt..."
# Add missing dependencies if not present
grep -q "pydantic>=2.0.0" requirements.txt || echo "pydantic>=2.0.0" >> requirements.txt
grep -q "pydantic-settings>=2.0.0" requirements.txt || echo "pydantic-settings>=2.0.0" >> requirements.txt

# Fix graphiti version
sed -i 's/graphiti==0.1.0/graphiti-core==0.3.0/' requirements.txt

# Remove duplicate tiktoken if exists
sed -i '/tiktoken==0.7.0/d' requirements.txt

# 6. Update Dockerfiles
echo "🐳 Optimizing Dockerfiles..."

# Main Dockerfile
cat > Dockerfile << 'EOF'
FROM python:3.10-slim as builder

WORKDIR /app

# Устанавливаем зависимости для сборки
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Копируем только requirements.txt сначала для кэширования слоя с зависимостями
COPY requirements.txt .

# Устанавливаем зависимости
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir pytest pytest-cov ruff

# Финальный образ
FROM python:3.10-slim

WORKDIR /app

# Install curl for healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Копируем установленные пакеты из builder
COPY --from=builder /usr/local/lib/python3.10/site-packages/ /usr/local/lib/python3.10/site-packages/
COPY --from=builder /usr/local/bin/ /usr/local/bin/

# Копируем код приложения
COPY . .

# Создаем необходимые директории
RUN mkdir -p /app/logs

# Устанавливаем права
RUN chmod -R 755 /app

# Добавляем путь к модулям в PYTHONPATH
ENV PYTHONPATH=/app

# Проверяем здоровье приложения
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
EOF

# Telegram bot Dockerfile
cat > telegram_bot/Dockerfile << 'EOF'
FROM python:3.10-slim

WORKDIR /app

# Install system dependencies if needed
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy only requirements first for better caching
COPY requirements.txt telegram_bot/requirements.txt* ./
COPY telegram_bot/requirements.txt* ./telegram_bot/

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir python-telegram-bot==21.0 aiohttp[speedups]

# Copy the rest of the application
COPY . .

# Set Python path
ENV PYTHONPATH=/app

# Set working directory to telegram_bot
WORKDIR /app/telegram_bot

# Run the bot
CMD ["python", "main.py"]
EOF

# Graphiti Dockerfile
cat > Dockerfile.graphiti << 'EOF'
FROM python:3.10-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies first for better caching
RUN pip install --no-cache-dir \
    graphiti-core==0.3.0 \
    fastapi \
    uvicorn \
    neo4j \
    requests

# Create user for security
RUN useradd -m -u 1000 graphiti

# Copy application files
COPY graphiti_service/ /app/

# Change ownership
RUN chown -R graphiti:graphiti /app

# Switch to non-root user
USER graphiti

# Expose port
EXPOSE 7878

# Run command with Neo4j initialization
CMD ["sh", "-c", "python /app/neo4j_init.py && uvicorn main:app --host 0.0.0.0 --port 7878"]
EOF

# 7. Create test script
echo "🧪 Creating test script..."
cat > scripts/test_system.py << 'EOF'
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
EOF

chmod +x scripts/test_system.py

# 8. Update .env.example
echo "📝 Updating .env.example..."
cat > .env.example << 'EOF'
# OpenAI Configuration
OPENAI_API_KEY=your_openai_api_key_here
OPENAI_MODEL=gpt-4
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
OPENAI_TEMPERATURE=0.7
OPENAI_MAX_TOKENS=

# Telegram Bot
BOT_TOKEN=your_telegram_bot_token_here
ADMIN_USERS=123456789,987654321  # Comma-separated Telegram user IDs

# Memory System
USE_DIRECT_NEO4J=true
SYNC_TO_GRAPHITI=false

# Neo4j Database
NEO4J_URI=bolt://graphiti-neo4j:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=password

# Graphiti Service
GRAPHITI_URL=http://graphiti:7878

# Redis
REDIS_URL=redis://redis:6379

# Application Settings
APP_HOST=http://app:8000
DEBUG=false
LOG_LEVEL=INFO
BOT_DEV_MODE=false

# Learning System
REAP_CYCLE_AUTO_RUN=false
REAP_CYCLE_INTERVAL=300

# Proxy Settings (optional)
HTTP_PROXY=
HTTPS_PROXY=
NO_PROXY=localhost,127.0.0.1,app,bot,redis,graphiti,graphiti-neo4j

# Environment
ENV=production
EOF

echo "✅ All fixes applied!"
echo ""
echo "📋 Next steps:"
echo "1. Review the changes: git status"
echo "2. Add and commit: git add . && git commit -m 'Fix all critical issues'"
echo "3. Push to a new branch: git push origin HEAD:fixes"
echo "4. Create a pull request to merge fixes into main"
echo ""
echo "Or to test immediately:"
echo "1. Copy .env.example to .env and configure"
echo "2. Run: docker-compose build --no-cache"
echo "3. Run: docker-compose up -d"
echo "4. Test: docker-compose exec app python scripts/test_system.py"