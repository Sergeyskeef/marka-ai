// Фрактальная схема: индексы и констрейнты

// Уникальность по id
CREATE CONSTRAINT node_id IF NOT EXISTS FOR (n:Node) REQUIRE n.id IS UNIQUE;

// Индексы по типу и масштабу
CREATE INDEX node_type IF NOT EXISTS FOR (n:Node) ON (n.type);
CREATE INDEX node_scale IF NOT EXISTS FOR (n:Node) ON (n.scale);

// Индекс по масштабу на рёбрах
CREATE INDEX rel_scale IF NOT EXISTS FOR ()-[r]-() ON (r.scale);

// Примечание: адаптер хранит scale/payload/motifs в properties узла Graphiti.

