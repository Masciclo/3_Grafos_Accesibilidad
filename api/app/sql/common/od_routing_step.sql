-- od_routing_step.sql
-- Description: Executes Dijkstra for a set of targets from ONE origin.
-- FIXED: We join against the CONSOLIDATED table to ensure each node-to-node path inherits its volume exactly once.

INSERT INTO {network_table}_betweenness_results (edge_id, flow)
SELECT 
    r.edge,
    d.total_trips as flow
FROM pgr_dijkstra(
    'SELECT id, source, target, {edge_weight_column} AS cost FROM {network_table}',
    {origin_id},
    ARRAY(SELECT target_node FROM {location_prefix}_node_demand_consolidated WHERE source_node = {origin_id}),
    directed := {directed}
) r
JOIN {location_prefix}_node_demand_consolidated d 
    ON d.source_node = {origin_id} 
    AND d.target_node = r.end_vid
WHERE r.edge != -1;
