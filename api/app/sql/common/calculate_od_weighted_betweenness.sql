-- calculate_od_weighted_betweenness.sql
-- Phase 3: Aggregates H3-to-H3 demand into Node-to-Node demand for routing.

-- 1. Create a consolidated demand table at the node level
DROP TABLE IF EXISTS {location_prefix}_node_demand;
CREATE TABLE {location_prefix}_node_demand AS
SELECT 
    sn_o.node_id as source_node,
    sn_d.node_id as target_node,
    SUM(m.trips) as total_trips
FROM {od_matrix_table} m
JOIN {location_prefix}_h3_to_node sn_o ON m.h3_origin = sn_o.h3_index
JOIN {location_prefix}_h3_to_node sn_d ON m.h3_dest = sn_d.h3_index
WHERE 
    sn_o.is_coverage_loss = false 
    AND sn_d.is_coverage_loss = false
    AND sn_o.node_id != sn_d.node_id
GROUP BY sn_o.node_id, sn_d.node_id;

-- 2. Audit result
DO $$
BEGIN
    RAISE NOTICE 'Demand aggregation completed.';
    RAISE NOTICE 'Unique Node Pairs with demand: %', (SELECT COUNT(*) FROM {location_prefix}_node_demand);
END $$;
