-- inject_projects.sql
-- Phase 15.8: Executes Project Injection without premature amputation.
-- Amputation is now handled by topology_refactor.py AFTER suturing.

-- 1. Inject sovereign geometries
INSERT INTO {network_table} (geometry, highway, is_project, project_id, impedance)
SELECT 
    (ST_Dump(ST_MakeValid(p.geometry))).geom as geometry,
    'project_new' as highway,
    TRUE as is_project,
    p.id as project_id,
    0.5 as impedance 
FROM {projects_table} p;

-- 2. Audit
DO $$
BEGIN
    RAISE NOTICE 'Project injection complete. Total project edges: %', 
        (SELECT COUNT(*) FROM {network_table} WHERE is_project = TRUE);
END $$;
