# Sprint #6 Issues (14-20 июля 2025)

## Создать в GitHub Issues

### 1. API v2 refactor
- **Title**: `[Sprint-6] API v2 refactor`
- **Labels**: `sprint-6`, `priority-medium`, `backend`
- **Assignee**: `@cursor`
- **Estimate**: `24h`
- **Acceptance criteria**:
  1) Endpoints вынесены в `routers/`
  2) business-logic в `services/`
  3) OpenAPI schema обновлена и доступна на `/docs`
  4) все unit-/integration-tests зелёные без xfail

### 2. Prometheus exporter
- **Title**: `[Sprint-6] Prometheus exporter`
- **Labels**: `sprint-6`, `priority-medium`, `ops`
- **Assignee**: `@ops-bot`
- **Estimate**: `8h`
- **Acceptance criteria**:
  1) `/metrics` отдаёт default + custom counters
  2) histogram request_duration_seconds
  3) test `test_12_prometheus_metrics` зеленый

### 3. Alert-flow fix
- **Title**: `[Sprint-6] Alert-flow fix`
- **Labels**: `sprint-6`, `priority-medium`, `ops`
- **Assignee**: `@ops-bot`
- **Estimate**: `8h`
- **Acceptance criteria**:
  1) `/alerts` POST/GET работает
  2) alert создаётся в TaskScheduler
  3) related tests зелёные

### 4. Deprecation cleanup (Pydantic v2)
- **Title**: `[Sprint-6] Deprecation cleanup (Pydantic v2)`
- **Labels**: `sprint-6`, `priority-medium`, `backend`
- **Assignee**: `@core-team`
- **Estimate**: `6h`
- **Acceptance criteria**: убрать все `PydanticDeprecatedSince20` warnings; pytest без warnings

### 5. UI design kick-off
- **Title**: `[Sprint-6] UI design kick-off`
- **Labels**: `sprint-6`, `priority-medium`, `design`
- **Assignee**: `@ux-lead`
- **Estimate**: `4h`
- **Acceptance criteria**:
  1) Создан FigJam/MIRO mood-board
  2) согласован перечень экранов «Spine dashboard»
  3) тикет в дизайн-бэклоге

### 6. Pydantic v2 field deprecation warning
- **Title**: `[Sprint-6] Pydantic v2 field deprecation warning`
- **Labels**: `sprint-6`, `tech-debt`
- **Assignee**: `@core-team`
- **Estimate**: `2h`
- **Acceptance criteria**: Убрать warning в sandbox/autonomous_development_system.py:75

## Действия после создания
1. Добавить все issues в Project board → Sprint #6 column
2. Уведомить команду в #dev-updates 