-- Robust Local Betweenness Centrality Algorithm (Dijkstra-Loop)
-- This script calculates centrality within a 5km radius to avoid memory OOM errors.

-- 1. Create a temporary table to store the results of the ruteo
DROP TABLE IF EXISTS {network_table}_betweenness_results;
CREATE TABLE {network_table}_betweenness_results (
    edge_id bigint,
    flow numeric
);

-- 2. Iterative loop per node to calculate the Shortest Path Tree (SPT)
DO $$
DECLARE
    r RECORD;
BEGIN
    -- We iterate through all nodes that are part of the routable network
    FOR r IN (SELECT id, the_geom FROM {network_table}_vertices_pgr) LOOP
        -- Insert the use of edges directly into the results table
        INSERT INTO {network_table}_betweenness_results (edge_id, flow)
        SELECT edge, 1.0 FROM pgr_dijkstra(
            'SELECT id, source, target, {edge_weight_column} AS cost FROM {network_table}',
            r.id,
            -- Limit destinations to a 5km radius to maintain local realism and memory stability
            ARRAY(SELECT id FROM {network_table}_vertices_pgr v 
                  WHERE ST_DWithin(v.the_geom, r.the_geom, 5000)),
            directed := {directed}
        )
        WHERE edge != -1;
    END LOOP;
END $$;

-- 3. Aggregate results and update the main network table
ALTER TABLE {network_table} ADD COLUMN IF NOT EXISTS betweenness numeric;

UPDATE {network_table} n
SET betweenness = sub.total_flow / (SELECT COUNT(*) FROM {network_table}_vertices_pgr)
FROM (
    SELECT edge_id, SUM(flow) as total_flow
    FROM {network_table}_betweenness_results
    GROUP BY edge_id
) sub
WHERE n.id = sub.edge_id;

-- 4. Cleanup temporary results
DROP TABLE IF EXISTS {network_table}_betweenness_results;
