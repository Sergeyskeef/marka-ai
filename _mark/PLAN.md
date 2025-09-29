
### ✅ Шаг D — аудит MCP (завершён) — 2025-09-29 19:28 CEST
- Контейнер `mark-mcp` пересоздан; за последние 10 минут ошибок вида `Failed to write audit log` не наблюдаем.
- Файл аудита доступен через бинд `./logs -> /var/log/mark`.

### ✅ Шаг B — TYPE_CHECKING для `mark_agent.py` (завершён)
- Импорты типов перенесены под `TYPE_CHECKING`; рантайм использует словари-алиасы.
- Сервис `app` пересобран; статус **healthy**, `CMDLINE` без `--reload`.

### ✅ Шаг C — reverse‑proxy + rate‑limit (завершён) — 2025-09-29 20:00 CEST
- **C**: NGINX реверс-прокси настроен с rate-limiting (10 r/s, burst 20)
- **C.1**: TLS включён (самоподписанный сертификат), HTTP → HTTPS редирект
- **C.2**: Прокси-заголовки добавлены в uvicorn (`--proxy-headers`, `--forwarded-allow-ips=127.0.0.1`)
- **C.3**: Заголовки безопасности: HSTS, CSP (report-only), X-Frame-Options, etc.
- **Housekeeping**: Временные стабы `langchain_api/openai/types/*` удалены

### Осталось / Опционально
- **C.4**: При появлении домена — заменить самоподписанный сертификат на Let's Encrypt
- **C.5**: Мониторинг rate-limiting (корректировка при ложных 429)
- **C.6**: CSP перевести из report-only в enforce после тестирования
- Продолжать режим коротких проходов и чекпоинтов (`RUN_LOG.jsonl`).
