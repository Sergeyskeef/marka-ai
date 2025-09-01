# Mark AI — система промптов

## Где хранятся промпты
- Диск внутри контейнера: `/app/data/prompts`
  - `production/` — боевые промпты (используются роутером)
  - `development/` — вспомогательные/локальные
- Кеш Redis (опционально). При недоступности Redis всё работает без него.

## Базовые промпты (production)
- `mark_base` — общий базовый промпт ассистента
- `mark_code_expert` — режим эксперта по коду (выше приоритет инструментов/примеров)
- `mark_learning_mode` — режим самообучения (REAP, метрики, инсайты)
- `mark_chat` — дружелюбный режим «просто поболтать» (смягчён стиль, минимум инструментов)

## Импорт из YAML
Файл: `langchain_api/prompts/prompts.yaml`
- При старте сервис импортирует разделы `chat`, `code`, `plan`, `test_mode` как отдельные промпты
- Импортер не создаёт дубликаты (проверка по имени)

## API промптов
- Список: `GET /prompts?environment=production`
- Получить один: `GET /prompts/{name}?environment=production`
- Создать: `POST /prompts` (см. модель в `app/api/prompts_api.py`)
- Продвинуть/откатить: `POST /prompts/{name}/promote` / `POST /prompts/{name}/rollback`

## Динамический роутер
- Выбор идёт по UCB (LinUCB) + лёгкие предпочтения по контексту:
  - `domain=technical` или `requires_tools` → склонность к `mark_code_expert`
  - обычные разговоры → `mark_chat`/`mark_base`
- При отсутствии кандидатов система автоматически сидирует базовые промпты (production)
- При любой ошибке в выборке срабатывает фолбэк: используется системный промпт агента

## Защита от ошибок
- Битые файлы/кеш игнорируются; приложение не падает
- Pydantic v2: используется `model_dump_json`/`model_validate_json`
- Метаданные памяти приводятся к `dict` перед отправкой в Graphiti

## Быстрые команды (в контейнере `app`)
```bash
# список промптов
python - << 'PY'
import requests, json
print(json.dumps(requests.get('http://localhost:8000/prompts?environment=production', timeout=15).json(), ensure_ascii=False, indent=2))
PY

# дерево хранилища
bash -lc 'find /app/data/prompts -maxdepth 2 -type f -name "*.json" -print'
```

## Где сохраняются файлы, которые создаёт Марк

- Базовая директория для файловых операций: `/app` (настраивается параметром `FILE_TOOLS_BASE_DIR` в `app/config.py`).
- Относительные пути (например, `reports/summary.md`) будут сохранены как `/app/reports/summary.md`.
- Папки создаются автоматически, если `create_dirs=True` (по умолчанию так в `write_file`).
- Разрешённые директории для инструментов: `/app` и `/sandbox`. `/workspace` отключён.

Примеры:

```bash
# Список файлов проекта
docker compose exec -T app python - << 'PY'
import asyncio, json
from app.agents.file_tools import list_files
print(asyncio.run(list_files(directory='.', recursive=False)))
PY

# Создание файла в проекте
docker compose exec -T app python - << 'PY'
import asyncio
from app.agents.file_tools import write_file
print(asyncio.run(write_file('notes/plan.md', '# План работ\n', create_dirs=True)))
PY
```
