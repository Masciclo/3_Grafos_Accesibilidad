-- Calculate Connected Components for pgRouting Graph
-- Generates:
-- 1. {result_table}: Edge table with 'component' ID (for H3 intersection)
-- 2. {result_table}_nodes: Node table with 'component' ID (for Snapping)

DROP TABLE IF EXISTS {result_table}_nodes;
CREATE TABLE {result_table}_nodes AS
SELECT node as id, component
FROM pgr_connectedComponents(
    'SELECT id, source, target, ST_Length(geometry) as cost FROM {table_name}'
);

DROP TABLE IF EXISTS {result_table};
CREATE TABLE {result_table} AS
SELECT 
    n.*,
    n.geometry as the_geom,
    c.component
FROM {table_name} n
JOIN {result_table}_nodes c ON n.source = c.id;

-- Create spatial indices
CREATE INDEX IF NOT EXISTS {result_table}_geom_idx ON {result_table} USING GIST (the_geom);
CREATE INDEX IF NOT EXISTS {result_table}_nodes_idx ON {result_table}_nodes (id);
