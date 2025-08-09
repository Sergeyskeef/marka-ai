# 📊 ОТЧЕТ АНАЛИЗА ЗАВИСИМОСТЕЙ

**Дата анализа:** 1754572746.3918111
**Корневая директория:** /workspace

## 📈 Общая статистика

- **Всего Python файлов:** 226
- **Используемых файлов:** 160
- **Мертвых файлов:** 66
- **Строк мертвого кода:** ~12045

## 🔴 ТОЧНО МЕРТВЫЙ КОД (57 файлов)
*Эти файлы можно безопасно удалить - на них нет ссылок*

- `__init__.py` (0 строк)
- `app/core/memory_manager.py` (97 строк)
- `core/__init__.py` (2 строк)
- `core/agent/__init__.py` (13 строк)
- `core/agent/reflexion.py` (326 строк)
- `core/agent/runner.py` (317 строк)
- `core/command_monitoring.py` (394 строк)
- `core/connection_pool.py` (96 строк)
- `core/event_monitor.py` (171 строк)
- `core/graphiti/__init__.py` (13 строк)
- `core/graphiti/backend_neo4j.py` (320 строк)
- `core/guardrails_client.py` (208 строк)
- `core/memory/__init__.py` (4 строк)
- `core/memory/base_memory.py` (31 строк)
- `core/memory/enhanced_memory.py` (461 строк)
- `core/memory/hybrid_search.py` (358 строк)
- `core/memory/mistake_insights.py` (307 строк)
- `core/memory/prefs.py` (168 строк)
- `core/memory/sessions.py` (210 строк)
- `core/message_analyzer.py` (283 строк)
- `core/metrics/__init__.py` (24 строк)
- `core/metrics/outcome_logger.py` (208 строк)
- `core/middleware.py` (80 строк)
- `core/prometheus_metrics.py` (148 строк)
- `core/prompt_adapter.py` (208 строк)
- `core/prompt_manager.py` (96 строк)
- `core/reflection/memory_integration.py` (209 строк)
- `core/reflection/reasoning_chains.py` (249 строк)
- `core/reflection/reflection_system.py` (278 строк)
- `core/reflection/self_learning.py` (275 строк)
- `core/tools/__init__.py` (65 строк)
- `core/tools/schemas.py` (169 строк)
- `globals.py` (4 строк)
- `graphiti_service/utils.py` (62 строк)
- `memory/__init__.py` (0 строк)
- `memory/graphiti_memory.py` (164 строк)
- `memory_logic.py` (67 строк)
- `middlewares/agents_trace.py` (324 строк)
- `routers/task_router.py` (94 строк)
- `routes/trace_ui.py` (154 строк)
- `sandbox/ci_pipeline.py` (39 строк)
- `sandbox/production_validation_system.py` (32 строк)
- `sandbox/reflection_manager.py` (120 строк)
- `sandbox/self_learning_system.py` (32 строк)
- `sandbox/task_planning_system.py` (407 строк)
- `scripts/auto_sync_passport.py` (209 строк)
- `scripts/generate_project_map.py` (112 строк)
- `scripts/sandbox_dashboard.py` (76 строк)
- `services/__init__.py` (0 строк)
- `services/task_executor.py` (351 строк)
- `telegram_bot/handlers/buttons.py` (221 строк)
- `utils/logger.py` (24 строк)
- `utils/metrics.py` (105 строк)
- `utils/proxy.py` (13 строк)
- `utils/task_analyzer_new.py` (186 строк)
- `utils/task_manager.py` (296 строк)
- `utils/toolkit.py` (316 строк)


## 🟡 ВОЗМОЖНО МЕРТВЫЙ КОД (9 файлов)
*Эти файлы имеют ссылки, но не достижимы из точек входа*

- `core/analysis_engine.py` (1090 строк) - ссылки из: tests/core/test_analysis_engine.py
- `core/feedback_system.py` (171 строк) - ссылки из: tests/test_feedback_system.py
- `core/memory/schema.py` (227 строк) - ссылки из: core/memory/mistake_insights.py
- `core/monitoring.py` (98 строк) - ссылки из: tests/core/test_monitoring.py
- `sandbox/self_awareness.py` (741 строк) - ссылки из: core/analysis_engine.py
- `scripts/question_parser.py` (136 строк) - ссылки из: tests/test_question_parser.py
- `scripts/update_passport.py` (7 строк) - ссылки из: scripts/auto_sync_passport.py
- `utils/openai_proxy_client.py` (183 строк) - ссылки из: sandbox/task_planning_system.py
- `utils/task_analyzer.py` (196 строк) - ссылки из: tests/test_task_analyzer.py


## 🧪 ТЕСТОВЫЕ ФАЙЛЫ (40 файлов)
*Тесты, которые возможно не работают*

- `core/memory/tests/__init__.py`
- `core/memory/tests/test_enhanced_memory.py`
- `core/tests/test_command_monitoring.py`
- `examples/debug_test.py`
- `scripts/test_experience_elevation.py`
- `scripts/test_manual_elevate.py`
- `telegram_bot/tests/test_buttons.py`
- `telegram_bot/tests/test_sandbox_commands.py`
- `telegram_bot/tests/test_task_commands.py`
- `tests/__init__.py`
- `tests/agent/__init__.py`
- `tests/agent/test_reflexion.py`
- `tests/conftest.py`
- `tests/core/reflection/test_memory_integration.py`
- `tests/core/reflection/test_reasoning_chains.py`
- `tests/core/reflection/test_reflection_analyzer.py`
- `tests/core/reflection/test_reflection_system.py`
- `tests/core/reflection/test_self_learning.py`
- `tests/core/test_analysis_engine.py`
- `tests/core/test_command_monitoring.py`
- `tests/core/test_message_analyzer.py`
- `tests/core/test_monitoring.py`
- `tests/e2e/__init__.py`
- `tests/e2e/test_reflexion_success.py`
- `tests/graphiti/__init__.py`
- `tests/graphiti/test_backend_neo4j.py`
- `tests/guardrails/test_length_limit.py`
- `tests/metrics/__init__.py`
- `tests/metrics/test_outcome_logger.py`
- `tests/prefs/test_prefs_crud.py`
- `tests/prompt/test_prompt_adapter.py`
- `tests/sessions/test_sessions_eviction.py`
- `tests/test_feedback_system.py`
- `tests/test_llm_roundtrip.py`
- `tests/test_memory_commands.py`
- `tests/test_memory_search.py`
- `tests/test_question_parser.py`
- `tests/test_task_analyzer.py`
- `tests/test_task_executor.py`
- `tests/tools/test_pydantic_tools.py`


## 💾 Сохранено

- `dependency_map.json` - полная карта зависимостей
- Используйте эту карту для безопасного удаления файлов

## ⚡ Рекомендуемые команды для очистки

```bash
# Создать backup
tar -czf backup_$(date +%Y%m%d_%H%M%S).tar.gz .

# Удалить точно мертвый код
rm -f __init__.py
rm -f app/core/memory_manager.py
rm -f core/__init__.py
rm -f core/agent/__init__.py
rm -f core/agent/reflexion.py
rm -f core/agent/runner.py
rm -f core/command_monitoring.py
rm -f core/connection_pool.py
rm -f core/event_monitor.py
rm -f core/graphiti/__init__.py
# ... и остальные файлы из списка
```