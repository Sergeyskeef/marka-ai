from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import secrets
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from .engine import Engine
from .provider import CodexProvider
from .queue import Queue
from .redact import redact
from .store import Store
from .telegram import TelegramClient, TelegramError, TelegramRetryAfter, parse_message, valid_private_message

LOG = logging.getLogger("marka")
HELP = """Я Марк. Можно просто написать вопрос или поручение.

/task поручение — выполнить с инструментами
/evolve конкретное улучшение — подготовить и проверить изменение моего кода
/status — память, лимит, текущая работа
/tasks — последние задачи и их номера
/stop — остановить текущую работу и отменить очередь
/cancel номер — отменить задачу/её повторы
/resume номер — продолжить сохранённую задачу
/remember факт — сохранить твоё утверждение
/learn правило — запомнить твою поправку как урок
/memory слова — найти в принятой памяти
/candidates — предложенные мной факты и уроки
/accept номер — принять проверенный тобой кандидат
/forget номер — исключить знание из поиска (аудит остаётся)
/file путь — получить созданный файл из рабочего каталога
/help — эта справка

Для отложенной работы напиши, что сделать, когда и сколько раз.
Могу исследовать публичные страницы, создавать файлы и запускать код в отдельной среде.
Работа ограничена числом шагов и дневным лимитом. Непроверенные догадки не становятся фактами."""


@contextmanager
def instance_lock(path: Path):
    """One gateway/worker per state directory, without stale PID guessing."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+b")
    try:
        handle.seek(0)
        if not handle.read(1):
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        try:
            if __import__("os").name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise RuntimeError("Another Mark instance is using this state directory") from None
        yield
    finally:
        handle.close()


def issue_pairing(store: Store) -> str:
    if store.get_meta("owner_id"):
        raise ValueError("This installation already has an owner")
    code = secrets.token_urlsafe(24)
    store.set_meta("pairing", {"hash": hashlib.sha256(code.encode()).hexdigest(), "expires": time.time() + 86400})
    return code


class Application:
    def __init__(self, settings, *, provider=None, client=None):
        self.settings = settings
        self.store = Store(settings.database)
        self.queue = Queue(settings.database)
        self.client = client or TelegramClient(settings.token)
        self.provider = provider or CodexProvider(settings.codex_binary, settings.codex_home, settings.model, settings.provider_timeout)
        self.engine = Engine(settings, self.store, self.queue, self.provider, self.progress)
        self.stopping = asyncio.Event()
        self.current: asyncio.Task | None = None
        self.current_id: str | None = None
        self.last_progress = 0.0
        self.last_status = ""

    async def progress(self, job, message):
        self.last_status = message
        # Work summaries only, not private model reasoning or every tool call.
        if job["chat_id"] > 0 and time.monotonic() - self.last_progress > 45:
            self.last_progress = time.monotonic()
            self.queue.deliver(f"progress:{job['id']}:{int(time.time())}", job["chat_id"], message)

    def reply(self, message, text, document=""):
        self.queue.deliver(f"command:{message.update_id}", message.chat_id, text, document)

    @staticmethod
    def _reply_in_transaction(db, message, text):
        """The unique outbox source also acts as a durable command receipt."""
        db.execute("INSERT OR IGNORE INTO deliveries(source,chat_id,text,due) VALUES(?,?,?,?)",
                   (f"command:{message.update_id}", message.chat_id, redact(text), time.time()))

    def _has_command_receipt(self, update_id):
        with self.queue.connection() as db:
            return db.execute("SELECT 1 FROM deliveries WHERE source=?", (f"command:{update_id}",)).fetchone() is not None

    def _pair_owner(self, message, supplied):
        """Bind ownership, consume its code and acknowledge in one transaction."""
        if not supplied:
            return False
        with self.store._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            owner = db.execute("SELECT value FROM meta WHERE key='owner_id'").fetchone()
            pairing_row = db.execute("SELECT value FROM meta WHERE key='pairing'").fetchone()
            pairing = json.loads(pairing_row["value"]) if pairing_row else {}
            if owner is not None or not isinstance(pairing, dict):
                return False
            digest = hashlib.sha256(supplied.encode()).hexdigest()
            if pairing.get("expires", 0) <= time.time() or not hmac.compare_digest(digest, pairing.get("hash", "")):
                return False
            db.execute("INSERT INTO meta(key,value) VALUES('owner_id',?)", (json.dumps(message.user_id),))
            db.execute("UPDATE meta SET value='{}' WHERE key='pairing'")
            self._reply_in_transaction(db, message, "Привязал этот личный чат к владельцу. Я Марк. Можно начинать общаться и давать поручения. /help — возможности и управление.")
            db.execute("INSERT INTO cursors VALUES('telegram',?) ON CONFLICT(name) DO UPDATE SET value=max(value,excluded.value)",
                       (message.update_id + 1,))
            return True

    def _remember_owner(self, message, command, argument):
        """Commit an authenticated statement and its receipt together.

        The source event, accepted memory, immutable source snapshot and reply
        either all commit or all roll back. Replayed update IDs cannot duplicate
        knowledge; the same text in a later user message remains a new statement.
        """
        content = redact(argument)
        captured = datetime.now(timezone.utc).isoformat(timespec="microseconds")
        with self.store._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM deliveries WHERE source=?", (f"command:{message.update_id}",)).fetchone():
                return
            # Match Store.event's monotonic allocation, including old SQLite
            # schemas where retention can otherwise reuse an INTEGER PRIMARY KEY.
            previous = db.execute("SELECT value FROM meta WHERE key='_event_high_watermark'").fetchone()
            maximum = db.execute("SELECT coalesce(max(id),0) FROM events").fetchone()[0]
            snapshot_maximum = db.execute("SELECT coalesce(max(event_id),0) FROM memory_sources").fetchone()[0]
            source = max(int(json.loads(previous[0])) if previous else 0, maximum, snapshot_maximum) + 1
            db.execute("INSERT INTO events(id,role,content,session,created_at,meta) VALUES(?,'user',?,'main',?,?)",
                       (source, content, captured, json.dumps({"command": command, "telegram_update": message.update_id})))
            db.execute("INSERT INTO meta(key,value) VALUES('_event_high_watermark',?) "
                       "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (str(source),))
            is_fact = command == "/remember"
            identifier = db.execute(
                "INSERT INTO memories(content,kind,level,status,actor,evidence_kind,created_at,accepted_at) "
                "VALUES(?,?,?,'accepted','owner','direct_fact',?,?)",
                (content, "fact" if is_fact else "lesson", 1 if is_fact else 2, captured, captured),
            ).lastrowid
            db.execute("INSERT INTO memory_sources(memory_id,event_id,role,content,content_hash,captured_at) VALUES(?,?,'user',?,?,?)",
                       (identifier, source, content, hashlib.sha256(content.encode()).hexdigest(), captured))
            self._reply_in_transaction(db, message, f"Сохранил под номером {identifier}. /forget {identifier} исключит запись из поиска.")

    def _enqueue_owner(self, prompt, chat_id, *, source, kind="chat"):
        with self.queue.connection() as db:
            existing = db.execute("SELECT id FROM jobs WHERE source=?", (source,)).fetchone()
            if existing:
                return existing["id"]
            count = db.execute("SELECT count(*) FROM jobs WHERE chat_id=? AND state IN ('queued','running')", (chat_id,)).fetchone()[0]
            if count >= 100:
                raise ValueError("В очереди уже 100 задач. Дождись выполнения или используй /stop")
        return self.queue.enqueue(prompt, chat_id, source=source, kind=kind)

    async def ingest(self, update: dict):
        if not isinstance(update, dict):
            return
        update_id = update.get("update_id")
        if type(update_id) is not int or update_id < 0 or update_id < self.queue.offset():
            return
        message = parse_message(update)
        if message is None or not valid_private_message(message):
            self.queue.advance(update_id)
            return
        owner = self.store.get_meta("owner_id")
        if owner is None:
            supplied = message.text.partition(" ")[2].strip() if message.text.startswith("/start ") else ""
            self._pair_owner(message, supplied)
            self.queue.advance(update_id)
            return
        if message.user_id != owner or message.chat_id != owner:
            self.queue.advance(update_id)
            return
        if self._has_command_receipt(update_id):
            self.queue.advance(update_id)
            return
        try:
            if message.text.startswith("/"):
                handled = await self.command(message)
            else:
                handled = False
            if not handled:
                self._enqueue_owner(message.text, message.chat_id, source=f"telegram:{update_id}")
        except (ValueError, KeyError) as exc:
            self.reply(message, "Не удалось выполнить команду: " + str(exc)[:300])
        self.queue.advance(update_id)

    async def command(self, message) -> bool:
        command, _, argument = message.text.partition(" ")
        command = command.split("@")[0].lower()
        argument = argument.strip()
        if command in {"/start", "/help"}:
            self.reply(message, HELP)
        elif command == "/status":
            stats = self.store.stats()
            text = f"Марк работает. Память: {stats['by_status']['accepted']} принятых, {stats['by_status']['candidate']} кандидатов.\nВызовы Codex за сутки UTC: {stats['budget_used']}/{self.settings.daily_calls}.\n"
            text += f"Текущая задача: {self.current_id or 'нет'}. " + self.last_status
            issues = self.queue.delivery_issues()
            if issues:
                text += "\nЕсть неподтверждённые/неудачные доставки. Результат сохранён; /tasks покажет номера, /result номер повторно выдаст ответ."
            self.reply(message, text)
        elif command == "/tasks":
            self.reply(message, "\n".join(f"{x['id']} [{x['state']}] {x['prompt'][:100]}" for x in self.queue.list()) or "Задач пока нет.")
        elif command == "/result":
            job = self.queue.get(argument)
            if not job:
                raise ValueError("Задача не найдена")
            self.reply(message, job["result"] or job["error"] or "Итог ещё не готов.")
        elif command in {"/stop", "/cancel"}:
            ids = self.queue.cancel(argument if command == "/cancel" and argument else None)
            if self.current_id in ids and self.current:
                self.current.cancel()
            self.reply(message, f"Остановлено/отменено задач: {len(ids)}. Результаты и журнал сохранены.")
        elif command == "/resume":
            if not argument or not self.queue.resume(argument):
                raise ValueError("Нужен номер остановленной/неудачной задачи из /tasks")
            self.reply(message, "Продолжу задачу " + argument + " по сохранённому журналу.")
        elif command in {"/remember", "/learn", "/good", "/bad"}:
            if not argument or len(argument) > 6000:
                raise ValueError("После команды нужен текст до 6000 символов")
            # Only this direct authenticated owner path can accept knowledge.
            self._remember_owner(message, command, argument)
        elif command == "/memory":
            rows = self.store.search(argument, limit=10)
            self.reply(message, "\n\n".join(f"{x['id']} · {x['kind']} · L{x['level']}\n{x['content']}" for x in rows) or "Принятых записей по этому запросу пока нет.")
        elif command == "/candidates":
            rows = self.store.list_memories(limit=10)
            self.reply(message, "\n\n".join(f"{x['id']} · {x['kind']}\n{x['content']}\n/accept {x['id']}" for x in rows) or "Кандидатов пока нет.")
        elif command == "/accept":
            row = self.store.accept(int(argument))
            self.reply(message, f"Принял запись {row['id']}: {row['content']}")
        elif command == "/forget":
            changed = self.store.forget(int(argument))
            self.reply(message, "Исключил запись из поиска. История и источники остаются в локальном аудите." if changed else "Активная запись не найдена.")
        elif command == "/file":
            path = self.engine.tools.workspace.path(argument)
            if not path.is_file() or path.stat().st_size > 20 * 1024 * 1024:
                raise ValueError("Нужен файл до 20 MiB в рабочем каталоге")
            self.reply(message, path.name, document=argument)
        elif command == "/task":
            identifier = self._enqueue_owner(argument, message.chat_id, kind="task", source=f"telegram:{message.update_id}")
            self.reply(message, "Принял задачу " + identifier + ". /stop — остановить, /status — проверить ход.")
        elif command == "/evolve":
            identifier = self._enqueue_owner(argument, message.chat_id, kind="self_improve", source=f"telegram:{message.update_id}")
            self.reply(message, "Принял улучшение " + identifier + ". Подготовлю кандидат изменения моего кода, сравню результаты тестов и выдам патч с отчётом. Установка изменения потребует отдельного решения.")
        else:
            self.reply(message, "Неизвестная команда. /help — список. Поручение можно написать обычным текстом.")
        return True

    async def polling(self):
        failures = 0
        while not self.stopping.is_set():
            try:
                updates = await self.client.get_updates(self.queue.offset(), timeout=25)
                for update in sorted(updates, key=lambda x: x.get("update_id", 0)):
                    await self.ingest(update)
                failures = 0
            except TelegramRetryAfter as exc:
                await self.pause(min(exc.seconds, 60))
            except TelegramError as exc:
                if exc.permanent:
                    raise
                failures += 1
                LOG.warning("Telegram polling unavailable (%s)", type(exc).__name__)
                await self.pause(min(60, 2 ** min(failures, 6)))

    async def worker(self):
        while not self.stopping.is_set():
            job = self.queue.claim()
            if not job:
                await self.pause(0.5)
                continue
            self.current_id = job["id"]
            self.last_status = ""
            self.last_progress = time.monotonic()
            self.current = asyncio.create_task(self.engine.run(job))
            try:
                await self.current
            except asyncio.CancelledError:
                if self.stopping.is_set():
                    return
            finally:
                self.current, self.current_id = None, None
                self.last_status = ""

    async def delivery(self):
        while not self.stopping.is_set():
            item = self.queue.next_delivery()
            if not item:
                await self.pause(0.5)
                continue
            try:
                if item["document"]:
                    target = self.engine.tools.workspace.path(item["document"])
                    await self.client.send_document(item["chat_id"], target, caption=item["text"][:800])
                else:
                    await self.client.send_message(item["chat_id"], item["text"])
                self.queue.delivery_result(item["id"], "sent")
            except TelegramRetryAfter as exc:
                if exc.sent_message_ids:
                    self.queue.delivery_result(item["id"], "uncertain", error="Part of the response was sent before a rate limit")
                else:
                    self.queue.delivery_result(item["id"], "pending", delay=exc.seconds)
            except TelegramError as exc:
                state = "uncertain" if exc.uncertain or exc.sent_message_ids else "failed"
                self.queue.delivery_result(item["id"], state, error=str(exc))
            except (ValueError, OSError):
                self.queue.delivery_result(item["id"], "failed", error="Artifact is unavailable")

    async def pause(self, seconds):
        try:
            await asyncio.wait_for(self.stopping.wait(), seconds)
        except asyncio.TimeoutError:
            pass

    async def run(self):
        with instance_lock(self.settings.data_dir / "gateway.lock"):
            await self.client.get_me()
            hook = await self.client.call("getWebhookInfo", {})
            if hook.get("url"):
                raise RuntimeError("This bot already has a webhook. Use a new bot token or remove that webhook deliberately.")
            self.queue.recover()
            self.store.prune(self.settings.retention_days)
            tasks = [asyncio.create_task(self.polling()), asyncio.create_task(self.worker()), asyncio.create_task(self.delivery())]
            try:
                done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_EXCEPTION)
                for task in done:
                    task.result()
            finally:
                self.stopping.set()
                for task in tasks:
                    task.cancel()
                if self.current:
                    self.current.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
