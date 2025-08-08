# 📋 НЕОБХОДИМЫЕ ДОРАБОТКИ ФАЗЫ 2

## 🚨 Критические недоработки

### 1. Прямая работа с Neo4j для типизированных узлов

```python
# Нужно создать модуль neo4j_direct.py
class Neo4jDirectClient:
    async def create_fact(self, subject, predicate, object, **kwargs):
        query = """
        CREATE (f:Fact {
            id: $id,
            subject: $subject,
            predicate: $predicate,
            object: $object,
            confidence: $confidence,
            valid_from: datetime(),
            embedding: $embedding
        })
        RETURN f
        """
        
    async def update_fact_confidence(self, fact_id, new_confidence):
        query = """
        MATCH (f:Fact {id: $fact_id})
        SET f.confidence = $new_confidence,
            f.updated_at = datetime()
        RETURN f
        """
        
    async def create_skill_evolution(self, old_id, new_skill_data):
        query = """
        MATCH (old:Skill {id: $old_id})
        CREATE (new:Skill $new_data)
        CREATE (new)-[:EVOLVED_FROM {
            reason: $reason,
            timestamp: datetime()
        }]->(old)
        RETURN new
        """
```

### 2. Реализация методов в advanced_memory_adapter.py

```python
async def update_fact_confidence(self, fact_id, new_confidence, reason):
    # Реальная реализация через neo4j_direct
    result = await self.neo4j.update_fact_confidence(fact_id, new_confidence)
    
    # Создать эпизод об обновлении
    await self.save_episode(
        situation=f"Обновление уверенности в факте {fact_id}",
        actions_taken=["Анализ новых данных", "Корректировка уверенности"],
        outcome="success",
        reasoning=reason,
        satisfaction=0.9
    )
    
async def evolve_skill(self, skill_id, improved_procedure, improved_prompt, performance_improvement, reason):
    # Получить старый навык
    old_skill = await self.neo4j.get_skill(skill_id)
    
    # Создать новую версию
    new_skill = await self.neo4j.create_skill({
        **old_skill,
        version: old_skill['version'] + 1,
        procedure: improved_procedure,
        system_prompt: improved_prompt,
        performance_score: old_skill['performance_score'] + performance_improvement
    })
    
    # Создать связь EVOLVED_FROM
    await self.neo4j.create_evolution_link(new_skill['id'], skill_id, reason)
```

### 3. Сохранение embeddings обратно в Neo4j

```python
# В vector_search_tools.py
async def update_memory_embeddings(memory_type, force):
    # ... существующий код ...
    
    # ДОБАВИТЬ: Сохранение обратно
    for item in items:
        if "embedding" in item or "metadata" in item and "embedding" in item["metadata"]:
            await neo4j_direct.update_node_embedding(
                node_id=item.get("metadata", {}).get("id"),
                embedding=item.get("embedding") or item["metadata"]["embedding"]
            )
```

### 4. Реализация анализа паттернов в REAP

```python
def _find_common_actions(self, episode, similar_episodes):
    # Извлечь действия из всех эпизодов
    all_actions = []
    all_actions.extend(json.loads(episode.get("metadata", {}).get("actions_taken", "[]")))
    
    for ep in similar_episodes:
        actions = json.loads(ep.get("metadata", {}).get("actions_taken", "[]"))
        all_actions.extend(actions)
    
    # Найти частые действия
    from collections import Counter
    action_counts = Counter(all_actions)
    
    # Вернуть действия, встречающиеся > 2 раз
    common = [action for action, count in action_counts.items() if count > 2]
    return common
```

### 5. Архивация старых данных

```python
async def _archive_old_memories(self):
    query = """
    MATCH (n)
    WHERE (n:Fact OR n:Episode OR n:Skill)
    AND n.created_at < datetime() - duration('P90D')
    AND NOT (n)<-[:SUPERSEDES]-()
    SET n:Archived
    RETURN count(n) as archived_count
    """
    result = await self.neo4j.run_query(query)
    return result['archived_count']
```

## 📝 План исправления

### Шаг 1: Создать neo4j_direct.py (1 день)
- Прямое подключение к Neo4j
- Все необходимые Cypher запросы
- Обработка ошибок и retry логика

### Шаг 2: Доработать advanced_memory_adapter.py (1 день)
- Реализовать все TODO методы
- Добавить валидацию данных
- Интегрировать с neo4j_direct

### Шаг 3: Улучшить REAP цикл (1 день)
- Реализовать анализ паттернов
- Добавить архивацию
- Улучшить извлечение навыков

### Шаг 4: Интеграционное тестирование (1 день)
- Проверить сохранение всех типов памяти
- Тестировать эволюцию навыков
- Валидировать векторный поиск

## ⚠️ Риски текущей реализации

1. **Данные не персистентны** - embeddings теряются при перезапуске
2. **Нет версионирования** - факты не могут обновляться корректно
3. **Связи не работают** - граф не строится
4. **Масштабирование** - все держится в памяти Python

## 🎯 Критерии готовности

- [ ] Все TODO в коде заменены на реализацию
- [ ] Прямые Cypher запросы работают
- [ ] Embeddings сохраняются в Neo4j
- [ ] Связи между узлами создаются
- [ ] Архивация работает
- [ ] Интеграционные тесты проходят