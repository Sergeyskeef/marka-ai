# Mark AI — LangChain API

## Кратко
- Приложение: FastAPI (`app`), Telegram‑бот (`bot`), Redis, Graphiti.
- Модель: `gpt-4.1-mini` (по умолчанию), температура по умолчанию `0.4`.
- Стриминг: выключен (флаг `USE_STREAMED_CHAT=false`).
- История: хранится в Redis по `user_id` (ключи `user_history:{user_id}`), подгружается при старте диалога.
- Промпты: хранение в `/app/data/prompts`, авто‑сидинг базовых шаблонов при пустом хранилище.

## Переменные окружения
- `OPENAI_API_KEY` — ключ OpenAI.
- `OPENAI_TEMPERATURE=0.4` — базовая температура.
- `REDIS_URL` (опционально) — по умолчанию `redis://redis:6379`.
- `REDIS_PASSWORD` — пароль Redis; если задан, используется `redis://:{REDIS_PASSWORD}@redis:6379`.
- `USE_STREAMED_CHAT=false` — стриминг отключен.
- `VERBOSITY_MODE=auto` — авто‑режим краткости: кратко по умолчанию, развёрнуто по запросу.

## Запуск (Docker Compose)
Из директории `langchain_api`:
```bash
# перезапуск сервисов
docker compose restart app bot

# здоровье API
curl -s http://localhost:8000/health
```

## Telegram‑бот
- Работает в синхронном режиме (без стрима).
- При ответе сообщения длиннее 4096 символов делятся на части.

## История диалогов
- При каждом ответе сохраняются два сообщения: `user` и `assistant`.
- Лимит in‑memory на пользователя: 100 сообщений; в Redis хранится больше (настраивается через `HISTORY_MAX_MESSAGES`).

## Промпт‑система
- Базовые промпты сидируются в `production` при пустом каталоге `/app/data/prompts`.
- Компоненты сохраняются в JSON с текстовыми ключами слоёв (`INSTRUCTIONS`, `USER_INFO`, ...).
- Внутри элементов поле `layer` — тоже строка.

## Проверка связи из контейнера бота
```bash
docker compose exec -T bot python - << 'PY'
import asyncio, httpx, os
base = os.getenv('APP_HOST','http://app:8000')
async def main():
    async with httpx.AsyncClient(base_url=base, timeout=20) as c:
        r = await c.post('/api/chat', json={'message':'ping','user_id':'310647615','context':{'mode':'chat'}})
        print(r.status_code, r.text[:200])
asyncio.run(main())
PY
```

## Изменения в этой версии
- Отключён стриминг (фиче‑флаг), добавлен безопасный ретрай без `temperature` для совместимости моделей.
- Исправлена сериализация промптов (enum → строковые ключи; даты через `default=str`).
- Восстановление/персист истории из Redis по `user_id`.
- Базовый промпт: добавлено самосознание проекта и авто‑режим краткости.
- Ограничение токенов/вызовов:
  - `LLM_CALLS_PER_REQUEST_LIMIT` — лимит LLM‑вызовов за один ответ (по умолчанию 10) с автоотчётом при достижении.
  - `PROGRESS_CHECKPOINT_CALLS` — ранний промежуточный отчёт после N вызовов без инструментов (по умолчанию 2).
  - `TOOL_CALLS_PER_REQUEST_LIMIT` — бюджет вызовов инструментов, которым управляет сама модель (по умолчанию 6).
  - Первый ход без инструментов: модель даёт краткий план, критерии результата и бюджет инструментов; дальше следует выполнение по бюджету.

## Фрактальная память и контекст (beta)
- `app/memory/fractal_graph.py` — upsert узлов с `scale/payload/motifs`, связи `SUPERSEDES/SUPPORTS/CAUSES`, `retrieve_context(query, scale, k)`.
- Инъекция «фрактального контекста» в системный промпт агента: релевантные факты/эпизоды под запрос (zoom‑attention).
- Миграция Neo4j: `migrations/neo4j/001_fractal_schema.cypher` (индексы/констрейнты по `id/type/scale`, индекс `rel.scale`).
- Планировщик (каркас): `app/agents/fractal/{budget.py,rules.py,planner.py,reap.py}`.
