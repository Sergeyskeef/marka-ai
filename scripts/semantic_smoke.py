#!/usr/bin/env python3
"""Offline multilingual retrieval smoke with synthetic public fixtures only.

First explicitly download pinned assets with --install-only. Then run this
script in a separate --network none --memory 512m --cpus 1 container. It uses
temporary canonical data, no bot token, account auth or production state.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import resource
import socket
import sys
import tempfile
import time

from marka.semantic import ASSETS, MODEL, PIPELINE, REVISION, RUNTIME_BYTES, RUNTIME_PROFILE, SemanticIndex, hybrid, install_model
from marka.store import Store


# Fixed before evaluating. This small human-authored diagnostic is not a
# held-out representative benchmark and must not be marketed as one.
CASES = [
    ("Перед изменением базы данных сохраните резервную копию, чтобы восстановиться после сбоя.",
     "Как защитить информацию перед миграцией хранилища?"),
    ("Забытый пароль от аккаунта можно восстановить через электронную почту.",
     "Я не могу войти: потерял секретную комбинацию для входа."),
    ("При нехватке места на диске удалите ненужные временные файлы и старые логи.",
     "Storage is almost full. How can I reclaim space?"),
    ("Если запрос к серверу завершился таймаутом, проверьте соединение и повторите позже.",
     "The remote service takes too long to respond."),
    ("Перед публикацией отчёта уберите персональные сведения и секретные ключи.",
     "What should I remove before sharing a report publicly?"),
    ("Напоминание о встрече нужно отправить за пятнадцать минут до начала.",
     "Предупреди меня незадолго до назначенного разговора."),
    ("Не повторяйте платёж, пока не проверите, был ли предыдущий перевод проведён банком.",
     "Money transfer status is uncertain. Should I submit it again?"),
    ("Когда программа падает, сначала прочитайте сообщение об ошибке и журнал выполнения.",
     "С чего начать диагностику аварийного завершения приложения?"),
]
DISTRACTORS = [
    "В саду зацвели яблони, а вечером ожидается прохладная погода.",
    "Для хлеба нужны мука, вода, соль и достаточно времени на расстойку.",
    "Поезд прибывает на третью платформу, билеты продаются в кассе вокзала.",
    "В библиотеке появилась новая книга об истории мореплавания.",
    "Спортивная команда тренировалась на стадионе перед воскресным матчем.",
    "Для акварельного рисунка художник выбрал холодные синие оттенки.",
    "На прогулку лучше взять удобную обувь и бутылку питьевой воды.",
    "Кошка уснула на подоконнике рядом с горшком домашнего растения.",
]
EXTENDED_CASES = [
    ("Для подключения к тестовой PostgreSQL используется порт 5544.", "Какой порт у тестовой PostgreSQL?"),
    ("ECONNRESET означает, что другая сторона неожиданно закрыла сетевое соединение.", "Что означает ECONNRESET?"),
    ("Расписание напоминаний хранится в UTC; при показе времени учитывается часовой пояс пользователя.", "Why does the reminder time differ from the server clock?"),
    ("Секретные пароли нужно хранить в менеджере паролей, а не в исходниках программы.", "Where should application credentials be kept?"),
    ("Новый программный модуль сначала проверяется тестами на отдельной копии приложения.", "Как убедиться, что правка программы не сломает рабочую версию?"),
    ("На затяжной подъём велосипедисту лучше заранее переключиться на более лёгкую передачу.", "The road becomes steep. How should I change gears?"),
    ("Если телефон сильно нагрелся во время зарядки, отключите зарядное устройство и дайте аппарату остыть.", "The smartphone is overheating while connected to power."),
    ("Черновик статьи должен отделять проверенные факты от предположений автора.", "How should uncertainty be presented in an article?"),
    ("Для переноса встречи нужно согласовать новую дату со всеми участниками.", "Наш разговор приходится отменить. Как договориться о другом времени?"),
    ("Удалённую ветку Git можно заново получить командой git fetch из сохранённого репозитория.", "Как обновить локальные сведения о ветках Git?"),
    ("В документации к функции нужно объяснять её входные параметры и возвращаемое значение.", "What information should a function's documentation contain?"),
    ("Перед долгой поездкой проверьте давление в шинах и заряд аккумулятора автомобиля.", "Как подготовить машину к дальней дороге?"),
    ("После неудачной команды полезно сохранить ошибку и обстоятельства, чтобы не повторить её причину.", "What should the agent remember when an action fails?"),
    ("Бот принимает управляющие сообщения только из привязанного личного чата владельца.", "Can a stranger send commands to the personal Telegram bot?"),
    ("Если большой документ не помещается в контекст, читайте его относящимися к вопросу фрагментами.", "How can I analyze a document that is too long for one prompt?"),
    ("Ученик лучше запоминает материал, когда возвращается к нему через увеличивающиеся интервалы.", "Как организовать повторение изученного, чтобы оно дольше оставалось в памяти?"),
    ("Перед запуском ночного задания нужно определить лимит времени и условие остановки.", "What bounds should an unattended overnight task have?"),
    ("Покупку нового оборудования следует сравнить с ремонтом уже имеющегося устройства.", "Сломался прибор: стоит ли сразу заказывать замену?"),
    ("При обработке таблицы сохраняйте исходные строки, чтобы можно было проверить расчёты.", "How can spreadsheet calculations remain auditable?"),
    ("Кодировка UTF-8 позволяет хранить русский текст вместе с латинскими символами.", "Какая кодировка подходит для кириллицы и английского текста?"),
]


def read_optional(path: str):
    try:
        return Path(path).read_text().strip()
    except OSError:
        return None


def current_rss():
    for line in (read_optional("/proc/self/status") or "").splitlines():
        if line.startswith("VmRSS:"):
            return int(line.split()[1]) * 1024
    return None


def stage(name: str):
    print(json.dumps({"stage":name,"rss_bytes":current_rss(),
                      "cgroup_memory_current":read_optional("/sys/fs/cgroup/memory.current")}), file=sys.stderr, flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--install-only", action="store_true")
    parser.add_argument("--sources", type=int, choices=(100, 1000), default=100)
    parser.add_argument("--extended", action="store_true", help="Use twenty prewritten, previously unmeasured queries")
    args = parser.parse_args()
    if args.install_only:
        started = time.perf_counter()
        install_model(args.model_dir)
        print(json.dumps({"installed": True, "model": MODEL, "revision": REVISION,
                          "asset_bytes": sum(item[1] for item in ASSETS.values()),
                          "derived_asset_bytes": RUNTIME_BYTES, "runtime_profile": RUNTIME_PROFILE,
                          "seconds": round(time.perf_counter()-started, 3)}, indent=2), flush=True)
        return 0

    # Older cgroup kernels do not export memory.peak. Sample charged memory as a
    # separate metric: mmap pages in process RSS can be shared/reclaimable.
    import threading
    stop = threading.Event()
    charge_samples = [0]
    def sample_charge():
        while not stop.is_set():
            value = read_optional("/sys/fs/cgroup/memory.current")
            if value and value.isdigit():
                charge_samples[0] = max(charge_samples[0], int(value))
            stop.wait(0.02)
    sampler = threading.Thread(target=sample_charge, daemon=True)
    sampler.start()

    try:
        connection = socket.create_connection(("1.1.1.1", 443), timeout=0.5)
    except OSError:
        network_denied = True
    else:
        connection.close()
        raise RuntimeError("Run the semantic smoke in a network-disabled container")

    with tempfile.TemporaryDirectory(prefix="marka-semantic-smoke-") as directory:
        store = Store(Path(directory) / "canonical.sqlite3")
        cases = EXTENDED_CASES if args.extended else CASES
        identifiers = []
        long_sources = 0
        for i in range(args.sources):
            text = cases[i][0] if i < len(cases) else DISTRACTORS[(i-len(cases)) % len(DISTRACTORS)] + f" Запись наблюдения номер {i}."
            if i >= len(cases) and i % 50 == 0:
                text = (text + " ") * 25
                long_sources += 1
            event = store.event("user", text)
            memory = store.remember(text, sources=[event], actor="owner", status="accepted")
            identifiers.append(memory)
        index = SemanticIndex(store, args.model_dir)
        if not index.available():
            raise RuntimeError("Install the pinned public model assets first")

        before_load_rss = current_rss()
        stage("before_model_load")
        started = time.perf_counter()
        encoder = index._encoder()
        load_seconds = time.perf_counter()-started
        loaded_rss = current_rss()
        stage("after_model_load")
        initial_vectors = encoder.encode(["Сохраните резервную копию", "Create a backup before changing data"])
        stage("after_first_encode")
        assert len(initial_vectors) == 2 and all(len(vector) == 384 for vector in initial_vectors)

        started = time.perf_counter()
        updated = index.update(max_sources=args.sources, include_events=False)
        index_seconds = time.perf_counter()-started
        indexed_rss = current_rss()
        stage("after_memory_index")
        assert updated["indexed"] == args.sources
        assert index.update(max_sources=args.sources, include_events=False)["indexed"] == 0
        started = time.perf_counter()
        event_update = index.update(max_sources=args.sources)
        events_index_seconds = time.perf_counter()-started
        stage("after_event_index")
        assert event_update["indexed"] == args.sources
        started = time.perf_counter()
        idle = index.update(max_sources=4)
        idle_seconds = time.perf_counter()-started
        assert idle["indexed"] == 0 and idle["checked"] == 0
        for number in range(4):
            store.event("tool", f"Проверка фонового наблюдения номер {number} завершена; инструмент вернул ожидаемый результат.")
        started = time.perf_counter()
        maintenance = index.update(max_sources=4)
        maintenance_seconds = time.perf_counter()-started
        assert maintenance["indexed"] == 4 and maintenance["checked"] == 4

        rows, latencies = [], []
        totals = {mode: {"hit_at_1": 0, "hit_at_3": 0} for mode in ("lexical", "semantic", "hybrid")}
        for number, (_, query) in enumerate(cases):
            expected = identifiers[number]
            lexical = store.search(query, limit=3)
            started = time.perf_counter()
            semantic = index.search(query, kind="memory", limit=3)
            latencies.append(time.perf_counter()-started)
            fused = hybrid(store.search(query, limit=8), index.search(query, kind="memory", limit=8), limit=3)
            row = {"case": number+1, "query": query, "expected": expected}
            for mode, results in (("lexical",lexical),("semantic",semantic),("hybrid",fused)):
                ids = [result["id"] for result in results]
                row[mode] = ids
                totals[mode]["hit_at_1"] += bool(ids and ids[0] == expected)
                totals[mode]["hit_at_3"] += expected in ids
            rows.append(row)

        # Ensure the real encoder's stale cache still obeys canonical withdrawal.
        store.forget(identifiers[0])
        assert all(row["id"] != identifiers[0] for row in index.search(cases[0][1], limit=20))
        fixture_digest = hashlib.sha256(json.dumps(cases, ensure_ascii=False).encode()).hexdigest()
        stop.set()
        sampler.join(timeout=1)
        receipt = {
            "model": MODEL, "revision": REVISION, "pipeline": PIPELINE,
            "runtime_profile": RUNTIME_PROFILE,
            "network_denied": network_denied, "cpu_max": read_optional("/sys/fs/cgroup/cpu.max"),
            "memory_max": read_optional("/sys/fs/cgroup/memory.max"),
            "cgroup_memory_peak_bytes": read_optional("/sys/fs/cgroup/memory.peak"),
            "cgroup_sampled_peak_bytes_20ms": charge_samples[0],
            "cgroup_memory_current": read_optional("/sys/fs/cgroup/memory.current"),
            "cgroup_memory_events": read_optional("/sys/fs/cgroup/memory.events"),
            "process_peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024,
            "rss_before_model_bytes": before_load_rss, "rss_after_model_load_bytes": loaded_rss,
            "rss_after_index_bytes": indexed_rss, "rss_after_queries_bytes": current_rss(),
            "asset_bytes": sum(item[1] for item in ASSETS.values()),
            "derived_asset_bytes": RUNTIME_BYTES,
            "model_load_seconds": round(load_seconds, 3), "index_memory_seconds": round(index_seconds, 3),
            "index_events_seconds": round(events_index_seconds, 3), "idle_update_seconds": round(idle_seconds, 5),
            "maintenance_four_sources_seconds": round(maintenance_seconds, 4),
            "query_mean_seconds": round(sum(latencies)/len(latencies), 4),
            "query_max_seconds": round(max(latencies), 4), "canonical_memory_records": args.sources,
            "long_multichunk_sources": long_sources,
            "index": index.stats(), "fixture_sha256": fixture_digest, "query_count": len(cases),
            "hits": totals, "cases": rows, "forgotten_source_filtered": True,
            "limitation": "Fixed synthetic diagnostic queries; not an independent representative quality benchmark.",
        }
        print(json.dumps(receipt, ensure_ascii=False, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
