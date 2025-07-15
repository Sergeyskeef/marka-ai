"""
GraphitiMemoryAdapter - адаптер для работы с памятью Graphiti
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class MemoryEntry:
    """Запись в памяти"""

    def __init__(self, content: str, metadata: dict[str, Any] | None = None):
        self.content = content
        self.metadata = metadata or {}
        self.timestamp = datetime.now().isoformat()
        self.id = f"entry_{int(datetime.now().timestamp())}"

    def to_dict(self) -> dict[str, Any]:
        """Преобразует запись в словарь"""
        return {
            "id": self.id,
            "content": self.content,
            "metadata": self.metadata,
            "timestamp": self.timestamp
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> 'MemoryEntry':
        """Создает запись из словаря"""
        entry = cls(data["content"], data.get("metadata"))
        entry.id = data["id"]
        entry.timestamp = data["timestamp"]
        return entry


class GraphitiMemoryAdapter:
    """Адаптер для работы с памятью Graphiti"""

    def __init__(self, short_term_limit: int = 20, memory_file: str = "memory.json"):
        self.short_term_limit = short_term_limit
        self.memory_file = Path(memory_file)
        self.short_term_memory: list[MemoryEntry] = []
        self.long_term_memory: list[MemoryEntry] = []

        # Загружаем существующую память
        self._load_memory()

        logger.info(f"✅ GraphitiMemoryAdapter инициализирован (limit={short_term_limit})")

    def _load_memory(self):
        """Загружает память из файла"""
        try:
            if self.memory_file.exists():
                with open(self.memory_file, encoding='utf-8') as f:
                    data = json.load(f)
                    self.short_term_memory = [
                        MemoryEntry.from_dict(entry)
                        for entry in data.get("short_term", [])
                    ]
                    self.long_term_memory = [
                        MemoryEntry.from_dict(entry)
                        for entry in data.get("long_term", [])
                    ]
                logger.info(f"📚 Загружено {len(self.short_term_memory)} краткосрочных и {len(self.long_term_memory)} долгосрочных записей")
        except Exception as e:
            logger.warning(f"⚠️ Ошибка загрузки памяти: {e}")

    def _save_memory(self):
        """Сохраняет память в файл"""
        try:
            data = {
                "short_term": [entry.to_dict() for entry in self.short_term_memory],
                "long_term": [entry.to_dict() for entry in self.long_term_memory],
                "last_updated": datetime.now().isoformat()
            }
            with open(self.memory_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.debug("💾 Память сохранена")
        except Exception as e:
            logger.error(f"❌ Ошибка сохранения памяти: {e}")

    async def search(self, query: str, k: int = 5) -> list[dict[str, Any]]:
        """Поиск в памяти по запросу"""
        try:
            # Простой поиск по содержимому (в будущем будет заменен на векторный поиск)
            all_entries = self.short_term_memory + self.long_term_memory
            results = []

            query_lower = query.lower()
            for entry in all_entries:
                if query_lower in entry.content.lower():
                    results.append({
                        "id": entry.id,
                        "content": entry.content,
                        "metadata": entry.metadata,
                        "timestamp": entry.timestamp,
                        "score": 0.8  # Простой скор
                    })

            # Сортируем по времени (новые сначала)
            results.sort(key=lambda x: x["timestamp"], reverse=True)

            logger.info(f"🔍 Найдено {len(results)} результатов для запроса: {query}")
            return results[:k]

        except Exception as e:
            logger.error(f"❌ Ошибка поиска: {e}")
            return []

    async def store(self, entry: MemoryEntry) -> bool:
        """Сохраняет запись в память"""
        try:
            # Добавляем в краткосрочную память
            self.short_term_memory.append(entry)

            # Ограничиваем размер краткосрочной памяти
            if len(self.short_term_memory) > self.short_term_limit:
                # Перемещаем старые записи в долгосрочную память
                old_entry = self.short_term_memory.pop(0)
                self.long_term_memory.append(old_entry)
                logger.debug(f"📦 Запись перемещена в долгосрочную память: {old_entry.id}")

            # Сохраняем память
            self._save_memory()

            logger.info(f"💾 Запись сохранена в память: {entry.id}")
            return True

        except Exception as e:
            logger.error(f"❌ Ошибка сохранения записи: {e}")
            return False

    async def store_text(self, content: str, metadata: dict[str, Any] | None = None) -> bool:
        """Сохраняет текст в память"""
        entry = MemoryEntry(content, metadata)
        return await self.store(entry)

    def get_memory_stats(self) -> dict[str, Any]:
        """Возвращает статистику памяти"""
        return {
            "short_term_count": len(self.short_term_memory),
            "long_term_count": len(self.long_term_memory),
            "short_term_limit": self.short_term_limit,
            "total_entries": len(self.short_term_memory) + len(self.long_term_memory)
        }

    def clear_short_term(self):
        """Очищает краткосрочную память"""
        cleared_count = len(self.short_term_memory)
        self.short_term_memory.clear()
        self._save_memory()
        logger.info(f"🧹 Очищена краткосрочная память: {cleared_count} записей")

    def clear_all(self):
        """Очищает всю память"""
        self.short_term_memory.clear()
        self.long_term_memory.clear()
        self._save_memory()
        logger.info("🧹 Вся память очищена")
