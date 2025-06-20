#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Реализация многоуровневой памяти для улучшения контекстуализации запросов.

Модель многоуровневой памяти:
1. Краткосрочная память: последние N сообщений текущей сессии
2. Среднесрочная память: ключевые факты о пользователе (имя, предпочтения)
3. Долгосрочная память: векторный поиск по всей истории диалогов

Эта архитектура позволяет избежать проблем с "загрязнением" контекста
старыми или нерелевантными сообщениями.
"""

import os
import logging
import json
import re
import traceback
import time
from typing import List, Dict, Any, Optional, Tuple, Union
from datetime import datetime
from langchain_api.memory.memory_manager import MemoryManager
from langchain_api.core.message_analyzer import MessageAnalyzer
from weaviate import Client
from weaviate.classes.config import Property, DataType, Configure
from weaviate.classes.query import Filter
from weaviate.util import generate_uuid5
from langchain_api.utils.openai_proxy_client import embeddings, chat_model

# Настройка логирования
log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'logs')
os.makedirs(log_dir, exist_ok=True)
log_path = os.path.join(log_dir, 'multi_layer_memory.log')
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_path),
        logging.StreamHandler()
    ]
)

class UserFact:
    """Класс для представления фактов о пользователе."""
    
    def __init__(self, user_id: str, key: str, value: str, confidence: float = 1.0,
                timestamp: Optional[str] = None):
        self.user_id = user_id
        self.key = key
        self.value = value
        self.confidence = confidence  # уверенность в факте (0.0-1.0)
        self.timestamp = timestamp or datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
    
    def __str__(self) -> str:
        return f"{self.key}: {self.value} (confidence: {self.confidence:.2f})"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "key": self.key,
            "value": self.value,
            "confidence": self.confidence,
            "timestamp": self.timestamp
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'UserFact':
        return cls(
            user_id=data["user_id"],
            key=data["key"],
            value=data["value"],
            confidence=data.get("confidence", 1.0),
            timestamp=data.get("timestamp")
        )


class MultiLayerMemory:
    """
    Реализация многоуровневой памяти для хранения и извлечения диалоговой информации.
    
    Уровни памяти:
    1. Краткосрочная память - кэш последних сообщений сессии (в RAM)
    2. Среднесрочная память - факты о пользователе (в Weaviate)
    3. Долгосрочная память - вся история диалогов (в Weaviate)
    """
    
    SUMMARY_EVERY_N = 20  # Каждые N сообщений сохранять summary в Experience
    HISTORY_TURNS = 10   # 10 user-assistant pairs  (≈ 20 сообщений)

    def __init__(self, short_term_limit: int = 20):
        """
        Инициализация многоуровневой памяти.
        
        Args:
            short_term_limit: Максимальное количество сообщений в краткосрочной памяти
        """
        self.memory_manager = MemoryManager()
        self.short_term_memory = {}  # session_id -> List[Dict]
        self.short_term_limit = short_term_limit
        self._session_message_counters = {}  # session_id -> int
        self.message_analyzer = MessageAnalyzer()  # Анализатор сообщений
        self._ensure_user_facts_collection()
        
        logging.info("✅ Многоуровневая память инициализирована")
    
    def _ensure_user_facts_collection(self) -> None:
        """Проверяет наличие коллекции UserFacts и создает её при необходимости."""
        try:
            self.memory_manager._ensure_connected()
            
            # Проверяем существование коллекции UserFacts
            try:
                # Пытаемся получить коллекцию - если она существует, это не вызовет ошибку
                user_facts_collection = self.memory_manager.client.collections.get("UserFacts")
                logging.info("✅ Коллекция UserFacts уже существует")
            except Exception as e:
                logging.info("Создаем коллекцию UserFacts...")
                
                # Создаем коллекцию для фактов о пользователях
                properties = [
                    {
                        "name": "user_id",
                        "dataType": ["text"],
                        "description": "Уникальный идентификатор пользователя"
                    },
                    {
                        "name": "key", 
                        "dataType": ["text"],
                        "description": "Ключ факта (например, имя, возраст, предпочтения)",
                        "indexFilterable": True,
                        "indexSearchable": True
                    },
                    {
                        "name": "value",
                        "dataType": ["text"],
                        "description": "Значение факта",
                        "indexFilterable": True,
                        "indexSearchable": True
                    },
                    {
                        "name": "confidence",
                        "dataType": ["number"],
                        "description": "Уверенность в факте (0.0-1.0)"
                    },
                    {
                        "name": "timestamp",
                        "dataType": ["date"],
                        "description": "Время добавления или обновления факта"
                    }
                ]
                
                # Создаем коллекцию с помощью нового API
                user_facts_collection = self.memory_manager.client.collections.create(
                    name="UserFacts",
                    properties=properties,
                    vectorizer_config={"vectorizer": "text2vec-openai"}
                )
                
                logging.info(f"✅ Коллекция UserFacts успешно создана")
        except Exception as e:
            logging.error(f"❌ Ошибка при создании коллекции UserFacts: {e}")
            traceback.print_exc()
    
    def add_to_short_term(self, session_id: str, role: str, content: str) -> None:
        """
        Добавляет сообщение в краткосрочную память с анализом тональности и важности.
        
        Args:
            session_id: ID сессии (например, chat_id в Telegram)
            role: Роль отправителя ('user' или 'assistant')
            content: Текст сообщения
        """
        if session_id not in self.short_term_memory:
            self.short_term_memory[session_id] = []
        
        timestamp = datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
        
        # Анализируем сообщение
        analysis = self.message_analyzer.analyze_message(content, role)
        
        # Добавляем сообщение в краткосрочную память с метаданными анализа
        message_data = {
            "role": role,
            "content": content,
            "timestamp": timestamp,
            "analysis": analysis  # Добавляем результаты анализа
        }
        
        self.short_term_memory[session_id].append(message_data)
        
        # Ограничиваем размер краткосрочной памяти
        if len(self.short_term_memory[session_id]) > self.short_term_limit:
            self.short_term_memory[session_id].pop(0)
        
        # Счётчик сообщений для Experience
        if session_id not in self._session_message_counters:
            self._session_message_counters[session_id] = 0
        self._session_message_counters[session_id] += 1
        
        # Если достигли лимита — формируем summary и сохраняем в Experience
        if self._session_message_counters[session_id] % self.SUMMARY_EVERY_N == 0:
            summary = self._build_session_summary(session_id)
            if summary:
                try:
                    self.memory_manager.store_experience(
                        question="Session summary",
                        answer=summary,
                        memory_ids=None,
                        session_id=session_id
                    )
                    logging.info(f"✅ Сохранён summary в Experience для session_id: {session_id}")
                except Exception as e:
                    logging.error(f"❌ Ошибка при сохранении summary в Experience: {e}")
        
        logging.info(f"✅ Сообщение добавлено в краткосрочную память для session_id: {session_id}")
    
    def get_short_term_context(self, session_id: str) -> List[Dict[str, str]]:
        """
        Возвращает контекст краткосрочной памяти для указанной сессии.
        
        Args:
            session_id: ID сессии
            
        Returns:
            Список сообщений в формате для LLM
        """
        if session_id not in self.short_term_memory:
            return []
        
        # Конвертируем в формат для LLM, убирая метаданные анализа
        context = []
        for msg in self.short_term_memory[session_id]:
            # Извлекаем только основные поля для LLM
            llm_msg = {
                "role": msg["role"],
                "content": msg["content"],
                "timestamp": msg["timestamp"]
            }
            context.append(llm_msg)
        
        return context
    
    def save_user_fact(self, user_fact: UserFact) -> Optional[str]:
        """
        Сохраняет или обновляет факт о пользователе только если confidence >= 0.9.
        """
        if user_fact.confidence < 0.9:
            logging.info(f"Факт {user_fact.key} не сохранён: confidence={user_fact.confidence} < 0.9")
            return None
        try:
            self.memory_manager._ensure_connected()
            user_facts_collection = self.memory_manager.client.collections.get("UserFacts")
            # Новый синтаксис фильтрации
            filter_obj = Filter.all([
                Filter.by_property("user_id").equal(user_fact.user_id),
                Filter.by_property("key").equal(user_fact.key)
            ])
            result = user_facts_collection.query.fetch_objects(
                filters=filter_obj,
                limit=1
            )
            if result.objects:
                # Обновляем существующий факт
                existing_id = result.objects[0].uuid
                user_facts_collection.data.update(
                    uuid=existing_id,
                    properties=user_fact.to_dict()
                )
                return existing_id
            else:
                # Вставляем новый факт
                obj = user_facts_collection.data.insert(properties=user_fact.to_dict())
                return obj.uuid if obj else None
        except Exception as e:
            logging.error(f"Ошибка при сохранении факта о пользователе: {e}")
            return None
    
    def get_user_facts(self, user_id: str = None, confidence_threshold: float = 0.5) -> List[UserFact]:
        """
        Получает все факты из среднесрочной памяти с confidence выше порога (user_id не используется для фильтрации).
        Args:
            confidence_threshold: Порог уверенности (0.0-1.0)
        Returns:
            Список объектов UserFact
        """
        try:
            self.memory_manager._ensure_connected()
            user_facts_collection = self.memory_manager.client.collections.get("UserFacts")
            # Фильтруем только по confidence
            filter_obj = Filter.by_property("confidence").greater_than(confidence_threshold)
            result = user_facts_collection.query.fetch_objects(
                filters=filter_obj,
                limit=50  # Максимальное количество фактов
            )
            user_facts = []
            for obj in result.objects:
                props = obj.properties
                user_facts.append(UserFact(
                    user_id=props.get("user_id"),
                    key=props.get("key"),
                    value=props.get("value"),
                    confidence=props.get("confidence", 1.0),
                    timestamp=props.get("timestamp")
                ))
            logging.info(f"✅ Получено {len(user_facts)} фактов (user_id не используется для фильтрации)")
            return user_facts
        except Exception as e:
            logging.error(f"❌ Ошибка при получении фактов: {e}")
            return []
    
    def query_documents(self, query: str, limit: int = 3) -> List[Dict[str, Any]]:
        """
        Ищет документы, релевантные запросу.
        Args:
            query: Текст запроса
            limit: Максимальное количество документов для возврата
        Returns:
            Список документов в формате [{"text": "...", "filename": "..."}, ...]
        """
        try:
            logging.info(f"Поиск документов по запросу: '{query}'")
            self.memory_manager._ensure_connected()
            document_collection = self.memory_manager.client.collections.get("Document")
            documents = []

            # BM25 поиск (актуальный синтаксис)
            try:
                bm25_results = document_collection.query.bm25(
                    query=query,
                    limit=limit,
                    return_properties=["text", "filename"]
                )
                if bm25_results.objects:
                    for obj in bm25_results.objects:
                        if hasattr(obj, 'properties') and obj.properties and obj.properties.get("text"):
                            documents.append({
                                "text": obj.properties.get("text"),
                                "filename": obj.properties.get("filename", "Неизвестно")
                            })
                    logging.info(f"BM25 поиск вернул {len(documents)} документов")
            except Exception as bm25_error:
                logging.error(f"Ошибка при BM25 поиске документов: {bm25_error}")

            # Векторный поиск (актуальный синтаксис)
            if len(documents) < limit:
                try:
                    vector_results = document_collection.query.near_text(
                        query=query,
                        limit=limit,
                        return_properties=["text", "filename"]
                    )
                    if vector_results.objects:
                        existing_texts = {doc["text"] for doc in documents}
                        for obj in vector_results.objects:
                            if hasattr(obj, 'properties') and obj.properties:
                                text = obj.properties.get("text")
                                if text and text not in existing_texts:
                                    documents.append({
                                        "text": text,
                                        "filename": obj.properties.get("filename", "Неизвестно")
                                    })
                                    existing_texts.add(text)
                        logging.info(f"После векторного поиска всего найдено {len(documents)} документов")
                except Exception as vector_error:
                    logging.error(f"Ошибка при векторном поиске документов: {vector_error}")

            documents.sort(key=lambda x: len(x["text"]) if x["text"] else 0)
            return documents[:limit]
        except Exception as e:
            logging.error(f"❌ Ошибка при запросе документов: {e}")
            return []
    
    def extract_facts_from_dialogue(self, text: str, role: str) -> dict:
        """
        Извлекает факты о пользователе из диалога (например, имя).
        Только из текущего user-вопроса, с учетом отрицаний и границ слова.
        """
        if role != "user":
            return {}
        text_low = text.lower()
        if " не зовут" in text_low:
            return {}
        facts = []
        STOP_WORDS = {"зовут", "не", "нет", "спрашивал", "потрясающе", "да", "нету", "не знаю", "ничего"}
        try:
            # Новый паттерн для имени с границами слова
            match = re.search(r"\b(?:меня зовут|мо[её] имя)\s+([A-ЯЁA-Za-z\-]{3,})", text, flags=re.I)
            if match:
                name = match.group(1).capitalize()
                if name.lower() not in STOP_WORDS and name.isalpha() and 1 < len(name) < 32:
                    facts.append(UserFact(
                        user_id=role,
                        key="name",
                        value=name,
                        confidence=0.9
                    ))
                    logging.info(f"Извлечено имя пользователя из приветствия: {name}")
                else:
                    logging.warning(f"Имя не прошло валидацию: '{name}'")
            return facts
        except Exception as e:
            logging.error(f"[DEBUG] Ошибка при извлечении фактов из диалога: {e}")
            return []
    
    def save_dialogue(self, question: str, answer: str, session_id: str, needs_reflection: bool = False, rubric_score: int = None, rubric_summary: str = None, rubric_justification: str = None) -> Tuple[Optional[str], Optional[str]]:
        """
        Сохраняет диалог во все уровни памяти с поддержкой RUBRIC-полей.
        """
        try:
            self.add_to_short_term(session_id, "user", question)
            self.add_to_short_term(session_id, "assistant", answer)
            facts = self.extract_facts_from_dialogue(question, "user")
            for fact in facts:
                fact_id = self.save_user_fact(fact)
                if fact_id:
                    logging.info(f"✅ Сохранен факт: {fact.key} = {fact.value} (user_id: {fact.user_id})")
                    logging.info(f"Сохранен факт для пользователя {session_id}: {fact.key} = {fact.value} (confidence: {fact.confidence})")
            timestamp = datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
            # Сохраняем вопрос
            try:
                question_id = self.memory_manager.add_message(
                    sender="user",
                    message=question,
                    timestamp=timestamp,
                    importance=0.5,
                    session_id=session_id,
                    needs_reflection=needs_reflection,
                    rubric_score=rubric_score,
                    rubric_summary=rubric_summary,
                    rubric_justification=rubric_justification
                )
                logging.info(f"✅ Вопрос сохранен в долгосрочную память (session_id: {session_id})")
            except Exception as e:
                logging.error(f"❌ Ошибка при сохранении вопроса: {e}")
                question_id = None
            # Сохраняем ответ
            try:
                answer_id = self.memory_manager.add_message(
                    sender="assistant",
                    message=answer,
                    timestamp=timestamp,
                    importance=0.5,
                    session_id=session_id,
                    needs_reflection=needs_reflection,
                    rubric_score=rubric_score,
                    rubric_summary=rubric_summary,
                    rubric_justification=rubric_justification
                )
                logging.info(f"✅ Ответ сохранен в долгосрочную память (session_id: {session_id})")
            except Exception as e:
                logging.error(f"❌ Ошибка при сохранении ответа: {e}")
                answer_id = None
            try:
                combined_id = self.memory_manager.add_message(
                    sender="dialogue",
                    message=f"Q: {question}\nA: {answer}",
                    timestamp=timestamp,
                    importance=0.7,
                    session_id=session_id,
                    needs_reflection=needs_reflection,
                    rubric_score=rubric_score,
                    rubric_summary=rubric_summary,
                    rubric_justification=rubric_justification
                )
                logging.info(f"✅ Сохранен комбинированный диалог Q/A (session_id: {session_id})")
            except Exception as e:
                logging.error(f"❌ Ошибка при сохранении комбинированного диалога: {e}")
            return question_id, answer_id
        except Exception as e:
            logging.error(f"❌ Ошибка при сохранении диалога: {e}")
            traceback.print_exc()
            return None, None
    
    def build_context(self, session_id: str, current_question: str):
        """
        Возвращает список сообщений для LLM с улучшенным анализом контекста:
          system-prompt
          ≤ HISTORY_TURNS пар [assistant, user]   (хронологически)
          + финальный текущий user-вопрос
        
        Улучшенная дедупликация:
        - Проверка на дубликаты по содержанию
        - Фильтрация слишком коротких сообщений
        - Сохранение контекстной последовательности
        - Анализ тональности и важности
        - Автоматическое архивирование старых диалогов
        """
        # 1) все прошлые сообщения в хронологическом порядке
        chronological = [m for m in self.get_short_term_context(session_id) if m["role"] in {"user", "assistant"}]
        chronological.append({"role": "user", "content": current_question})

        # 2) Анализируем контекст разговора
        context_analysis = self.message_analyzer.analyze_conversation_context(chronological)
        logging.info(f"Анализ контекста: тональность={context_analysis['overall_sentiment']}, "
                    f"важность={context_analysis['conversation_importance']}, "
                    f"вовлеченность={context_analysis['user_engagement']}")

        # 3) Дедупликация и фильтрация с учетом важности
        seen_contents = set()
        filtered_chronological = []
        
        for msg in chronological:
            content = msg["content"].strip()
            # Пропускаем слишком короткие сообщения (менее 3 символов)
            if len(content) < 3:
                continue
            # Пропускаем дубликаты по содержанию
            if content in seen_contents:
                continue
            # Пропускаем системные сообщения типа "ok", "да", "нет"
            if content.lower() in {"ok", "да", "нет", "хорошо", "понятно", "спасибо"}:
                continue
            
            # Проверяем важность сообщения (если есть анализ)
            if "analysis" in msg:
                importance = msg["analysis"].get("importance", "medium")
                # Сохраняем важные сообщения даже если они короткие
                if importance == "high" and len(content) >= 2:
                    seen_contents.add(content)
                    filtered_chronological.append(msg)
                    continue
            
            seen_contents.add(content)
            filtered_chronological.append(msg)

        # 4) Автоматическое архивирование старых диалогов
        if len(filtered_chronological) > self.HISTORY_TURNS * 2 + 5:  # Если слишком много сообщений
            self._archive_old_messages(session_id, filtered_chronological[:-self.HISTORY_TURNS * 2])

        # 5) идём с конца, собирая ПАРЫ User-Assistant
        pairs = []
        expecting = "assistant"         # сначала ищем ответ, затем вопрос
        for msg in reversed(filtered_chronological):
            if msg["role"] != expecting:
                continue
            pairs.append(msg)
            expecting = "user" if expecting == "assistant" else "assistant"
            if len(pairs) // 2 >= self.HISTORY_TURNS:
                break

        # pairs сейчас в обратном порядке → разворачиваем
        pairs.reverse()

        # 6) формируем финальный payload
        messages = [{"role": "system", "content": "You are a helpful assistant."}]
        # summary отключён → не добавляем
        messages.extend(pairs)
        # последний элемент — всегда текущий вопрос
        logging.debug("📌 current user question: %s", current_question)
        messages.append({"role": "user", "content": current_question})
        
        logging.info(f"Построен контекст: {len(pairs)} пар сообщений, {len(messages)} всего сообщений")
        return messages
    
    def _archive_old_messages(self, session_id: str, old_messages: List[Dict]) -> None:
        """
        Архивирует старые сообщения в долгосрочную память.
        
        Args:
            session_id: ID сессии
            old_messages: Список старых сообщений для архивирования
        """
        try:
            if not old_messages:
                return
            
            # Группируем сообщения по парам user-assistant
            message_pairs = []
            current_pair = []
            
            for msg in old_messages:
                current_pair.append(msg)
                if len(current_pair) == 2:
                    message_pairs.append(current_pair)
                    current_pair = []
            
            # Архивируем каждую пару
            for pair in message_pairs:
                if len(pair) == 2 and pair[0]["role"] == "user" and pair[1]["role"] == "assistant":
                    question = pair[0]["content"]
                    answer = pair[1]["content"]
                    
                    # Анализируем важность для определения приоритета архивирования
                    question_analysis = pair[0].get("analysis", {})
                    answer_analysis = pair[1].get("analysis", {})
                    
                    importance = max(
                        question_analysis.get("importance", "medium"),
                        answer_analysis.get("importance", "medium")
                    )
                    
                    # Архивируем только важные диалоги
                    if importance in ["high", "medium"]:
                        self.memory_manager.add_message(
                            sender="user",
                            message=question,
                            timestamp=pair[0]["timestamp"],
                            importance=0.7 if importance == "high" else 0.5,
                            session_id=session_id
                        )
                        self.memory_manager.add_message(
                            sender="assistant", 
                            message=answer,
                            timestamp=pair[1]["timestamp"],
                            importance=0.7 if importance == "high" else 0.5,
                            session_id=session_id
                        )
            
            logging.info(f"Заархивировано {len(message_pairs)} пар сообщений для сессии {session_id}")
            
        except Exception as e:
            logging.error(f"Ошибка при архивировании сообщений: {e}")

    def clear_short_term_memory(self, session_id: str) -> None:
        """
        Очищает краткосрочную память для указанной сессии.
        
        Args:
            session_id: ID сессии
        """
        if session_id in self.short_term_memory:
            self.short_term_memory.pop(session_id)
            logging.info(f"✅ Краткосрочная память очищена для session_id: {session_id}") 

    def _build_session_summary(self, session_id: str) -> str:
        """Summary временно отключён: возвращаем пустую строку."""
        return ""

    def add_message(self, *args, **kwargs):
        return self.memory_manager.add_message(*args, **kwargs)

def get_session_summary(session_id: str) -> str | None:
    """Однострочное LLM‑резюме последних сообщений пользователя."""
    try:
        msgs = MultiLayerMemory().get_short_term_context(session_id)
        if len(msgs) < 3:
            return None

        from langchain.chains.summarize import load_summarize_chain

        chain = load_summarize_chain(
            chat_model(model="gpt-4.1-mini", temperature=0),
            chain_type="map_reduce",
        )
        summary = chain.run([m["content"] for m in msgs])
        # убираем возможные префиксы "user: ..." / "assistant: ..."
        summary = re.sub(r"^(user|assistant):", "", summary, flags=re.I).strip()
        return summary if len(summary.split()) > 3 else None
    except Exception:
        return None

# ---------------- helper ----------------

NAME_RE = r"\b(?:меня зовут|мо[её] имя)\s+([A-ЯЁA-Za-z\-]{3,})"
PROF_RE = r"\bя\s+(?:—|-)?\s*([A-ЯЁA-Za-z]{4,})" 

if __name__ == "__main__":
    # ... существующий код ...
    logging.shutdown() 