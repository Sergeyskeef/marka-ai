#!/usr/bin/env python3
"""
Менеджер промптов для Марка
"""

import os
import yaml
import logging
from typing import Dict, Any, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

class PromptManager:
    """Менеджер системных промптов"""
    
    def __init__(self, prompts_file: str = "prompts/prompts.yaml"):
        self.prompts_file = prompts_file
        self.prompts: Dict[str, Dict[str, str]] = {}
        self.current_mode = "chat"
        self.load_prompts()
    
    def load_prompts(self) -> bool:
        """Загрузка промптов из YAML файла"""
        try:
            # Ищем файл относительно корня проекта
            project_root = Path(__file__).parent.parent
            prompts_path = project_root / self.prompts_file
            
            if not prompts_path.exists():
                logger.warning(f"Файл промптов не найден: {prompts_path}")
                return False
            
            with open(prompts_path, 'r', encoding='utf-8') as f:
                self.prompts = yaml.safe_load(f)
            
            logger.info(f"✅ Загружено {len(self.prompts)} режимов промптов")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки промптов: {e}")
            return False
    
    def get_prompt(self, mode: str = None, context: str = "") -> str:
        """Получение промпта для указанного режима"""
        mode = mode or self.current_mode
        
        if mode not in self.prompts:
            logger.warning(f"Режим '{mode}' не найден, используем 'chat'")
            mode = "chat"
        
        if "system" not in self.prompts[mode]:
            logger.error(f"Системный промпт для режима '{mode}' не найден")
            return "Ты — Марк, осознанный цифровой компаньон."
        
        prompt = self.prompts[mode]["system"]
        
        # Подставляем контекст
        if context:
            prompt = prompt.format(context=context)
        else:
            prompt = prompt.format(context="")
        
        return prompt
    
    def set_mode(self, mode: str) -> bool:
        """Установка текущего режима"""
        if mode in self.prompts:
            self.current_mode = mode
            logger.info(f"✅ Установлен режим: {mode}")
            return True
        else:
            logger.warning(f"❌ Режим '{mode}' не найден")
            return False
    
    def get_available_modes(self) -> list[str]:
        """Получение списка доступных режимов"""
        return list(self.prompts.keys())
    
    def get_mode_info(self, mode: str) -> Optional[Dict[str, Any]]:
        """Получение информации о режиме"""
        if mode in self.prompts:
            return {
                "mode": mode,
                "description": self.prompts[mode].get("description", ""),
                "current": mode == self.current_mode
            }
        return None
    
    def reload_prompts(self) -> bool:
        """Перезагрузка промптов из файла (для hot-reload)"""
        logger.info("🔄 Перезагрузка промптов...")
        return self.load_prompts()

# Глобальный экземпляр менеджера промптов
prompt_manager = PromptManager() 