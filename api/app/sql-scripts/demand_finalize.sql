-- demand_finalize.sql
-- Description: Aggregates total OD flow and updates the network table.

ALTER TABLE {network_table} ADD COLUMN IF NOT EXISTS od_flow numeric;

UPDATE {network_table} n
SET od_flow = sub.total_flow
FROM (
    SELECT edge_id, SUM(flow) as total_flow
    FROM {network_table}_betweenness_results
    GROUP BY edge_id
) sub
WHERE n.id = sub.edge_id;

-- Cleanup
DROP TABLE IF EXISTS {network_table}_betweenness_results;
