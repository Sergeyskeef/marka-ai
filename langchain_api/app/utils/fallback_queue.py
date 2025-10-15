"""Утилиты для резервной очереди Graphiti."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from typing import Any, Optional

from redis.asyncio import Redis

from app.config import settings
from core.memory.graphiti_adapter import graphiti_adapter

logger = logging.getLogger(__name__)

FALLBACK_QUEUE_KEY = "graphiti:fallback_queue"
MAX_ATTEMPTS = 5
DEFAULT_POLL_INTERVAL = 5.0
DEFAULT_RETRY_DELAY = 5.0

_redis: Optional[Redis] = None


def _decode(raw: Any) -> Optional[dict[str, Any]]:
    if raw is None:
        return None
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    try:
        return json.loads(raw)
    except Exception:  # noqa: BLE001
        logger.exception("❌ Не удалось распарсить payload из fallback-очереди: %r", raw)
        return None


async def _get_redis() -> Optional[Redis]:
    """Лениво инициализирует клиент Redis."""
    global _redis
    if _redis is not None:
        return _redis

    try:
        client = Redis.from_url(settings.redis_url_with_auth)
        await client.ping()
        _redis = client
        logger.info("✅ Подключение к Redis для fallback очереди успешно")
    except Exception as exc:  # noqa: BLE001
        logger.warning("⚠️ Не удалось подключиться к Redis для fallback очереди: %s", exc)
        _redis = None
    return _redis


async def enqueue_payload(payload: dict[str, Any]) -> bool:
    """Добавляет payload в хвост fallback-очереди."""
    redis = await _get_redis()
    if not redis:
        logger.error("❌ Redis недоступен, не удалось добавить payload в fallback очередь")
        return False

    data = dict(payload)
    data.setdefault("attempts", 0)
    data.setdefault("enqueued_at", datetime.utcnow().isoformat())
    serialized = json.dumps(data, ensure_ascii=False)
    await redis.rpush(FALLBACK_QUEUE_KEY, serialized)
    logger.info(
        "🧵 Payload поставлен в fallback очередь Graphiti (session_id=%s, attempts=%s)",
        data.get("session_id"),
        data.get("attempts"),
    )
    return True


async def requeue_payload(payload: dict[str, Any]) -> bool:
    """Возвращает payload в очередь без сброса счётчиков попыток."""
    redis = await _get_redis()
    if not redis:
        logger.error("❌ Redis недоступен, не удалось переочередить payload")
        return False
    serialized = json.dumps(payload, ensure_ascii=False)
    await redis.rpush(FALLBACK_QUEUE_KEY, serialized)
    return True


async def pop_payload() -> Optional[dict[str, Any]]:
    """Забирает следующий payload из очереди."""
    redis = await _get_redis()
    if not redis:
        return None
    raw = await redis.lpop(FALLBACK_QUEUE_KEY)
    return _decode(raw)


async def persist_payload(payload: dict[str, Any]) -> bool:
    """Пытается пересохранить сообщения в Graphiti."""
    session_id = payload.get("session_id")
    user_id = payload.get("user_id")
    messages = payload.get("messages", [])

    if not session_id:
        logger.error("❌ Payload из fallback очереди не содержит session_id: %s", payload)
        return True  # Нечего сохранять, не зацикливаемся

    try:
        await graphiti_adapter.create_session(session_id=session_id, user_id=user_id)
        for message in messages:
            await graphiti_adapter.create_message(
                session_id=session_id,
                role=message.get("role", "assistant"),
                text=message.get("text", ""),
                metadata=message.get("metadata") or {},
            )
        logger.info("✅ Успешно сохранён payload из fallback очереди (session_id=%s)", session_id)
        return True
    except Exception as exc:  # noqa: BLE001
        payload["last_error"] = str(exc)
        logger.warning(
            "⚠️ Не удалось пересохранить payload из fallback очереди (session_id=%s): %s",
            session_id,
            exc,
        )
        return False


async def process_queue_once(*, retry_delay: float = 0.0, max_attempts: int = MAX_ATTEMPTS) -> bool:
    """Обрабатывает один элемент очереди. Возвращает True, если сохранение прошло успешно."""
    payload = await pop_payload()
    if not payload:
        return False

    success = await persist_payload(payload)
    if success:
        return True

    attempts = int(payload.get("attempts", 0)) + 1
    payload["attempts"] = attempts

    if attempts >= max_attempts:
        logger.error(
            "❌ Достигнут лимит попыток для payload (session_id=%s), удаляем из очереди",
            payload.get("session_id"),
        )
        return False

    if retry_delay > 0:
        await asyncio.sleep(retry_delay)

    requeued = await requeue_payload(payload)
    if not requeued:
        logger.error(
            "❌ Не удалось вернуть payload в fallback очередь (session_id=%s)",
            payload.get("session_id"),
        )
    return False


async def fallback_worker_loop(
    *,
    poll_interval: float = DEFAULT_POLL_INTERVAL,
    retry_delay: float = DEFAULT_RETRY_DELAY,
    max_attempts: int = MAX_ATTEMPTS,
) -> None:
    """Фоновый воркер, периодически обрабатывающий fallback очередь."""
    logger.info(
        "▶️ Запуск фонового воркера fallback очереди (poll_interval=%.1f, retry_delay=%.1f)",
        poll_interval,
        retry_delay,
    )
    while True:
        try:
            processed = await process_queue_once(retry_delay=retry_delay, max_attempts=max_attempts)
            if not processed:
                await asyncio.sleep(poll_interval)
        except Exception as exc:  # noqa: BLE001
            logger.exception("❌ Ошибка в фоновой задаче fallback очереди: %s", exc)
            await asyncio.sleep(poll_interval)


def reset_redis_client() -> None:
    """Сбрасывает кешированный Redis клиент (для тестов)."""
    global _redis
    _redis = None
