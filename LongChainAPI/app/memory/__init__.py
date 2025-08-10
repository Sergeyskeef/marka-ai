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