-- spatial_match_projects.sql
-- Phase 5: Matches GeoJSON project proposals to the road graph.

-- 1. Ensure control columns exist
ALTER TABLE {network_table} ADD COLUMN IF NOT EXISTS is_project BOOLEAN DEFAULT FALSE;

-- 2. Spatial Join using ST_DWithin + Linear Overlap Ratio
-- We use a CTE to find all edges that are within 10m of any project geometry
-- and share at least 80% of their length (Parallelism constraint)
WITH matched_edges AS (
    SELECT DISTINCT n.id
    FROM {network_table} n
    JOIN {projects_table} p ON ST_DWithin(n.geometry, p.geometry, 10)
    WHERE ST_Length(ST_Intersection(p.geometry, ST_Buffer(n.geometry, 10))) / NULLIF(ST_Length(p.geometry), 0) > 0.8
)
UPDATE {network_table} n
SET 
    is_project = TRUE,
    impedance = 1.0  -- Override impedance to minimum for proposed projects
FROM matched_edges m
WHERE n.id = m.id;

-- 3. Audit
DO $$
BEGIN
    RAISE NOTICE 'Project matching completed.';
    RAISE NOTICE 'Edges flagged as project: %', (SELECT COUNT(*) FROM {network_table} WHERE is_project = TRUE);
END $$;
