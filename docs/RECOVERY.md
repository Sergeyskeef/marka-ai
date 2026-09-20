# Сбой и восстановление

В 2.6.1 gateway записывает `last-exit.json` до завершения фоновых компонентов.
Запись содержит версию, время, идентификатор запуска, компонент, тип события,
разрешённый класс исключения и номера строк известных модулей. Текст исключения,
строки исходника, локальные переменные, сообщения и ключи не записываются.
Сбой запуска, неожиданное завершение корутины, отмена и SIGTERM/SIGINT различаются.

Перед заменой контейнера независимый guardian сохраняет технический снимок
в своей закрытой папке `incident-*.json`, вне mounts бота. Сохраняются не более
32 снимков: состояние контейнера, разрешённые поля heartbeat/last-exit и классы
исключений/номера строк из ограниченного хвоста Docker log. Сырые журналы не
сохраняются. Совпадение идентификаторов запуска проверяется явно: старый
`last-exit` не приписывается новому процессу. Данные бота считаются его отчётом,
а не доказательством причины; независимые проверки базы и контейнера сохраняются.
Ошибка сбора снимка не отключает восстановление. FIFO и symlink не читаются.

После принятого выпуска первая потеря liveness допускает один перезапуск того
же образа. Он не расходуется заново при рестарте самого guardian и не стирает
предыдущий образ для отката. Повторная ошибка приводит к откату, затем действует
общий предел двух попыток восстановления. Для OOM, изменения истории/схемы,
явной команды владельца и неудачного кандидата в период проверки прежние строгие
правила сохраняются. Перезапуск не объявляется устранением первопричины.

Bridge и runner остаются независимыми закреплёнными компонентами. Самообновление
и восстановление изменяемого бота не переписывают их автоматически. Модель получает
фактическую версию своего пакета и версию bridge; снимок сервера показывает текущий
образ и версию бота по контроллеру, а также действие восстановления. История
экспериментов не выдаётся за полный журнал операторских установок.

19 сентября 2026 года 2.6 успешно прошёл стартовые проверки, затем watchdog
вернул бот на 2.5.1 с причиной `heartbeat unavailable`. База не восстанавливалась
из старой копии. Точная причина завершения неизвестна: старый контейнер и его
журнал были удалены. Новый механизм исправляет потерю доказательств и немедленный
откат при первом сбое, но сам по себе не доказывает устранение неизвестной причины.
Позже 2.5.1 также была возвращена на 2.4 по тому же признаку, без отката базы.
Поэтому операторская установка 2.6.1 использует фактическую 2.4 как резервный
образ бота; закреплённые bridge и runner установлены отдельно в версии 2.6.1.
# 2.6.2: queue contention and SQLite diagnostics

Worker and delivery claims use a 100 ms SQLite busy timeout and yield between
retries, for at most 30 seconds. Only SQLite BUSY, LOCKED and PROTOCOL errors
are retried, before any external action. Other database errors still fail
visibly; model calls, tool actions and Telegram sends are never replayed by
this mechanism. Shutdown interrupts the wait. Queue connection setup failures
also close their connection.

Runtime exit receipts and guardian incident records retain the numeric SQLite
error code without SQL text, exception messages or private data. The September
20 incident identified OperationalError in worker/delivery claim transactions,
but the older receipts did not contain this code: contention is a tested failure
mode addressed by this release, not a proven explanation of that incident.

The operator restored the existing database without checkpoint rollback. The
waiting Telegram update was processed and its delivery marked sent before the
2.6.2 deployment. The candidate passed 671 offline tests in its Linux container
(one skipped); the previous container and fresh database checkpoint were kept
for recovery.
