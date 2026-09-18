# Codex provider: проверка 18 сентября 2026

`marka` вызывает официальный Codex CLI, а не извлекает OAuth-токены и не
реализует частный ChatGPT HTTP API. Токены остаются в хранилище Codex. Подписка
даёт квоту аккаунта; отдельный процесс или отдельный вход не создают новую квоту.

## Что подтверждено

- На существующем сервере Hermes установлен `/usr/bin/codex` версии `0.144.1`.
  `codex login status` сообщил вход через ChatGPT. Три Hermes gateway services
  были активны; настройки, auth-файлы и сервисы не изменялись.
- Main и graphiti-brain используют модель `gpt-5.6-sol` и provider
  `openai-codex`. Hermes source commit на момент проверки:
  `29112bef099274229cadff79cdff7bf7b99c4b77`.
- Hermes ведёт собственное OAuth-хранилище `~/.hermes/auth.json`, а официальный
  CLI использует `~/.codex/auth.json`. В Hermes `hermes_cli/auth.py` около строки
  4169 описана проблема одноразовых refresh-токенов при копировании общей
  цепочки между хранилищами. Наличие обоих файлов не доказывает, что это одна
  актуальная сессия. Значения токенов не читались и не переносились.
- Для CLI `0.144.1` проверен настоящий запрос к временному loopback mock
  Responses provider с пустым `CODEX_HOME`: после отключения встроенных
  возможностей запрос не содержит инструментов: **`tools: []`** в минимальном
  запросе, поле `tools` опущено при использовании `--output-schema`. Probe не использовал
  учётные данные и не вызывал облачную модель.
- Провайдер прошёл 10 тестов с настоящими подпроцессами на Windows и Linux
  Python 3.11: UTF-8,
  очистка окружения, ошибки авторизации, отказ от API-key login, старый CLI,
  неверный JSON, лишний инструмент, ограничения размера, timeout и cancellation.
- Реальный вызов `complete()` с текущим локальным ChatGPT login и моделью
  `gpt-5.6-sol` вернул `{"reply":"MARKA_AUTH_OK"}` по заданной JSON Schema.
  Локальный desktop CLI: `0.154.0-alpha.6.2`. Auth-файлы не копировались.
- После выбора постоянного размещения рядом с Hermes владелец завершил
  официальный device login в отдельный Docker volume `marka_state`.
  Главный агент проверил `doctor --live`: CLI `0.144.1` в bot-образе выполнил
  реальный вызов по подписке успешно. Это отдельная авторизация Марка;
  существующие auth-файлы Hermes не копировались и не изменялись. На момент
  проверки Telegram token ещё не задан, личный чат ещё не привязан.
- В отдельном Docker Compose проекте собраны bot/sandbox образы; официальный
  Codex `0.144.1` внутри bot-образа также прошёл `scripts/probe_codex_tools.py`.
  `scripts/container_smoke.py` прошёл 10 проверок реального отдельного runner:
  файлы, Python/Node/Bash, закрытые state/auth, отсутствие сети, отказ рекурсивного
  вызова runner, удаление отсоединённого потомка, лимиты вывода/времени/файлов и
  работоспособность после отказов. Telegram gateway при этом не запускался.
- Финальный Linux runtime прошёл 130 unit/integration tests (1 ожидаемый skip).
  `scripts/evolution_smoke.py` сравнил 131 одинаковый тест для baseline/candidate
  через реальный runner: candidate исправил единственный добавленный regression
  case с заведомо фиктивным Slack token, `improved_on_provided_case`.
  Patch сохранён, установленный runtime не изменён; это проверка конкретного
  улучшения, а не доказательство общего роста интеллекта.

## Изоляция модели

Каждый вызов работает в пустом временном каталоге, с `--ephemeral`,
`--ignore-user-config`, `--ignore-rules`, read-only sandbox и approval `never`.
Shell, unified exec, apps, plugins, remote plugins, browser, computer use,
image generation, multi-agent, hooks, memories, goals, code mode, workspace
dependencies и tool suggestions отключены; web search и view_image выключены.
`HOME`, XDG-каталоги и temp-каталоги изолированы. В подпроцесс передаётся небольшой
allowlist окружения без Telegram/GitHub/API токенов.

Вся история, память, разрешённые инструменты и их выполнение принадлежат runtime
`marka`. CLI получает текст и JSON Schema и возвращает один JSON-объект. Runtime
обязан дополнительно проверять схему решения и права каждого действия. Провайдер
не сохраняет reasoning, не возвращает сырой stderr и не пишет промпты в логи.

Capability check требует CLI не старее `0.144.1` и нужных flags/features. Это
проверка совместимости, а не доказательство поведения всех будущих версий.
После обновления Codex надо повторять проверку отсутствия инструментов:
`python scripts/probe_codex_tools.py --binary codex`. В HTTP Responses это
`tools: []` или опущенное поле `tools`.
JSONL-событие встроенного инструмента дополнительно вызывает отказ провайдера,
но эта проверка сама по себе не предотвращает уже выполненный инструмент.
Для эксплуатации предпочтителен отдельный непривилегированный пользователь/VM.

Свежая документация `agents.enabled=false` несовместима с серверным CLI
`0.144.1`; используется проверенный `features.multi_agent=false`.

## Авторизация и эксплуатация

Для нового `marka` создать отдельный постоянный `CODEX_HOME` под его пользователем
и выполнить `codex login --device-auth` в этом окружении. Это тот же аккаунт
подписки, но отдельный вход; обновлением токенов управляет официальный CLI.
Не копировать `~/.hermes/auth.json`, не давать боту доступ к root-home Hermes и
не использовать `codex logout` в действующем Hermes-контуре.

Существующий Hermes gate ограничивает только вызовы `codex exec`, прошедшие через
его wrapper. Он не гарантирует общую очередь прямых HTTP-вызовов Hermes и нового
агента. `marka` сериализует вызовы своего provider; общей квотой аккаунта всё
равно пользуются остальные приложения. При исчерпании квоты возвращается
понятная ошибка; автоматического перехода на платный API нет.

## Официальные источники

- [Authentication](https://learn.chatgpt.com/docs/auth): ChatGPT login,
  device authorization, хранение и refresh credentials.
- [Non-interactive mode](https://learn.chatgpt.com/docs/non-interactive-mode):
  `codex exec`, JSON Schema, ephemeral mode и saved CLI authentication.
- [Configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference):
  feature flags и отключение web search/view_image. Возможности документации
  необходимо сверять с реально установленной версией.

Официальная документация рекомендует API keys как обычный выбор для automation,
но также описывает trusted automation с Codex account auth, когда необходимы
ChatGPT/Codex entitlements. Этот проект использует именно персональный доверенный
контур владельца; бот не является публичным proxy к его подписке.
