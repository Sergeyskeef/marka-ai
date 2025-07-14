# 📍 **Обновлённый роадмап «Марк v2»**  (версия 13 июля 2025)

*Cleanup-0 ✅ → MVP-Spine → Orchestrator → Self-Improving Agents → Prod-Hardening*

---

## 🧭 Общее

| Этап                                         | Цель                                                                       | Срок*      |
| -------------------------------------------- | -------------------------------------------------------------------------- | ---------- |
| **Cleanup-0**                                | убрать Weaviate / Rust-core, ввести MemoryManager v1 (файловый Graphiti)   | **Done ✅** |
| **MVP-Spine**                                | тонкий «позвоночник» (инструменты, CI-пояс, Prompt-Switcher, e2e-сценарий) | +1 нед.    |
| **MVP-2.5**                                  | **Graphiti-Neo4j backend** (см. ниже)                                      | 2 раб. дня |
| **Phase 3 — Orchestrator & Instrumentation** | Prompt-Router, контекст-инъекция, Observability                            | 2 нед.     |
| **Phase 4 — Self-Improving Agents**          | A-Self-Improving Agent, Sandbox-Runner v2                                  | 3–4 нед.   |
| **Phase 5 — Prod-Hardening**                 | Security audit, Perf-opt, Gradual roll-out                                 | 1 нед.     |

* Сроки указаны **от текущего момента** при 1 фокус-разработчике (Курсор).

---

## 🧹 **Phase 1 — Cleanup-0 (завершён)**  *(≤ 2 раб. дня — ✅)*

| Шаг                                              | Статус |
| ------------------------------------------------ | ------ |
| удалить Weaviate-сервис, код, тесты, зависимости | ✅      |
| удалить Rust-core, grpcio, CI-шаги               | ✅      |
| внедрить `MemoryManager v1` + глобальный `mem`   | ✅      |
| очистить документацию, Makefile, CI              | ✅      |

---

## 🏗 **Phase 2 — MVP-Spine (3 нед.)**

| Модуль                                       | Шаги                                                                                                                                                   | Статус    |
| -------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------ | --------- |
| **MVP-1 — Tool-Registry**                    | `@log_to_memory`, YAML-реестр, тесты                                                                                                                   | 🔄        |
| **MVP-2 — CI-пояс**                          | ✅ `pytest` (зелёный: 249 passed, 0 failed)<br>⏳ `ruff`, `pre-commit`                                                                                 | 🔄 (частично) |
| **★ MVP-2.5 — Graphiti-Neo4j backend (NEW)** | 1) Docker-Neo4j контейнер <br>2) `GraphitiBackend` в MemoryManager <br>3) миграция файловых эпизодов → Neo4j <br>4) гибридный поиск (BM25 + embedding) | ⏳ (2 дня) |
| **MVP-3 — Prompt-Switcher**                  | 3 системных промпта, YAML-конфиг                                                                                                                       | ⏳         |
| **MVP-4 — e2e-сценарий**                     | «Проанализируй систему…»                                                                                                                               | ⏳         |

---

## 🎛 **Phase 3 — Orchestrator & Instrumentation (2 нед.)**

| Пункт                    | Детали                                          |
| ------------------------ | ----------------------------------------------- |
| Prompt Orchestrator (v1) | YAML-DSL, Router, Policy Engine                 |
| Context Tags             | `source / channel / mode`                       |
| Event Bus                | `event_recorder.py`                             |
| **Tools Registry v2**    | LLM-rerank top-N <br>meta-документация          |
| Observability            | JSON-логи, OpenTelemetry, Neo4j-latency метрика |
| CI workflow              | `orchestrator.yml`                              |

---

## 🤖 **Phase 4 — Self-Improving Agents (3–4 нед.)**

| Пункт                  | Задачи                                               |
| ---------------------- | ---------------------------------------------------- |
| A-Self-Improving Agent | executor · critic · rewriter · memory (bi-темпораль) |
| Sandbox Runner v2      | ограничения, timeouts, resource-guard                |
| PromptBreeder          | авто-эволюция промптов                               |
| Benchmark v2           | до/после + community clusters                        |

---

## 🛡 **Phase 5 — Prod-Hardening (1 нед.)**

* Security audit
* Perf optimization (Neo4j parallel-runtime, индексы)
* Namespace support (`group_id` → multi-tenant)
* Gradual roll-out + monitoring

---

## 📦 **Зависимости**

| Категория           | Пакеты / Сервисы                                                                                  |
| ------------------- | ------------------------------------------------------------------------------------------------- |
| **Infra**           | Docker Compose, Python 3.10+, Neo4j 5.x (+ `neo4j-driver`), (пром. метрики → `prometheus_client`) |
| **Dev**             | pytest, ruff, pre-commit, anyio, pydantic v2                                                      |
| **LLM / Retrieval** | `openai`, `transformers` (NER / summaries)                                                        |
| **Исключено**       | Weaviate, Pinecone, grpcio*, weaviate-client                                                     |

---

## ⚠️ Challenges & Mitigations

| Риск                                | Решение                                           |
| ----------------------------------- | ------------------------------------------------- |
| Деградация Neo4j при росте графа    | индексы, параллельный runtime, community clusters |
| Переполнение prompt’а фактами       | LLM-контракция + summarization узлов-кластеров    |
| «Холодный» старт (файловый → Neo4j) | однократная миграция, дальше только Neo4j         |
| Безопасность Sandbox Runner         | строгие limits + static-analysis                  |

---

## ✅ Статус чек-листа

* [x] **Cleanup-0** — *Weaviate & Rust ядро удалены*
* [x] **MemoryManager v1** — *Graphiti-files*
* [x] **MVP-Spine (MVP-2 частично)** — *pytest зелёный (249 passed, 0 failed)*
* [ ] **MVP-1 Tool-Registry** — *@log_to_memory, YAML-реестр*
* [ ] **MVP-2.5 Graphiti-Neo4j backend**
* [ ] **MVP-3 Prompt-Switcher** — *3 системных промпта*
* [ ] **MVP-4 e2e-сценарий** — *«Проанализируй систему…»*
* [ ] Orchestrator v1
* [ ] Self-Improving Agents
* [ ] Prod-Hardening

---

---

## 📝 **Последние обновления**

**13 июля 2025** — ✅ **pytest зелёный!** 
- Исправлены CodeAnalyzer, telegram_commands, ci_pipeline
- Добавлен conftest.py для xfail маркеров
- Результат: 249 passed, 0 failed, 5 xfailed
- Готово к MVP-1 (Tool-Registry)

---

> **Сохрани** этот роадмап как актуальную версию «Марка v2».
> Если нужны точные оценки по людям-часам или сдвиги сроков — дай знать!