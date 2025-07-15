"""
Модуль для управления контекстом системы.
"""

from typing import Dict, List, Optional, Any
from datetime import datetime
import json

import logging

logger = logging.getLogger(__name__)

class ContextManager:
    """
    Класс для управления контекстом системы.
    
    Отвечает за:
    - Хранение текущего контекста
    - Управление историей контекста
    - Интеграцию с системой памяти
    - Анализ и обновление контекста
    - Анализ ответов LLM
    """
    
    def __init__(self, memory_manager=None):
        """
        Инициализация менеджера контекста.
        
        Args:
            memory_manager: Менеджер памяти для интеграции с системой памяти (опционально)
        """
        self.memory_manager = memory_manager
        self.current_context: Dict[str, Any] = {
            'session_id': 'default_session',
            'timestamp': datetime.utcnow().isoformat(),
            'active_tasks': [],
            'recent_actions': [],
            'relevant_memories': [],
            'user_state': {},
            'system_state': {},
            'llm_interactions': [],  # Добавляем историю взаимодействий с LLM
            'key_ideas': [],  # Добавляем ключевые идеи
            'topics': [],  # Добавляем темы
            'entities': [],  # Добавляем сущности
            'relations': [],  # Добавляем связи
            'idea_links': [],  # Добавляем связи между идеями
            'priorities': []  # Добавляем приоритеты
        }
        self.context_history: List[Dict[str, Any]] = []
        self.logger = logger
        
    def update_context(self, updates: Dict[str, Any]) -> None:
        """
        Обновление текущего контекста.
        
        Args:
            updates: Словарь с обновлениями контекста
        """
        # Обновляем контекст
        self.current_context.update(updates)
        self.current_context['timestamp'] = datetime.utcnow().isoformat()
        
        # Сохраняем обновленный контекст в историю
        self.context_history.append(self.current_context.copy())
        
        # Сохраняем важные изменения в памяти (если доступен)
        if self.memory_manager:
            self._save_context_to_memory()
        
    def get_context(self) -> Dict[str, Any]:
        """
        Получение текущего контекста.
        
        Returns:
            Текущий контекст
        """
        return self.current_context.copy()
        
    def get_context_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Получение истории контекста.
        
        Args:
            limit: Максимальное количество записей истории
            
        Returns:
            Список последних контекстов
        """
        return self.context_history[-limit:]
        
    def _save_context_to_memory(self) -> None:
        """
        Сохранение важных изменений контекста в память.
        """
        # Создаем опыт из важных изменений
        if self.current_context.get('recent_actions') and self.memory_manager:
            experience = {
                'summary': f"Контекстное изменение: {json.dumps(self.current_context['recent_actions'][-1])}",
                'timestamp': datetime.utcnow().isoformat() + 'Z',
                'session_id': self.current_context['session_id']
            }
            if hasattr(self.memory_manager, 'memory_registry'):
                self.memory_manager.memory_registry.get('Experience').insert(experience)
            
    def analyze_context(self) -> Dict[str, Any]:
        """
        Анализ текущего контекста.
        
        Returns:
            Словарь с результатами анализа
        """
        analysis = {
            'active_tasks_count': len(self.current_context['active_tasks']),
            'recent_actions_count': len(self.current_context['recent_actions']),
            'relevant_memories_count': len(self.current_context['relevant_memories']),
            'context_age': (datetime.utcnow() - datetime.fromisoformat(self.current_context['timestamp'])).total_seconds(),
            'llm_interactions_count': len(self.current_context['llm_interactions'])
        }
        return analysis

    async def analyze_llm_response(self, response: str, query: str) -> Dict[str, Any]:
        """
        Анализ ответа от LLM.
        
        Args:
            response: Ответ от LLM
            query: Исходный запрос
            
        Returns:
            Dict[str, Any]: Результаты анализа
        """
        # Базовый анализ
        relevance = self._calculate_relevance(response, query)
        quality = self._calculate_quality(response)
        consistency = self._check_consistency(response)
        
        # Расширенный анализ
        semantic_analysis = self._analyze_semantics(response)
        key_ideas = self._extract_key_ideas(response)
        sentiment = self._analyze_sentiment(response)
        
        # Генерируем связи между сущностями
        entities = semantic_analysis.get('entities', [])
        relations = self._analyze_relations(response, entities)
        semantic_analysis['relations'] = relations
        
        analysis = {
            'relevance_score': relevance,
            'quality_score': quality,
            'consistency_score': consistency,
            'semantic_analysis': semantic_analysis,
            'key_ideas': key_ideas,
            'sentiment': sentiment,
            'timestamp': datetime.now().isoformat()
        }
        
        # Сохраняем взаимодействие
        interaction = {
            'query': query,
            'response': response,
            'analysis': analysis
        }
        
        # Сохраняем в контекст
        if 'llm_interactions' not in self.current_context:
            self.current_context['llm_interactions'] = []
        self.current_context['llm_interactions'].append(interaction)
        
        # Сохраняем в память (если доступен)
        if self.memory_manager:
            self._save_llm_interaction(interaction)
        
        return analysis
        
    def _calculate_relevance(self, response: str, query: str) -> float:
        """
        Расчет релевантности ответа.
        
        Args:
            response: Ответ от LLM
            query: Исходный запрос
            
        Returns:
            float: Оценка релевантности от 0 до 1
        """
        # TODO: Реализовать более сложную логику оценки релевантности
        # Пока используем простую проверку наличия ключевых слов
        query_words = set(query.lower().split())
        response_words = set(response.lower().split())
        
        if not query_words:
            return 0.0
            
        common_words = query_words.intersection(response_words)
        return len(common_words) / len(query_words)
        
    def _calculate_quality(self, response: str) -> float:
        """
        Расчет качества ответа.
        
        Args:
            response: Ответ от LLM
            
        Returns:
            float: Оценка качества от 0 до 1
        """
        # TODO: Реализовать более сложную логику оценки качества
        # Пока используем простые метрики
        if not response:
            return 0.0
            
        # Проверяем длину ответа
        length_score = min(len(response) / 100, 1.0)
        
        # Проверяем наличие структуры (заголовки, списки и т.д.)
        structure_score = 0.0
        if '#' in response or '-' in response or '*' in response:
            structure_score = 0.5
            
        return (length_score + structure_score) / 2
        
    def _check_consistency(self, response: str) -> float:
        """
        Проверка консистентности ответа.
        
        Args:
            response: Ответ от LLM
            
        Returns:
            float: Оценка консистентности от 0 до 1
        """
        if not response:
            return 0.0
            
        # Разбиваем на предложения
        sentences = [s.strip() for s in response.split('.') if s.strip()]
        if len(sentences) < 2:
            return 1.0
            
        # Проверяем каждую пару предложений на противоречие
        for i in range(len(sentences)):
            for j in range(i + 1, len(sentences)):
                sent1 = sentences[i].lower()
                sent2 = sentences[j].lower()
                
                # Проверяем на прямое отрицание
                if sent1.replace('не ', '') == sent2.replace('не ', ''):
                    return 0.0
                    
                # Проверяем на противоречивые пары слов
                contradictions = [
                    ('да', 'нет'),
                    ('всегда', 'никогда'),
                    ('все', 'ничего'),
                    ('является', 'не является'),
                    ('это', 'не это'),
                    ('поддерживает', 'не поддерживает'),
                    ('работает', 'не работает'),
                    ('имеет', 'не имеет'),
                    ('может', 'не может'),
                    ('должен', 'не должен')
                ]
                
                for word1, word2 in contradictions:
                    if (word1 in sent1 and word2 in sent2) or (word1 in sent2 and word2 in sent1):
                        # Проверяем, что слова относятся к одному предмету
                        # Для этого ищем общие существительные в обоих предложениях
                        common_words = set(sent1.split()) & set(sent2.split())
                        if len(common_words) > 0:
                            return 0.0
                            
        return 1.0
        
    def _analyze_semantics(self, text: str) -> Dict[str, Any]:
        """
        Семантический анализ текста.
        
        Args:
            text: Анализируемый текст
            
        Returns:
            Dict[str, Any]: Результаты семантического анализа
        """
        if not text:
            return {
                'topics': [],
                'entities': [],
                'relations': [],
                'complexity': 0.0
            }
            
        # TODO: Реализовать более сложный семантический анализ
        # Пока используем простые эвристики
        
        # Определяем основные темы
        topics = self._extract_topics(text)
        
        # Извлекаем именованные сущности
        entities = self._extract_entities(text)
        
        # Анализируем отношения между сущностями
        relations = self._analyze_relations(text, entities)
        
        # Оцениваем сложность текста
        complexity = self._calculate_complexity(text)
        
        return {
            'topics': topics,
            'entities': entities,
            'relations': relations,
            'complexity': complexity
        }
        
    def _extract_topics(self, text: str) -> List[str]:
        """
        Извлечение основных тем из текста.
        
        Args:
            text: Анализируемый текст
            
        Returns:
            List[str]: Список тем
        """
        if not text:
            return []
            
        # TODO: Реализовать более сложное извлечение тем
        # Пока используем простые эвристики
        
        topics = []
        
        # Разбиваем на предложения
        sentences = text.split('.')
        
        # Ключевые слова, указывающие на тему
        topic_indicators = ['это', 'является', 'представляет', 'включает', 'содержит']
        
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue
                
            # Ищем предложения с ключевыми словами
            for indicator in topic_indicators:
                if indicator in sentence.lower():
                    # Берем слово перед индикатором как тему
                    words = sentence.split()
                    for i, word in enumerate(words):
                        if word.lower() == indicator and i > 0:
                            # Проверяем, что предыдущее слово - существительное
                            prev_word = words[i-1]
                            if prev_word.endswith(('а', 'я', 'о', 'е', 'и', 'ы', 'й')):
                                topics.append(prev_word)
                                
            # Если не нашли тему через индикаторы, берем первое существительное
            if not topics:
                words = sentence.split()
                for word in words:
                    if word.endswith(('а', 'я', 'о', 'е', 'и', 'ы', 'й')):
                        topics.append(word)
                        break
                        
        # Добавляем технические термины, если они есть
        tech_terms = ['Python', 'API', 'LLM', 'контекст', 'память', 'система']
        for term in tech_terms:
            if term in text:
                topics.append(term)
                
        return list(set(topics))
        
    def _extract_entities(self, text: str) -> List[Dict[str, Any]]:
        """
        Извлечение именованных сущностей из текста.
        
        Args:
            text: Анализируемый текст
            
        Returns:
            List[Dict[str, Any]]: Список сущностей с их типами
        """
        entities = []
        
        # Ищем технические термины
        tech_terms = ['Python', 'API', 'LLM', 'контекст', 'память', 'система', 'язык', 'программирование', 'данные']
        for term in tech_terms:
            if term in text:
                entities.append({
                    'text': term,
                    'type': 'technical_term',
                    'confidence': 0.8
                })
                
        # Ищем числовые значения
        import re
        numbers = re.findall(r'\d+', text)
        for num in numbers:
            entities.append({
                'text': num,
                'type': 'number',
                'confidence': 0.9
            })
            
        # Ищем существительные (простые эвристики)
        nouns = ['язык', 'программирование', 'данные', 'основы', 'интерпретатор', 'обработка']
        for noun in nouns:
            if noun in text.lower():
                entities.append({
                    'text': noun,
                    'type': 'concept',
                    'confidence': 0.7
                })
                
        # Ищем глаголы (простые эвристики)
        verbs = ['работает', 'обрабатывает', 'является', 'понимать']
        for verb in verbs:
            if verb in text.lower():
                entities.append({
                    'text': verb,
                    'type': 'action',
                    'confidence': 0.7
                })
                
        return entities
        
    def _analyze_relations(self, text: str, entities: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Анализ отношений между сущностями.
        
        Args:
            text: Анализируемый текст
            entities: Список сущностей
            
        Returns:
            List[Dict[str, Any]]: Список отношений
        """
        relations = []
        
        # Ищем отношения между всеми сущностями
        for i, entity1 in enumerate(entities):
            for entity2 in entities[i+1:]:
                # Проверяем, находятся ли сущности в одном предложении
                sentences = text.split('.')
                for sentence in sentences:
                    if entity1['text'] in sentence and entity2['text'] in sentence:
                        # Определяем тип отношения
                        relation_type = 'related'
                        sentence_lower = sentence.lower()
                        
                        # Проверяем различные типы отношений
                        if any(word in sentence_lower for word in ['это', 'является', 'представляет собой']):
                            relation_type = 'is_a'
                        elif any(word in sentence_lower for word in ['имеет', 'содержит', 'включает']):
                            relation_type = 'has_a'
                        elif any(word in sentence_lower for word in ['может', 'способен', 'умеет']):
                            relation_type = 'can_do'
                        elif any(word in sentence_lower for word in ['использует', 'применяет', 'работает с']):
                            relation_type = 'uses'
                        elif any(word in sentence_lower for word in ['связан с', 'относится к', 'касается']):
                            relation_type = 'related_to'
                            
                        relations.append({
                            'source': entity1['text'],
                            'target': entity2['text'],
                            'type': relation_type,
                            'confidence': 0.7
                        })
                        
        return relations
        
    def _calculate_complexity(self, text: str) -> float:
        """
        Расчет сложности текста.
        
        Args:
            text: Анализируемый текст
            
        Returns:
            float: Оценка сложности от 0 до 1
        """
        if not text:
            return 0.0
            
        # Простые метрики сложности
        sentences = text.split('.')
        words = text.split()
        
        # Средняя длина предложения
        avg_sentence_length = len(words) / len(sentences) if sentences else 0
        
        # Количество технических терминов
        tech_terms = ['Python', 'API', 'LLM', 'контекст', 'память', 'система']
        tech_term_count = sum(1 for term in tech_terms if term in text)
        
        # Нормализуем метрики
        complexity = min(1.0, (avg_sentence_length / 20 + tech_term_count / 5) / 2)
        
        return complexity
        
    def _extract_key_ideas(self, text: str) -> List[Dict[str, Any]]:
        """
        Извлечение ключевых идей из текста.
        
        Args:
            text: Анализируемый текст
            
        Returns:
            List[Dict[str, Any]]: Список ключевых идей
        """
        if not text:
            return []
            
        # TODO: Реализовать более сложное извлечение идей
        # Пока используем простые эвристики
        
        ideas = []
        
        # Разбиваем на предложения
        sentences = text.split('.')
        
        # Анализируем каждое предложение
        for sentence in sentences:
            if not sentence.strip():
                continue
                
            # Проверяем на наличие ключевых слов
            if any(word in sentence.lower() for word in ['важно', 'ключевой', 'основной', 'главный']):
                ideas.append({
                    'text': sentence.strip(),
                    'importance': 0.9,
                    'type': 'key_point'
                })
            # Проверяем на наличие технических терминов
            elif any(term in sentence for term in ['Python', 'API', 'LLM']):
                ideas.append({
                    'text': sentence.strip(),
                    'importance': 0.8,
                    'type': 'technical_info'
                })
            # Проверяем на наличие определений
            elif 'это' in sentence.lower() or 'является' in sentence.lower():
                ideas.append({
                    'text': sentence.strip(),
                    'importance': 0.7,
                    'type': 'definition'
                })
                
        return ideas
        
    def _analyze_sentiment(self, text: str) -> Dict[str, float]:
        """
        Анализ тональности текста.
        
        Args:
            text: Анализируемый текст
            
        Returns:
            Dict[str, float]: Оценки тональности
        """
        if not text:
            return {
                'positive': 0.0,
                'negative': 0.0,
                'neutral': 1.0
            }
            
        # TODO: Реализовать более сложный анализ тональности
        # Пока используем простые эвристики
        
        # Словари для анализа тональности
        positive_words = ['хорошо', 'отлично', 'успешно', 'эффективно', 'правильно']
        negative_words = ['плохо', 'ошибка', 'проблема', 'неправильно', 'неудачно']
        
        # Подсчитываем количество слов каждой тональности
        positive_count = sum(1 for word in positive_words if word in text.lower())
        negative_count = sum(1 for word in negative_words if word in text.lower())
        
        # Нормализуем результаты
        total = positive_count + negative_count
        if total == 0:
            return {
                'positive': 0.0,
                'negative': 0.0,
                'neutral': 1.0
            }
            
        return {
            'positive': positive_count / total,
            'negative': negative_count / total,
            'neutral': 1.0 - (positive_count + negative_count) / total
        }
        
    def _save_llm_interaction(self, interaction: Dict[str, Any]) -> None:
        """
        Сохранение взаимодействия с LLM в память.
        
        Args:
            interaction: Данные взаимодействия
        """
        if not self.memory_manager or not hasattr(self.memory_manager, 'memory_registry'):
            return
            
        experience = {
            'summary': f"Взаимодействие с LLM: {interaction['query'][:100]}...",
            'content': json.dumps(interaction),
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'session_id': self.current_context['session_id'],
            'type': 'llm_interaction'
        }
        self.memory_manager.memory_registry.get('Experience').insert(experience)
        
    async def update_context_from_analysis(self, analysis: Dict[str, Any]) -> bool:
        """Обновление контекста на основе анализа."""
        try:
            # Обновляем ключевые идеи
            if 'key_ideas' in analysis:
                self.current_context['key_ideas'] = analysis['key_ideas']
                
            # Обновляем семантический анализ
            if 'semantic_analysis' in analysis:
                semantic = analysis['semantic_analysis']
                
                # Обновляем темы
                if 'topics' in semantic:
                    self.current_context['topics'] = semantic['topics']
                    
                # Обновляем сущности
                if 'entities' in semantic:
                    self.current_context['entities'] = semantic['entities']
                    
                # Обновляем связи
                if 'relations' in semantic:
                    self.current_context['relations'] = semantic['relations']
                    
            # Обновляем общую информацию об анализе
            self.current_context.update({
                'last_analysis': analysis,
                'analysis_timestamp': datetime.now().isoformat()
            })
            
            # Сохраняем в историю
            self.context_history.append(self.current_context.copy())
            
            # Сохраняем в память
            self._save_context_to_memory()
            
            # Логируем обновление
            self.logger.info(f"Context updated from analysis: {analysis}")
            
            return True
        except Exception as e:
            self.logger.error(f"Error updating context from analysis: {e}")
            return False
        
    def link_related_ideas(self) -> None:
        """
        Связывание связанных идей в контексте.
        """
        # Очищаем существующие связи
        self.current_context['idea_links'] = []
        
        # Связываем идеи на основе семантической близости
        for i, idea1 in enumerate(self.current_context['key_ideas']):
            for j, idea2 in enumerate(self.current_context['key_ideas'][i+1:], i+1):
                # Проверяем семантическую близость
                content1 = idea1.get('content', idea1.get('text', ''))
                content2 = idea2.get('content', idea2.get('text', ''))
                similarity = self._calculate_semantic_similarity(content1, content2)
                
                if similarity > 0.5:  # Порог схожести
                    link = {
                        'source': i,
                        'target': j,
                        'type': 'semantic',
                        'strength': similarity
                    }
                    self.current_context['idea_links'].append(link)
                    
        # Связываем идеи с сущностями
        for i, idea in enumerate(self.current_context['key_ideas']):
            for j, entity in enumerate(self.current_context['entities']):
                idea_content = idea.get('content', idea.get('text', ''))
                entity_text = entity.get('text', entity.get('name', ''))
                if entity_text in idea_content:
                    link = {
                        'source': i,
                        'target': j,
                        'type': 'entity',
                        'strength': 1.0
                    }
                    self.current_context['idea_links'].append(link)
                    
        # Обновляем временную метку
        self.current_context['last_update'] = datetime.utcnow().isoformat()
        
        # Сохраняем в историю
        self.context_history.append(self.current_context.copy())
        
        # Сохраняем в память
        self._save_context_to_memory()
        
    def prioritize_information(self) -> None:
        """
        Приоритизация информации в контексте.
        """
        priorities = []
        
        # Приоритизируем ключевые идеи
        for idea in self.current_context['key_ideas']:
            score = idea.get('importance', 0.5)
            content = idea.get('content', idea.get('text', ''))
            priority = {
                'item': content,
                'score': score,
                'reason': 'key_idea',
                'type': idea.get('type', 'unknown')
            }
            priorities.append(priority)
            
        # Приоритизируем сущности
        for entity in self.current_context['entities']:
            score = 0.5  # Базовая оценка
            if entity.get('type') == 'technical':
                score += 0.2
            if entity.get('importance', 0) > 0.5:
                score += 0.3
                
            entity_text = entity.get('text', entity.get('name', ''))
            priority = {
                'item': entity_text,
                'score': score,
                'reason': 'entity',
                'type': entity.get('type', 'unknown')
            }
            priorities.append(priority)
            
        # Приоритизируем темы
        for topic in self.current_context['topics']:
            score = 0.4  # Базовая оценка
            idea_contents = [idea.get('content', idea.get('text', '')) for idea in self.current_context['key_ideas']]
            if topic in idea_contents:
                score += 0.3
                
            priority = {
                'item': topic,
                'score': score,
                'reason': 'topic',
                'type': 'topic'
            }
            priorities.append(priority)
            
        # Сортируем по приоритету
        priorities.sort(key=lambda x: x['score'], reverse=True)
        
        # Обновляем контекст
        self.current_context['priorities'] = priorities
        self.current_context['last_update'] = datetime.utcnow().isoformat()
        
        # Сохраняем в историю
        self.context_history.append(self.current_context.copy())
        
        # Сохраняем в память
        self._save_context_to_memory()
        
    def _calculate_semantic_similarity(self, text1: str, text2: str) -> float:
        """
        Расчет семантической схожести между двумя текстами.
        
        Args:
            text1: Первый текст
            text2: Второй текст
            
        Returns:
            float: Оценка схожести от 0 до 1
        """
        # TODO: Реализовать более сложную логику расчета схожести
        # Пока используем простую проверку общих слов
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())
        
        if not words1 or not words2:
            return 0.0
            
        common_words = words1.intersection(words2)
        return len(common_words) / max(len(words1), len(words2))

    async def update_context(self, changes: Dict[str, Any]) -> bool:
        """Обновление контекста на основе изменений."""
        try:
            # Обновляем контекст
            self.current_context.update(changes)
            
            # Логируем обновление
            self.logger.info(f"Context updated with changes: {changes}")
            
            return True
        except Exception as e:
            self.logger.error(f"Error updating context: {e}")
            return False
    
    async def add_event_links(self, event_id: str, related_events: List[str]) -> bool:
        """
        Добавление связей между событиями.
        
        Args:
            event_id: ID основного события
            related_events: Список связанных событий
            
        Returns:
            bool: True если успешно добавлено
        """
        try:
            if 'event_links' not in self.current_context:
                self.current_context['event_links'] = {}
                
            self.current_context['event_links'][event_id] = related_events
            return True
        except Exception as e:
            self.logger.error(f"Ошибка при добавлении связей событий: {str(e)}")
            return False
            
    async def auto_update_context(self) -> Dict[str, Any]:
        """
        Автоматическое обновление контекста на основе анализа данных.
        
        Returns:
            Dict[str, Any]: Результаты автоматического обновления
        """
        try:
            updates = {}
            
            # Анализируем тренды в LLM взаимодействиях
            if self.current_context.get('llm_interactions'):
                trends = self._analyze_llm_trends()
                updates['llm_trends'] = trends
                
            # Обновляем приоритеты на основе активности
            priority_updates = self._update_priorities()
            updates['priority_updates'] = priority_updates
            
            # Генерируем интеллектуальные подсказки
            suggestions = self._generate_intelligent_suggestions()
            updates['suggestions'] = suggestions
            
            # Обновляем контекст (используем синхронный метод)
            self.update_context(updates)
            
            return {
                'status': 'success',
                'updates_applied': len(updates),
                'trends_analyzed': bool(updates.get('llm_trends')),
                'priorities_updated': bool(updates.get('priority_updates')),
                'suggestions_generated': len(updates.get('suggestions', []))
            }
            
        except Exception as e:
            self.logger.error(f"Ошибка при автоматическом обновлении контекста: {str(e)}")
            return {
                'status': 'error',
                'error': str(e)
            }
            
    def _analyze_llm_trends(self) -> Dict[str, Any]:
        """
        Анализ трендов в LLM взаимодействиях.
        
        Returns:
            Dict[str, Any]: Результаты анализа трендов
        """
        interactions = self.current_context.get('llm_interactions', [])
        if not interactions:
            return {}
            
        # Анализируем последние 10 взаимодействий
        recent_interactions = interactions[-10:]
        
        # Анализ качества ответов
        quality_scores = [interaction.get('analysis', {}).get('quality_score', 0) 
                         for interaction in recent_interactions]
        avg_quality = sum(quality_scores) / len(quality_scores) if quality_scores else 0
        
        # Анализ релевантности
        relevance_scores = [interaction.get('analysis', {}).get('relevance_score', 0) 
                           for interaction in recent_interactions]
        avg_relevance = sum(relevance_scores) / len(relevance_scores) if relevance_scores else 0
        
        # Анализ тем
        all_topics = []
        for interaction in recent_interactions:
            topics = interaction.get('analysis', {}).get('semantic_analysis', {}).get('topics', [])
            all_topics.extend(topics)
            
        # Находим популярные темы
        topic_frequency = {}
        for topic in all_topics:
            topic_frequency[topic] = topic_frequency.get(topic, 0) + 1
            
        popular_topics = sorted(topic_frequency.items(), key=lambda x: x[1], reverse=True)[:5]
        
        return {
            'avg_quality_score': avg_quality,
            'avg_relevance_score': avg_relevance,
            'popular_topics': popular_topics,
            'interactions_count': len(recent_interactions),
            'trend_direction': 'improving' if avg_quality > 0.7 else 'stable' if avg_quality > 0.5 else 'declining'
        }
        
    def _update_priorities(self) -> Dict[str, Any]:
        """
        Обновление приоритетов на основе активности.
        
        Returns:
            Dict[str, Any]: Результаты обновления приоритетов
        """
        updates = {}
        
        # Анализируем активные задачи
        active_tasks = self.current_context.get('active_tasks', [])
        if active_tasks:
            # Повышаем приоритет задач, которые долго выполняются
            for task in active_tasks:
                if isinstance(task, dict) and 'created_at' in task:
                    # Логика обновления приоритета
                    pass
                    
        # Анализируем ключевые идеи
        key_ideas = self.current_context.get('key_ideas', [])
        if key_ideas:
            # Сортируем идеи по важности
            sorted_ideas = sorted(key_ideas, key=lambda x: x.get('importance', 0), reverse=True)
            updates['prioritized_ideas'] = sorted_ideas[:5]
            
        return updates
        
    def _generate_intelligent_suggestions(self) -> List[Dict[str, Any]]:
        """
        Генерация интеллектуальных подсказок на основе контекста.
        
        Returns:
            List[Dict[str, Any]]: Список подсказок
        """
        suggestions = []
        
        # Анализируем контекст для генерации подсказок
        context_analysis = self.analyze_context()
        
        # Подсказка на основе количества активных задач
        if context_analysis['active_tasks_count'] > 5:
            suggestions.append({
                'type': 'task_management',
                'priority': 'high',
                'message': 'Много активных задач. Рекомендуется приоритизация.',
                'action': 'prioritize_tasks'
            })
            
        # Подсказка на основе возраста контекста
        if context_analysis['context_age'] > 3600:  # больше часа
            suggestions.append({
                'type': 'context_refresh',
                'priority': 'medium',
                'message': 'Контекст устарел. Рекомендуется обновление.',
                'action': 'refresh_context'
            })
            
        # Подсказка на основе качества LLM ответов
        llm_trends = self._analyze_llm_trends()
        if llm_trends.get('trend_direction') == 'declining':
            suggestions.append({
                'type': 'llm_optimization',
                'priority': 'medium',
                'message': 'Качество ответов LLM снижается. Рекомендуется оптимизация.',
                'action': 'optimize_llm_prompts'
            })
            
        return suggestions
        
    async def get_context_summary(self) -> Dict[str, Any]:
        """
        Получение краткого резюме текущего контекста.
        
        Returns:
            Dict[str, Any]: Резюме контекста
        """
        analysis = self.analyze_context()
        llm_trends = self._analyze_llm_trends()
        
        return {
            'session_id': self.current_context.get('session_id'),
            'active_tasks': len(self.current_context.get('active_tasks', [])),
            'recent_actions': len(self.current_context.get('recent_actions', [])),
            'key_ideas': len(self.current_context.get('key_ideas', [])),
            'llm_interactions': analysis.get('llm_interactions_count', 0),
            'context_age_seconds': analysis.get('context_age', 0),
            'llm_quality_trend': llm_trends.get('trend_direction', 'unknown'),
            'popular_topics': llm_trends.get('popular_topics', [])[:3],
            'suggestions_count': len(self._generate_intelligent_suggestions())
        } 