// Graph Schema v1 — DDL и тестовые данные для pytest

// Constraints
CREATE CONSTRAINT user_id IF NOT EXISTS FOR (u:User) REQUIRE u.id IS UNIQUE;
CREATE CONSTRAINT preference_id IF NOT EXISTS FOR (p:Preference) REQUIRE p.id IS UNIQUE;
CREATE CONSTRAINT toolcall_id IF NOT EXISTS FOR (t:ToolCall) REQUIRE t.id IS UNIQUE;
CREATE CONSTRAINT outcome_id IF NOT EXISTS FOR (o:Outcome) REQUIRE o.id IS UNIQUE;
CREATE CONSTRAINT diary_entry_id IF NOT EXISTS FOR (d:DiaryEntry) REQUIRE d.id IS UNIQUE;
CREATE CONSTRAINT concept_id IF NOT EXISTS FOR (c:Concept) REQUIRE c.id IS UNIQUE;

// Indexes
CREATE INDEX user_email IF NOT EXISTS FOR (u:User) ON (u.email);
CREATE INDEX user_created_at IF NOT EXISTS FOR (u:User) ON (u.created_at);
CREATE INDEX preference_key IF NOT EXISTS FOR (p:Preference) ON (p.key);
CREATE INDEX toolcall_user_tool IF NOT EXISTS FOR (t:ToolCall) ON (t.user_id, t.tool_name);
CREATE INDEX toolcall_started_at IF NOT EXISTS FOR (t:ToolCall) ON (t.started_at);
CREATE INDEX toolcall_status IF NOT EXISTS FOR (t:ToolCall) ON (t.status);
CREATE INDEX outcome_toolcall IF NOT EXISTS FOR (o:Outcome) ON (o.toolcall_id);
CREATE INDEX outcome_success IF NOT EXISTS FOR (o:Outcome) ON (o.success);
CREATE INDEX outcome_created_at IF NOT EXISTS FOR (o:Outcome) ON (o.created_at);
CREATE INDEX diary_user IF NOT EXISTS FOR (d:DiaryEntry) ON (d.user_id);
CREATE INDEX diary_timestamp IF NOT EXISTS FOR (d:DiaryEntry) ON (d.timestamp);
CREATE INDEX diary_content IF NOT EXISTS FOR (d:DiaryEntry) ON (d.content);
CREATE INDEX concept_name IF NOT EXISTS FOR (c:Concept) ON (c.name);
CREATE INDEX concept_category IF NOT EXISTS FOR (c:Concept) ON (c.category);
CREATE INDEX concept_description IF NOT EXISTS FOR (c:Concept) ON (c.description);

// Test data
MERGE (u:User {id: 'test_user_001'})
  SET u.email='test@example.com', u.created_at=timestamp();
MERGE (p:Preference {id: 'pref_001'})
  SET p.key='theme', p.value='dark';
MERGE (d:DiaryEntry {id: 'diary_001'})
  SET d.user_id='test_user_001', d.timestamp=timestamp(), d.content='Test entry';
MATCH (u:User {id:'test_user_001'}), (p:Preference {id:'pref_001'})
  MERGE (u)-[:PREFERS]->(p);
MATCH (u:User {id:'test_user_001'}), (d:DiaryEntry {id:'diary_001'})
  MERGE (u)-[:WRITES]->(d);

