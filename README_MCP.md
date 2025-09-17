# mark-mcp

MCP сервер для управления проектом «Марк» через ChatGPT (Developer Mode).

## Возможности
- fs_glob: просмотр списка файлов (allowlist)
- fs_read: чтение файлов
- security_request_write / confirm_write: интерлок на запись
- memory_search / memory_upsert: интеграция с Graphiti
- agent_run_task: запуск задач в dry-run по умолчанию
- /health: проверка состояния
- /events: SSE-ивенты для health/heartbeat

## Развёртывание
1. Добавьте переменные в `.env`:
```
MCP_TOKEN=change-me
GRAPHITI_URL=http://graphiti:7878
ALLOW_PATHS=/srv/mark,/var/log/mark,/data/mark
```
2. Запустите сервис:
```
docker compose -f docker-compose.yml -f docker-compose.override.yml up -d --build mark-mcp
```
3. Проверьте health:
```
curl http://localhost:8788/health
```

## Nginx
Включите `docs/nginx/mcp.conf` и проксируйте `/mcp/`.

## Подключение к ChatGPT (Developer Mode)
- Включите Developer Mode
- Добавьте MCP source: URL `https://<ваш-домен>/mcp/` и Bearer-токен `MCP_TOKEN`
- Проверьте инструменты:
  - GET `/mcp/tools/fs_glob?pattern=/srv/mark/*`
  - GET `/mcp/tools/fs_read?path=/srv/mark/README.md`
  - GET `/mcp/tools/memory_search?query=test`

## Примеры
- Запрос на запись:
```
curl -H "Authorization: Bearer $MCP_TOKEN" -X POST https://<host>/mcp/tools/security_request_write \
  -H 'Content-Type: application/json' \
  -d '{"path":"/srv/mark/file.txt","content":"hello"}'
```
- Подтверждение:
```
curl -H "Authorization: Bearer $MCP_TOKEN" -X POST https://<host>/mcp/tools/confirm_write \
  -H 'Content-Type: application/json' \
  -d '{"request_id":"<id>","allow":true}'
```
