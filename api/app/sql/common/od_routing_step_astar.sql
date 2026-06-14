-- od_routing_step_astar.sql
-- Description: Executes A* for multiple targets from ONE origin.
-- Optimized: Uses denormalized x1,y1,x2,y2 for Euclidean Heuristic (5).

INSERT INTO {network_table}_betweenness_results (edge_id, flow)
SELECT 
    r.edge,
    d.total_trips as flow
FROM pgr_aStar(
    'SELECT id, source, target, {edge_weight_column} AS cost, x1, y1, x2, y2 FROM {network_table}',
    {origin_id},
    ARRAY(SELECT target_node FROM {location_prefix}_node_demand_consolidated WHERE source_node = {origin_id}),
    directed := {directed},
    heuristic := 5
) r
JOIN {location_prefix}_node_demand_consolidated d 
    ON d.source_node = {origin_id} 
    AND d.target_node = r.end_vid
WHERE r.edge != -1;
