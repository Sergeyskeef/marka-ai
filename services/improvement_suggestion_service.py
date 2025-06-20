import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional

SUGGESTIONS_FILE = Path(__file__).parent.parent / "improvement_suggestions.json"

class ImprovementSuggestion:
    def __init__(self, text: str, source: str = "self_analysis", status: str = "new", history: Optional[List[str]] = None):
        self.id = str(uuid.uuid4())
        self.timestamp = datetime.now().isoformat()
        self.text = text
        self.source = source
        self.status = status
        self.history = history or []

    def to_dict(self):
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "text": self.text,
            "source": self.source,
            "status": self.status,
            "history": self.history,
        }

    @staticmethod
    def from_dict(data: Dict) -> 'ImprovementSuggestion':
        obj = ImprovementSuggestion(
            text=data["text"],
            source=data.get("source", "self_analysis"),
            status=data.get("status", "new"),
            history=data.get("history", [])
        )
        obj.id = data["id"]
        obj.timestamp = data["timestamp"]
        return obj

class ImprovementSuggestionService:
    def __init__(self, storage_path: Path = SUGGESTIONS_FILE):
        self.storage_path = storage_path
        self.suggestions: List[ImprovementSuggestion] = self._load()

    def _load(self) -> List[ImprovementSuggestion]:
        if self.storage_path.exists():
            with open(self.storage_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return [ImprovementSuggestion.from_dict(item) for item in data]
        return []

    def _save(self):
        with open(self.storage_path, "w", encoding="utf-8") as f:
            json.dump([s.to_dict() for s in self.suggestions], f, ensure_ascii=False, indent=2)

    def generate_suggestions(self, analysis_results: List[Dict]) -> List[ImprovementSuggestion]:
        """Генерирует предложения на основе результатов самоанализа."""
        new_suggestions = []
        for result in analysis_results:
            if "recommendation" in result and result["recommendation"]:
                suggestion = ImprovementSuggestion(
                    text=result["recommendation"],
                    source=result.get("source", "self_analysis"),
                    history=result.get("history", [])
                )
                self.suggestions.append(suggestion)
                new_suggestions.append(suggestion)
        self._save()
        return new_suggestions

    def list_suggestions(self, status: Optional[str] = None) -> List[ImprovementSuggestion]:
        if status:
            return [s for s in self.suggestions if s.status == status]
        return self.suggestions

    def update_status(self, suggestion_id: str, status: str):
        for s in self.suggestions:
            if s.id == suggestion_id:
                s.status = status
                self._save()
                return True
        return False

    def get_suggestion(self, suggestion_id: str) -> Optional[ImprovementSuggestion]:
        for s in self.suggestions:
            if s.id == suggestion_id:
                return s
        return None 