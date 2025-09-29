# MemoryService — спецификация v0.1

## Контракт
```python
class MemoryService: 
    async def store(text: str, *, meta: dict | None = None) -> dict: ...
    async def retrieve(query: str, *, user_id: str, k: int = 10, filters: dict | None = None) -> list[dict]: ...
    async def hybrid_search(query: str, *, user_id: str, k: int = 10, filters: dict | None = None) -> list[dict]: ...
    async def consolidate(topic: str, *, window: int = 20) -> dict: ...  # свёртка эпизодов в инсайт/факт
    async def distill(node_ids: list[str], *, into: str = 'insight') -> dict: ...
    async def link(src_id: str, dst_id: str, rel: str, *, props: dict | None = None) -> dict: ...
    async def health() -> dict: ...
```

## Хуки
- `pre_store(text, meta) -> (text, meta)` — нормализация/редакция секретов.
- `post_store(node)` — инвалидация кеша, автосвязи Person/Project/Session.
- `post_retrieve(results)` — маркировка для xtrace (used_memory).
- `consolidate/distill` — простые правила группировки по теме/сессии/тегам.

## Эмбеддинги
- Драйвер: `text-embedding-3-small` (бюджет) или `3-large` с `dimensions=1024/256`.
- Сохраняем в `metadata.embedding` у узла.
- При `retrieve` выполняем keyword + rerank по косинусу.

## Explainability (xtrace)
- В ответах инструментов и чат-эндпоинтов добавлять поле `xtrace.used_memory=[{id, preview, score}]`.

## Acceptance
- Энд-ту-энд тест: `store → retrieve/hybrid → consolidate → distill` проходит на dev-данных.
- Эмбеддинг присутствует у новых узлов; гибридный поиск использует его.
- Секреты редактируются в `pre_store`.
- Документация обновлена; примеры вызовов приложены.

— v0.1, 2025-09-28
