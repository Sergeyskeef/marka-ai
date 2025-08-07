# 📋 ПЛАН РАСШИРЕНИЯ GRAPHITI ДЛЯ ПРОДВИНУТОЙ ПАМЯТИ

**Фаза 2:** Реализация трех типов памяти и REAP цикла  
**Цель:** Превратить Graphiti в полноценную систему самообучения

---

## 🔍 Анализ текущей реализации

### Что есть сейчас:
1. **Базовая интеграция Graphiti + Neo4j**
   - HTTP API для создания/поиска узлов
   - Простая структура: Node(id, type, properties)
   - Кеширование через Redis
   - Event bus для мониторинга

2. **Проблемы текущей реализации:**
   - Нет различия между типами памяти
   - Нет би-темпоральности (когда произошло vs когда узнано)
   - Нет векторного поиска
   - Нет связей между узлами
   - Нет версионирования фактов

---

## 🏗️ Архитектура трех типов памяти

### 1. Семантическая память (Факты)
```cypher
(:Fact {
  id: UUID,
  subject: String,      // О ком/чем
  predicate: String,    // Отношение/действие
  object: String,       // Что/кого
  confidence: Float,    // Уверенность 0-1
  valid_from: DateTime, // Когда факт стал истинным
  valid_to: DateTime?,  // null = текущий факт
  learned_at: DateTime, // Когда агент узнал
  source: String,       // Откуда информация
  embedding: Float[]    // Векторное представление
})

// Отношения
(:Fact)-[:CONTRADICTS]->(:Fact)
(:Fact)-[:SUPPORTS]->(:Fact)
(:Fact)-[:SUPERSEDES]->(:Fact)
```

### 2. Эпизодическая память (События)
```cypher
(:Episode {
  id: UUID,
  occurred_at: DateTime,    // Когда произошло
  recorded_at: DateTime,    // Когда записано
  situation: String,        // Описание ситуации
  actions_taken: String[],  // Что делал агент
  outcome: String,          // success/failure/partial
  reasoning: String,        // Ход рассуждений
  lesson_learned: String,   // Извлеченный урок
  satisfaction: Float,      // Оценка результата
  embedding: Float[]
})

// Отношения
(:Episode)-[:LED_TO]->(:Episode)
(:Episode)-[:SIMILAR_TO {score}]->(:Episode)
(:Episode)-[:USED_FACT]->(:Fact)
(:Episode)-[:LEARNED_SKILL]->(:Skill)
```

### 3. Процедурная память (Навыки)
```cypher
(:Skill {
  id: UUID,
  name: String,
  trigger_patterns: String[],  // Когда применять
  procedure: String,           // Что делать
  system_prompt: String,       // Промпт для LLM
  version: Integer,
  performance_score: Float,    // Эффективность
  usage_count: Integer,
  last_used: DateTime,
  created_at: DateTime,
  evolved_from: UUID?          // Предыдущая версия
})

// Отношения  
(:Skill)-[:EVOLVED_FROM]->(:Skill)
(:Skill)-[:REQUIRES]->(:Skill)
(:Skill)-[:USED_IN]->(:Episode)
```

---

## 🔄 REAP Цикл самообучения

### Reflect (Рефлексия)
```python
async def reflect_on_experience(episode_id: str):
    """Анализ прошедшего эпизода"""
    # 1. Загрузить эпизод
    episode = await get_episode(episode_id)
    
    # 2. Найти похожие эпизоды
    similar = await find_similar_episodes(episode)
    
    # 3. Проанализировать паттерны
    patterns = await analyze_patterns(episode, similar)
    
    # 4. Оценить эффективность
    effectiveness = await evaluate_effectiveness(episode)
    
    return ReflectionResult(patterns, effectiveness, insights)
```

### Extract (Извлечение)
```python
async def extract_knowledge(reflection: ReflectionResult):
    """Извлечь знания из рефлексии"""
    # 1. Новые факты
    facts = await extract_facts(reflection)
    
    # 2. Обновления навыков
    skill_updates = await extract_skill_improvements(reflection)
    
    # 3. Уроки
    lessons = await extract_lessons(reflection)
    
    return KnowledgePackage(facts, skill_updates, lessons)
```

### Apply (Применение)
```python
async def apply_knowledge(knowledge: KnowledgePackage):
    """Применить полученные знания"""
    # 1. Сохранить новые факты
    for fact in knowledge.facts:
        await save_fact_with_validation(fact)
    
    # 2. Эволюционировать навыки
    for update in knowledge.skill_updates:
        await evolve_skill(update)
    
    # 3. Обновить процедуры
    await update_procedures(knowledge.lessons)
```

### Persist (Закрепление)
```python
async def persist_learnings():
    """Закрепить изменения"""
    # 1. Оптимизировать граф
    await optimize_graph_structure()
    
    # 2. Обновить индексы
    await update_search_indices()
    
    # 3. Архивировать старые данные
    await archive_old_memories()
```

---

## 📝 План реализации

### Шаг 1: Расширение модели данных (День 1-2)
1. Создать Cypher скрипты для новых типов узлов
2. Добавить индексы для би-темпоральных запросов
3. Настроить векторные индексы
4. Создать миграцию существующих данных

### Шаг 2: Обновление API (День 3-4)
1. Расширить GraphitiMemoryAdapter для новых типов
2. Добавить методы для работы с отношениями
3. Реализовать би-темпоральные запросы
4. Добавить векторный поиск

### Шаг 3: Реализация REAP цикла (День 5-7)
1. Создать модуль learning_system.py
2. Реализовать каждую фазу REAP
3. Добавить background задачи для обучения
4. Интегрировать с агентом

### Шаг 4: Инструменты для агента (День 8-9)
1. Обновить memory_tools.py для новых типов
2. Добавить инструменты для REAP
3. Создать инструменты анализа памяти
4. Добавить отладочные инструменты

### Шаг 5: Тестирование и оптимизация (День 10)
1. Unit тесты для каждого компонента
2. Интеграционные тесты REAP цикла
3. Нагрузочное тестирование
4. Оптимизация запросов

---

## 🚀 Технические детали реализации

### 1. Векторный поиск в Neo4j
```cypher
// Создание векторного индекса
CREATE VECTOR INDEX episode_embeddings
FOR (e:Episode) ON e.embedding
OPTIONS {
  indexConfig: {
    `vector.dimensions`: 1536,
    `vector.similarity_function`: 'cosine'
  }
}

// Поиск похожих эпизодов
MATCH (e:Episode)
WHERE e.embedding <-> $query_embedding < 0.3
RETURN e
ORDER BY e.embedding <-> $query_embedding
LIMIT 10
```

### 2. Би-темпоральные запросы
```cypher
// Найти факты, действительные на определенную дату
MATCH (f:Fact)
WHERE f.valid_from <= $target_date 
  AND (f.valid_to IS NULL OR f.valid_to > $target_date)
RETURN f

// История изменений факта
MATCH (f1:Fact)-[:SUPERSEDES*]->(f2:Fact)
WHERE f1.subject = $subject AND f1.predicate = $predicate
RETURN f1, f2
ORDER BY f1.valid_from DESC
```

### 3. Эволюция навыков
```cypher
// Создать новую версию навыка
CREATE (new:Skill {
  id: randomUUID(),
  name: $name,
  version: $old_version + 1,
  procedure: $improved_procedure,
  performance_score: $new_score,
  created_at: datetime()
})
WITH new
MATCH (old:Skill {id: $old_id})
CREATE (new)-[:EVOLVED_FROM {
  reason: $reason,
  improvement: $new_score - $old_score
}]->(old)
RETURN new
```

---

## 📊 Метрики успеха

- **Точность памяти:** 85%+ (правильные факты)
- **Скорость обучения:** 20% улучшение за 100 эпизодов
- **Эффективность навыков:** +30% performance score
- **Время поиска:** <100ms для векторного поиска
- **Объем памяти:** Эффективное хранение 1M+ узлов

---

## ⚠️ Риски и митигация

1. **Производительность Neo4j**
   - Риск: Замедление при росте графа
   - Митигация: Партиционирование, архивация

2. **Качество векторных представлений**
   - Риск: Плохие embeddings = плохой поиск
   - Митигация: Fine-tuning модели embeddings

3. **Циклы в обучении**
   - Риск: Агент может зациклиться на плохих паттернах
   - Митигация: Валидация и human-in-the-loop

---

*Следующий шаг: Начать с расширения модели данных в Neo4j*