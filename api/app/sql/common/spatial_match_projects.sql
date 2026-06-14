-- spatial_match_projects.sql
-- Phase 5: Identifies baseline segments for "Geometric Replacement" (Amputation).

-- 1. Ensure control columns exist
ALTER TABLE {network_table} ADD COLUMN IF NOT EXISTS is_project BOOLEAN DEFAULT FALSE;
ALTER TABLE {network_table} ADD COLUMN IF NOT EXISTS to_delete BOOLEAN DEFAULT FALSE;

-- 2. Identify segments for Amputation
-- We use a buffer-based approach to find anything within the project's spatial footprint.
WITH matches AS (
    SELECT DISTINCT n.id
    FROM {network_table} n
    JOIN {projects_table} p ON ST_DWithin(n.geometry, p.geometry, 1.0) -- REDUCED to 1m to avoid over-amputation
    WHERE ST_Length(ST_Intersection(p.geometry, ST_Buffer(n.geometry, 1.0))) / NULLIF(ST_Length(n.geometry), 0) > 0.8
)
UPDATE {network_table} n
SET to_delete = TRUE
FROM matches m
WHERE n.id = m.id;

-- 3. Audit
DO $$
BEGIN
    RAISE NOTICE 'Segments identified for amputation: %', (SELECT COUNT(*) FROM {network_table} WHERE to_delete = TRUE);
END $$;
