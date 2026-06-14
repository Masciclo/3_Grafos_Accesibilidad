-- batch_od_routing.sql
-- Description: Server-side execution of OD routing using A* or Dijkstra.
-- This eliminates the Python loop overhead.

DO $$
DECLARE
    r RECORD;
    directed_bool BOOLEAN := {directed};
BEGIN
    FOR r IN (SELECT source_node, target_node, total_trips FROM {location_prefix}_node_demand_consolidated) LOOP
        INSERT INTO {network_table}_betweenness_results (edge_id, flow)
        SELECT 
            res.edge,
            r.total_trips as flow
        FROM pgr_aStar(
            'SELECT id, source, target, {edge_weight_column} AS cost, x1, y1, x2, y2 FROM {network_table}',
            r.source_node,
            r.target_node,
            directed := directed_bool,
            heuristic := 5 -- Euclidean distance
        ) res
        WHERE res.edge != -1;
    END LOOP;
END $$;
