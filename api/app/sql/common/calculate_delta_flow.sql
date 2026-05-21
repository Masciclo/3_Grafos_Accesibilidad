-- calculate_delta_flow.sql
-- Description: Calculates Delta Flow (Current - Baseline) using a two-layer resilient location mapping.
-- Parameters: result_table, current_network, baseline_network

-- 1. Create the Delta Table with current geometry
DROP TABLE IF EXISTS {result_table};
CREATE TABLE {result_table} AS 
SELECT 
    curr.id as edge_id,
    curr.geometry,
    curr.is_project,
    curr.highway,
    curr.od_flow as flow_current,
    0::numeric as flow_baseline,
    0::numeric as delta_flow
FROM {current_network} curr;

-- 2. LAYER 1: Resilient Spatial Overlap (High Precision)
-- We ignore internal serial IDs because they drift between runs.
-- We use a 5cm tolerance and Hausdorff distance to find nearly identical paths.
WITH location_matches AS (
    SELECT DISTINCT ON (curr.id)
        curr.id, base.od_flow
    FROM {current_network} curr
    JOIN {baseline_network} base ON ST_DWithin(curr.geometry, base.geometry, 0.05)
    WHERE ST_HausdorffDistance(curr.geometry, base.geometry) < 0.05
    ORDER BY curr.id, base.od_flow DESC, ST_Distance(curr.geometry, base.geometry) ASC
)
UPDATE {result_table} r
SET flow_baseline = m.od_flow
FROM location_matches m
WHERE r.edge_id = m.id;

-- 3. LAYER 2: Topological Shatter (Parent-Child Projection)
-- For fragments where the 95% linear overlap failed.
WITH fragments AS (
    SELECT DISTINCT ON (curr.id)
        curr.id, 
        base.od_flow as baseline_flow_value
    FROM {current_network} curr
    JOIN {baseline_network} base ON ST_DWithin(curr.geometry, base.geometry, 10.0)
    WHERE curr.id NOT IN (SELECT edge_id FROM {result_table} WHERE flow_baseline > 0)
      AND ST_Length(ST_Intersection(curr.geometry, ST_Buffer(base.geometry, 10.0))) / NULLIF(ST_Length(curr.geometry), 0) > 0.8
    ORDER BY curr.id, base.od_flow DESC, ST_Distance(curr.geometry, base.geometry) ASC
)
UPDATE {result_table} r
SET flow_baseline = f.baseline_flow_value
FROM fragments f
WHERE r.edge_id = f.id;

-- 4. Final Math
UPDATE {result_table} 
SET delta_flow = flow_current - flow_baseline;

-- 5. Final Index
CREATE INDEX IF NOT EXISTS {result_table}_gist ON {result_table} USING GIST (geometry);
