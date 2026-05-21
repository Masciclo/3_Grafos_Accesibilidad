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
