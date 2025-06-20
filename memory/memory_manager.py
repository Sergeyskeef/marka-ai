import os
import requests
import logging
import time
import httpx
from datetime import datetime
from weaviate import WeaviateClient, ConnectionParams
from weaviate.classes.config import Property, DataType, Configure
from langchain_api.utils.openai_proxy_client import get_proxy_config, embeddings, chat_model
from weaviate.classes.query import Filter
import threading
from typing import Protocol, List, Dict, Any, Optional
import numpy as np
from functools import reduce
import json
import traceback
import sys
from weaviate import Client
from weaviate.util import generate_uuid5

# Настройка логирования
log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'logs')
os.makedirs(log_dir, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)

class MemoryClass(Protocol):
    def insert(self, data: Dict[str, Any]) -> str: ...
    def search(self, query: str, limit: int = 3) -> List[Dict[str, Any]]: ...
    def update(self, obj_id: str, data: dict) -> bool: ...
    def delete(self, obj_id: str) -> bool: ...
    def link(self, source_id: str, target_id: str) -> None: ...
    def snapshot(self) -> Dict[str, Any]: ...
    def to_dict(self) -> Dict[str, Any]: ...

class ExperienceMemoryWrapper:
    """
    Обёртка для коллекции Experience, реализующая MemoryClass-интерфейс.
    Использует существующий Weaviate-клиент и методы memory_manager.
    """
    def __init__(self, memory_manager):
        import logging
        logging.error(f"[ExperienceMemoryWrapper.__init__] type(memory_manager)={type(memory_manager)}, dir={dir(memory_manager)}")
        if not hasattr(memory_manager, 'memory_registry'):
            logging.error(f"[ExperienceMemoryWrapper.__init__] ПЕРЕДАН НЕВЕРНЫЙ ОБЪЕКТ: type={type(memory_manager)}, dir={dir(memory_manager)}")
        self.memory_manager = memory_manager
        self.collection = memory_manager.client.collections.get("Experience")

    def insert(self, data: Dict[str, Any]) -> str:
        # Ожидается: data = {"summary": ..., "source_ids": ..., "timestamp": ..., "session_id": ..., "elevated": ...}
        try:
            import logging
            logging.error(f"[ExperienceMemoryWrapper.insert] Вставляю data: {data}")
            if "elevated" not in data:
                data["elevated"] = False
            experience_id = self.collection.data.insert(properties=data)
            # После вставки — fetch по session_id и summary
            from weaviate.classes.query import Filter
            filters = Filter.by_property("session_id").equal(data.get("session_id")) & Filter.by_property("summary").equal(data.get("summary"))
            results = self.collection.query.fetch_objects(
                limit=3,
                filters=filters,
                return_properties=["summary", "session_id", "manual_elevate", "elevated"]
            ).objects
            logging.error(f"[ExperienceMemoryWrapper.insert] После insert fetch: {[getattr(obj, 'properties', obj) for obj in results]}")
            # После успешной вставки — проверяем, нужно ли запускать автоматизацию
            try:
                # Исправлено: не self.memory_manager.memory_manager, а self.memory_manager
                exp_wrapper = self
                new_exp_count = len(exp_wrapper.get_new_experiences(limit=10))
                if new_exp_count >= 5:
                    self.memory_manager.automate_experience_elevation_scenarios(trigger_n=5)
            except Exception as e:
                import logging, traceback, sys
                logging.error(f"[ExperienceMemoryWrapper] Ошибка при автозапуске automate_experience_elevation_scenarios: {e}")
                logging.error(f"[ExperienceMemoryWrapper] Локальные переменные: {locals()}")
                logging.error(f"[ExperienceMemoryWrapper] Стек вызова:\n{traceback.format_exc()}")
            return experience_id
        except Exception as e:
            import logging, traceback, sys
            logging.error(f"[ExperienceMemoryWrapper] Ошибка при insert: {e}")
            logging.error(f"[ExperienceMemoryWrapper] Локальные переменные: {locals()}")
            logging.error(f"[ExperienceMemoryWrapper] Стек вызова:\n{traceback.format_exc()}")
            return None

    def search(self, query: str, limit: int = 3, filter_by: dict = None, fallback_to_filter: bool = False) -> List[Dict[str, Any]]:
        try:
            filters = None
            if filter_by:
                for k, v in filter_by.items():
                    f = Filter.by_property(k).equal(v)
                    filters = f if filters is None else filters & f
            results = self.collection.query.near_text(
                query=query,
                limit=limit,
                filters=filters,
                return_properties=["summary", "source_ids", "timestamp", "session_id", "elevated"]
            ).objects
            results = [getattr(obj, 'properties', obj) for obj in results]
            if results or not fallback_to_filter or not filter_by:
                print(f"[DEBUG][search] near_text найдено: {len(results)} объектов")
                return results
            # Fallback: фильтр по полям
            from weaviate.classes.query import Filter
            filters = None
            for k, v in (filter_by or {}).items():
                f = Filter.by_property(k).equal(v)
                filters = f if filters is None else filters & f
            fetch = self.collection.query.fetch_objects(
                filters=filters,
                limit=limit,
                return_properties=["summary", "source_ids", "timestamp", "session_id", "elevated"]
            ).objects
            print(f"[DEBUG][search] fallback фильтр найдено: {len(fetch)} объектов")
            return [getattr(obj, 'properties', obj) for obj in fetch]
        except Exception as e:
            import logging
            logging.error(f"[ExperienceMemoryWrapper] Ошибка при search: {e}")
            return []

    def _fetch_objects_with_id(self, limit=100, filters=None, return_properties=None):
        # Универсальный метод для получения объектов с id через fetch_objects
        if return_properties is None:
            return_properties = ["summary", "source_ids", "timestamp", "session_id", "elevated"]
        # Убираем 'id' из return_properties, если вдруг он там есть
        return_properties = [p for p in return_properties if p != "id"]
        try:
            results = self.collection.query.fetch_objects(
                limit=limit,
                filters=filters,
                return_properties=return_properties
            ).objects
            out = []
            for obj in results:
                d = dict(getattr(obj, 'properties', obj))
                # id всегда берём из obj.uuid
                d["id"] = getattr(obj, 'uuid', None)
                out.append(d)
            return out
        except Exception as e:
            import logging
            logging.error(f"[DEBUG][_fetch_objects_with_id] Ошибка: {e}")
            return []

    def get_new_experiences(self, limit: int = 100, session_id: str = None) -> List[Dict[str, Any]]:
        # Возвращает все Experience с elevated: false, включая id (uuid) через GraphQL
        from weaviate.classes.query import Filter
        filters = Filter.by_property("elevated").equal(False)
        if session_id:
            filters = filters & Filter.by_property("session_id").equal(session_id)
        return self._fetch_objects_with_id(limit=limit, filters=filters, return_properties=["summary", "source_ids", "timestamp", "session_id", "elevated"])

    def mark_experiences_elevated(self, ids: list):
        import logging
        import time
        if not ids:
            logging.error("[mark_experiences_elevated] Пустой список id для обновления!")
            return []
        ids = [str(eid) for eid in ids]
        logging.error(f"[mark_experiences_elevated] Обновляю elevated=True для id: {ids}")
        updated_ids = []
        try:
            updated = 0
            for eid in ids:
                res = self.collection.data.update(str(eid), {"elevated": True})
                logging.error(f"[mark_experiences_elevated] update({eid}) => {res}")
                # Явно проверяем, что elevated обновился
                time.sleep(1)
                from weaviate.classes.query import Filter
                filters = Filter.by_id().contains_any([str(eid)])
                results = self.collection.query.fetch_objects(
                    limit=1,
                    filters=filters,
                    return_properties=["summary", "elevated", "session_id"]
                ).objects
                for obj in results:
                    d = getattr(obj, 'properties', obj)
                    logging.error(f"[mark_experiences_elevated] После update: id={eid}, elevated={d.get('elevated')}, ВСЕ ПОЛЯ: {d}")
                    if d.get('elevated') is not True:
                        logging.warning(f"[mark_experiences_elevated] ВНИМАНИЕ: elevated не обновился для id={eid}!")
                updated += 1
                updated_ids.append(eid)
            logging.error(f"[mark_experiences_elevated] Всего обновлено: {updated} из {len(ids)}")
            from weaviate.classes.query import Filter
            for attempt in range(3):
                time.sleep(6)
                filters = Filter.by_id().contains_any([str(eid) for eid in ids])
                results = self.collection.query.fetch_objects(
                    limit=len(ids),
                    filters=filters,
                    return_properties=["summary", "elevated", "session_id"]
                ).objects
                id_to_elevated = {str(getattr(obj, 'uuid', '')): getattr(obj, 'properties', obj).get('elevated', False) for obj in results}
                logging.error(f"[mark_experiences_elevated] elevated по id: {id_to_elevated}")
                if all(id_to_elevated.get(eid) is True for eid in ids):
                    break
                else:
                    logging.error(f"[mark_experiences_elevated] Не все объекты elevated=True, попытка {attempt+1}/3: {id_to_elevated}")
            results_false = self.collection.query.fetch_objects(
                limit=len(ids),
                filters=Filter.by_property("elevated").equal(False),
                return_properties=["summary", "elevated", "session_id"]
            ).objects
            logging.error(f"[mark_experiences_elevated] elevated=False объекты: {[getattr(obj, 'properties', obj) for obj in results_false]}")
        except Exception as e:
            logging.error(f"[mark_experiences_elevated] Ошибка: {e}")
        return updated_ids

    def link(self, source_id: str, target_id: str) -> None:
        # Для Experience пока не требуется явная связь, можно реализовать позже
        pass

    def snapshot(self) -> Dict[str, Any]:
        # Заглушка: возвращает все объекты коллекции (можно оптимизировать)
        try:
            results = self.collection.query.fetch_objects(limit=1000).objects
            return {"snapshot": [getattr(obj, 'properties', obj) for obj in results]}
        except Exception as e:
            import logging
            logging.error(f"[ExperienceMemoryWrapper] Ошибка при snapshot: {e}")
            return {"snapshot": []}

    def to_dict(self) -> Dict[str, Any]:
        return {"collection": "Experience"}

    def automate_experience_elevation_scenarios(self, batch_size: int = 100, trigger_n: int = 5):
        """
        Универсальная автоматизация подъёма опыта (Experience → Insight) по сценариям:
        - Повторяемость (кластеризация)
        - Ошибки (ключевые слова/rubric_score)
        - Успехи (ключевые слова/rubric_score)
        - Аномалии (outlier по embedding)
        - Ручной триггер (manual_elevate)
        """
        import logging
        logging.error(f"[automate_experience_elevation_scenarios] ВХОД: self={self}, type(self)={type(self)}")
        exp_wrapper = self.memory_manager.memory_registry.get("Experience")
        criticlog_wrapper = self.memory_manager.memory_registry.get("CriticLog")
        insight_wrapper = self.memory_manager.memory_registry.get("Insight")
        if not exp_wrapper or not insight_wrapper or not criticlog_wrapper:
            logging.error("[automate_experience_elevation_scenarios] Не найдены нужные обёртки!")
            return []
        new_exps = exp_wrapper.get_new_experiences(limit=batch_size)
        logging.error(f"[automate_experience_elevation_scenarios] Найдено Experience: {len(new_exps)}")
        # --- Повторяемость (кластеризация, как раньше) ---
        try:
            summaries = [e["summary"] for e in new_exps]
            embeddings_list = [embeddings.embed_query(s) for s in summaries]
        except Exception as e:
            logging.error(f"[automate_experience_elevation_scenarios] Ошибка при получении эмбеддингов: {e}")
            return []
        clusters = []
        used = set()
        threshold = 0.85
        for i, emb_i in enumerate(embeddings_list):
            if i in used:
                continue
            cluster = [i]
            for j, emb_j in enumerate(embeddings_list):
                if j != i and j not in used:
                    sim = np.dot(emb_i, emb_j) / (np.linalg.norm(emb_i) * np.linalg.norm(emb_j) + 1e-8)
                    if sim >= threshold:
                        cluster.append(j)
            if len(cluster) >= 2:
                clusters.append(cluster)
                used.update(cluster)
        # --- Ошибки, успехи, аномалии, ручной триггер ---
        error_keywords = ["ошибка", "fail", "exception", "critical"]
        success_keywords = ["успешно", "решено", "success", "solved"]
        error_exps, success_exps, outlier_exps, manual_exps = [], [], [], []
        # rubric_score threshold
        for e in new_exps:
            summ = (e.get("summary") or "").lower()
            score = e.get("rubric_score")
            if any(kw in summ for kw in error_keywords) or (score is not None and score < 0.5):
                error_exps.append(e)
            if any(kw in summ for kw in success_keywords) or (score is not None and score > 0.8):
                success_exps.append(e)
        # Аномалии (outlier по embedding)
        if embeddings_list:
            mean_emb = np.mean(embeddings_list, axis=0)
            dists = [np.linalg.norm(emb - mean_emb) for emb in embeddings_list]
            outlier_thr = np.mean(dists) + 2 * np.std(dists)
            for idx, dist in enumerate(dists):
                if dist > outlier_thr:
                    outlier_exps.append(new_exps[idx])
        # --- manual_elevate: отдельный fetch ---
        from weaviate.classes.query import Filter
        manual_filters = Filter.by_property("manual_elevate").equal(True) & Filter.by_property("elevated").equal(False)
        manual_objs = exp_wrapper._fetch_objects_with_id(limit=20, filters=manual_filters, return_properties=["summary", "source_ids", "timestamp", "session_id", "elevated", "manual_elevate"])
        import logging
        logging.error(f"[manual_elevate] manual_objs (fetch): {manual_objs}")
        manual_exps.extend(manual_objs)
        # --- Группируем и поднимаем ---
        elevated_ids = set()
        manual_elevate_ids = set([str(e.get("id")) for e in manual_exps if e.get("id")])
        elevated_manual = set()
        def elevate_and_log(exp_objs, reason):
            if not exp_objs:
                return
            import logging
            logging.error(f"[elevate_and_log] Причина: {reason}, количество объектов: {len(exp_objs)}")
            for e in exp_objs:
                logging.error(f"[elevate_and_log] Experience: id={e.get('id')}, session_id={e.get('session_id')}, summary={e.get('summary')}, elevated={e.get('elevated')}, rubric_score={e.get('rubric_score')}, manual_elevate={e.get('manual_elevate')}")
            cluster_summaries = "\n".join([e["summary"] for e in exp_objs])
            source_ids = []
            for e in exp_objs:
                if "source_ids" in e and isinstance(e["source_ids"], list):
                    source_ids.extend(e["source_ids"])
            criticlog_wrapper.insert({
                "action": "elevate_analyze",
                "details": f"{reason}: {cluster_summaries}",
                "timestamp": self._get_rfc3339_timestamp(),
                "session_id": exp_objs[0].get("session_id", ""),
                "status": "in_progress",
                "error_message": "",
                "source_ids": source_ids
            })
            critic_llm = chat_model(model="gpt-4.1-mini", temperature=0.2, max_tokens=512)
            critique = critic_llm.invoke(f"Проанализируй и сформулируй инсайт по этим случаям (причина: {reason}):\n{cluster_summaries}\nИнсайт:")
            insight_text = critique.content if hasattr(critique, 'content') else str(critique)
            session_ids = list({e.get('session_id') for e in exp_objs if e.get('session_id')})
            all_source_ids = list(set(source_ids + session_ids))
            logging.error(f"[elevate_and_log] Создаю Insight: insight='{insight_text[:80]}...', source_ids={all_source_ids}")
            insight_id = insight_wrapper.insert({
                "insight": insight_text,
                "source_ids": all_source_ids,
                "timestamp": self._get_rfc3339_timestamp(),
            })
            criticlog_wrapper.insert({
                "action": "insight_created",
                "details": f"Insight: {insight_text}",
                "timestamp": self._get_rfc3339_timestamp(),
                "session_id": exp_objs[0].get("session_id", ""),
                "status": "success",
                "error_message": "",
                "source_ids": source_ids
            })
            exp_ids = [str(e.get("id")) for e in exp_objs if e.get("id")]
            logging.error(f"[elevate_and_log] Поднимаю Experience: ids={exp_ids}")
            elevated = exp_wrapper.mark_experiences_elevated(exp_ids)
            logging.error(f"[elevate_and_log] Результат подъёма: elevated={elevated}")
            elevated_ids.update(elevated)
            # Если это manual_elevate — отмечаем
            for eid in exp_ids:
                if eid in manual_elevate_ids:
                    elevated_manual.add(eid)
        # Кластеризация (повторяемость)
        for cluster in clusters:
            exp_objs = [new_exps[idx] for idx in cluster]
            elevate_and_log(exp_objs, "repeat_cluster")
        # Ошибки
        elevate_and_log(error_exps, "error")
        # Успехи
        elevate_and_log(success_exps, "success")
        # Аномалии
        elevate_and_log(outlier_exps, "outlier")
        # Ручной триггер
        elevate_and_log(manual_exps, "manual_elevate")
        # Логируем все id для диагностики manual_elevate
        logging.error(f"[manual_elevate] manual_exps ids: {[str(e.get('id')) for e in manual_exps]}")
        logging.error(f"[manual_elevate] manual_elevate_ids: {manual_elevate_ids}")
        logging.error(f"[manual_elevate] elevated_manual: {elevated_manual}")
        not_elevated_manual = manual_elevate_ids - elevated_manual
        logging.error(f"[manual_elevate] not_elevated_manual: {not_elevated_manual}")
        # Гарантия: если manual_elevate Experience не был поднят — поднимаем явно
        if not_elevated_manual:
            logging.error(f"[automate_experience_elevation_scenarios] ВНИМАНИЕ: manual_elevate Experience не были подняты: {not_elevated_manual}. Поднимаем явно!")
            elevated = exp_wrapper.mark_experiences_elevated(list(not_elevated_manual))
            logging.error(f"[manual_elevate] Результат явного подъёма: {elevated}")
        return list(elevated_ids)

    def update(self, obj_id: str, data: dict) -> bool:
        try:
            self.collection.data.update(obj_id, data)
            return True
        except Exception as e:
            import logging
            logging.error(f"[ExperienceMemoryWrapper] Ошибка при update: {e}")
            return False

    def delete(self, obj_id: str) -> bool:
        try:
            self.collection.data.delete(obj_id)
            return True
        except Exception as e:
            import logging
            logging.error(f"[ExperienceMemoryWrapper] Ошибка при delete: {e}")
            return False

class InsightMemoryWrapper:
    """
    Обёртка для коллекции Insight, реализующая MemoryClass-интерфейс.
    """
    def __init__(self, memory_manager):
        self.memory_manager = memory_manager
        self.collection = memory_manager.client.collections.get("Insight")

    def insert(self, data: Dict[str, Any]) -> str:
        try:
            # Проверка на дубликаты по source_ids и session_id
            source_ids = set(data.get("source_ids") or [])
            session_id = data.get("session_id")
            # Ищем инсайты с теми же source_ids (или session_id)
            from weaviate.classes.query import Filter
            filters = []
            if source_ids:
                filters.append(Filter.by_property("source_ids").contains_any(list(source_ids)))
            if session_id:
                filters.append(Filter.by_property("session_id").equal(session_id))
            if filters:
                filter_obj = filters[0] if len(filters) == 1 else Filter.all(*filters)
                existing = self.collection.query.fetch_objects(filters=filter_obj, limit=10).objects
                existing = [getattr(obj, 'properties', obj) for obj in existing]
                for obj in existing:
                    # Сравниваем source_ids как множества
                    if set(obj.get("source_ids") or []) == source_ids:
                        return obj.get("id") or getattr(obj, 'uuid', None)
            insight_id = self.collection.data.insert(properties=data)
            return insight_id
        except Exception as e:
            print(f"[ERROR][Insight] insert: {e}")
            raise

    def search(self, query: str, limit: int = 3, filter_by: dict = None, fallback_to_filter: bool = False) -> List[Dict[str, Any]]:
        try:
            results = self.collection.query.near_text(
                query=query,
                limit=limit,
                return_properties=["insight", "source_ids", "timestamp"]
            ).objects
            results = [getattr(obj, 'properties', obj) for obj in results]
            found = False
            if filter_by:
                for r in results:
                    for k, v in filter_by.items():
                        if isinstance(v, list):
                            if any(val in r.get(k, []) for val in v):
                                found = True
                                break
                        else:
                            if r.get(k) == v:
                                found = True
                                break
                    if found:
                        break
            if found or not fallback_to_filter or not filter_by:
                print(f"[DEBUG][search][Insight] near_text найдено: {len(results)} объектов, found={found}")
                return results
            # fallback: фильтр по полям
            filters = []
            for k, v in (filter_by or {}).items():
                if k == "source_ids":
                    from weaviate.classes.query import Filter
                    filters.append(Filter.by_property(k).contains_any([v] if not isinstance(v, list) else v))
                else:
                    from weaviate.classes.query import Filter
                    filters.append(Filter.by_property(k).equal(v))
            if filters:
                from weaviate.classes.query import Filter
                filter_obj = filters[0] if len(filters) == 1 else Filter.all(*filters)
                filtered = self.collection.query.fetch_objects(filters=filter_obj, limit=limit).objects
                filtered = [getattr(obj, 'properties', obj) for obj in filtered]
                print(f"[DEBUG][search][Insight] fallback фильтр найдено: {len(filtered)} объектов")
                return filtered
            return []
        except Exception as e:
            print(f"[ERROR][search][Insight] {e}")
            return []

    def link(self, source_id: str, target_id: str) -> None:
        # Для Insight пока не требуется явная связь, можно реализовать позже
        pass

    def snapshot(self) -> Dict[str, Any]:
        # Возвращает все объекты коллекции (можно оптимизировать)
        try:
            results = self.collection.query.fetch_objects(limit=1000).objects
            return {"snapshot": [getattr(obj, 'properties', obj) for obj in results]}
        except Exception as e:
            import logging
            logging.error(f"[InsightMemoryWrapper] Ошибка при snapshot: {e}")
            return {"snapshot": []}

    def to_dict(self) -> Dict[str, Any]:
        return {"collection": "Insight"}

    def update(self, obj_id: str, data: dict) -> bool:
        try:
            self.collection.data.update(obj_id, data)
            return True
        except Exception as e:
            import logging
            logging.error(f"[InsightMemoryWrapper] Ошибка при update: {e}")
            return False

    def delete(self, obj_id: str) -> bool:
        try:
            self.collection.data.delete(obj_id)
            return True
        except Exception as e:
            import logging
            logging.error(f"[InsightMemoryWrapper] Ошибка при delete: {e}")
            return False

class MemoryMemoryWrapper:
    """
    Обёртка для коллекции Memory, реализующая MemoryClass-интерфейс.
    """
    def __init__(self, memory_manager):
        self.memory_manager = memory_manager
        self.collection = memory_manager.client.collections.get("Memory")

    def insert(self, data: Dict[str, Any]) -> str:
        try:
            memory_id = self.collection.data.insert(properties=data)
            return memory_id
        except Exception as e:
            print(f"[ERROR][Memory] insert: {e}")
            raise

    def search(self, query: str, limit: int = 3, filter_by: dict = None, fallback_to_filter: bool = False) -> List[Dict[str, Any]]:
        try:
            results = self.collection.query.near_text(
                query=query,
                limit=limit,
                return_properties=["sender", "message", "timestamp", "importance", "session_id"]
            ).objects
            results = [getattr(obj, 'properties', obj) for obj in results]
            found = False
            if filter_by:
                for r in results:
                    for k, v in filter_by.items():
                        if isinstance(v, list):
                            if any(val in r.get(k, []) for val in v):
                                found = True
                                break
                        else:
                            if r.get(k) == v:
                                found = True
                                break
                    if found:
                        break
            if found or not fallback_to_filter or not filter_by:
                print(f"[DEBUG][search][Memory] near_text найдено: {len(results)} объектов, found={found}")
                return results
            from weaviate.classes.query import Filter
            filters = []
            for k, v in (filter_by or {}).items():
                filters.append(Filter.by_property(k).equal(v))
            if filters:
                filter_obj = filters[0] if len(filters) == 1 else Filter.all(*filters)
                filtered = self.collection.query.fetch_objects(filters=filter_obj, limit=limit).objects
                filtered = [getattr(obj, 'properties', obj) for obj in filtered]
                print(f"[DEBUG][search][Memory] fallback фильтр найдено: {len(filtered)} объектов")
                return filtered
            return []
        except Exception as e:
            print(f"[ERROR][search][Memory] {e}")
            return []

    def link(self, source_id: str, target_id: str) -> None:
        pass

    def snapshot(self) -> Dict[str, Any]:
        try:
            results = self.collection.query.fetch_objects(limit=1000).objects
            return {"snapshot": [getattr(obj, 'properties', obj) for obj in results]}
        except Exception as e:
            import logging
            logging.error(f"[MemoryMemoryWrapper] Ошибка при snapshot: {e}")
            return {"snapshot": []}

    def to_dict(self) -> Dict[str, Any]:
        return {"collection": "Memory"}

    def update(self, obj_id: str, data: dict) -> bool:
        try:
            self.collection.data.update(obj_id, data)
            return True
        except Exception as e:
            import logging
            logging.error(f"[MemoryMemoryWrapper] Ошибка при update: {e}")
            return False

    def delete(self, obj_id: str) -> bool:
        try:
            self.collection.data.delete(obj_id)
            return True
        except Exception as e:
            import logging
            logging.error(f"[MemoryMemoryWrapper] Ошибка при delete: {e}")
            return False

class PersonaMemoryWrapper:
    """
    Обёртка для коллекции Persona, реализующая MemoryClass-интерфейс.
    """
    def __init__(self, memory_manager):
        self.memory_manager = memory_manager
        self.collection = memory_manager.client.collections.get("Persona")

    def insert(self, data: Dict[str, Any]) -> str:
        try:
            persona_id = self.collection.data.insert(properties=data)
            return persona_id
        except Exception as e:
            print(f"[ERROR][Persona] insert: {e}")
            raise

    def search(self, query: str, limit: int = 3, filter_by: dict = None, fallback_to_filter: bool = False) -> List[Dict[str, Any]]:
        try:
            results = self.collection.query.near_text(
                query=query,
                limit=limit,
                return_properties=["name", "description", "traits", "timestamp"]
            ).objects
            results = [getattr(obj, 'properties', obj) for obj in results]
            found = False
            if filter_by:
                for r in results:
                    for k, v in filter_by.items():
                        if isinstance(v, list):
                            if any(val in r.get(k, []) for val in v):
                                found = True
                                break
                        else:
                            if r.get(k) == v:
                                found = True
                                break
                    if found:
                        break
            if found or not fallback_to_filter or not filter_by:
                print(f"[DEBUG][search][Persona] near_text найдено: {len(results)} объектов, found={found}")
                return results
            from weaviate.classes.query import Filter
            filters = []
            for k, v in (filter_by or {}).items():
                filters.append(Filter.by_property(k).equal(v))
            if filters:
                filter_obj = filters[0] if len(filters) == 1 else Filter.all(*filters)
                filtered = self.collection.query.fetch_objects(filters=filter_obj, limit=limit).objects
                filtered = [getattr(obj, 'properties', obj) for obj in filtered]
                print(f"[DEBUG][search][Persona] fallback фильтр найдено: {len(filtered)} объектов")
                return filtered
            return []
        except Exception as e:
            print(f"[ERROR][search][Persona] {e}")
            return []

    def link(self, source_id: str, target_id: str) -> None:
        pass

    def snapshot(self) -> Dict[str, Any]:
        try:
            results = self.collection.query.fetch_objects(limit=1000).objects
            return {"snapshot": [getattr(obj, 'properties', obj) for obj in results]}
        except Exception as e:
            import logging
            logging.error(f"[PersonaMemoryWrapper] Ошибка при snapshot: {e}")
            return {"snapshot": []}

    def to_dict(self) -> Dict[str, Any]:
        return {"collection": "Persona"}

    def update(self, obj_id: str, data: dict) -> bool:
        try:
            self.collection.data.update(obj_id, data)
            return True
        except Exception as e:
            import logging
            logging.error(f"[PersonaMemoryWrapper] Ошибка при update: {e}")
            return False

    def delete(self, obj_id: str) -> bool:
        try:
            self.collection.data.delete(obj_id)
            return True
        except Exception as e:
            import logging
            logging.error(f"[PersonaMemoryWrapper] Ошибка при delete: {e}")
            return False

class UserFactsMemoryWrapper:
    """
    Обёртка для коллекции UserFacts, реализующая MemoryClass-интерфейс.
    """
    def __init__(self, memory_manager):
        self.memory_manager = memory_manager
        self.collection = memory_manager.client.collections.get("UserFacts")

    def insert(self, data: Dict[str, Any]) -> str:
        try:
            userfact_id = self.collection.data.insert(properties=data)
            return userfact_id
        except Exception as e:
            import logging
            logging.error(f"[UserFactsMemoryWrapper] Ошибка при insert: {e}")
            return None

    def search(self, query: str, limit: int = 3, filter_by: dict = None, fallback_to_filter: bool = False) -> List[Dict[str, Any]]:
        try:
            results = self.collection.query.near_text(
                query=query,
                limit=limit,
                return_properties=["user_id", "key", "value", "confidence", "timestamp"]
            ).objects
            results = [getattr(obj, 'properties', obj) for obj in results]
            found = False
            if filter_by:
                for r in results:
                    for k, v in filter_by.items():
                        if isinstance(v, list):
                            if any(val in r.get(k, []) for val in v):
                                found = True
                                break
                        else:
                            if r.get(k) == v:
                                found = True
                                break
                    if found:
                        break
            if found or not fallback_to_filter or not filter_by:
                print(f"[DEBUG][search][UserFacts] near_text найдено: {len(results)} объектов, found={found}")
                return results
            from weaviate.classes.query import Filter
            filters = []
            for k, v in (filter_by or {}).items():
                filters.append(Filter.by_property(k).equal(v))
            if filters:
                filter_obj = filters[0] if len(filters) == 1 else Filter.all(*filters)
                filtered = self.collection.query.fetch_objects(filters=filter_obj, limit=limit).objects
                filtered = [getattr(obj, 'properties', obj) for obj in filtered]
                print(f"[DEBUG][search][UserFacts] fallback фильтр найдено: {len(filtered)} объектов")
                return filtered
            return []
        except Exception as e:
            print(f"[ERROR][search][UserFacts] {e}")
            return []

    def link(self, source_id: str, target_id: str) -> None:
        pass

    def snapshot(self) -> Dict[str, Any]:
        try:
            results = self.collection.query.fetch_objects(limit=1000).objects
            return {"snapshot": [getattr(obj, 'properties', obj) for obj in results]}
        except Exception as e:
            import logging
            logging.error(f"[UserFactsMemoryWrapper] Ошибка при snapshot: {e}")
            return {"snapshot": []}

    def to_dict(self) -> Dict[str, Any]:
        return {"collection": "UserFacts"}

    def update(self, obj_id: str, data: dict) -> bool:
        try:
            self.collection.data.update(obj_id, data)
            return True
        except Exception as e:
            import logging
            logging.error(f"[UserFactsMemoryWrapper] Ошибка при update: {e}")
            return False

    def delete(self, obj_id: str) -> bool:
        try:
            self.collection.data.delete(obj_id)
            return True
        except Exception as e:
            import logging
            logging.error(f"[UserFactsMemoryWrapper] Ошибка при delete: {e}")
            return False

class ChatGPTMemoryWrapper:
    """
    Обёртка для коллекции ChatGPTMemory, реализующая MemoryClass-интерфейс.
    """
    def __init__(self, memory_manager):
        self.memory_manager = memory_manager
        self.collection = memory_manager.client.collections.get("ChatGPTMemory")

    def insert(self, data: Dict[str, Any]) -> str:
        try:
            chatgpt_id = self.collection.data.insert(properties=data)
            return chatgpt_id
        except Exception as e:
            import logging
            logging.error(f"[ChatGPTMemoryWrapper] Ошибка при insert: {e}")
            return None

    def search(self, query: str, limit: int = 3, filter_by: dict = None, fallback_to_filter: bool = False) -> List[Dict[str, Any]]:
        try:
            results = self.collection.query.near_text(
                query=query,
                limit=limit,
                return_properties=["text", "timestamp", "session_id"]
            ).objects
            results = [getattr(obj, 'properties', obj) for obj in results]
            found = False
            if filter_by:
                for r in results:
                    for k, v in filter_by.items():
                        if isinstance(v, list):
                            if any(val in r.get(k, []) for val in v):
                                found = True
                                break
                        else:
                            if r.get(k) == v:
                                found = True
                                break
                    if found:
                        break
            if found or not fallback_to_filter or not filter_by:
                print(f"[DEBUG][search][ChatGPTMemory] near_text найдено: {len(results)} объектов, found={found}")
                return results
            from weaviate.classes.query import Filter
            filters = []
            for k, v in (filter_by or {}).items():
                filters.append(Filter.by_property(k).equal(v))
            if filters:
                filter_obj = filters[0] if len(filters) == 1 else Filter.all(*filters)
                filtered = self.collection.query.fetch_objects(filters=filter_obj, limit=limit).objects
                filtered = [getattr(obj, 'properties', obj) for obj in filtered]
                print(f"[DEBUG][search][ChatGPTMemory] fallback фильтр найдено: {len(filtered)} объектов")
                return filtered
            return []
        except Exception as e:
            print(f"[ERROR][search][ChatGPTMemory] {e}")
            return []

    def link(self, source_id: str, target_id: str) -> None:
        pass

    def snapshot(self) -> Dict[str, Any]:
        try:
            results = self.collection.query.fetch_objects(limit=1000).objects
            return {"snapshot": [getattr(obj, 'properties', obj) for obj in results]}
        except Exception as e:
            import logging
            logging.error(f"[ChatGPTMemoryWrapper] Ошибка при snapshot: {e}")
            return {"snapshot": []}

    def to_dict(self) -> Dict[str, Any]:
        return {"collection": "ChatGPTMemory"}

    def update(self, obj_id: str, data: dict) -> bool:
        try:
            self.collection.data.update(obj_id, data)
            return True
        except Exception as e:
            import logging
            logging.error(f"[ChatGPTMemoryWrapper] Ошибка при update: {e}")
            return False

    def delete(self, obj_id: str) -> bool:
        try:
            self.collection.data.delete(obj_id)
            return True
        except Exception as e:
            import logging
            logging.error(f"[ChatGPTMemoryWrapper] Ошибка при delete: {e}")
            return False

class CriticLogMemoryWrapper:
    """
    Обёртка для коллекции CriticLog, реализующая MemoryClass-интерфейс.
    Использует существующий Weaviate-клиент и методы memory_manager.
    """
    def __init__(self, memory_manager):
        self.memory_manager = memory_manager
        self.collection = memory_manager.client.collections.get("CriticLog")

    def insert(self, data: Dict[str, Any]) -> str:
        try:
            log_id = self.collection.data.insert(properties=data)
            return log_id
        except Exception as e:
            import logging
            logging.error(f"[CriticLogMemoryWrapper] Ошибка при insert: {e}")
            return None

    def search(self, query: str, limit: int = 3, filter_by: dict = None, fallback_to_filter: bool = False) -> List[Dict[str, Any]]:
        try:
            # Если есть фильтр — всегда используем fetch_objects по полям
            if filter_by:
                from weaviate.classes.query import Filter
                filters = []
                for k, v in filter_by.items():
                    if k == "source_ids":
                        filters.append(Filter.by_property(k).contains_any([v] if not isinstance(v, list) else v))
                    else:
                        filters.append(Filter.by_property(k).equal(v))
                if len(filters) == 1:
                    filter_obj = filters[0]
                else:
                    filter_obj = reduce(lambda a, b: a & b, filters)
                filtered = self.collection.query.fetch_objects(filters=filter_obj, limit=limit).objects
                filtered = [getattr(obj, 'properties', obj) for obj in filtered]
                print(f"[DEBUG][search][CriticLog] fallback фильтр найдено: {len(filtered)} объектов")
                return filtered
            # Если фильтра нет — используем semsearch
            results = self.collection.query.near_text(
                query=query,
                limit=limit,
                return_properties=["action", "details", "timestamp", "session_id", "status", "error_message", "source_ids"]
            ).objects
            results = [getattr(obj, 'properties', obj) for obj in results]
            print(f"[DEBUG][search][CriticLog] near_text найдено: {len(results)} объектов")
            return results
        except Exception as e:
            print(f"[ERROR][search][CriticLog] {e}")
            return []

    def link(self, source_id: str, target_id: str) -> None:
        # Для CriticLog пока не требуется явная связь, можно реализовать позже
        pass

    def snapshot(self) -> Dict[str, Any]:
        try:
            results = self.collection.query.fetch_objects(limit=1000).objects
            return {"snapshot": [getattr(obj, 'properties', obj) for obj in results]}
        except Exception as e:
            import logging
            logging.error(f"[CriticLogMemoryWrapper] Ошибка при snapshot: {e}")
            return {"snapshot": []}

    def to_dict(self) -> Dict[str, Any]:
        return {"collection": "CriticLog"}

    def update(self, obj_id: str, data: dict) -> bool:
        try:
            self.collection.data.update(obj_id, data)
            return True
        except Exception as e:
            import logging
            logging.error(f"[CriticLogMemoryWrapper] Ошибка при update: {e}")
            return False

    def delete(self, obj_id: str) -> bool:
        try:
            self.collection.data.delete(obj_id)
            return True
        except Exception as e:
            import logging
            logging.error(f"[CriticLogMemoryWrapper] Ошибка при delete: {e}")
            return False

class SandboxSnapshotMemoryWrapper:
    """
    Обёртка для коллекции SandboxSnapshot (Weaviate). Поддерживает insert, search, restore, diff, list_snapshots.
    """
    def __init__(self, memory_manager):
        self.memory_manager = memory_manager
        self.collection = memory_manager.client.collections.get("SandboxSnapshot")

    def insert(self, data: Dict[str, Any]) -> str:
        """
        Сохраняет снапшот в коллекцию. Ожидает поля: snapshot_id, timestamp, session_id, object_refs, object_states, snapshot_type, meta
        """
        try:
            snapshot_id = data.get("snapshot_id") or str(datetime.now().timestamp())
            timestamp = data.get("timestamp") or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            session_id = data.get("session_id")
            object_refs = data.get("object_refs") or []
            object_states = data.get("object_states") or ""
            snapshot_type = data.get("snapshot_type") or "refs"
            meta = data.get("meta") or ""
            props = {
                "snapshot_id": snapshot_id,
                "timestamp": timestamp,
                "session_id": session_id,
                "object_refs": object_refs,
                "object_states": object_states,
                "snapshot_type": snapshot_type,
                "meta": meta
            }
            snapshot_uuid = self.collection.data.insert(properties=props)
            logging.info(f"[SandboxSnapshotMemoryWrapper] Сохранён snapshot: {snapshot_id} (uuid={snapshot_uuid})")
            # Логирование действия
            criticlog = self.memory_manager.memory_registry.get("CriticLog")
            if criticlog:
                criticlog.insert({
                    "action": "insert_snapshot",
                    "details": f"snapshot_id={snapshot_id}, session_id={session_id}, type={snapshot_type}",
                    "timestamp": timestamp,
                    "session_id": session_id,
                    "status": "success" if snapshot_uuid else "error",
                    "error_message": "" if snapshot_uuid else "insert failed",
                    "source_ids": object_refs
                })
            return snapshot_uuid
        except Exception as e:
            logging.error(f"[SandboxSnapshotMemoryWrapper] Ошибка при insert: {e}")
            return None

    def search(self, query: str = None, limit: int = 10, filter_by: dict = None) -> List[Dict[str, Any]]:
        """
        Ищет снапшоты по session_id или snapshot_id. Если query не задан — возвращает последние N снапшотов.
        """
        try:
            filters = None
            if filter_by:
                for k, v in filter_by.items():
                    f = Filter.by_property(k).equal(v)
                    filters = f if filters is None else filters & f
            elif query:
                # Поиск по snapshot_id или session_id
                filters = Filter.by_property("snapshot_id").like(f"*{query}*") | Filter.by_property("session_id").like(f"*{query}*")
            results = self.collection.query.fetch_objects(
                filters=filters,
                limit=limit,
                return_properties=["snapshot_id", "timestamp", "session_id", "object_refs", "object_states", "snapshot_type", "meta"]
            ).objects
            return [getattr(obj, 'properties', obj) for obj in results]
        except Exception as e:
            logging.error(f"[SandboxSnapshotMemoryWrapper] Ошибка при search: {e}")
            return []

    def list_snapshots(self, session_id: str = None, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Возвращает список снапшотов по session_id (или все, если не задан).
        """
        filter_by = {"session_id": session_id} if session_id else None
        return self.search(limit=limit, filter_by=filter_by)

    def restore(self, snapshot_id: str) -> Optional[Dict[str, Any]]:
        try:
            from weaviate.classes.query import Filter
            filters = Filter.by_property("snapshot_id").equal(snapshot_id)
            results = self.collection.query.fetch_objects(filters=filters, limit=1).objects
            if not results:
                logging.warning(f"[SandboxSnapshotMemoryWrapper] restore: snapshot {snapshot_id} не найден")
                criticlog = self.memory_manager.memory_registry.get("CriticLog")
                if criticlog:
                    criticlog.insert({
                        "action": "restore_snapshot",
                        "details": f"snapshot_id={snapshot_id}",
                        "timestamp": self.memory_manager._get_rfc3339_timestamp(),
                        "session_id": None,
                        "status": "error",
                        "error_message": "not found",
                        "source_ids": [snapshot_id]
                    })
                return None
            snapshot = results[0]
            snapshot_dict = getattr(snapshot, 'properties', snapshot)
            logging.info(f"[SandboxSnapshotMemoryWrapper] Восстановлен snapshot: {snapshot_id}")
            criticlog = self.memory_manager.memory_registry.get("CriticLog")
            if criticlog:
                criticlog.insert({
                    "action": "restore_snapshot",
                    "details": f"snapshot_id={snapshot_id}",
                    "timestamp": self.memory_manager._get_rfc3339_timestamp(),
                    "session_id": snapshot_dict.get("session_id"),
                    "status": "success",
                    "error_message": "",
                    "source_ids": [snapshot_id]
                })
            return snapshot_dict
        except Exception as e:
            logging.error(f"[SandboxSnapshotMemoryWrapper] Ошибка при restore: {e}")
            return None

    def diff(self, snapshot_id_1: str, snapshot_id_2: str) -> Dict[str, Any]:
        """
        Сравнивает два снапшота по их snapshot_id (diff по object_states).
        """
        try:
            snap1 = self.restore(snapshot_id_1)
            snap2 = self.restore(snapshot_id_2)
            if not snap1 or not snap2:
                # Логирование ошибки
                criticlog = self.memory_manager.memory_registry.get("CriticLog")
                if criticlog:
                    criticlog.insert({
                        "action": "diff_snapshots",
                        "details": f"{snapshot_id_1} vs {snapshot_id_2}",
                        "timestamp": self.memory_manager._get_rfc3339_timestamp(),
                        "session_id": None,
                        "status": "error",
                        "error_message": "Один из снапшотов не найден",
                        "source_ids": [snapshot_id_1, snapshot_id_2]
                    })
                return {"error": "Один из снапшотов не найден"}
            import json
            state1 = json.loads(snap1.get("object_states") or "{}")
            state2 = json.loads(snap2.get("object_states") or "{}")
            diff = {"added": {}, "removed": {}, "changed": {}}
            keys1, keys2 = set(state1.keys()), set(state2.keys())
            for k in keys1 - keys2:
                diff["removed"][k] = state1[k]
            for k in keys2 - keys1:
                diff["added"][k] = state2[k]
            for k in keys1 & keys2:
                if state1[k] != state2[k]:
                    diff["changed"][k] = {"from": state1[k], "to": state2[k]}
            # Логирование успеха
            criticlog = self.memory_manager.memory_registry.get("CriticLog")
            if criticlog:
                criticlog.insert({
                    "action": "diff_snapshots",
                    "details": f"{snapshot_id_1} vs {snapshot_id_2}",
                    "timestamp": self.memory_manager._get_rfc3339_timestamp(),
                    "session_id": None,
                    "status": "success",
                    "error_message": "",
                    "source_ids": [snapshot_id_1, snapshot_id_2]
                })
            return diff
        except Exception as e:
            logging.error(f"[SandboxSnapshotMemoryWrapper] Ошибка при diff: {e}")
            return {"error": str(e)}

    def link(self, source_id: str, target_id: str) -> None:
        # Для снапшотов не требуется явная связь
        pass

    def snapshot(self) -> Dict[str, Any]:
        """
        Возвращает все снапшоты (до 100 шт).
        """
        try:
            results = self.collection.query.fetch_objects(limit=100).objects
            return {"snapshot": [getattr(obj, 'properties', obj) for obj in results]}
        except Exception as e:
            logging.error(f"[SandboxSnapshotMemoryWrapper] Ошибка при snapshot: {e}")
            return {"snapshot": []}

    def to_dict(self) -> Dict[str, Any]:
        return {"collection": "SandboxSnapshot"}

    def update(self, obj_id: str, data: dict) -> bool:
        try:
            self.collection.data.update(obj_id, data)
            return True
        except Exception as e:
            import logging
            logging.error(f"[SandboxSnapshotMemoryWrapper] Ошибка при update: {e}")
            return False

    def delete(self, obj_id: str) -> bool:
        try:
            self.collection.data.delete(obj_id)
            return True
        except Exception as e:
            import logging
            logging.error(f"[SandboxSnapshotMemoryWrapper] Ошибка при delete: {e}")
            return False

class MemoryClassRegistry:
    """
    Реестр для всех MemoryClass-обёрток. Позволяет регистрировать, получать и перечислять обёртки по имени коллекции.
    """
    def __init__(self):
        self._registry = {}

    def register(self, name: str, wrapper: MemoryClass):
        self._registry[name] = wrapper

    def get(self, name: str) -> MemoryClass:
        return self._registry.get(name)

    def all(self) -> dict:
        return self._registry.copy()

class MemoryManager:
    """
    HTTP-реализация менеджера диалоговой памяти для Weaviate.
    Не требует ключей, использует анонимный доступ.
    """

    def __init__(self, max_retries=3, retry_delay=2):
        self.client = None
        # Создаем HTTP клиент БЕЗ proxy для Weaviate
        self.http_client = httpx.Client()
        
        self.connection_params = ConnectionParams.from_params(
            http_host=os.getenv("WEAVIATE_HTTP_HOST", "weaviate"),
            http_port=int(os.getenv("WEAVIATE_HTTP_PORT", "8080")),
            http_secure=False,
            grpc_host=os.getenv("WEAVIATE_GRPC_HOST", "weaviate"),
            grpc_port=int(os.getenv("WEAVIATE_GRPC_PORT", "50051")),
            grpc_secure=False
        )
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self._initialize_connection()

        self.docs = None
        self.mem_col = None
        self.exp_col = None
        self.ins_col = None

        # После подключения и ensure_all_classes — инициализируем коллекции
        self._init_collections()

        self.chatgpt_memory = ChatGPTMemory(self.client)

        # === MemoryClassRegistry ===
        self.memory_registry = MemoryClassRegistry()
        self.memory_registry.register("Experience", ExperienceMemoryWrapper(self))
        self.memory_registry.register("Insight", InsightMemoryWrapper(self))
        self.memory_registry.register("Memory", MemoryMemoryWrapper(self))
        self.memory_registry.register("Persona", PersonaMemoryWrapper(self))
        self.memory_registry.register("UserFacts", UserFactsMemoryWrapper(self))
        self.memory_registry.register("ChatGPTMemory", ChatGPTMemoryWrapper(self))
        self.memory_registry.register("CriticLog", CriticLogMemoryWrapper(self))
        self.memory_registry.register("SandboxSnapshot", SandboxSnapshotMemoryWrapper(self))

    def _initialize_connection(self):
        """Инициализирует подключение к Weaviate с повторными попытками."""
        if self.client is not None:
            try:
                self.client.close()
            except:
                pass

        logging.info("⏳ Попытка подключения к Weaviate...")

        for attempt in range(self.max_retries):
            try:
                self.client = WeaviateClient(self.connection_params)
                self.client.connect()
                logging.info("✅ Успешное подключение к Weaviate")
                break
            except Exception as e:
                if attempt < self.max_retries - 1:
                    logging.warning(f"Попытка {attempt + 1}/{self.max_retries} подключения к Weaviate не удалась: {e}")
                    time.sleep(self.retry_delay)
                else:
                    logging.error(f"Не удалось подключиться к Weaviate после {self.max_retries} попыток: {e}")
                    raise

        self._ensure_all_classes()

    def _ensure_connected(self):
        """Проверяет подключение и переподключается при необходимости."""
        try:
            if self.client is None:
                self._initialize_connection()
                return
        except Exception as e:
            logging.error(f"Ошибка при проверке подключения: {e}")
            self._initialize_connection()
            
    def _get_rfc3339_timestamp(self):
        """Возвращает текущую дату в формате RFC3339 без дробной части."""
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    def _ensure_all_classes(self):
        """Создаёт все необходимые классы, если они ещё не добавлены."""
        self._ensure_connected()

        required_classes = {
            "Memory": {
                "description": "Диалоговая память: Q/A из чата и Telegram",
                "vectorizer": "text2vec-openai",
                "properties": [
                    Property(name="sender", data_type=DataType.TEXT),
                    Property(name="message", data_type=DataType.TEXT),
                    Property(name="timestamp", data_type=DataType.DATE),
                    Property(name="importance", data_type=DataType.NUMBER),
                    Property(name="session_id", data_type=DataType.TEXT),
                    Property(name="tags", data_type=DataType.TEXT_ARRAY),
                ]
            },
            "Experience": {
                "description": "Опыт (важные случаи, инсайты)",
                "vectorizer": "text2vec-openai",
                "properties": [
                    Property(name="summary", data_type=DataType.TEXT),
                    Property(name="source_ids", data_type=DataType.TEXT_ARRAY),
                    Property(name="timestamp", data_type=DataType.DATE),
                    Property(name="session_id", data_type=DataType.TEXT),
                    Property(name="elevated", data_type=DataType.BOOL),
                    Property(name="manual_elevate", data_type=DataType.BOOL),
                ]
            },
            "Document": {
                "description": "Документы и их содержимое",
                "vectorizer": "text2vec-openai",
                "properties": [
                    Property(name="text", data_type=DataType.TEXT),
                    Property(name="filename", data_type=DataType.TEXT),
                    Property(name="timestamp", data_type=DataType.DATE),
                    Property(name="content_hash", data_type=DataType.TEXT),
                ]
            },
            "Insight": {
                "description": "Инсайты и важные выводы",
                "vectorizer": "text2vec-openai",
                "properties": [
                    Property(name="insight", data_type=DataType.TEXT),
                    Property(name="source_ids", data_type=DataType.TEXT_ARRAY),
                    Property(name="timestamp", data_type=DataType.DATE),
                ]
            },
            "Persona": {
                "description": "Персонажи и их характеристики",
                "vectorizer": "text2vec-openai",
                "properties": [
                    Property(name="name", data_type=DataType.TEXT),
                    Property(name="description", data_type=DataType.TEXT),
                    Property(name="traits", data_type=DataType.TEXT),
                    Property(name="timestamp", data_type=DataType.DATE),
                ]
            }
        }

        for class_name, class_config in required_classes.items():
            try:
                if not self.client.collections.exists(class_name):
                    logging.info(f"Создаём класс {class_name}")
                    self.client.collections.create(
                        name=class_name,
                        description=class_config["description"],
                        vectorizer_config=Configure.Vectorizer.text2vec_openai(),
                        properties=class_config["properties"]
                    )
                    logging.info(f"✅ Класс {class_name} успешно создан")
                else:
                    logging.info(f"Класс {class_name} уже существует, пропускаем создание")
            except Exception as e:
                logging.error(f"Ошибка при создании класса {class_name}: {e}")

    def add_message(self, sender: str, message: str, timestamp: str = None, importance: float = 0.0, session_id: str = None, needs_reflection: bool = False, rubric_score: int = None, rubric_summary: str = None, rubric_justification: str = None):
        self._ensure_connected()
        memory_collection = self.client.collections.get("Memory")

        # Семантическая дедупликация
        try:
            vector = embeddings.embed_query(message)
            result = memory_collection.query.near_vector(
                vector,
                limit=1,
                certainty=0.95,
                return_properties=["sender", "message", "timestamp", "importance", "session_id"]
            )
            if result.objects:
                logging.info("Семантический дубликат найден, сообщение не сохраняется.")
                return None
        except Exception as e:
            logging.error(f"Ошибка при семантической дедупликации: {e}")
            # В случае ошибки продолжаем обычное сохранение

        # Если timestamp не передан, создаем его с правильным форматом RFC3339
        if timestamp is None:
            timestamp = self._get_rfc3339_timestamp()
        
        # Формируем объект для сохранения
        data_object = {
            "sender": sender,
            "message": message,
            "timestamp": timestamp,
            "importance": importance,
            "session_id": session_id or str(datetime.now().timestamp())
        }
        # Добавляем RUBRIC-поля, если они заданы
        if needs_reflection is not None:
            data_object["needs_reflection"] = needs_reflection
        if rubric_score is not None:
            data_object["rubric_score"] = rubric_score
        if rubric_summary is not None:
            data_object["rubric_summary"] = rubric_summary
        if rubric_justification is not None:
            data_object["rubric_justification"] = rubric_justification

        logging.info(f"[DEBUG] type(memory_collection)={type(memory_collection)}; type(memory_collection.data)={type(memory_collection.data)}")
        memory_collection.data.insert(properties=data_object)

    def query_relevant(self, query: str, top_k: int = 5):
        self._ensure_connected()
        try:
            memory_collection = self.client.collections.get("Memory")
            # Использование нового API для поиска
            result = memory_collection.query.near_text(
                query=query,
                limit=top_k,
                return_properties=["sender", "message", "timestamp", "importance", "session_id"]
            )
            return result.objects
        except Exception as e:
            logging.error(f"Ошибка при поиске в Memory: {e}")
            # Пробуем альтернативный поиск - простой фильтр по слову из запроса
            try:
                if len(query.split()) > 2:
                    # Возьмем самое длинное слово из запроса для фильтрации
                    search_word = max(query.split(), key=len)
                    if len(search_word) > 3:  # Игнорируем короткие слова
                        logging.info(f"Пробуем поиск по ключевому слову: {search_word}")
                        memory_collection = self.client.collections.get("Memory")
                        
                        # Используем правильный формат для фильтров
                        result = memory_collection.query.fetch_objects(
                            limit=top_k,
                            filters=Filter.by_property("message").like(f"*{search_word}*"),
                            return_properties=["sender", "message", "timestamp", "importance", "session_id"]
                        )
                        
                        if result.objects:
                            logging.info(f"Найдено {len(result.objects)} записей по ключевому слову")
                            return result.objects
            except Exception as inner_e:
                logging.error(f"Ошибка при альтернативном поиске: {inner_e}")
            
            return []

    def query_by_filter(self, filter_expr: str, limit: int = 10):
        """
        Универсальный поиск по фильтру через Weaviate SDK v4 Filter.
        filter_expr: строка вида 'field == "value"' или 'field like "*value*"'.
        """
        self._ensure_connected()
        memory_collection = self.client.collections.get("Memory")
        try:
            # Поддержка только простых фильтров вида 'field == "value"' или 'field like "*value*"'
            if "==" in filter_expr:
                field, value = filter_expr.split("==", 1)
                field = field.strip()
                value = value.strip().strip('"')
                filter_obj = Filter.by_property(field).equal(value)
            elif "like" in filter_expr:
                field, value = filter_expr.split("like", 1)
                field = field.strip()
                value = value.strip().strip('"')
                filter_obj = Filter.by_property(field).like(value)
            else:
                logging.error(f"Неверный формат фильтра: {filter_expr}. Ожидается 'поле == значение' или 'поле like значение'")
                return []
            result = memory_collection.query.fetch_objects(
                filters=filter_obj,
                limit=limit,
                return_properties=["sender", "message", "timestamp", "importance", "session_id"]
            )
            if result.objects:
                logging.info(f"Найдено {len(result.objects)} объектов по фильтру: {filter_expr}")
                return result.objects
            else:
                logging.info(f"Объекты по фильтру не найдены: {filter_expr}")
                return []
        except Exception as e:
            logging.error(f"Ошибка при поиске по фильтру '{filter_expr}': {e}")
            return []

    def save_dialogue(self, question: str, answer: str, session_id: str = None, needs_reflection: bool = False, rubric_score: int = None, rubric_summary: str = None, rubric_justification: str = None) -> None:
        try:
            self._ensure_connected()
            # Семантическая дедупликация для пары вопрос-ответ
            try:
                vector = embeddings.embed_query(f"{question}\n{answer}")
                memory_collection = self.client.collections.get("Memory")
                result = memory_collection.query.near_vector(
                    vector,
                    limit=1,
                    certainty=0.95,
                    return_properties=["sender", "message", "timestamp", "importance", "session_id"]
                )
                if result.objects:
                    logging.info("Семантический дубликат диалога найден, не сохраняем.")
                    return None, None
            except Exception as e:
                logging.error(f"Ошибка при семантической дедупликации диалога: {e}")
                # В случае ошибки продолжаем обычное сохранение

            # Форматируем дату в соответствии с RFC3339, убираем дробную часть секунд
            timestamp = self._get_rfc3339_timestamp()
            session_id = session_id or str(datetime.now().timestamp())
            memory_collection = self.client.collections.get("Memory")
            
            logging.info(f"Сохранение диалога в память:")
            logging.info(f"Вопрос: {question[:50]}..." if len(question) > 50 else f"Вопрос: {question}")
            logging.info(f"Ответ: {answer[:50]}..." if len(answer) > 50 else f"Ответ: {answer}")
            
            try:
                # Сохраняем вопрос пользователя и ответ ассистента напрямую через insert (без batch)
                logging.info(f"[DEBUG] type(memory_collection)={type(memory_collection)}; type(memory_collection.data)={type(memory_collection.data)}")
                user_memory_id = memory_collection.data.insert(
                    properties={
                        "sender": "user",
                        "message": question,
                        "timestamp": timestamp,
                        "importance": 0.0,
                        "session_id": session_id,
                        "needs_reflection": needs_reflection,
                        "rubric_score": rubric_score,
                        "rubric_summary": rubric_summary,
                        "rubric_justification": rubric_justification
                    }
                )
                logging.info(f"[DEBUG] type(memory_collection)={type(memory_collection)}; type(memory_collection.data)={type(memory_collection.data)}")
                assistant_memory_id = memory_collection.data.insert(
                    properties={
                        "sender": "assistant",
                        "message": answer,
                        "timestamp": timestamp,
                        "importance": 0.0,
                        "session_id": session_id,
                        "needs_reflection": needs_reflection,
                        "rubric_score": rubric_score,
                        "rubric_summary": rubric_summary,
                        "rubric_justification": rubric_justification
                    }
                )
                logging.info(f"[DEBUG] type(memory_collection)={type(memory_collection)}; type(memory_collection.data)={type(memory_collection.data)}")
                # Проверяем, является ли вопрос важным
                important_keywords = ["важно", "запомни", "ошибка", "критично", "❗", "⚠️"]
                is_important = any(keyword in question.lower() for keyword in important_keywords)
                # Если вопрос важный, сохраняем в Experience
                if is_important:
                    self.store_experience(question, answer, [user_memory_id, assistant_memory_id], session_id)
                logging.info(f"✅ Диалог успешно сохранен: {session_id}")
                # Асинхронный запуск рефлексии, если требуется
                if needs_reflection:
                    threading.Thread(target=reflect_dialogue, args=(self, session_id, question, answer), daemon=True).start()
                return user_memory_id, assistant_memory_id
            except Exception as e:
                logging.error(f"❌ Ошибка при сохранении сообщений диалога: {e}")
                return None, None
        except Exception as e:
            logging.error(f"❌ Ошибка при сохранении диалога: {e}")
            return None, None
    
    def store_experience(self, question: str, answer: str, memory_ids=None, session_id=None) -> str:
        """
        Сохраняет важный диалог в Experience через MemoryClass-обёртку.
        """
        self._ensure_connected()
        timestamp = self._get_rfc3339_timestamp()
        source_ids = []
        if memory_ids is not None:
            if isinstance(memory_ids, list):
                source_ids = [str(x) for x in memory_ids]
            else:
                source_ids = [str(memory_ids)]
        summary = f"Q: {question}\nA: {answer}"
        try:
            wrapper = self.memory_registry.get("Experience")
            experience_id = wrapper.insert({
                "summary": summary,
                "source_ids": source_ids,
                "timestamp": timestamp,
                "session_id": session_id
            }) if wrapper else None
            logging.info(f"✅ Опыт успешно сохранен в Experience с ID: {experience_id}")
            return experience_id
        except Exception as e:
            logging.error(f"❌ Ошибка при сохранении опыта: {e}")
            return None
    
    def __del__(self):
        """Закрываем соединения при уничтожении объекта."""
        if self.client:
            try:
                self.client.close()
            except:
                pass
        
        if self.http_client:
            try:
                self.http_client.close()
            except:
                pass

    def retrieve_documents(self, query: str, k_core=4, k_mem=3, k_exp=3, k_ins=2, k_cgpt=3, snapshot_before=False, session_id=None) -> list:
        """
        Расширенный retrieval: объединяет результаты из всех классов памяти в нужном порядке.
        Если snapshot_before=True, делает снапшот перед поиском.
        """
        if snapshot_before and session_id:
            self.create_snapshot(session_id=session_id, object_types=["Memory", "Experience", "Insight", "Persona", "UserFacts", "ChatGPTMemory"], with_state=True, meta="auto snapshot before retrieval")
        self._ensure_connected()
        # Поиск через MemoryClass-обёртки
        docs = self.memory_registry.get("Document")
        mem = self.memory_registry.get("Memory")
        exp = self.memory_registry.get("Experience")
        ins = self.memory_registry.get("Insight")
        cgpt = self.memory_registry.get("ChatGPTMemory")
        # Document (глобальный)
        try:
            doc_sem = docs.search(query, limit=k_core) if docs else []
        except Exception as e:
            doc_sem = []
            logging.error(f"Ошибка search по Document: {e}")
        # Memory
        try:
            mem_res = mem.search(query, limit=k_mem) if mem else []
        except Exception as e:
            mem_res = []
            logging.error(f"Ошибка search по Memory: {e}")
        # Experience
        try:
            exp_res = exp.search(query, limit=k_exp) if exp else []
        except Exception as e:
            exp_res = []
            logging.error(f"Ошибка search по Experience: {e}")
        # Insight
        try:
            ins_res = ins.search(query, limit=k_ins) if ins else []
        except Exception as e:
            ins_res = []
            logging.error(f"Ошибка search по Insight: {e}")
        # ChatGPTMemory
        try:
            cgpt_res = cgpt.search(query, limit=k_cgpt) if cgpt else []
        except Exception as e:
            cgpt_res = []
            logging.error(f"Ошибка search по ChatGPTMemory: {e}")
        # Краткосрочная память (если реализована как self.stm)
        stm = getattr(self, 'stm', [])
        # Объединяем и удаляем дубликаты в нужном порядке
        ordered = list(stm) + list(doc_sem) + list(ins_res) + list(exp_res) + list(cgpt_res) + list(mem_res)
        def deduplicate(seq):
            seen = set()
            result = []
            for item in seq:
                uid = str(item)
                if uid not in seen:
                    seen.add(uid)
                    result.append(item)
            return result
        result = deduplicate(ordered)
        # Логируем retrieval-блок для отладки
        logging.info(f"[RETRIEVAL BLOCK] query='{query}'\n" +
            f"DOCUMENT: {len(doc_sem)} | INSIGHT: {len(ins_res)} | EXPERIENCE: {len(exp_res)} | CHATGPTMEMORY: {len(cgpt_res)} | MEMORY: {len(mem_res)}\n" +
            f"UIDs: {[str(x)[:32] for x in result]}")
        return result

    def _init_collections(self):
        """Инициализирует short-wrapper для основных коллекций."""
        try:
            self.docs = self.client.collections.get("Document")
            self.mem_col = self.client.collections.get("Memory")
            self.exp_col = self.client.collections.get("Experience")
            self.ins_col = self.client.collections.get("Insight")
            logging.info("✅ Коллекции Document, Memory, Experience, Insight инициализированы")
        except Exception as e:
            logging.error(f"Ошибка инициализации коллекций: {e}")

    def persona_snippet(self) -> str:
        """
        Возвращает краткое описание первой найденной Persona для подстановки в SYSTEM_PROMPT.
        """
        self._ensure_connected()
        try:
            persona_col = self.client.collections.get("Persona")
            result = persona_col.query.fetch_objects(limit=1, return_properties=["name", "description", "traits"])
            if result.objects:
                p = result.objects[0].properties
                name = p.get("name", "Персонаж")
                desc = p.get("description", "")
                traits = p.get("traits", "")
                snippet = f"{name}: {desc} (черты: {traits})"
                return snippet
            else:
                return None
        except Exception as e:
            logging.error(f"Ошибка при получении Persona: {e}")
            return None

    def query_documents(self, query: str, limit: int = 3):
        """
        Алиас для retrieve_documents для обратной совместимости с кодом retrieval.
        """
        return self.retrieve_documents(query, k_core=limit)

    def snapshot_all(self) -> dict:
        """
        Возвращает снапшоты всех коллекций памяти через MemoryClass-обёртки.
        """
        snapshots = {}
        for name in ["Experience", "Insight", "Memory", "Persona", "UserFacts", "ChatGPTMemory"]:
            wrapper = self.memory_registry.get(name)
            if wrapper:
                try:
                    snapshots[name] = wrapper.snapshot()
                except Exception as e:
                    import logging
                    logging.error(f"[snapshot_all] Ошибка при snapshot {name}: {e}")
                    snapshots[name] = {"snapshot": []}
        return snapshots

    def automate_experience_elevation_scenarios(self, batch_size: int = 100, trigger_n: int = 5):
        """
        Универсальная автоматизация подъёма опыта (Experience → Insight) по сценариям:
        - Повторяемость (кластеризация)
        - Ошибки (ключевые слова/rubric_score)
        - Успехи (ключевые слова/rubric_score)
        - Аномалии (outlier по embedding)
        - Ручной триггер (manual_elevate)
        """
        import logging
        logging.error(f"[automate_experience_elevation_scenarios] ВХОД: self={self}, type(self)={type(self)}")
        exp_wrapper = self.memory_registry.get("Experience")
        criticlog_wrapper = self.memory_registry.get("CriticLog")
        insight_wrapper = self.memory_registry.get("Insight")
        if not exp_wrapper or not insight_wrapper or not criticlog_wrapper:
            logging.error("[automate_experience_elevation_scenarios] Не найдены нужные обёртки!")
            return []
        new_exps = exp_wrapper.get_new_experiences(limit=batch_size)
        logging.error(f"[automate_experience_elevation_scenarios] Найдено Experience: {len(new_exps)}")
        # --- Повторяемость (кластеризация, как раньше) ---
        try:
            summaries = [e["summary"] for e in new_exps]
            embeddings_list = [embeddings.embed_query(s) for s in summaries]
        except Exception as e:
            logging.error(f"[automate_experience_elevation_scenarios] Ошибка при получении эмбеддингов: {e}")
            return []
        clusters = []
        used = set()
        threshold = 0.85
        for i, emb_i in enumerate(embeddings_list):
            if i in used:
                continue
            cluster = [i]
            for j, emb_j in enumerate(embeddings_list):
                if j != i and j not in used:
                    sim = np.dot(emb_i, emb_j) / (np.linalg.norm(emb_i) * np.linalg.norm(emb_j) + 1e-8)
                    if sim >= threshold:
                        cluster.append(j)
            if len(cluster) >= 2:
                clusters.append(cluster)
                used.update(cluster)
        # --- Ошибки, успехи, аномалии, ручной триггер ---
        error_keywords = ["ошибка", "fail", "exception", "critical"]
        success_keywords = ["успешно", "решено", "success", "solved"]
        error_exps, success_exps, outlier_exps, manual_exps = [], [], [], []
        # rubric_score threshold
        for e in new_exps:
            summ = (e.get("summary") or "").lower()
            score = e.get("rubric_score")
            if any(kw in summ for kw in error_keywords) or (score is not None and score < 0.5):
                error_exps.append(e)
            if any(kw in summ for kw in success_keywords) or (score is not None and score > 0.8):
                success_exps.append(e)
        # Аномалии (outlier по embedding)
        if embeddings_list:
            mean_emb = np.mean(embeddings_list, axis=0)
            dists = [np.linalg.norm(emb - mean_emb) for emb in embeddings_list]
            outlier_thr = np.mean(dists) + 2 * np.std(dists)
            for idx, dist in enumerate(dists):
                if dist > outlier_thr:
                    outlier_exps.append(new_exps[idx])
        # --- manual_elevate: отдельный fetch ---
        from weaviate.classes.query import Filter
        manual_filters = Filter.by_property("manual_elevate").equal(True) & Filter.by_property("elevated").equal(False)
        manual_objs = exp_wrapper._fetch_objects_with_id(limit=20, filters=manual_filters, return_properties=["summary", "source_ids", "timestamp", "session_id", "elevated", "manual_elevate"])
        import logging
        logging.error(f"[manual_elevate] manual_objs (fetch): {manual_objs}")
        manual_exps.extend(manual_objs)
        # --- Группируем и поднимаем ---
        elevated_ids = set()
        manual_elevate_ids = set([str(e.get("id")) for e in manual_exps if e.get("id")])
        elevated_manual = set()
        def elevate_and_log(exp_objs, reason):
            if not exp_objs:
                return
            import logging
            logging.error(f"[elevate_and_log] Причина: {reason}, количество объектов: {len(exp_objs)}")
            for e in exp_objs:
                logging.error(f"[elevate_and_log] Experience: id={e.get('id')}, session_id={e.get('session_id')}, summary={e.get('summary')}, elevated={e.get('elevated')}, rubric_score={e.get('rubric_score')}, manual_elevate={e.get('manual_elevate')}")
            cluster_summaries = "\n".join([e["summary"] for e in exp_objs])
            source_ids = []
            for e in exp_objs:
                if "source_ids" in e and isinstance(e["source_ids"], list):
                    source_ids.extend(e["source_ids"])
            criticlog_wrapper.insert({
                "action": "elevate_analyze",
                "details": f"{reason}: {cluster_summaries}",
                "timestamp": self._get_rfc3339_timestamp(),
                "session_id": exp_objs[0].get("session_id", ""),
                "status": "in_progress",
                "error_message": "",
                "source_ids": source_ids
            })
            critic_llm = chat_model(model="gpt-4.1-mini", temperature=0.2, max_tokens=512)
            critique = critic_llm.invoke(f"Проанализируй и сформулируй инсайт по этим случаям (причина: {reason}):\n{cluster_summaries}\nИнсайт:")
            insight_text = critique.content if hasattr(critique, 'content') else str(critique)
            session_ids = list({e.get('session_id') for e in exp_objs if e.get('session_id')})
            all_source_ids = list(set(source_ids + session_ids))
            logging.error(f"[elevate_and_log] Создаю Insight: insight='{insight_text[:80]}...', source_ids={all_source_ids}")
            insight_id = insight_wrapper.insert({
                "insight": insight_text,
                "source_ids": all_source_ids,
                "timestamp": self._get_rfc3339_timestamp(),
            })
            criticlog_wrapper.insert({
                "action": "insight_created",
                "details": f"Insight: {insight_text}",
                "timestamp": self._get_rfc3339_timestamp(),
                "session_id": exp_objs[0].get("session_id", ""),
                "status": "success",
                "error_message": "",
                "source_ids": source_ids
            })
            exp_ids = [str(e.get("id")) for e in exp_objs if e.get("id")]
            logging.error(f"[elevate_and_log] Поднимаю Experience: ids={exp_ids}")
            elevated = exp_wrapper.mark_experiences_elevated(exp_ids)
            logging.error(f"[elevate_and_log] Результат подъёма: elevated={elevated}")
            elevated_ids.update(elevated)
            # Если это manual_elevate — отмечаем
            for eid in exp_ids:
                if eid in manual_elevate_ids:
                    elevated_manual.add(eid)
        # Кластеризация (повторяемость)
        for cluster in clusters:
            exp_objs = [new_exps[idx] for idx in cluster]
            elevate_and_log(exp_objs, "repeat_cluster")
        # Ошибки
        elevate_and_log(error_exps, "error")
        # Успехи
        elevate_and_log(success_exps, "success")
        # Аномалии
        elevate_and_log(outlier_exps, "outlier")
        # Ручной триггер
        elevate_and_log(manual_exps, "manual_elevate")
        # Логируем все id для диагностики manual_elevate
        logging.error(f"[manual_elevate] manual_exps ids: {[str(e.get('id')) for e in manual_exps]}")
        logging.error(f"[manual_elevate] manual_elevate_ids: {manual_elevate_ids}")
        logging.error(f"[manual_elevate] elevated_manual: {elevated_manual}")
        not_elevated_manual = manual_elevate_ids - elevated_manual
        logging.error(f"[manual_elevate] not_elevated_manual: {not_elevated_manual}")
        # Гарантия: если manual_elevate Experience не был поднят — поднимаем явно
        if not_elevated_manual:
            logging.error(f"[automate_experience_elevation_scenarios] ВНИМАНИЕ: manual_elevate Experience не были подняты: {not_elevated_manual}. Поднимаем явно!")
            elevated = exp_wrapper.mark_experiences_elevated(list(not_elevated_manual))
            logging.error(f"[manual_elevate] Результат явного подъёма: {elevated}")
        return list(elevated_ids)

    @staticmethod
    def _json_safe(obj):
        import datetime
        if isinstance(obj, dict):
            return {k: MemoryManager._json_safe(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [MemoryManager._json_safe(v) for v in obj]
        elif isinstance(obj, datetime.datetime):
            return obj.isoformat()
        return obj

    def create_snapshot(self, session_id: str, object_types: list = None, with_state: bool = False, meta: str = "") -> str:
        import json
        object_types = object_types or ["Memory", "Experience", "Insight", "Persona", "UserFacts", "ChatGPTMemory"]
        timestamp = self._get_rfc3339_timestamp()
        snapshot_id = f"snap_{session_id}_{int(time.time())}"
        object_refs = []
        object_states = {}
        for name in object_types:
            wrapper = self.memory_registry.get(name)
            if wrapper:
                try:
                    objs = wrapper.snapshot().get("snapshot", [])
                    ids = [o.get("id") or o.get("uuid") for o in objs if o.get("id") or o.get("uuid")]
                    object_refs.extend([f"{name}:{oid}" for oid in ids])
                    if with_state:
                        object_states[name] = MemoryManager._json_safe(objs)
                except Exception as e:
                    logging.error(f"[create_snapshot] Ошибка snapshot {name}: {e}")
        snapshot_type = "hybrid" if with_state else "refs"
        object_states_json = json.dumps(object_states, ensure_ascii=False) if with_state else ""
        data = {
            "snapshot_id": snapshot_id,
            "timestamp": timestamp,
            "session_id": session_id,
            "object_refs": object_refs,
            "object_states": object_states_json,
            "snapshot_type": snapshot_type,
            "meta": meta
        }
        wrapper = self.memory_registry.get("SandboxSnapshot")
        snap_uuid = wrapper.insert(data) if wrapper else None
        logging.warning(f"[DEBUG][create_snapshot] snapshot_id={snapshot_id}, snap_uuid={snap_uuid}")
        # Логируем все snapshot_id в коллекции после вставки
        if wrapper:
            all_snaps = wrapper.list_snapshots(session_id=session_id, limit=10)
            logging.warning(f"[DEBUG][create_snapshot] Все snapshot_id в коллекции: {[s.get('snapshot_id') for s in all_snaps]}")
        criticlog = self.memory_registry.get("CriticLog")
        if criticlog:
            criticlog.insert({
                "action": "create_snapshot",
                "details": f"snapshot_id={snapshot_id}, session_id={session_id}, type={snapshot_type}",
                "timestamp": timestamp,
                "session_id": session_id,
                "status": "success" if snap_uuid else "error",
                "error_message": "" if snap_uuid else "insert failed",
                "source_ids": object_refs
            })
        return snapshot_id

    def restore_snapshot(self, snapshot_id: str) -> dict:
        wrapper = self.memory_registry.get("SandboxSnapshot")
        # DEBUG: логируем все snapshot_id перед поиском
        if wrapper:
            all_snaps = wrapper.list_snapshots(limit=10)
            logging.warning(f"[DEBUG][restore_snapshot] Все snapshot_id в коллекции: {[s.get('snapshot_id') for s in all_snaps]}")
        snap = wrapper.restore(snapshot_id) if wrapper else None
        criticlog = self.memory_registry.get("CriticLog")
        if criticlog:
            criticlog.insert({
                "action": "restore_snapshot",
                "details": f"snapshot_id={snapshot_id}",
                "timestamp": self._get_rfc3339_timestamp(),
                "session_id": snap.get("session_id") if snap else None,
                "status": "success" if snap else "error",
                "error_message": "" if snap else "not found",
                "source_ids": [snapshot_id]
            })
        return snap

    def list_snapshots(self, session_id: str = None, limit: int = 20) -> list:
        """
        Возвращает список снапшотов по session_id (или все).
        """
        wrapper = self.memory_registry.get("SandboxSnapshot")
        return wrapper.list_snapshots(session_id=session_id, limit=limit) if wrapper else []

    def diff_snapshots(self, snapshot_id_1: str, snapshot_id_2: str) -> dict:
        """
        Сравнивает два снапшота по их snapshot_id.
        """
        wrapper = self.memory_registry.get("SandboxSnapshot")
        diff = wrapper.diff(snapshot_id_1, snapshot_id_2) if wrapper else {"error": "no wrapper"}
        # Логируем действие
        criticlog = self.memory_registry.get("CriticLog")
        if criticlog:
            criticlog.insert({
                "action": "diff_snapshots",
                "details": f"{snapshot_id_1} vs {snapshot_id_2}",
                "timestamp": self._get_rfc3339_timestamp(),
                "session_id": None,
                "status": "success" if "error" not in diff else "error",
                "error_message": diff["error"] if "error" in diff else "",
                "source_ids": [snapshot_id_1, snapshot_id_2]
            })
        return diff

    def update(self, obj_id: str, data: dict) -> bool:
        try:
            self.collection.data.update(obj_id, data)
            return True
        except Exception as e:
            import logging
            logging.error(f"[MemoryMemoryWrapper] Ошибка при update: {e}")
            return False

    def delete(self, obj_id: str) -> bool:
        try:
            self.collection.data.delete(obj_id)
            return True
        except Exception as e:
            import logging
            logging.error(f"[MemoryMemoryWrapper] Ошибка при delete: {e}")
            return False

class ChatGPTMemory:
    """
    Класс для хранения и поиска ChatGPTMemory (отдельная память для retrieval).
    """
    def __init__(self, client):
        self.client = client
        self.collection = None
        self._ensure_collection()
    def _ensure_collection(self):
        try:
            if not self.client.collections.exists("ChatGPTMemory"):
                self.client.collections.create(
                    name="ChatGPTMemory",
                    description="Память для retrieval-блока ChatGPT",
                    vectorizer_config=Configure.Vectorizer.text2vec_openai(),
                    properties=[
                        Property(name="text", data_type=DataType.TEXT),
                        Property(name="timestamp", data_type=DataType.DATE),
                        Property(name="session_id", data_type=DataType.TEXT),
                    ]
                )
            self.collection = self.client.collections.get("ChatGPTMemory")
        except Exception as e:
            logging.error(f"Ошибка при создании/получении ChatGPTMemory: {e}")
    def insert(self, text: str, session_id: str = None):
        try:
            timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            self.collection.data.insert({
                "text": text,
                "timestamp": timestamp,
                "session_id": session_id
            })
        except Exception as e:
            logging.error(f"Ошибка при вставке в ChatGPTMemory: {e}")
    def search(self, query: str, limit: int = 3):
        try:
            return self.collection.query.near_text(query=query, limit=limit, return_properties=["text", "timestamp", "session_id"]).objects
        except Exception as e:
            logging.error(f"Ошибка при поиске в ChatGPTMemory: {e}")
            return []

    def update(self, obj_id: str, data: dict) -> bool:
        try:
            self.collection.data.update(obj_id, data)
            return True
        except Exception as e:
            import logging
            logging.error(f"[ChatGPTMemoryWrapper] Ошибка при update: {e}")
            return False

    def delete(self, obj_id: str) -> bool:
        try:
            self.collection.data.delete(obj_id)
            return True
        except Exception as e:
            import logging
            logging.error(f"[ChatGPTMemoryWrapper] Ошибка при delete: {e}")
            return False

def reflect_dialogue(memory_manager, session_id, question, answer):
    try:
        logging.info(f"[DEBUG] reflect_dialogue: type(memory_manager)={type(memory_manager)}")
        try:
            wrapper = memory_manager.memory_registry.get("Insight")
        except Exception as e:
            logging.error(f"[DEBUG] Ошибка при получении Insight wrapper: {e}")
            raise
        try:
            critic_llm = chat_model(model="gpt-4.1-mini", temperature=0.2, max_tokens=512)
            critique = critic_llm.invoke(f"Проанализируй ответ ассистента и сформулируй инсайт для самообучения ИИ.\nВопрос: {question}\nОтвет: {answer}\nИнсайт:")
            if wrapper:
                wrapper.insert({
                    "insight": critique.content if hasattr(critique, 'content') else str(critique),
                    "source_ids": [session_id]
                })
            logging.info(f"✅ Рефлексия выполнена для session_id={session_id}")
        except Exception as e:
            logging.error(f"[DEBUG] Ошибка при insert в Insight: {e}")
            raise
    except Exception as e:
        logging.error(f"❌ Ошибка при рефлексии: {e}")

if __name__ == "__main__":
    # ... существующий код ...
    logging.shutdown()

