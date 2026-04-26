-- Harmonized Accessibility Centrality Algorithm (pgRouting Standard)
-- This script uses pgr_dijkstra on the source/target topology for consistency.

-- 1. Prepare H3 centroid and find nearest routing node
ALTER TABLE {h3_table_name} 
ADD COLUMN IF NOT EXISTS centroid GEOMETRY(POINT, {srid});

UPDATE {h3_table_name}
SET centroid = ST_Centroid(geometry);

ALTER TABLE {h3_table_name} 
ADD COLUMN IF NOT EXISTS nearest_node_id INTEGER;

-- Create spatial index for fast nearest neighbor search
CREATE INDEX IF NOT EXISTS node_geom_idx ON {node_table} USING gist(geom);

UPDATE {h3_table_name} AS h
SET nearest_node_id = (
    SELECT id FROM {node_table} AS n
    ORDER BY h.centroid <-> n.the_geom ASC
    LIMIT 1
);

-- 2. Calculate Accessibility using pgr_dijkstra on the synchronized topology
ALTER TABLE {h3_table_name} 
ADD COLUMN IF NOT EXISTS accessibility FLOAT;

-- Aggregate cost to all other reachable nodes within a baseline set
-- (Using the same source/target logic as betweenness_centrality.sql)
UPDATE {h3_table_name} AS h1
SET accessibility = (
    SELECT SUM(cost) FROM (
        SELECT cost FROM pgr_dijkstra(
            'SELECT id, source, target, cost FROM {table_name}',
            h1.nearest_node_id,
            ARRAY(SELECT nearest_node_id FROM {h3_table_name} WHERE nearest_node_id IS NOT NULL),
            directed := false
        )
    ) AS total_cost
)
WHERE h1.nearest_node_id IS NOT NULL;
