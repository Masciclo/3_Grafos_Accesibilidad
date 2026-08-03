-- calculate_delta_flow.sql
-- Description: Calculates Delta Flow (Current - Baseline) using a three-layer resilient location mapping.
-- Parameters: result_table, current_network, baseline_network, ma_distance (Magnetismo a Antecesor)

-- 1. Create the Delta Table with participating flags
DROP TABLE IF EXISTS {result_table};
CREATE TABLE {result_table} AS
SELECT 
    curr.id as edge_id,
    curr.geometry,
    curr.is_project,
    curr.project_id,
    curr.od_flow as flow_current,
    0.0::numeric as flow_baseline,
    0.0::numeric as delta_flow,
    FALSE as participating_in_analysis
FROM {current_network} curr;

-- 2. LAYER 0: Persistent Lineage Match (Task 18.6)
-- Rule A Implementation: Use the unbreakable link established during the Phase 18 Refactoring.
WITH lineage_matches AS (
    SELECT 
        curr.id,
        AVG(base.od_flow) as baseline_flow -- Simple average as the segment was split from this parent
    FROM {current_network} curr
    JOIN {baseline_network} base ON curr.parent_baseline_id = base.id
    GROUP BY curr.id
)
UPDATE {result_table} r
SET flow_baseline = m.baseline_flow,
    participating_in_analysis = TRUE
FROM lineage_matches m
WHERE r.edge_id = m.id;

-- 3. LAYER 1: Resilient Spatial Overlap (High Precision)
-- Used for segments that were NOT assimilated but are physically identical.
WITH location_matches AS (
    SELECT 
        curr.id,
        SUM(base.od_flow * ST_Length(ST_Intersection(curr.geometry, ST_Buffer(base.geometry, 0.05)))) / 
        NULLIF(SUM(ST_Length(ST_Intersection(curr.geometry, ST_Buffer(base.geometry, 0.05)))), 0) as weighted_baseline_flow
    FROM {current_network} curr
    JOIN {baseline_network} base 
        ON curr.geometry && base.geometry
        AND ST_DWithin(curr.geometry, base.geometry, 0.05)
    WHERE ST_HausdorffDistance(curr.geometry, base.geometry) < 0.05
      AND curr.id NOT IN (SELECT edge_id FROM {result_table} WHERE participating_in_analysis = TRUE)
    GROUP BY curr.id
)
UPDATE {result_table} r
SET flow_baseline = m.weighted_baseline_flow,
    participating_in_analysis = TRUE
FROM location_matches m
WHERE r.edge_id = m.id;

-- 4. LAYER 2: Topological Shatter (Parent Lineage Distance - parent_lineage_dist)
-- Rule A Implementation: Weighted average for fragmented segments using parent_lineage_dist.
WITH fragments AS (
    SELECT 
        curr.id, 
        SUM(base.od_flow * ST_Length(ST_Intersection(curr.geometry, ST_Buffer(base.geometry, {parent_lineage_dist})))) / 
        NULLIF(SUM(ST_Length(ST_Intersection(curr.geometry, ST_Buffer(base.geometry, {parent_lineage_dist})))), 0) as weighted_baseline_flow
    FROM {current_network} curr
    JOIN {baseline_network} base 
        ON curr.geometry && ST_Expand(base.geometry, {parent_lineage_dist})
        AND ST_DWithin(curr.geometry, base.geometry, {parent_lineage_dist})
    WHERE curr.id NOT IN (SELECT edge_id FROM {result_table} WHERE participating_in_analysis = TRUE)
      AND ST_Length(ST_Intersection(curr.geometry, ST_Buffer(base.geometry, {parent_lineage_dist}))) / NULLIF(ST_Length(curr.geometry), 0) > 0.65
    GROUP BY curr.id
)
UPDATE {result_table} r
SET flow_baseline = f.weighted_baseline_flow,
    participating_in_analysis = TRUE
FROM fragments f
WHERE r.edge_id = f.id;

-- 5. FINAL CALCULATION: Delta Flow
-- Rule B Implementation: Projects without matches are Innovation (Delta = Flow)
UPDATE {result_table} 
SET participating_in_analysis = TRUE
WHERE is_project = TRUE;

UPDATE {result_table} 
SET delta_flow = flow_current - flow_baseline;

-- 6. Spatial Indexes
CREATE INDEX {result_table}_gix ON {result_table} USING GIST (geometry);
CREATE INDEX {result_table}_proj_idx ON {result_table} (is_project);
