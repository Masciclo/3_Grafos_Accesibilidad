-- inject_projects.sql
-- Phase 5: Injects new project geometries into the base network.

-- 1. Identify "New" geometries (those not matched by spatial_match_projects.sql)
-- We insert geometries from projects_table that are NOT within 10m of any ALREADY matched edge.
-- This prevents double-injection of existing roads.

INSERT INTO {network_table} (geometry, highway, is_project, impedance)
SELECT 
    p.geometry,
    'project_new' as highway,
    TRUE as is_project,
    1.0 as impedance
FROM {projects_table} p
WHERE NOT EXISTS (
    SELECT 1 
    FROM {network_table} n 
    WHERE ST_DWithin(p.geometry, n.geometry, 10)
    AND n.is_project = TRUE
);

-- 2. Audit
DO $$
BEGIN
    RAISE NOTICE 'New project geometries injected into the network.';
END $$;
