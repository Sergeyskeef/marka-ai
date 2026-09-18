# Развёртывание

## Рядом с Hermes

Используйте отдельный каталог `/opt/marka-ai` и Compose project `marka`.
Контейнеры не публикуют порты и не подключаются к томам, auth-файлам или Docker
socket Hermes. Тома называются `marka_state` и `marka_runner`; не используйте
имена уже работающих приложений.

```bash
cd /opt/marka-ai
docker compose build
docker compose run --rm --no-deps mark setup
docker compose run --rm --no-deps mark login
docker compose run --rm --no-deps mark doctor --live
docker compose up -d
docker compose ps
```

Ввод токена скрыт. Не передавайте его через аргумент командной строки, issue,
чат или Git. `setup` записывает секрет в приватный том с режимом `0600`.
Новый login относится к той же подписке, но имеет собственное хранилище;
повторный вход существующего Hermes не выполняется.

После `/start <код>` в личном чате проверьте: обычный ответ; `/remember` и поиск;
создание/получение файла; выполнение короткого Python-скрипта; `/stop` во время
длинной задачи; сохранение памяти после `docker compose restart mark`.

## Ресурсы и файлы

Bot container: до 1 GB RAM, 1 CPU, 128 процессов. Runner: 512 MB RAM,
1 CPU, 64 процесса, сеть выключена. Рабочая копия runner находится на tmpfs
до 128 MiB. В неё передаются до 200 файлов / 1 MiB, возвращается до 2 MiB
артефактов, каждый до 512 KiB. Команда работает до 60 секунд.

Постоянная память, рабочие файлы и Codex credentials находятся в state-томе.
Логи ротируются. Вызовы модели ограничены бюджетом, но место постоянной памяти
следует контролировать обычным мониторингом сервера. Это контейнерная изоляция
ядра Linux, не отдельная виртуальная машина.

Проверка runner без Telegram и модели:

```bash
docker compose up -d sandbox
docker compose run --rm --no-deps --entrypoint python mark scripts/container_smoke.py
```

## Обновление и откат

Перед обновлением зафиксируйте текущий commit и сделайте резервную копию:

```bash
docker compose run --rm --no-deps mark backup /state/backups/before-update.sqlite3
git rev-parse HEAD
git pull --ff-only
docker compose build
docker compose up -d
docker compose run --rm --no-deps mark doctor
```

Для отката кода выберите предыдущий **commit новой версии 2.x**, пересоберите
и запустите контейнеры. Старый стек до `2303443` использует другую архитектуру
и не является совместимым runtime для state v2. Перед восстановлением базы
остановите bot; не подменяйте открытую SQLite-базу и её WAL отдельными файлами.
Резервные копии содержат личные данные. Не публикуйте их.

## Нативный процесс без исполнения кода

Python 3.11+ и Node.js 22+, официальный `@openai/codex@0.144.1`.
Создайте отдельного непривилегированного пользователя `marka`, разместите код
в `/opt/marka-ai`, а state в `/var/lib/marka`. Пример unit-файла:
[`deploy/marka.service`](../deploy/marka.service).

```bash
cd /opt/marka-ai
python3 -m venv .venv
.venv/bin/pip install .
sudo -u marka env MARKA_DATA=/var/lib/marka .venv/bin/marka setup
sudo -u marka env MARKA_DATA=/var/lib/marka .venv/bin/marka login
sudo -u marka env MARKA_DATA=/var/lib/marka .venv/bin/marka doctor --live
```

Установите unit после проверки путей. Этот вариант поддерживает чат, память,
веб и файлы; `code.run` отключён, пока не подключён отдельный sandbox container.
Не запускайте runner как обычный host-процесс.

## Импорт личного контекста

```json
[
  {"kind":"preference","level":1,"key":"style","content":"Предпочитаю краткие ответы с проверяемым результатом."},
  {"kind":"lesson","level":2,"content":"Перед повтором неудачной команды сначала выяснить причину ошибки."}
]
```

Передайте JSON в приватный state-том и выполните `marka import-memory /state/seed.json`.
По умолчанию записи попадут в кандидаты. `--accept` используйте только для лично
проверенных исходных утверждений. Полный архив чатов не нужен при каждом запросе.

## Если что-то не работает

- `doctor` различает наличие токена, авторизацию Codex и проверку базы.
- `doctor --live` дополнительно делает один реальный запрос модели.
- Ошибка входа в Codex: повторите `docker compose run --rm --no-deps mark login` в **том же state-томе**; при нативной установке — `marka login` с прежним `MARKA_DATA`.
- Telegram 401: проверьте актуальность токена бота в приватном `settings.json`; вход в Codex его не исправит.
- Лимит подписки: дождитесь сброса и `/resume номер`; платный API автоматически не включается.
- Telegram 409/webhook: проверьте, что токен принадлежит новому боту и не используется другим polling/webhook.
- `blocked` после перезапуска во время инструмента: изучите результат `/result` и файлы, затем явно `/resume`.
- Неопределённая доставка: `/result номер` запросит ответ повторно по вашему решению.
- Нет runner socket: `docker compose logs sandbox`, затем изолированный smoke test.
