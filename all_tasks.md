# 🚀 Roadmap: Cleanup‑0 ➜ MVP‑Spine

*Approved by PO → 12 July 2025*

---

## 📋 **PLAN MODE: Level 4 Complex System Planning**

### **Task Overview**
- **Purpose**: Полная переработка системы с удалением Weaviate/Rust и созданием MVP-Spine
- **Complexity**: Level 4 - Complex System
- **Type**: Architectural Refactoring & System Rebuild
- **Status**: Planning Complete ✅

### **Technology Stack**
- **Framework**: Python (FastAPI/Flask)
- **Build Tool**: Docker Compose
- **Language**: Python
- **Storage**: SQLite/PostgreSQL (после удаления Weaviate)
- **CI/CD**: GitHub Actions

### **Technology Validation Checkpoints**
- [ ] Project initialization command verified
- [ ] Required dependencies identified and installed
- [ ] Build configuration validated
- [ ] Hello world verification completed
- [ ] Test build passes successfully

---

## 🧹 **Phase 1: Cleanup‑0 — удаляем Weaviate и Rust‑core**

### **✅ Cleanup‑0 Checklist:**
- [ ] **0.** Создать ветку `cleanup/weaviate-rust`
- [ ] **1.** Удалить сервис weaviate из docker-compose.yml
- [ ] **2.** Выпилить код Weaviate из backend_selector.py
- [ ] **3.** Удалить weaviate-client из requirements
- [ ] **4.** Удалить/отключить тесты Weaviate
- [ ] **5.** Создать git-tag rust_core_snapshot
- [ ] **6.** Удалить папку rust_core/
- [ ] **7.** Удалить rust_core из compose и CI
- [ ] **8.** Удалить grpcio* пакеты
- [ ] **9.** Обновить docs/architecture.md
- [ ] **10.** Обновить docs/roadmap.md

**Оценка**: ≤ 2 рабочих дня, дифф ≈ 400‑600 LOC.

---

## 🏗️ **Phase 2: MVP‑Spine — тонкий «позвоночник» после очистки**

### **✅ MVP‑1 Checklist:**
- [ ] Создать декоратор `@log_to_memory`
- [ ] Реализовать YAML‑описание инструментов
- [ ] Создать централизованную регистрацию инструментов
- [ ] Протестировать Tool‑Registry

### **✅ MVP‑2 Checklist:**
- [ ] Настроить pytest с полным покрытием
- [ ] Настроить ruff для линтинга
- [ ] Настроить pre‑commit хуки
- [ ] Протестировать CI‑пояс

### **✅ MVP‑3 Checklist:**
- [ ] Создать 3 системных промпта (базовый, аналитический, творческий)
- [ ] Реализовать Prompt‑Switcher
- [ ] Настроить конфигурацию через YAML
- [ ] Протестировать автоматический выбор промпта

### **✅ MVP‑4 Checklist:**
- [ ] Реализовать end‑to‑end сценарий "Проанализируй систему…"
- [ ] Интегрировать все компоненты
- [ ] Создать рабочий прототип
- [ ] Протестировать полный цикл

---

## 🔄 **Phase 3: Orchestrator & Instrumentation**

### **✅ Orchestrator Checklist:**
- [ ] **1.** Реализовать Prompt Orchestrator с prompt_router.py
- [ ] **2.** Добавить Context Tags (source, channel, mode)
- [ ] **3.** Создать Event Bus с event_recorder.py
- [ ] **4.** Реализовать Tools Registry v2 с автодокументацией
- [ ] **5.** Настроить Observability с JSON логами и OpenTelemetry
- [ ] **6.** Создать CI workflow orchestrator.yml

**Ожидаемое время:** 1–2 спринта (≈ 2 недели)

---

## 🤖 **Phase 4: Self‑Improving Agents Bootstrapping**

### **✅ Self-Improving Agents Checklist:**
- [ ] **1.** Реализовать A‑Self‑Improving Agent (executor, critic, rewriter, memory)
- [ ] **2.** Интегрировать с Orchestrator (события & память)
- [ ] **3.** Усилить Sandbox Runner (безопасность, таймауты)
- [ ] **4.** Создать PromptBreeder hook (авто‑эволюция промптов)
- [ ] **5.** Реализовать Benchmark v2 (сравнение до/после)

**Ожидаемое время:** 2–3 спринта (≈ 3–4 недели)

---

## 🏭 **Phase 5: Prod‑Hardening & Gradual Roll‑Out**

### **✅ Prod-Hardening Checklist:**
- [ ] Провести Security audit
- [ ] Выполнить Performance optimization
- [ ] Настроить Monitoring setup
- [ ] Планировать Gradual roll-out

---

## 📋 **Implementation Plan**

### **Phase 1: Cleanup‑0 (≤ 2 рабочих дня)**
1. **Day 1: Weaviate Removal**
   - [ ] Создать ветку `cleanup/weaviate-rust`
   - [ ] Удалить weaviate из docker-compose.yml
   - [ ] Выпилить код Weaviate из Python файлов
   - [ ] Удалить weaviate-client из requirements
   - [ ] Отключить тесты Weaviate

2. **Day 2: Rust Removal**
   - [ ] Создать git-tag `rust_core_snapshot`
   - [ ] Удалить папку rust_core/
   - [ ] Удалить rust_core из compose и CI
   - [ ] Удалить grpcio* пакеты
   - [ ] Обновить документацию

### **Phase 2: MVP‑Spine (≈ 3 недели)**
1. **Week 1: MVP‑1 - Tool‑Registry**
   - [ ] Реализовать `@log_to_memory` декоратор
   - [ ] Создать YAML‑описание инструментов
   - [ ] Реализовать централизованную регистрацию

2. **Week 2: MVP‑2 - CI‑пояс**
   - [ ] Настроить pytest
   - [ ] Настроить ruff
   - [ ] Настроить pre‑commit

3. **Week 3: MVP‑3 & MVP‑4**
   - [ ] Реализовать Prompt‑Switcher
   - [ ] Создать end‑to‑end сценарий
   - [ ] Интегрировать все компоненты

### **Phase 3: Orchestrator (≈ 2 недели)**
1. **Week 1: Core Orchestrator**
   - [ ] Реализовать Prompt Orchestrator
   - [ ] Добавить Context Tags
   - [ ] Создать Event Bus

2. **Week 2: Advanced Features**
   - [ ] Реализовать Tools Registry v2
   - [ ] Настроить Observability
   - [ ] Создать CI workflow

### **Phase 4: Self‑Improving Agents (≈ 3-4 недели)**
1. **Week 1-2: Core Agent**
   - [ ] Реализовать A‑Self‑Improving Agent
   - [ ] Интегрировать с Orchestrator

2. **Week 3-4: Advanced Features**
   - [ ] Усилить Sandbox Runner
   - [ ] Создать PromptBreeder hook
   - [ ] Реализовать Benchmark v2

---

## 🚨 **Creative Phases Required**

### **Architecture Design:**
- [x] **Prompt Orchestrator Architecture** - дизайн системы выбора промптов ✅ **ГОТОВ**
- [ ] **Event Bus Architecture** - дизайн системы событий
- [ ] **Tool Registry Architecture** - дизайн регистратуры инструментов

### **UI/UX Design:**
- [ ] **Prompt Switcher Interface** - интерфейс переключения промптов
- [ ] **Tool Documentation UI** - интерфейс автодокументации

### **Data Model Design:**
- [ ] **Event Data Model** - модель данных для событий
- [ ] **Context Tags Model** - модель контекстных тегов
- [ ] **Tool Registry Model** - модель регистратуры инструментов

---

## 🏗️ **Prompt Orchestrator Architecture Design**

### **1. Требования**

#### **Сценарии использования:**
1. **Системная маршрутизация**: выбор шаблона подсказки на основе типа сообщения
2. **Динамическое переключение**: runtime-выбор между базовыми, аналитическими и креативными подсказками
3. **Контекстно-зависимые переопределения**: внешние сигналы влияют на выбор подсказки
4. **Резервный вариант**: использование подсказки по умолчанию

#### **Метрики и SLA:**
- **Задержка**: P50 ≤ 1 мс, P95 ≤ 3 мс, P99 ≤ 5 мс
- **Пропускная способность**: ≥ 2500 запросов/сек/CPU-core
- **Покрытие правил**: ≥ 95% известных сценариев
- **Уровень ошибок**: < 0.1%

### **2. Компоненты высокого уровня**

1. **Prompt Router**: принимает метаданные сообщений и выбирает ID подсказки
2. **Policy Engine**: применяет правила маршрутизации из YAML с учётом контекстных тегов
3. **Prompt Registry**: централизованное хранилище ID подсказок с шаблонами
4. **Hooks/Extensions**: плагины для кастомной логики (A/B-тестирование, feature-флаги)
5. **Metrics Collector**: собирает метрики задержки, ошибок и выбора подсказок
6. **API Gateway**: единая точка входа для сервисов

### **3. Последовательность взаимодействия**

1. Upstream-сервис отправляет `POST /route-prompt` с { message, tags, mode }
2. API Gateway аутентифицирует запрос и пересылает в Prompt Router
3. Prompt Router запрашивает Policy Engine, передавая метаданные
4. Policy Engine оценивает правила в YAML и возвращает ID подсказки
5. Prompt Router получает шаблон из Prompt Registry
6. Prompt Router отправляет данные метрик в Metrics Collector
7. Возвращается ответ с полной подсказкой и метаданными

### **4. Контракт API**

#### `POST /route-prompt`

**Запрос:**
```json
{
  "message": "...",
  "source": "user|system",
  "channel": "text|voice|...",
  "mode": "basic|analytical|creative",
  "context_tags": { "tag1": "value1", ... }
}
```

**Ответ (200 OK):**
```json
{
  "prompt_id": "analytical_v2",
  "template": "Вы — полезный ассистент...",
  "metadata": {
    "version": "v2",
    "used_rules": ["rule_12", "fallback_default"]
  }
}
```

**Ошибки:**
- 4xx: некорректный ввод
- 5xx: внутренняя ошибка сервера

### **5. Следующие шаги**
- [ ] Уточнить требования с заинтересованными сторонами
- [ ] Перевести YAML-правила в DSL Policy Engine
- [ ] Спроектировать инфраструктуру развертывания
- [ ] Прототипировать минимальный модуль Prompt Router на Python

---

## 📊 **Dependencies**

### **Technical Dependencies:**
- Docker Compose для контейнеризации
- Python 3.8+ для основного кода
- pytest для тестирования
- ruff для линтинга
- pre-commit для хуков

### **Architectural Dependencies:**
- Cleanup‑0 должен завершиться перед MVP‑Spine
- MVP‑Spine должен завершиться перед Orchestrator
- Orchestrator должен завершиться перед Self‑Improving Agents

---

## ⚠️ **Challenges & Mitigations**

### **Challenge 1: Потеря функциональности при удалении Weaviate**
- **Mitigation**: Создать альтернативное решение на SQLite/PostgreSQL

### **Challenge 2: Сложность интеграции Prompt Orchestrator**
- **Mitigation**: Поэтапная реализация с тестированием каждого компонента

### **Challenge 3: Безопасность Sandbox Runner**
- **Mitigation**: Тщательное тестирование безопасности и ограничений

### **Challenge 4: Производительность Self‑Improving Agents**
- **Mitigation**: Оптимизация алгоритмов и кеширование

---

## ✅ **PLAN VERIFICATION CHECKLIST**

- [x] Requirements clearly documented
- [x] Technology stack validated
- [x] Affected components identified
- [x] Implementation steps detailed
- [x] Dependencies documented
- [x] Challenges & mitigations addressed
- [x] Creative phases identified (Level 4)
- [x] tasks.md updated with plan

**→ PLANNING COMPLETE - Ready for next mode**

---

## 🔄 **NEXT RECOMMENDED MODE: CREATIVE MODE**

Требуются Creative Phases для архитектурного дизайна компонентов.