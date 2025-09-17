"""
Авторешатель проблем для Марка

Автоматически решает простые проблемы без обращения к LLM,
используя накопленные знания и паттерны
"""

import logging
import re
from typing import Dict, Any, Optional, List
from datetime import datetime
from dataclasses import dataclass

from app.agents.mark_agent import MarkAgent
from app.memory.advanced_memory_adapter import AdvancedMemoryAdapter

logger = logging.getLogger(__name__)


@dataclass
class AutoSolution:
    """Автоматическое решение проблемы"""
    success: bool
    response: str
    confidence: float
    method: str
    metadata: Dict[str, Any]


@dataclass
class ProblemPattern:
    """Паттерн проблемы для авторешения"""
    pattern: str
    solution: str
    confidence: float
    usage_count: int
    last_used: datetime
    category: str = "generic"  # greeting|gratitude|help|tech|generic


class AutoProblemSolver:
    """
    Авторешатель проблем
    
    Основные возможности:
    - Распознает простые проблемы по паттернам
    - Автоматически применяет решения
    - Учится на успешных решениях
    - Управляет базой знаний решений
    """
    
    def __init__(
        self,
        mark_agent: MarkAgent,
        memory_adapter: AdvancedMemoryAdapter
    ):
        self.agent = mark_agent
        self.memory = memory_adapter
        
        # База знаний паттернов
        self.problem_patterns: List[ProblemPattern] = []
        
        # Настройки
        self.min_confidence = 0.7
        self.max_patterns = 100
        
        # Инициализируем базовые паттерны
        self._init_basic_patterns()
        
        logger.info("🤖 AutoProblemSolver инициализирован")
    
    def _init_basic_patterns(self):
        """Инициализирует базовые паттерны проблем"""
        basic_patterns = [
            # Приветствия
            ProblemPattern(
                pattern=r"привет|здравствуй|добрый день|доброе утро|добрый вечер",
                solution="Привет! 👋 Рад вас видеть! Как я могу помочь?",
                confidence=0.95,
                usage_count=0,
                last_used=datetime.now(),
                category="greeting"
            ),
            ProblemPattern(
                pattern=r"как дела|как ты|как настроение",
                solution="Спасибо, у меня все отлично! 😊 Готов помогать с задачами.",
                confidence=0.9,
                usage_count=0,
                last_used=datetime.now(),
                category="smalltalk"
            ),
            
            # Простые вопросы
            ProblemPattern(
                pattern=r"кто ты|что ты умеешь|расскажи о себе",
                solution="Я Марк - ваш AI-ассистент! 🤖 Умею помогать с разработкой, анализировать код, планировать проекты и многое другое.",
                confidence=0.9,
                usage_count=0,
                last_used=datetime.now(),
                category="about"
            ),
            ProblemPattern(
                pattern=r"время|который час|дата",
                solution=f"Сейчас {datetime.now().strftime('%H:%M, %d.%m.%Y')} 📅",
                confidence=0.95,
                usage_count=0,
                last_used=datetime.now(),
                category="info"
            ),
            
            # Технические вопросы
            ProblemPattern(
                pattern=r"python|питон",
                solution="Python - отличный язык программирования! 🐍 Универсальный, читаемый, с богатой экосистемой библиотек.",
                confidence=0.85,
                usage_count=0,
                last_used=datetime.now(),
                category="tech"
            ),
            ProblemPattern(
                pattern=r"docker|докер",
                solution="Docker - платформа для контейнеризации приложений! 🐳 Позволяет упаковывать приложения в изолированные контейнеры.",
                confidence=0.85,
                usage_count=0,
                last_used=datetime.now(),
                category="tech"
            ),
            
            # Помощь
            ProblemPattern(
                pattern=r"помощь|help|что делать|как быть",
                solution="Я готов помочь! 🚀 Расскажите, что нужно сделать, и я предложу решение или выполню задачу.",
                confidence=0.9,
                usage_count=0,
                last_used=datetime.now(),
                category="help"
            ),
            
            # Благодарности
            ProblemPattern(
                pattern=r"спасибо|благодарю|thanks|thank you",
                solution="Рад был помочь! 😊 Если понадобится еще что-то - обращайтесь!",
                confidence=0.95,
                usage_count=0,
                last_used=datetime.now(),
                category="gratitude"
            ),
        ]
        
        self.problem_patterns.extend(basic_patterns)
        logger.info(f"📚 Загружено {len(basic_patterns)} базовых паттернов")
    
    async def has_solution(self, problem_description: str) -> bool:
        """
        Проверяет, есть ли готовое решение для проблемы
        
        Args:
            problem_description: Описание проблемы
            
        Returns:
            True если есть готовое решение
        """
        try:
            # Ищем подходящий паттерн
            best_pattern = self._find_best_pattern(problem_description)
            
            if best_pattern and best_pattern.confidence >= self.min_confidence:
                return True
            
            # Проверяем память на наличие похожих решений
            similar_solutions = await self._find_similar_solutions(problem_description)
            
            return len(similar_solutions) > 0
            
        except Exception as e:
            logger.error(f"❌ Ошибка проверки наличия решения: {e}")
            return False
    
    async def solve_problem(
        self, 
        problem_description: str, 
        context: Optional[Dict[str, Any]] = None
    ) -> AutoSolution:
        """
        Автоматически решает проблему
        
        Args:
            problem_description: Описание проблемы
            context: Дополнительный контекст
            
        Returns:
            Решение проблемы
        """
        try:
            logger.info(f"🤖 Авторешение проблемы: {problem_description[:100]}...")
            
            # 1. Ищем подходящий паттерн
            best_pattern = self._find_best_pattern(problem_description)
            
            if best_pattern and best_pattern.confidence >= self.min_confidence:
                # Обновляем статистику использования
                best_pattern.usage_count += 1
                best_pattern.last_used = datetime.now()
                
                logger.info(f"✅ Найден паттерн: {best_pattern.pattern}")
                
                return AutoSolution(
                    success=True,
                    response=best_pattern.solution,
                    confidence=best_pattern.confidence,
                    method="pattern_match",
                    metadata={"pattern_id": best_pattern.pattern}
                )
            
            # 2. Ищем решение в памяти
            memory_solution = await self._find_memory_solution(problem_description, context)
            
            if memory_solution:
                logger.info("✅ Найдено решение в памяти")
                
                return AutoSolution(
                    success=True,
                    response=memory_solution["response"],
                    confidence=memory_solution.get("confidence", 0.8),
                    method="memory_search",
                    metadata=memory_solution
                )
            
            # 3. Пытаемся сгенерировать решение на основе контекста
            generated_solution = await self._generate_context_solution(problem_description, context)
            
            if generated_solution:
                logger.info("✅ Сгенерировано контекстное решение")
                
                return AutoSolution(
                    success=True,
                    response=generated_solution,
                    confidence=0.7,
                    method="context_generation",
                    metadata={"context_based": True}
                )
            
            # 4. Если ничего не найдено
            logger.info("❌ Авторешение не найдено")
            
            return AutoSolution(
                success=False,
                response="Извините, не могу автоматически решить эту задачу. Обработаю через LLM.",
                confidence=0.0,
                method="no_solution",
                metadata={}
            )
            
        except Exception as e:
            logger.error(f"❌ Ошибка авторешения: {e}")
            
            return AutoSolution(
                success=False,
                response=f"Произошла ошибка при авторешении: {str(e)}",
                confidence=0.0,
                method="error",
                metadata={"error": str(e)}
            )
    
    def _find_best_pattern(self, problem_description: str) -> Optional[ProblemPattern]:
        """
        Находит лучший паттерн для проблемы
        
        Args:
            problem_description: Описание проблемы
            
        Returns:
            Лучший паттерн или None
        """
        try:
            best_pattern = None
            best_score = 0.0
            
            problem_lower = problem_description.lower()
            
            for pattern in self.problem_patterns:
                # Проверяем совпадение по регулярному выражению
                if re.search(pattern.pattern, problem_lower, re.IGNORECASE):
                    # Вычисляем оценку совпадения
                    score = pattern.confidence
                    
                    # Бонус за частоту использования
                    usage_bonus = min(pattern.usage_count * 0.01, 0.1)
                    score += usage_bonus
                    
                    # Бонус за свежесть использования
                    days_since_use = (datetime.now() - pattern.last_used).days
                    freshness_bonus = max(0, 0.05 - days_since_use * 0.001)
                    score += freshness_bonus
                    
                    if score > best_score:
                        best_score = score
                        best_pattern = pattern
            
            return best_pattern
            
        except Exception as e:
            logger.error(f"❌ Ошибка поиска паттерна: {e}")
            return None
    
    async def _find_similar_solutions(
        self, 
        problem_description: str, 
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Ищет похожие решения в памяти
        
        Args:
            problem_description: Описание проблемы
            limit: Максимальное количество решений
            
        Returns:
            Список похожих решений
        """
        try:
            # Ищем похожие эпизоды в памяти
            similar_episodes = await self.memory.find_similar_episodes(
                problem_description,
                limit=limit
            ) or []
            
            solutions = []
            for episode in similar_episodes if isinstance(similar_episodes, list) else []:
                if episode.get("outcome") == "успешно":
                    solutions.append({
                        "response": episode.get("action", ""),
                        "confidence": 0.8,
                        "source": "memory",
                        "episode_id": episode.get("id")
                    })
            
            return solutions
            
        except Exception as e:
            logger.error(f"❌ Ошибка поиска в памяти: {e}")
            return []
    
    async def _find_memory_solution(
        self, 
        problem_description: str, 
        context: Optional[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """
        Ищет готовое решение в памяти
        
        Args:
            problem_description: Описание проблемы
            context: Дополнительный контекст
            
        Returns:
            Решение из памяти или None
        """
        try:
            similar_solutions = await self._find_similar_solutions(problem_description, limit=1)
            
            if similar_solutions:
                return similar_solutions[0]
            
            return None
            
        except Exception as e:
            logger.error(f"❌ Ошибка поиска решения в памяти: {e}")
            return None
    
    async def _generate_context_solution(
        self, 
        problem_description: str, 
        context: Optional[Dict[str, Any]]
    ) -> Optional[str]:
        """
        Генерирует решение на основе контекста
        
        Args:
            problem_description: Описание проблемы
            context: Дополнительный контекст
            
        Returns:
            Сгенерированное решение или None
        """
        try:
            if not context:
                return None
            
            # Простая логика генерации на основе контекста
            if "error" in context:
                error_msg = context["error"]
                if "timeout" in error_msg.lower():
                    return "Попробуйте увеличить таймаут операции или разбить задачу на части."
                elif "permission" in error_msg.lower():
                    return "Проверьте права доступа и попробуйте запустить с соответствующими привилегиями."
                elif "not found" in error_msg.lower():
                    return "Проверьте правильность пути или имени файла."
            
            if "command" in context:
                cmd = context["command"]
                if "pip" in cmd:
                    return "Попробуйте обновить pip: python -m pip install --upgrade pip"
                elif "python" in cmd:
                    return "Проверьте версию Python и убедитесь, что она установлена корректно."
            
            return None
            
        except Exception as e:
            logger.error(f"❌ Ошибка генерации контекстного решения: {e}")
            return None
    
    async def learn_from_solution(
        self, 
        problem: str, 
        solution: str, 
        success: bool, 
        confidence: float
    ):
        """
        Учится на решении проблемы
        
        Args:
            problem: Описание проблемы
            solution: Примененное решение
            success: Успешность решения
            confidence: Уверенность в решении
        """
        try:
            if success and confidence > 0.8:
                # Создаем новый паттерн
                new_pattern = ProblemPattern(
                    pattern=self._create_pattern_from_text(problem),
                    solution=solution,
                    confidence=confidence,
                    usage_count=1,
                    last_used=datetime.now()
                )
                
                # Добавляем паттерн, если не превышен лимит
                if len(self.problem_patterns) < self.max_patterns:
                    self.problem_patterns.append(new_pattern)
                    logger.info(f"📚 Добавлен новый паттерн: {new_pattern.pattern}")
                else:
                    # Заменяем наименее используемый паттерн
                    self._replace_least_used_pattern(new_pattern)
                
                # Сохраняем в память
                await self.memory.save_episode(
                    situation=problem,
                    actions_taken=[f"Авторешение: {solution}"],
                    outcome="успешно" if success else "неудачно",
                    reasoning="",
                    lesson_learned="",
                    satisfaction=confidence,
                    metadata={
                        "method": "auto_solve",
                        "confidence": confidence,
                        "pattern_created": True
                    }
                )
                
        except Exception as e:
            logger.error(f"❌ Ошибка обучения на решении: {e}")
    
    def _create_pattern_from_text(self, text: str) -> str:
        """
        Создает паттерн из текста проблемы
        
        Args:
            text: Текст проблемы
            
        Returns:
            Регулярное выражение для паттерна
        """
        try:
            # Простая логика создания паттерна
            # Убираем специфичные детали, оставляем ключевые слова
            words = text.lower().split()
            key_words = [w for w in words if len(w) > 3 and w not in ["что", "как", "где", "когда", "почему"]]
            
            if len(key_words) > 3:
                key_words = key_words[:3]  # Берем только первые 3 ключевых слова
            
            pattern = "|".join(key_words)
            return pattern
            
        except Exception as e:
            logger.error(f"❌ Ошибка создания паттерна: {e}")
            return text.lower()[:20]  # Fallback
    
    def _replace_least_used_pattern(self, new_pattern: ProblemPattern):
        """
        Заменяет наименее используемый паттерн
        
        Args:
            new_pattern: Новый паттерн для добавления
        """
        try:
            if not self.problem_patterns:
                return
            
            # Находим паттерн с наименьшим количеством использований
            least_used = min(self.problem_patterns, key=lambda p: p.usage_count)
            
            # Заменяем его
            index = self.problem_patterns.index(least_used)
            self.problem_patterns[index] = new_pattern
            
            logger.info(f"🔄 Заменен паттерн: {least_used.pattern} -> {new_pattern.pattern}")
            
        except Exception as e:
            logger.error(f"❌ Ошибка замены паттерна: {e}")
    
    def get_patterns_stats(self) -> Dict[str, Any]:
        """Получает статистику паттернов"""
        try:
            total_patterns = len(self.problem_patterns)
            active_patterns = len([p for p in self.problem_patterns if p.usage_count > 0])
            total_usage = sum(p.usage_count for p in self.problem_patterns)
            
            return {
                "total_patterns": total_patterns,
                "active_patterns": active_patterns,
                "total_usage": total_usage,
                "average_confidence": sum(p.confidence for p in self.problem_patterns) / total_patterns if total_patterns > 0 else 0
            }
            
        except Exception as e:
            logger.error(f"❌ Ошибка получения статистики: {e}")
            return {}
    
    async def clear_patterns(self):
        """Очищает все паттерны (кроме базовых)"""
        try:
            # Оставляем только базовые паттерны
            basic_patterns = [p for p in self.problem_patterns if p.confidence >= 0.9]
            self.problem_patterns = basic_patterns
            
            logger.info(f"🧹 Очищены паттерны, оставлено {len(basic_patterns)} базовых")
            
        except Exception as e:
            logger.error(f"❌ Ошибка очистки паттернов: {e}")
