# 🧠 АРХИТЕКТУРА ПАМЯТИ МАРКА НА БАЗЕ GRAPHITI

**Дата:** Январь 2025  
**Архитектор:** AI Assistant  
**Базовая технология:** Graphiti (Zep) + Neo4j

---

## 📊 Обоснование выбора Graphiti

После детального анализа, Graphiti - оптимальный выбор для Марка:

### Ключевые преимущества:
1. **Би-темпоральная модель** - отслеживание когда факт произошел и когда был изучен
2. **Графовые связи** - сложные отношения между сущностями 
3. **Производительность** - 75.1% точность, p95 < 0.63с
4. **Инкрементальные обновления** - факты эволюционируют со временем
5. **Уже интегрирована** - Neo4j работает в текущем проекте

---

## 🏗️ Архитектура трех типов памяти в Graphiti

### 1. Семантическая память (Факты и знания)

**Структура в Neo4j:**
```cypher
// Узел факта
(:Fact {
  id: "uuid",
  subject: "Сергей",
  predicate: "любимый_язык",
  object: "Python",
  confidence: 0.95,
  valid_from: datetime(),
  valid_to: null,  // null = текущий факт
  learned_at: datetime(),
  source: "user_message|inference|observation",
  embedding: float[]  // для векторного поиска
})

// Связи между фактами
(:Fact)-[:CONTRADICTS {resolved_at, resolution}]->(:Fact)
(:Fact)-[:SUPPORTS {evidence_strength}]->(:Fact)
(:Fact)-[:SUPERSEDES {reason}]->(:Fact)
```

**Особенности:**
- Би-темпоральность для отслеживания эволюции знаний
- Автоматическое разрешение противоречий
- Векторные эмбеддинги для семантического поиска

### 2. Эпизодическая память (Опыт и события)

**Структура в Neo4j:**
```cypher
// Узел эпизода
(:Episode {
  id: "uuid",
  occurred_at: datetime(),  // когда произошло
  recorded_at: datetime(),  // когда записано
  situation: "Пользователь попросил написать парсер",
  reasoning: "Использовал BeautifulSoup как надежное решение",
  actions_taken: ["analyzed_requirements", "wrote_code", "tested"],
  outcome: "success",
  satisfaction_score: 0.9,
  lesson_learned: "BeautifulSoup хорошо работает для простого HTML",
  embedding: float[]
})

// Связи эпизодов
(:Episode)-[:SIMILAR_TO {similarity_score}]->(:Episode)
(:Episode)-[:LED_TO]->(:Episode)  // причинно-следственная связь
(:Episode)-[:REFERENCES]->(:Fact)  // использованные факты
(:Episode)-[:LEARNED]->(:Skill)  // полученные навыки
```

**Использование для обучения:**
```python
# Поиск похожих успешных эпизодов
MATCH (e:Episode {outcome: "success"})
WHERE e.embedding <-> $current_embedding < 0.3
RETURN e ORDER BY e.satisfaction_score DESC LIMIT 5
```

### 3. Процедурная память (Навыки и алгоритмы)

**Структура в Neo4j:**
```cypher
// Узел процедуры/навыка
(:Skill {
  id: "uuid",
  name: "parse_website",
  trigger_patterns: ["парсинг", "scraping", "извлечь данные"],
  system_prompt: "...",
  version: 3,
  performance_score: 0.85,
  created_at: datetime(),
  last_used: datetime(),
  usage_count: 42,
  evolution_history: [...]  // JSON с историей версий
})

// Связи навыков
(:Skill)-[:EVOLVED_FROM {improvements}]->(:Skill)
(:Skill)-[:REQUIRES]->(:Skill)  // зависимости
(:Skill)-[:USED_IN]->(:Episode)  // где применялся
```

---

## 🔄 Механизм самообучения через Graphiti

### 1. REAP цикл с графовой памятью

```python
# app/learning/graphiti_reap.py
from graphiti_client import GraphitiClient
from neo4j import AsyncGraphDatabase

class GraphitiLearningSystem:
    def __init__(self, graphiti_url: str, neo4j_uri: str):
        self.graphiti = GraphitiClient(graphiti_url)
        self.neo4j = AsyncGraphDatabase.driver(neo4j_uri)
    
    async def reflect_on_experience(self, experience: dict):
        """1. REFLECT - Анализ опыта через граф"""
        async with self.neo4j.session() as session:
            # Найти связанные эпизоды
            similar_episodes = await session.run("""
                MATCH (e:Episode)
                WHERE e.embedding <-> $embedding < 0.3
                RETURN e, 
                       [(e)-[:LED_TO]->(outcome:Episode) | outcome] as outcomes,
                       [(e)-[:REFERENCES]->(f:Fact) | f] as facts
                ORDER BY e.occurred_at DESC
                LIMIT 10
            """, embedding=experience['embedding'])
            
            # Анализ паттернов
            reflection = await self.analyze_patterns(
                current=experience,
                similar=similar_episodes,
                temporal_context=await self.get_temporal_context()
            )
            
        return reflection
    
    async def extract_knowledge(self, reflection: dict):
        """2. EXTRACT - Извлечение знаний с учетом времени"""
        extracted = {
            'facts': [],
            'episodes': [],
            'skill_updates': []
        }
        
        # Извлечь новые факты с би-темпоральностью
        for fact in reflection['discovered_facts']:
            fact_node = {
                'type': 'Fact',
                'properties': {
                    **fact,
                    'valid_from': datetime.now(),
                    'learned_at': datetime.now(),
                    'confidence': self.calculate_confidence(fact)
                }
            }
            
            # Проверить противоречия
            conflicts = await self.find_conflicting_facts(fact_node)
            if conflicts:
                fact_node['resolves'] = conflicts
                
            extracted['facts'].append(fact_node)
        
        # Создать эпизод с полным контекстом
        episode = {
            'type': 'Episode',
            'properties': {
                'occurred_at': reflection['experience']['timestamp'],
                'recorded_at': datetime.now(),
                'situation': reflection['situation'],
                'reasoning': reflection['reasoning_chain'],
                'outcome': reflection['outcome'],
                'lesson_learned': reflection['key_lesson']
            }
        }
        extracted['episodes'].append(episode)
        
        return extracted
    
    async def apply_knowledge(self, extracted: dict):
        """3. APPLY - Применение знаний через граф"""
        async with self.neo4j.session() as session:
            # Транзакционное обновление графа
            async with session.begin_transaction() as tx:
                # Обновить факты с версионированием
                for fact in extracted['facts']:
                    if 'resolves' in fact:
                        # Закрыть старые версии фактов
                        await tx.run("""
                            MATCH (old:Fact {subject: $subject, predicate: $predicate})
                            WHERE old.valid_to IS NULL
                            SET old.valid_to = datetime()
                            CREATE (old)-[:SUPERSEDED_BY {reason: $reason}]->(new:Fact $props)
                            RETURN new
                        """, subject=fact['properties']['subject'],
                            predicate=fact['properties']['predicate'],
                            reason=fact['resolves']['reason'],
                            props=fact['properties'])
                    else:
                        # Создать новый факт
                        await tx.run("CREATE (f:Fact $props)", props=fact['properties'])
                
                # Сохранить эпизод со связями
                for episode in extracted['episodes']:
                    result = await tx.run("""
                        CREATE (e:Episode $props)
                        WITH e
                        // Связать с использованными фактами
                        UNWIND $fact_ids as fact_id
                        MATCH (f:Fact {id: fact_id})
                        CREATE (e)-[:REFERENCES]->(f)
                        // Связать с похожими эпизодами
                        WITH e
                        MATCH (similar:Episode)
                        WHERE similar.embedding <-> e.embedding < 0.2
                        AND similar.id <> e.id
                        CREATE (e)-[:SIMILAR_TO {score: 1 - (similar.embedding <-> e.embedding)}]->(similar)
                        RETURN e
                    """, props=episode['properties'], 
                         fact_ids=episode.get('referenced_facts', []))
                
                # Обновить навыки
                for skill_update in extracted['skill_updates']:
                    await self.evolve_skill(tx, skill_update)
                
                await tx.commit()
    
    async def persist_learnings(self, applied_knowledge: dict):
        """4. PERSIST - Закрепление и оптимизация"""
        # Создать снапшот состояния памяти
        snapshot = await self.create_memory_snapshot()
        
        # Оптимизировать граф
        await self.optimize_graph_structure()
        
        # Обновить индексы для быстрого поиска
        await self.update_search_indices()
        
        # Уведомить об изменениях
        await self.notify_learning_complete(applied_knowledge)
```

### 2. Временные запросы для анализа эволюции

```cypher
// Как изменялись знания о предпочтениях пользователя
MATCH (f:Fact {subject: "user", predicate: "prefers"})
RETURN f.object as preference,
       f.valid_from as from,
       f.valid_to as to,
       f.confidence as confidence
ORDER BY f.valid_from

// Найти цепочки успешных действий
MATCH path = (e1:Episode {outcome: "success"})-[:LED_TO*1..5]->(e2:Episode {outcome: "success"})
WHERE e1.occurred_at < e2.occurred_at
RETURN path, 
       reduce(score = 0, e IN nodes(path) | score + e.satisfaction_score) as total_score
ORDER BY total_score DESC
LIMIT 10
```

### 3. Адаптивное обновление навыков

```python
async def evolve_skill(self, tx, skill_update: dict):
    """Эволюция навыка на основе использования"""
    # Получить текущую версию навыка
    current = await tx.run("""
        MATCH (s:Skill {name: $name})
        WHERE s.version = 
            coalesce((
                MATCH (s2:Skill {name: $name}) 
                RETURN max(s2.version)
            ), 0)
        RETURN s
    """, name=skill_update['name'])
    
    if current:
        # Создать новую версию
        new_version = {
            **current['properties'],
            'version': current['properties']['version'] + 1,
            'system_prompt': skill_update['improved_prompt'],
            'performance_score': skill_update['new_score'],
            'evolved_at': datetime.now()
        }
        
        # Сохранить с историей
        await tx.run("""
            CREATE (new:Skill $props)
            WITH new
            MATCH (old:Skill {name: $name, version: $version})
            CREATE (new)-[:EVOLVED_FROM {
                improvements: $improvements,
                performance_gain: $gain
            }]->(old)
            RETURN new
        """, props=new_version,
             name=skill_update['name'],
             version=current['properties']['version'],
             improvements=skill_update['improvements'],
             gain=skill_update['new_score'] - current['properties']['performance_score'])
```

---

## 🚀 Оптимизации для производительности

### 1. Индексы Neo4j
```cypher
// Векторный индекс для семантического поиска
CREATE VECTOR INDEX fact_embeddings FOR (f:Fact) ON f.embedding
OPTIONS {indexConfig: {`vector.dimensions`: 1536, `vector.similarity_function`: 'cosine'}}

// Композитные индексы для временных запросов
CREATE INDEX fact_temporal ON :Fact(subject, predicate, valid_from, valid_to)
CREATE INDEX episode_temporal ON :Episode(occurred_at, outcome)

// Текстовые индексы
CREATE TEXT INDEX fact_search ON :Fact(subject, object)
CREATE TEXT INDEX episode_search ON :Episode(situation, lesson_learned)
```

### 2. Кеширование через Redis
```python
class GraphitiCache:
    def __init__(self, redis_client):
        self.redis = redis_client
        self.ttl = {
            'facts': 3600,      # 1 час
            'episodes': 1800,   # 30 минут
            'skills': 7200      # 2 часа
        }
    
    async def get_or_fetch(self, key: str, fetcher, ttl_type: str):
        # Проверить кеш
        cached = await self.redis.get(f"graphiti:{key}")
        if cached:
            return json.loads(cached)
        
        # Загрузить из Graphiti
        data = await fetcher()
        
        # Сохранить в кеш
        await self.redis.setex(
            f"graphiti:{key}",
            self.ttl[ttl_type],
            json.dumps(data)
        )
        
        return data
```

### 3. Батчинг запросов
```python
async def batch_memory_operations(operations: List[dict]):
    """Группировка операций для эффективности"""
    async with neo4j_session() as session:
        async with session.begin_transaction() as tx:
            # Группировать по типам
            creates = [op for op in operations if op['type'] == 'create']
            updates = [op for op in operations if op['type'] == 'update']
            
            # Батч создание
            if creates:
                await tx.run("""
                    UNWIND $nodes as node
                    CREATE (n:Node) SET n = node.properties
                """, nodes=creates)
            
            # Батч обновление
            if updates:
                await tx.run("""
                    UNWIND $updates as update
                    MATCH (n {id: update.id})
                    SET n += update.properties
                """, updates=updates)
            
            await tx.commit()
```

---

## 📈 Метрики и мониторинг

### 1. Ключевые метрики Graphiti
```python
@dataclass
class GraphitiMetrics:
    # Производительность
    query_latency_p95: float  # целевое < 0.63с
    write_latency_p95: float  # целевое < 1с
    
    # Качество памяти
    fact_accuracy: float      # % корректных фактов
    episode_relevance: float  # % релевантных эпизодов
    skill_improvement: float  # средний прирост performance_score
    
    # Использование
    total_nodes: int
    total_edges: int
    memory_size_mb: float
    
    # Обучение
    facts_learned_per_day: int
    episodes_per_day: int
    skill_evolutions_per_week: int
```

### 2. Дашборд для мониторинга
```python
# Grafana запросы для Neo4j
memory_growth = """
MATCH (n)
RETURN 
  labels(n)[0] as type,
  count(n) as count,
  date(avg(n.created_at)) as date
ORDER BY date
"""

learning_effectiveness = """
MATCH (e:Episode)
WHERE e.occurred_at > datetime() - duration('P7D')
RETURN 
  date(e.occurred_at) as day,
  avg(CASE WHEN e.outcome = 'success' THEN 1 ELSE 0 END) as success_rate,
  avg(e.satisfaction_score) as avg_satisfaction
ORDER BY day
"""
```

---

## 🎯 Интеграция с остальной системой

### 1. OpenAI Agents SDK + Graphiti
```python
from agents import Agent, function_tool
from graphiti_client import GraphitiClient

@function_tool
async def search_memory(query: str, memory_type: str = "all") -> str:
    """Поиск в памяти Graphiti"""
    results = await graphiti.search(
        query=query,
        types=[memory_type] if memory_type != "all" else ["Fact", "Episode", "Skill"],
        use_vector_search=True,
        use_keyword_search=True,
        max_results=10
    )
    return format_memory_results(results)

@function_tool
async def remember_fact(subject: str, predicate: str, object: str) -> str:
    """Сохранить факт в памяти"""
    fact = await graphiti.add_fact(
        subject=subject,
        predicate=predicate,
        object=object,
        confidence=0.9,
        source="user_interaction"
    )
    return f"Запомнил: {fact}"

mark_agent = Agent(
    name="Mark",
    model="gpt-4.1-mini",  # Ваша модель!
    instructions="Ты - Марк, самообучающийся AI с графовой памятью",
    tools=[search_memory, remember_fact]
)
```

### 2. LangGraph workflow с Graphiti
```python
from langgraph.graph import StateGraph

class MarkState(TypedDict):
    user_input: str
    memory_context: dict
    reasoning: str
    response: str
    learnings: list

mark_workflow = StateGraph(MarkState)

# Узлы
mark_workflow.add_node("search_memory", graphiti_memory_search)
mark_workflow.add_node("reason", reason_with_memory)
mark_workflow.add_node("respond", generate_response)
mark_workflow.add_node("learn", extract_and_save_learnings)

# Поток
mark_workflow.set_entry_point("search_memory")
mark_workflow.add_edge("search_memory", "reason")
mark_workflow.add_edge("reason", "respond")
mark_workflow.add_edge("respond", "learn")

mark_system = mark_workflow.compile()
```

---

## 🏁 Выводы

Graphiti предоставляет идеальную основу для памяти Марка:

1. **Би-темпоральность** - отслеживание эволюции знаний
2. **Графовые связи** - сложные отношения между сущностями
3. **Производительность** - <1с для сложных запросов
4. **Масштабируемость** - готова к росту объема памяти
5. **Гибкость** - любые типы узлов и связей

С предложенной архитектурой трех типов памяти и REAP циклом, Марк сможет:
- Учиться на каждом взаимодействии
- Отслеживать изменения знаний во времени
- Находить сложные паттерны в опыте
- Эволюционировать свои навыки

Это создаст основу для по-настоящему сложного и умного агента!

---

*Следующий шаг: Начать с интеграции трех типов памяти в существующую Graphiti инфраструктуру.*