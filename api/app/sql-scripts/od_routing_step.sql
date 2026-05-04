-- od_routing_step.sql
-- Description: Executes Dijkstra from a single origin to multiple targets with weights.
-- Parameters: network_table, location_prefix, origin_id, edge_weight_column, directed

INSERT INTO {network_table}_betweenness_results (edge_id, flow)
SELECT 
    r.edge,
    d.total_trips as flow
FROM pgr_dijkstra(
    'SELECT id, source, target, {edge_weight_column} AS cost FROM {network_table}',
    {origin_id},
    ARRAY(SELECT target_node FROM {location_prefix}_node_demand WHERE source_node = {origin_id}),
    directed := {directed}
) r
JOIN {location_prefix}_node_demand d 
    ON d.source_node = {origin_id} 
    AND d.target_node = r.end_vid
WHERE r.edge != -1;
