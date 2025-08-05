#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Telegram-бот «Марк» v2.1  (фикс передачи chat_id + упрощённый API)

• /start       – приветствие
• /sync        – копировать проект в /sandbox
• !<cmd>       – shell-команда в /sandbox
• текст        – вопрос Марку  (POST /chat/ask → ответ + запись в Memory)
"""

from __future__ import annotations
import asyncio
import logging
import os
import textwrap
import time
import json
from typing import Final
from collections import defaultdict
from datetime import datetime, timedelta

import httpx
from telegram import Update, constants, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
from telegram.helpers import escape_markdown
from langchain_api.memory.multi_layer_memory import MultiLayerMemory
from langchain_api.memory_logic import (
    memory_search_logic,
    memory_save_logic,
    memory_update_logic,
    memory_delete_logic,
    memory_analyze_logic,
)
from scripts.self_analysis import SelfAnalyzer
from telegram_bot.handlers.task_commands import (
    task_list,
    task_status,
    task_analyze,
    task_create,
    task_cancel,
)

BOT_TOKEN: Final[str | None] = os.getenv("BOT_TOKEN")
APP_HOST: Final[str] = os.getenv("APP_HOST", "http://app:8000")
# Увеличенный таймаут по умолчанию
TIMEOUT: Final[int] = int(os.getenv("BOT_TIMEOUT", "60"))
MAX_CONNECTIONS: Final[int] = int(
    os.getenv("MAX_CONNECTIONS", "20")
)  # Максимум соединений в пуле

if not BOT_TOKEN:
    raise SystemExit("❌  BOT_TOKEN отсутствует в .env – бот остановлен")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)


# ────────── Rate Limiter ──────────────────────────────────────────────────
class RateLimiter:
    """Простой rate limiter для ограничения частоты запросов."""
    def __init__(self, max_requests: int = 10, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window = timedelta(seconds=window_seconds)
        self.requests = defaultdict(list)
    
    async def check_rate_limit(self, user_id: int) -> bool:
        """Проверяет, не превышен ли лимит запросов для пользователя."""
        now = datetime.now()
        user_requests = self.requests[user_id]
        
        # Удаляем старые запросы
        user_requests[:] = [req_time for req_time in user_requests 
                           if now - req_time < self.window]
        
        # Проверяем лимит
        if len(user_requests) >= self.max_requests:
            return False
        
        # Добавляем текущий запрос
        user_requests.append(now)
        return True

# Глобальный rate limiter
rate_limiter = RateLimiter(max_requests=30, window_seconds=60)

# ────────── helpers ──────────────────────────────────────────────────

def create_feedback_keyboard() -> InlineKeyboardMarkup:
    """Создает клавиатуру обратной связи."""
    keyboard = [
        [
            InlineKeyboardButton("👍 Хорошо", callback_data="feedback:positive"),
            InlineKeyboardButton("👎 Плохо", callback_data="feedback:negative")
        ],
        [
            InlineKeyboardButton("🔄 Повторить", callback_data="feedback:retry"),
            InlineKeyboardButton("📝 Уточнить", callback_data="feedback:clarify")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик inline callback кнопок."""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data.startswith("feedback:"):
        action = data.split(":")[1]
        
        if action == "positive":
            await query.edit_message_text("Спасибо за положительный отзыв! 👍")
        elif action == "negative":
            await query.edit_message_text("Спасибо за отзыв. Постараюсь улучшиться! 🤖")
        elif action == "retry":
            # Повторить последний запрос
            await query.edit_message_text("🔄 Повторяю последний запрос...")
            # TODO: Implement retry logic
        elif action == "clarify":
            await query.edit_message_text("📝 Пожалуйста, уточните ваш вопрос:")


async def _post(url: str, payload: dict | None = None) -> httpx.Response:
    """Создает новый клиент для каждого запроса вместо использования глобального."""
    try:
        # Создаем новый HTTP клиент для каждого запроса с оптимизированными
        # настройками
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(
                connect=TIMEOUT,  # Таймаут подключения
                read=TIMEOUT * 2,  # Таймаут чтения (увеличен в 2 раза)
                write=TIMEOUT,  # Таймаут записи
                pool=TIMEOUT / 2,
                # Таймаут получения соединения из пула (уменьшен)
            ),
            limits=httpx.Limits(
                max_connections=MAX_CONNECTIONS,
                max_keepalive_connections=5,
                keepalive_expiry=30,  # 30 секунд на хранение соединения
            ),
            http2=True,  # Включаем HTTP/2 для улучшения производительности
        ) as client:
            # Устанавливаем retries для автоматических повторов при ошибках
            # соединения
            for retry in range(3):  # Максимум 3 попытки
                try:
                    r = await client.post(url, json=payload, timeout=TIMEOUT * 2)
                    r.raise_for_status()
                    return r
                except (
                    httpx.TimeoutException,
                    httpx.ConnectError,
                    httpx.ReadError,
                ) as e:
                    if retry == 2:  # Последняя попытка
                        logging.error(
                            f"HTTP ошибка после 3 попыток при запросе {url}: {e}"
                        )
                        raise
                    logging.warning(
                        f"Попытка {retry+1}/3 для {url} не удалась: {e}. Повторяем..."
                    )
                    # Увеличиваем задержку с каждой попыткой
                    await asyncio.sleep(1 * (retry + 1))
    except httpx.HTTPStatusError as e:
        logging.error(f"HTTP ошибка при запросе {url}: {e.response.status_code}")
        raise
    except httpx.TimeoutException:
        logging.error(f"Таймаут при запросе {url}")
        raise
    except Exception as e:
        logging.error(f"Ошибка при запросе {url}: {e}")
        raise


async def _get(url: str) -> httpx.Response:
    """Создает новый клиент для каждого запроса вместо использования глобального."""
    try:
        # Создаем новый HTTP клиент для каждого запроса с оптимизированными
        # настройками
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(
                connect=TIMEOUT,  # Таймаут подключения
                read=TIMEOUT,  # Таймаут чтения
                write=TIMEOUT,  # Таймаут записи
                pool=TIMEOUT / 2,
                # Таймаут получения соединения из пула (уменьшен)
            ),
            limits=httpx.Limits(
                max_connections=MAX_CONNECTIONS,
                max_keepalive_connections=5,
                keepalive_expiry=30,  # 30 секунд на хранение соединения
            ),
            http2=True,  # Включаем HTTP/2 для улучшения производительности
        ) as client:
            # Устанавливаем retries для автоматических повторов при ошибках
            # соединения
            for retry in range(3):  # Максимум 3 попытки
                try:
                    r = await client.get(url, timeout=TIMEOUT)
                    r.raise_for_status()
                    return r
                except (
                    httpx.TimeoutException,
                    httpx.ConnectError,
                    httpx.ReadError,
                ) as e:
                    if retry == 2:  # Последняя попытка
                        logging.error(
                            f"HTTP ошибка после 3 попыток при запросе {url}: {e}"
                        )
                        raise
                    logging.warning(
                        f"Попытка {retry+1}/3 для {url} не удалась: {e}. Повторяем..."
                    )
                    # Увеличиваем задержку с каждой попыткой
                    await asyncio.sleep(1 * (retry + 1))
    except httpx.HTTPStatusError as e:
        logging.error(f"HTTP ошибка при запросе {url}: {e.response.status_code}")
        raise
    except httpx.TimeoutException:
        logging.error(f"Таймаут при запросе {url}")
        raise
    except Exception as e:
        logging.error(f"Ошибка при запросе {url}: {e}")
        raise


async def _chat_ask(question: str, chat_id: int) -> str | None:
    """Один вызов: и ответ, и запись в Memory."""
    try:
        logging.info(
            f"Отправка запроса к API: question='{question}', chat_id={chat_id}"
        )

        # Настраиваем параметры запроса с увеличенным таймаутом для длинных
        # вопросов
        # Увеличиваем таймаут для длинных вопросов
        timeout_multiplier = max(1, min(len(question) // 100, 5))
        custom_timeout = TIMEOUT * timeout_multiplier

        # Создаем отдельный клиент именно для этого запроса с увеличенным
        # таймаутом
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(custom_timeout * 2),
            # Увеличиваем общий таймаут
            limits=httpx.Limits(max_connections=1),  # Только одно соединение
            http2=True,  # Используем HTTP/2
        ) as client:
            logging.info(
                f"Создан клиент с таймаутом {custom_timeout*2}с для запроса к API"
            )

            for retry in range(3):  # Максимум 3 попытки
                try:
                    response = await client.post(
                        f"{APP_HOST}/chat/ask",
                        json={"question": question, "chat_id": chat_id},
                        timeout=custom_timeout * 2,
                    )
                    response.raise_for_status()
                    answer = response.json()["answer"].strip()
                    logging.info(f"Получен ответ от API длиной {len(answer)} символов")
                    return answer
                except Exception as e:
                    if retry == 2:  # Последняя попытка
                        logging.error(
                            f"Ошибка при запросе к API ask после 3 попыток: {e}",
                            exc_info=True,
                        )
                        raise
                    logging.warning(
                        f"Попытка {retry+1}/3 для запроса к API не удалась: {e}. Повторяем..."
                    )
                    # Увеличиваем задержку с каждой попыткой
                    await asyncio.sleep(2 * (retry + 1))
    except Exception as e:
        logging.error("Ошибка при запросе к API ask: %s", e, exc_info=True)
        return None


async def _sandbox_sync() -> bool:
    try:
        await _post(f"{APP_HOST}/sandbox/sync")
        return True
    except Exception as e:
        logging.error("Ошибка при синхронизации sandbox: %s", e, exc_info=True)
        return False


async def _sandbox_exec(cmd: str) -> str:
    try:
        r = await _post(f"{APP_HOST}/sandbox/exec", {"command": cmd})
        d = r.json()
        return textwrap.dedent(
            f"""\
            🖥️ *sandbox exec*
            `$ {d['cmd']}`
            _exit {d['returncode']}_

            ```stdout
            {d['stdout'] or '(пусто)'}
            ```

            ```stderr
            {d['stderr'] or '(пусто)'}
            ```
        """
        )[:4000]
    except Exception as e:
        logging.error("Ошибка при выполнении команды в sandbox: %s", e, exc_info=True)
        return f"⚠️ run error: {e}"


async def _check_status() -> str:
    """Проверяет статус сервисов."""
    try:
        # Проверка FastAPI
        r_api = await _get(f"{APP_HOST}/ping")
        api_status = (
            "✅ Работает"
            if r_api.status_code == 200
            else f"⚠️ Проблема ({r_api.status_code})"
        )

        # Проверка соединения с Weaviate
        try:
            r_weaviate = await _sandbox_exec("curl -s http://weaviate:8080/v1/meta")
            weaviate_status = "✅ Работает" if "version" in r_weaviate else "⚠️ Проблема"
        except BaseException:
            weaviate_status = "⚠️ Недоступен"

        # Проверка OpenAI API через прокси
        try:
            r_openai = await _sandbox_exec(
                "python -c 'from langchain_api.utils.openai_proxy_client import default_openai_client; print(default_openai_client.models.list())'"
            )
            openai_status = "✅ Работает" if "gpt" in r_openai.lower() else "⚠️ Проблема"
        except BaseException:
            openai_status = "⚠️ Недоступен"

        return textwrap.dedent(
            f"""
            📊 *Статус системы:*

            🔹 FastAPI: {api_status}
            🔹 Weaviate: {weaviate_status}
            🔹 OpenAI API: {openai_status}

            _Бот работает и принимает сообщения._
        """
        )
    except Exception as e:
        logging.error("Ошибка при проверке статуса: %s", e, exc_info=True)
        return f"⚠️ Ошибка при проверке статуса: {e}"


# ────────── Telegram callbacks ───────────────────────────────────────


async def start_cmd(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Привет! Я — Марк.")


async def sync_cmd(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    ok = await _sandbox_sync()
    await update.message.reply_text(
        "✅ Скопировал проект в /sandbox" if ok else "⚠️ sync error (см. логи)"
    )


async def run_code_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /run_code"""
    if not context.args:
        await update.message.reply_text(
            "❌ Укажите код для выполнения\n"
            "Пример: `/run_code print('Hello')`", 
            parse_mode='Markdown'
        )
        return

    code = ' '.join(context.args)
    
    try:
        # Отправляем сообщение о начале выполнения
        status_message = await update.message.reply_text("🔄 Выполняю код...")
        
        # Выполняем код через /sandbox/exec
        response = await _post(f"{APP_HOST}/sandbox/exec", {"command": f"python3 -c \"{code}\""})
        
        if response.status_code == 200:
            data = response.json()
            
            if data.get("success"):
                output = data.get("output", "(пусто)")
                execution_time = data.get("execution_time", 0)
                result_text = f"✅ **Результат:**\n```\n{output}\n```\n⏱️ Время: {execution_time:.2f}с"
            else:
                error = data.get("error", "Неизвестная ошибка")
                result_text = f"❌ **Ошибка:**\n```\n{error}\n```"
                
            await status_message.edit_text(result_text, parse_mode='Markdown')
        else:
            await status_message.edit_text(f"❌ Ошибка API: {response.status_code}")
            
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка выполнения: {str(e)}")


async def status_cmd(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    status_text = await _check_status()
    await update.message.reply_markdown_v2(status_text)


async def sandbox_report_cmd(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    """Отправляет краткий отчёт о последних действиях и diff-отчёте песочницы."""
    try:
        log_lines = []
        diff_lines = []
        # Читаем последние 10 строк лога
        try:
            with open("sandbox_experiments.log", "r", encoding="utf-8") as f:
                all_lines = f.readlines()
                log_lines = all_lines[-10:]
        except Exception as e:
            log_lines = [f"Не удалось прочитать sandbox_experiments.log: {e}\n"]
        # Читаем первые 40 строк diff-отчёта
        try:
            with open("sandbox_diff_report.txt", "r", encoding="utf-8") as f:
                diff_lines = f.readlines()[:40]
        except Exception as e:
            diff_lines = [f"Не удалось прочитать sandbox_diff_report.txt: {e}\n"]
        text = "🧪 *Sandbox Report*\n\n"
        text += "*Последние действия:*\n" + (
            "".join(log_lines) if log_lines else "(нет записей)\n"
        )
        text += "\n*Diff-отчёт (первые 40 строк):*\n" + (
            "".join(diff_lines) if diff_lines else "(нет diff-отчёта)\n"
        )
        # Telegram лимит 4000 символов
        for i in range(0, len(text), 4000):
            await update.message.reply_text(text[i : i + 4000])
    except Exception as e:
        await update.message.reply_text(f"⚠️ Ошибка sandbox_report: {e}")


# Добавляю async-функции для простых действий


async def approve_cmd(update, context):
    await update.message.reply_text("Согласование изменений инициировано.")


async def decompose_cmd(update, context):
    await update.message.reply_text("Декомпозиция задачи: ... (пример)")


async def pytest_cmd(update, context):
    await text_msg_fake(update, context, "!pytest")


def find_passport_file(filename="marka_passport.json"):
    import os

    d = os.path.abspath(os.path.dirname(__file__))
    # Сначала ищем в текущей директории
    candidate = os.path.join(d, filename)
    if os.path.isfile(candidate):
        return candidate
    # Потом ищем на уровень выше
    candidate_up = os.path.join(d, "..", filename)
    if os.path.isfile(candidate_up):
        return os.path.abspath(candidate_up)
    return None


async def selfcheck_cmd(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        passport_path = find_passport_file()
        if not passport_path:
            await update.message.reply_text(
                f"⚠️ Ошибка self-check: marka_passport.json не найден"
            )
            return
        with open(passport_path, "r", encoding="utf-8") as f:
            passport = json.load(f)
        text = json.dumps(passport, ensure_ascii=False, indent=2)
        if len(text) > 4000:
            chunks = [text[i : i + 4000] for i in range(0, len(text), 4000)]
            for i, chunk in enumerate(chunks):
                await update.message.reply_text(
                    chunk
                    + (f"\n(часть {i+1}/{len(chunks)})" if len(chunks) > 1 else "")
                )
        else:
            await update.message.reply_text(text)
    except Exception as e:
        await update.message.reply_text(f"⚠️ Ошибка self-check: {e}")


async def update_passport_cmd(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    """Обновляет паспорт Марка."""
    try:
        # Запускаем скрипт обновления паспорта
        result = await _sandbox_exec("python3 scripts/update_passport.py")
        await update.message.reply_markdown_v2(
            f"🔄 *Обновление паспорта*\n\n{escape_markdown(result)}"
        )
    except Exception as e:
        logging.error("Ошибка при обновлении паспорта: %s", e, exc_info=True)
        await update.message.reply_markdown_v2(
            f"⚠️ *Ошибка при обновлении паспорта:*\n\n{escape_markdown(str(e))}"
        )


memory = MultiLayerMemory(short_term_limit=20)


def memory_search_logic(mem_type: str, query: str, memory) -> str:
    """Логика поиска по памяти для автотестов и использования в memory_search_cmd."""
    if mem_type in [
        "experience",
        "memory",
        "insight",
        "persona",
        "userfacts",
        "chatgptmemory",
    ]:
        search_method = getattr(
            memory.memory_manager.memory_registry.get(mem_type.capitalize()),
            "search",
            None,
        )
        if search_method:
            found = search_method(query, limit=5)
            if not found:
                return f"По запросу '{query}' ничего не найдено в {mem_type}."
            text = f"Результаты поиска в {mem_type} по запросу '{query}':\n"
            for i, item in enumerate(found, 1):
                text += f"{i}. {item.get('summary', str(item))[:400]}\n"
            return text[:4000]
        else:
            return f"Тип памяти '{mem_type}' не поддерживает поиск."
    return None


async def memory_search_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        args = context.args
        if len(args) < 2:
            await update.message.reply_text(
                "Использование: /memory_search <тип> <запрос>"
            )
            return
        mem_type = args[0].strip().lower()
        query = " ".join(args[1:]).strip()
        # Вынесенная логика поиска
        result = memory_search_logic(mem_type, query, memory)
        if result:
            await update.message.reply_text(result)
            return
        # Fallback: паспорт/эмуляция
        passport_path = find_passport_file()
        if not passport_path:
            await update.message.reply_text("⚠️ marka_passport.json не найден")
            return
        import json

        with open(passport_path, "r", encoding="utf-8") as f:
            passport = json.load(f)
        found = None
        for t in passport.get("memory", {}).get("types", []):
            if t["name"].lower() == mem_type:
                found = t
                break
        if not found:
            await update.message.reply_text(
                f"Тип памяти '{mem_type}' не найден. Доступные: "
                + ", ".join(
                    [t["name"] for t in passport.get("memory", {}).get("types", [])]
                )
            )
            return
        text = (
            f"*Тип памяти:* {found['name']}\n"
            f"*Описание:* {found['description']}\n"
            f"*API:* {', '.join(found['api'])}\n"
            f"*Сценарии:* {'; '.join(found['scenarios'])}\n\n"
            f"_Пример запроса:_ '{query}'\n"
            "(Реальный поиск будет реализован позже)"
        )
        try:
            text_md = escape_markdown(text)
            await update.message.reply_markdown_v2(text_md)
        except Exception:
            await update.message.reply_text(text)
    except Exception as e:
        await update.message.reply_text(f"⚠️ Ошибка memory_search: {e}")


def memory_save_logic(mem_type: str, data: str, memory) -> str:
    if mem_type in [
        "experience",
        "memory",
        "insight",
        "persona",
        "userfacts",
        "chatgptmemory",
    ]:
        insert_method = getattr(
            memory.memory_manager.memory_registry.get(mem_type.capitalize()),
            "insert",
            None,
        )
        if insert_method:
            obj = {"summary": data, "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ")}
            inserted_id = insert_method(obj)
            return f"✅ Объект сохранён в {mem_type} (id: {inserted_id})"
        else:
            return f"Тип памяти '{mem_type}' не поддерживает сохранение."
    return None


def memory_update_logic(mem_type: str, obj_id: str, data: dict, memory) -> str:
    if mem_type in ["experience", "memory", "insight", "userfacts", "chatgptmemory"]:
        update_method = getattr(
            memory.memory_manager.memory_registry.get(mem_type.capitalize()),
            "update",
            None,
        )
        if update_method:
            ok = update_method(obj_id, data)
            if ok:
                return f"✅ Объект {obj_id} в {mem_type} обновлён."
            else:
                return f"❌ Не удалось обновить объект {obj_id} в {mem_type}."
        else:
            return f"Тип памяти '{mem_type}' не поддерживает обновление."
    return f"Тип памяти '{mem_type}' не поддерживает обновление через API."


def memory_delete_logic(mem_type: str, obj_id: str, memory) -> str:
    if mem_type in ["experience", "memory", "insight", "userfacts", "chatgptmemory"]:
        delete_method = getattr(
            memory.memory_manager.memory_registry.get(mem_type.capitalize()),
            "delete",
            None,
        )
        if delete_method:
            ok = delete_method(obj_id)
            if ok:
                return f"🗑️ Объект {obj_id} из {mem_type} удалён."
            else:
                return f"❌ Не удалось удалить объект {obj_id} из {mem_type}."
        else:
            return f"Тип памяти '{mem_type}' не поддерживает удаление."
    return f"Тип памяти '{mem_type}' не поддерживает удаление через API."


def memory_analyze_logic(memory) -> str:
    report = ["\U0001f9e0 Самоанализ памяти:\n"]
    try:
        exp = memory.memory_manager.memory_registry.get("Experience")
        all_exp = exp.snapshot().get("snapshot", []) if exp else []
        summaries = [e.get("summary", "") for e in all_exp]
        dups = len(summaries) - len(set(summaries))
        report.append(
            f"- Experience: найдено {dups} дубликатов из {len(summaries)} записей."
        )
    except Exception as e:
        report.append(f"- Experience: ошибка анализа ({e})")
    report.append(
        "\n(В будущем анализ будет глубже: поиск устаревших, неиспользуемых, неактуальных данных и оптимизация)"
    )
    return "\n".join(report)


async def memory_save_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        args = context.args
        if len(args) < 2:
            await update.message.reply_text(
                "Использование: /memory_save <тип> <данные>"
            )
            return
        mem_type = args[0].strip().lower()
        data = " ".join(args[1:]).strip()
        result = memory_save_logic(mem_type, data, memory)
        if result:
            await update.message.reply_text(result)
            return
        # Fallback: паспорт/эмуляция (оставить как есть)
        passport_path = find_passport_file()
        if not passport_path:
            await update.message.reply_text("⚠️ marka_passport.json не найден")
            return
        with open(passport_path, "r", encoding="utf-8") as f:
            passport = json.load(f)
        found = None
        for t in passport.get("memory", {}).get("types", []):
            if t["name"].lower() == mem_type:
                found = t
                break
        if not found:
            await update.message.reply_text(
                f"Тип памяти '{mem_type}' не найден. Доступные: "
                + ", ".join(
                    [t["name"] for t in passport.get("memory", {}).get("types", [])]
                )
            )
            return
        await update.message.reply_text(
            f"📝 Объект типа '{found['name']}' принят к сохранению.\nДанные: {data}\n(В будущем будет сохранено в память через API: {', '.join(found['api'])})"
        )
    except Exception as e:
        await update.message.reply_text(f"⚠️ Ошибка memory_save: {e}")


async def memory_update_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        args = context.args
        if len(args) < 3:
            await update.message.reply_text(
                "Использование: /memory_update <тип> <id> <json-данные>"
            )
            return
        mem_type = args[0].strip().lower()
        obj_id = args[1].strip()
        try:
            data = json.loads(" ".join(args[2:]))
        except Exception as e:
            await update.message.reply_text(f"Ошибка парсинга JSON: {e}")
            return
        result = memory_update_logic(mem_type, obj_id, data, memory)
        await update.message.reply_text(result)
    except Exception as e:
        await update.message.reply_text(f"⚠️ Ошибка memory_update: {e}")


async def memory_delete_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        args = context.args
        if len(args) < 2:
            await update.message.reply_text("Использование: /memory_delete <тип> <id>")
            return
        mem_type = args[0].strip().lower()
        obj_id = args[1].strip()
        result = memory_delete_logic(mem_type, obj_id, memory)
        await update.message.reply_text(result)
    except Exception as e:
        await update.message.reply_text(f"⚠️ Ошибка memory_delete: {e}")


async def memory_analyze_cmd(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        result = memory_analyze_logic(memory)
        await update.message.reply_text(result)
    except Exception as e:
        await update.message.reply_text(f"⚠️ Ошибка memory_analyze: {e}")


async def self_analyze_cmd(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /self_analyze - генерирует отчёт о состоянии системы"""
    try:
        analyzer = SelfAnalyzer()
        analysis = analyzer.get_analysis()

        # Разбиваем длинный отчёт на части по 4000 символов (лимит Telegram)
        chunks = [analysis[i : i + 4000] for i in range(0, len(analysis), 4000)]

        for i, chunk in enumerate(chunks):
            if i == 0:
                await update.message.reply_text(
                    f"📊 *Отчёт о состоянии системы*\n\n{chunk}",
                    parse_mode=constants.ParseMode.MARKDOWN,
                )
            else:
                await update.message.reply_text(
                    chunk, parse_mode=constants.ParseMode.MARKDOWN
                )
    except Exception as e:
        logging.error("Ошибка при генерации отчёта: %s", e, exc_info=True)
        await update.message.reply_text(
            f"⚠️ Ошибка при генерации отчёта: {str(e)}",
            parse_mode=constants.ParseMode.MARKDOWN,
        )


def escape_markdown(text: str) -> str:
    # Экранирует спецсимволы для Telegram MarkdownV2
    escape_chars = r"_ * [ ] ( ) ~ ` > # + - = | { } . !"
    for ch in escape_chars.split():
        text = text.replace(ch, "\\" + ch)
    return text


async def send_help_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправляет пользователю справку по всем доступным командам и триггерам."""
    lines = ["\U0001f916 *Доступные команды и триггеры:*\n"]
    for cmd in COMMANDS_REGISTRY:
        name = escape_markdown(cmd["name"])
        desc = escape_markdown(cmd["description"])
        triggers = ", ".join([escape_markdown(tr) for tr in cmd["triggers"]])
        lines.append(f"*{name}* — {desc}\n_Триггеры:_ {triggers}\n")
    text = "\n".join(lines)
    # Telegram лимит 4000 символов
    for i in range(0, len(text), 4000):
        await update.message.reply_markdown_v2(text[i : i + 4000])


# Универсальный реестр команд, триггеров и действий
COMMANDS_REGISTRY = [
    {
        "name": "/sync",
        "description": "Копировать проект в песочницу (/sandbox)",
        "triggers": [
            "песочница",
            "sandbox",
            "запусти песочницу",
            "sandbox mode",
            "/sync",
        ],
        "action": sync_cmd,
    },
    {
        "name": "!pytest",
        "description": "Запустить автотесты в песочнице",
        "triggers": [
            "запусти тест",
            "автотест",
            "pytest",
            "тесты в песочнице",
            "!pytest",
        ],
        "action": pytest_cmd,
    },
    {
        "name": "/sandbox_report",
        "description": "Получить отчёт о последних действиях и изменениях в песочнице",
        "triggers": [
            "отчёт песочницы",
            "sandbox report",
            "журнал песочницы",
            "diff песочницы",
            "/sandbox_report",
        ],
        "action": sandbox_report_cmd,
    },
    {
        "name": "Согласование",
        "description": "Инициировать согласование изменений",
        "triggers": ["согласуй", "approve", "согласование"],
        "action": approve_cmd,
    },
    {
        "name": "Декомпозиция",
        "description": "Декомпозировать задачу на подзадачи",
        "triggers": ["декомпозируй", "разбей на задачи", "decompose", "decomposition"],
        "action": decompose_cmd,
    },
    {
        "name": "/selfcheck",
        "description": "Показать паспорт Марка (архитектура, режимы, память, песочница и т.д.)",
        "triggers": [
            "паспорт",
            "selfcheck",
            "/selfcheck",
            "архитектура",
            "режимы",
            "что у тебя внутри",
        ],
        "action": selfcheck_cmd,
    },
    {
        "name": "/memory_search",
        "description": "Поиск по памяти: /memory_search <тип> <запрос>",
        "triggers": ["поиск по памяти", "/memory_search"],
        "action": memory_search_cmd,
    },
    {
        "name": "/memory_save",
        "description": "Сохранить объект в память: /memory_save <тип> <данные>",
        "triggers": ["сохрани в память", "/memory_save"],
        "action": memory_save_cmd,
    },
    {
        "name": "/memory_analyze",
        "description": "Самоанализ памяти",
        "triggers": ["самоанализ", "анализ памяти", "/memory_analyze"],
        "action": memory_analyze_cmd,
    },
    {
        "name": "/memory_update",
        "description": "Обновить объект в памяти: /memory_update <тип> <id> <json-данные>",
        "triggers": ["обнови память", "/memory_update"],
        "action": memory_update_cmd,
    },
    {
        "name": "/memory_delete",
        "description": "Удалить объект из памяти: /memory_delete <тип> <id>",
        "triggers": ["удали из памяти", "/memory_delete"],
        "action": memory_delete_cmd,
    },
    {
        "name": "help",
        "description": "Показать все доступные команды, их описания и триггеры",
        "triggers": [
            "что ты умеешь",
            "help",
            "помощь",
            "список команд",
            "команды",
            "возможности",
            "что можешь",
        ],
        "action": send_help_message,
    },
    {
        "name": "/update_passport",
        "description": "Обновить паспорт Марка",
        "triggers": ["обнови паспорт", "/update_passport"],
        "action": update_passport_cmd,
    },
    {
        "name": "/self_analyze",
        "description": "Получить отчёт о состоянии системы",
        "triggers": ["отчёт системы", "/self_analyze"],
        "action": self_analyze_cmd,
    },
    {
        "name": "code_mode",
        "description": "Переключить в режим выполнения кода",
        "triggers": ["👨‍💻 code", "code mode", "/code"],
        "action": lambda update, context: update.message.reply_text(
            "🖥️ Режим Code активирован!\n\n"
            "Теперь я буду выполнять код:\n"
            "• Python: `print(342*100)`\n"
            "• Shell: `!ls -la`\n"
            "• Или используйте /run_code"
        ),
    },
    {
        "name": "/run_code",
        "description": "Выполнить Python код",
        "triggers": ["/run_code"],
        "action": run_code_cmd,
    },
]


async def parse_and_dispatch_command(
    text: str, update: Update, context: ContextTypes.DEFAULT_TYPE
) -> bool:
    """
    Универсальный парсер команд и маппинг ключевых слов/триггеров на действия.
    Возвращает True, если команда обработана, иначе False.
    """
    text_l = text.lower().strip()
    for cmd in COMMANDS_REGISTRY:
        if any(tr in text_l for tr in cmd["triggers"]):
            await cmd["action"](update, context)
            return True
    return False


async def text_msg_fake(
    update: Update, context: ContextTypes.DEFAULT_TYPE, fake_text: str
):
    """Позволяет вызывать text_msg с подменённым текстом (для маппинга)."""

    class FakeMessage:

        def __init__(self, text):
            self.text = text

    fake_update = Update(update.update_id, message=FakeMessage(fake_text))
    await text_msg(fake_update, context)


async def text_msg(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (update.message.text or "").strip()
    user_id = update.effective_user.id

    # Проверяем rate limit
    if not await rate_limiter.check_rate_limit(user_id):
        await update.message.reply_text(
            "⚠️ Слишком много запросов. Пожалуйста, подождите немного перед следующим сообщением."
        )
        return

    # Универсальный парсер команд и маппинг
    if await parse_and_dispatch_command(text, update, context):
        return

    if text.startswith("!"):  # shell-команда
        out = await _sandbox_exec(text[1:].strip())
        await update.message.reply_markdown_v2(out)
        return

    chat_id = update.effective_chat.id
    logging.info(f"Получено сообщение от пользователя chat_id={chat_id}: '{text}'")

    # Показываем индикатор "печатает" во время обработки запроса
    await context.bot.send_chat_action(
        chat_id=chat_id, action=constants.ChatAction.TYPING
    )

    answer = await _chat_ask(text, chat_id)
    if answer is None:
        await update.message.reply_text("⚠️ Нет ответа — проверь логи `bot`/`app`")
        return

    # Для длинных ответов делим на части по 4000 символов
    if len(answer) > 4000:
        logging.info(f"Ответ слишком длинный ({len(answer)} символов), делим на части")
        chunks = [answer[i : i + 4000] for i in range(0, len(answer), 4000)]
        for i, chunk in enumerate(chunks):
            # Добавляем клавиатуру обратной связи только к последней части
            if i == len(chunks) - 1:
                await update.message.reply_text(
                    f"{chunk}"
                    + (f"\n(часть {i+1}/{len(chunks)})" if len(chunks) > 1 else ""),
                    reply_markup=create_feedback_keyboard()
                )
            else:
                await update.message.reply_text(
                    f"{chunk}"
                    + (f"\n(часть {i+1}/{len(chunks)})" if len(chunks) > 1 else "")
                )
    else:
        await update.message.reply_text(answer, reply_markup=create_feedback_keyboard())

    logging.info(f"Отправлен ответ пользователю chat_id={chat_id}")


# Обработчик ошибок для бота


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает ошибки, возникающие в обработчиках."""
    logging.error(
        "Ошибка при обработке сообщения: %s", context.error, exc_info=context.error
    )

    # Сообщаем пользователю об ошибке, если возможно
    if update and update.effective_message:
        await update.effective_message.reply_text(
            "⚠️ Произошла ошибка при обработке сообщения. Пожалуйста, попробуйте позже."
        )


# ────────── entrypoint ───────────────────────────────────────────────


def main() -> None:
    """Запускает бота."""
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    # Регистрируем обработчики команд
    application.add_handler(CommandHandler("start", start_cmd))
    application.add_handler(CommandHandler("sync", sync_cmd))
    application.add_handler(CommandHandler("run_code", run_code_cmd))
    application.add_handler(CommandHandler("status", status_cmd))
    application.add_handler(CommandHandler("sandbox_report", sandbox_report_cmd))
    application.add_handler(CommandHandler("approve", approve_cmd))
    application.add_handler(CommandHandler("decompose", decompose_cmd))
    application.add_handler(CommandHandler("pytest", pytest_cmd))
    application.add_handler(CommandHandler("selfcheck", selfcheck_cmd))
    application.add_handler(CommandHandler("update_passport", update_passport_cmd))
    application.add_handler(
        CommandHandler("self_analyze", self_analyze_cmd)
    )  # Добавляем новый обработчик

    # Регистрируем обработчики команд памяти
    application.add_handler(CommandHandler("memory_search", memory_search_cmd))
    application.add_handler(CommandHandler("memory_save", memory_save_cmd))
    application.add_handler(CommandHandler("memory_update", memory_update_cmd))
    application.add_handler(CommandHandler("memory_delete", memory_delete_cmd))
    application.add_handler(CommandHandler("memory_analyze", memory_analyze_cmd))

    # Регистрируем обработчики команд задач
    application.add_handler(CommandHandler("task_list", task_list))
    application.add_handler(CommandHandler("task_status", task_status))
    application.add_handler(CommandHandler("task_analyze", task_analyze))
    application.add_handler(CommandHandler("task_create", task_create))
    application.add_handler(CommandHandler("task_cancel", task_cancel))

    # Регистрируем обработчик текстовых сообщений
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_msg))

    # Регистрируем обработчик callback кнопок
    application.add_handler(CallbackQueryHandler(handle_callback, pattern="^(feedback:|pref:|menu:)"))

    # Регистрируем обработчик ошибок
    application.add_error_handler(error_handler)

    # Запускаем бота
    application.run_polling()


if __name__ == "__main__":
    main()
