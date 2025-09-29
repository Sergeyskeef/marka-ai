// Индекс по точному полю
CREATE INDEX episode_msg IF NOT EXISTS FOR (n:Episode) ON (n.msg);

// Полнотекстовый индекс по msg
CALL db.index.fulltext.createNodeIndex('episodeMsgFTS', ['Episode'], ['msg']);
