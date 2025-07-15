"""
ReflectionManager - менеджер рефлексии для самоанализа системы
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class ReflectionManager:
    """Менеджер рефлексии"""

    def __init__(self, reflection_file: str = "reflections.json"):
        self.reflection_file = Path(reflection_file)
        self.reflections: list[dict[str, Any]] = []
        self._load_reflections()
        logger.info("✅ ReflectionManager инициализирован")

    def _load_reflections(self):
        """Загружает рефлексии из файла"""
        try:
            if self.reflection_file.exists():
                with open(self.reflection_file, encoding='utf-8') as f:
                    self.reflections = json.load(f)
                logger.info(f"📚 Загружено {len(self.reflections)} рефлексий")
        except Exception as e:
            logger.warning(f"⚠️ Ошибка загрузки рефлексий: {e}")

    def _save_reflections(self):
        """Сохраняет рефлексии в файл"""
        try:
            with open(self.reflection_file, 'w', encoding='utf-8') as f:
                json.dump(self.reflections, f, ensure_ascii=False, indent=2)
            logger.debug("💾 Рефлексии сохранены")
        except Exception as e:
            logger.error(f"❌ Ошибка сохранения рефлексий: {e}")

    def add_reflection(self,
                      title: str,
                      content: str,
                      category: str = "general",
                      priority: str = "normal") -> str:
        """Добавляет новую рефлексию"""
        reflection_id = f"reflection_{len(self.reflections) + 1}"

        reflection = {
            "id": reflection_id,
            "title": title,
            "content": content,
            "category": category,
            "priority": priority,
            "created_at": datetime.now().isoformat(),
            "status": "active"
        }

        self.reflections.append(reflection)
        self._save_reflections()

        logger.info(f"🤔 Добавлена рефлексия: {title}")
        return reflection_id

    def get_reflections(self,
                       category: str | None = None,
                       status: str | None = None,
                       limit: int = 50) -> list[dict[str, Any]]:
        """Возвращает список рефлексий"""
        filtered = self.reflections

        if category:
            filtered = [r for r in filtered if r["category"] == category]

        if status:
            filtered = [r for r in filtered if r["status"] == status]

        return filtered[-limit:] if filtered else []

    def get_reflection(self, reflection_id: str) -> dict[str, Any] | None:
        """Возвращает рефлексию по ID"""
        for reflection in self.reflections:
            if reflection["id"] == reflection_id:
                return reflection
        return None

    def update_reflection(self, reflection_id: str, updates: dict[str, Any]) -> bool:
        """Обновляет рефлексию"""
        for reflection in self.reflections:
            if reflection["id"] == reflection_id:
                reflection.update(updates)
                reflection["updated_at"] = datetime.now().isoformat()
                self._save_reflections()
                logger.info(f"✏️ Рефлексия обновлена: {reflection_id}")
                return True
        return False

    def archive_reflection(self, reflection_id: str) -> bool:
        """Архивирует рефлексию"""
        return self.update_reflection(reflection_id, {"status": "archived"})

    def get_reflection_stats(self) -> dict[str, Any]:
        """Возвращает статистику рефлексий"""
        total = len(self.reflections)
        by_category = {}
        by_status = {}

        for reflection in self.reflections:
            category = reflection["category"]
            status = reflection["status"]

            by_category[category] = by_category.get(category, 0) + 1
            by_status[status] = by_status.get(status, 0) + 1

        return {
            "total_reflections": total,
            "by_category": by_category,
            "by_status": by_status
        }
