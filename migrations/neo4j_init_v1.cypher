CREATE CONSTRAINT user_id IF NOT EXISTS
  FOR (u:User) REQUIRE u.id IS UNIQUE;

CREATE INDEX user_email IF NOT EXISTS
  FOR (u:User) ON (u.email);

CREATE INDEX user_created_at IF NOT EXISTS
  FOR (u:User) ON (u.created_at);

CREATE CONSTRAINT preference_id IF NOT EXISTS
  FOR (p:Preference) REQUIRE p.id IS UNIQUE;

CREATE INDEX preference_key IF NOT EXISTS
  FOR (p:Preference) ON (p.key);

CREATE INDEX user_pref_relationship IF NOT EXISTS
  FOR ()-[r:PREFERS]-() ON (r.key);

CREATE CONSTRAINT toolcall_id IF NOT EXISTS
  FOR (t:ToolCall) REQUIRE t.id IS UNIQUE;

CREATE INDEX toolcall_user_tool IF NOT EXISTS
  FOR (t:ToolCall) ON (t.user_id, t.tool_name);

CREATE INDEX toolcall_started_at IF NOT EXISTS
  FOR (t:ToolCall) ON (t.started_at);

CREATE INDEX toolcall_status IF NOT EXISTS
  FOR (t:ToolCall) ON (t.status);

CREATE CONSTRAINT outcome_id IF NOT EXISTS
  FOR (o:Outcome) REQUIRE o.id IS UNIQUE;

CREATE INDEX outcome_toolcall IF NOT EXISTS
  FOR (o:Outcome) ON (o.toolcall_id);

CREATE INDEX outcome_success IF NOT EXISTS
  FOR (o:Outcome) ON (o.success);

CREATE INDEX outcome_created_at IF NOT EXISTS
  FOR (o:Outcome) ON (o.created_at);

CREATE CONSTRAINT diary_entry_id IF NOT EXISTS
  FOR (d:DiaryEntry) REQUIRE d.id IS UNIQUE;

CREATE INDEX diary_user IF NOT EXISTS
  FOR (d:DiaryEntry) ON (d.user_id);

CREATE INDEX diary_timestamp IF NOT EXISTS
  FOR (d:DiaryEntry) ON (d.timestamp);

CREATE FULLTEXT INDEX diary_content IF NOT EXISTS
  FOR (d:DiaryEntry) ON EACH [d.content];

CREATE CONSTRAINT concept_id IF NOT EXISTS
  FOR (c:Concept) REQUIRE c.id IS UNIQUE;

CREATE INDEX concept_name IF NOT EXISTS
  FOR (c:Concept) ON (c.name);

CREATE INDEX concept_category IF NOT EXISTS
  FOR (c:Concept) ON (c.category);

CREATE FULLTEXT INDEX concept_description IF NOT EXISTS
  FOR (c:Concept) ON EACH [c.description];

MERGE (u:User {
  id: "test_user_001",
  email: "test@example.com",
  name: "Test User",
  created_at: datetime(),
  is_active: true
});

MERGE (p:Preference {
  id: "pref_001",
  key: "response_style",
  value: "detailed",
  created_at: datetime()
});

MATCH (u:User {id: "test_user_001"})
MATCH (p:Preference {id: "pref_001"})
MERGE (u)-[:PREFERS {created_at: datetime()}]->(p);

MERGE (d:DiaryEntry {
  id: "diary_001",
  user_id: "test_user_001",
  content: "Сегодня я протестировал новую систему памяти Graphiti с Neo4j",
  timestamp: datetime(),
  mood: "excited",
  tags: ["testing", "graphiti", "neo4j"]
});

MATCH (u:User {id: "test_user_001"})
MATCH (d:DiaryEntry {id: "diary_001"})
MERGE (u)-[:WRITES]->(d);

SHOW INDEXES;

SHOW CONSTRAINTS;

MATCH (n) RETURN labels(n) as NodeType, count(n) as Count ORDER BY Count DESC;
