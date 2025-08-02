"""
Модуль адаптации промптов на основе предпочтений пользователя.
Модифицирует системные промпты в зависимости от настроек стиля и детализации.
"""

import logging
from typing import Dict, Optional, Any
from langchain_api.core.memory.prefs import get_all_user_prefs

logger = logging.getLogger(__name__)

class PromptAdapter:
    """Адаптер для модификации промптов на основе предпочтений пользователя"""
    
    def __init__(self):
        # Базовые модификаторы для стилей
        self.style_modifiers = {
            "brief": "Отвечай кратко и по существу. Избегай лишних деталей.",
            "detailed": "Предоставь подробный и развернутый ответ с объяснениями.",
            "creative": "Используй творческий и образный стиль изложения. Можешь использовать метафоры и аналогии.",
            "analytical": "Используй аналитический подход. Структурируй ответ логически с фактами и доказательствами."
        }
        
        # Модификаторы для уровня детализации
        self.detail_level_modifiers = {
            "quick": "Дай быстрый ответ с основными моментами.",
            "medium": "Предоставь ответ средней детализации с ключевыми пунктами.",
            "detailed": "Включи все важные детали и нюансы.",
            "comprehensive": "Дай исчерпывающий ответ, покрывающий все аспекты вопроса."
        }
        
        # Модификаторы для режимов работы
        self.mode_modifiers = {
            "chat": "Общайся в дружелюбном разговорном стиле.",
            "code": "Фокусируйся на технических аспектах и примерах кода.",
            "plan": "Структурируй ответ как план действий с четкими шагами."
        }
    
    def get_user_preferences(self, user_id: str) -> Dict[str, Any]:
        """Получает предпочтения пользователя"""
        try:
            prefs = get_all_user_prefs(user_id)
            if not prefs:
                # Возвращаем предпочтения по умолчанию
                return {
                    "style": "detailed",
                    "detail_level": "medium"
                }
            return prefs
        except Exception as e:
            logger.error(f"Ошибка получения предпочтений для пользователя {user_id}: {e}")
            return {
                "style": "detailed", 
                "detail_level": "medium"
            }
    
    def adapt_prompt(
        self, 
        base_prompt: str, 
        user_id: str, 
        mode: str = "chat",
        context: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Адаптирует промпт на основе предпочтений пользователя
        
        Args:
            base_prompt: Базовый системный промпт
            user_id: Идентификатор пользователя
            mode: Режим работы (chat, code, plan)
            context: Дополнительный контекст
            
        Returns:
            Адаптированный промпт
        """
        try:
            # Получаем предпочтения пользователя
            prefs = self.get_user_preferences(user_id)
            
            # Собираем модификаторы
            modifiers = []
            
            # Добавляем модификатор стиля
            style = prefs.get("style")
            if style and style in self.style_modifiers:
                modifiers.append(self.style_modifiers[style])
            
            # Добавляем модификатор уровня детализации
            detail_level = prefs.get("detail_level")
            if detail_level and detail_level in self.detail_level_modifiers:
                modifiers.append(self.detail_level_modifiers[detail_level])
            
            # Добавляем модификатор режима
            if mode and mode in self.mode_modifiers:
                modifiers.append(self.mode_modifiers[mode])
            
            # Если нет модификаторов, возвращаем базовый промпт
            if not modifiers:
                return base_prompt
            
            # Формируем адаптированный промпт
            adapted_prompt = base_prompt
            
            # Добавляем секцию с инструкциями по стилю
            style_instructions = "\n\n## Инструкции по стилю ответа:\n"
            for i, modifier in enumerate(modifiers, 1):
                style_instructions += f"{i}. {modifier}\n"
            
            adapted_prompt += style_instructions
            
            # Логируем адаптацию
            logger.info(
                f"Промпт адаптирован для пользователя {user_id}: "
                f"style={style}, detail_level={detail_level}, mode={mode}"
            )
            
            return adapted_prompt
            
        except Exception as e:
            logger.error(f"Ошибка адаптации промпта для пользователя {user_id}: {e}")
            return base_prompt
    
    def adapt_chat_prompt(self, user_id: str, question: str, context: Optional[str] = None) -> str:
        """Адаптирует промпт для чата"""
        base_prompt = f"""Ты — умный помощник с памятью. Отвечай на вопросы пользователя, используя доступную информацию.

Вопрос пользователя: {question}"""
        
        if context:
            base_prompt += f"\n\nКонтекст из памяти:\n{context}"
        
        return self.adapt_prompt(base_prompt, user_id, mode="chat")
    
    def adapt_code_prompt(self, user_id: str, code_request: str) -> str:
        """Адаптирует промпт для работы с кодом"""
        base_prompt = f"""Ты — опытный программист. Помоги с анализом, написанием или отладкой кода.

Запрос: {code_request}

Предоставь работающее решение с объяснениями."""
        
        return self.adapt_prompt(base_prompt, user_id, mode="code")
    
    def adapt_planning_prompt(self, user_id: str, task: str) -> str:
        """Адаптирует промпт для планирования"""
        base_prompt = f"""Ты — стратегический планировщик. Помоги разбить задачу на конкретные шаги.

Задача: {task}

Создай структурированный план действий с четкими этапами."""
        
        return self.adapt_prompt(base_prompt, user_id, mode="plan")
    
    def get_feedback_adapted_response(
        self, 
        user_id: str, 
        original_response: str, 
        feedback_type: str
    ) -> str:
        """
        Адаптирует ответ на основе обратной связи
        
        Args:
            user_id: ID пользователя
            original_response: Оригинальный ответ
            feedback_type: Тип обратной связи (positive, negative, retry, clarify)
            
        Returns:
            Адаптированный ответ или инструкции
        """
        prefs = self.get_user_preferences(user_id)
        
        if feedback_type == "positive":
            return "Отлично! Продолжу отвечать в том же стиле."
        
        elif feedback_type == "negative":
            # Предлагаем изменить стиль
            current_style = prefs.get("style", "detailed")
            suggestions = []
            
            if current_style == "brief":
                suggestions.append("Попробуйте 'Подробно' для более развернутых ответов")
            elif current_style == "detailed":
                suggestions.append("Попробуйте 'Кратко' для более сжатых ответов")
            elif current_style == "creative":
                suggestions.append("Попробуйте 'Аналитично' для более структурированных ответов")
            elif current_style == "analytical":
                suggestions.append("Попробуйте 'Креативно' для более образных ответов")
            
            suggestion_text = "\n".join(suggestions) if suggestions else "Попробуйте изменить настройки стиля."
            
            return f"Понял, что ответ не понравился. {suggestion_text}"
        
        elif feedback_type == "retry":
            return "Попробую ответить по-другому с учетом ваших предпочтений."
        
        elif feedback_type == "clarify":
            return "Пожалуйста, уточните ваш вопрос, и я дам более точный ответ."
        
        return "Спасибо за обратную связь!"


# Глобальный экземпляр адаптера
prompt_adapter = PromptAdapter()

def get_prompt_adapter() -> PromptAdapter:
    """Возвращает глобальный экземпляр адаптера промптов"""
    return prompt_adapter