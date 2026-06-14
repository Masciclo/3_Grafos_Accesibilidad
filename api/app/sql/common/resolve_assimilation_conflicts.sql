-- resolve_assimilation_conflicts.sql
-- Task 18.2: Resolves assimilation disputes using Greatest Overlap logic.
-- Parameters: result_table, baseline_table, buffers_table

-- 1. Generate all possible intersections between baseline and buffers
DROP TABLE IF EXISTS assimilation_candidates;
CREATE TEMP TABLE assimilation_candidates AS
SELECT 
    b.project_id,
    base.id as parent_baseline_id,
    base.highway,
    ST_Intersection(base.geometry, b.geometry) as geometry,
    ST_Length(ST_Intersection(base.geometry, b.geometry)) as intersection_len,
    ST_Length(base.geometry) as parent_total_len
FROM {baseline_table} base
JOIN {buffers_table} b ON ST_Intersects(base.geometry, b.geometry)
WHERE ST_Dimension(ST_Intersection(base.geometry, b.geometry)) = 1;

-- 2. Resolve Conflicts: Select project with Greatest Overlap for each baseline segment
DROP TABLE IF EXISTS {result_table};
CREATE TABLE {result_table} AS
WITH ranked_candidates AS (
    SELECT 
        parent_baseline_id,
        project_id,
        highway,
        geometry,
        intersection_len,
        parent_total_len,
        (intersection_len / NULLIF(parent_total_len, 0)) as overlap_pct,
        ROW_NUMBER() OVER(PARTITION BY parent_baseline_id ORDER BY intersection_len DESC) as rank
    FROM assimilation_candidates
)
SELECT 
    parent_baseline_id,
    project_id,
    highway,
    geometry,
    overlap_pct
FROM ranked_candidates
WHERE rank = 1 AND overlap_pct >= 0.8; -- Task 18.2: Applying 80% Assimilation Threshold

-- 3. Cleanup & Indexing
CREATE INDEX {result_table}_parent_idx ON {result_table} (parent_baseline_id);
CREATE INDEX {result_table}_gix ON {result_table} USING GIST (geometry);

DO $$
BEGIN
    RAISE NOTICE 'Greatest Overlap resolution complete. Segments identified for assimilation: %', 
        (SELECT COUNT(*) FROM {result_table});
END $$;
