-- planarize_innovation_project.sql
-- Description: Specialized surgical planarization for "Innovation" projects (Project 1 archetype).
-- Added ST_Snap to handle near-miss intersections (Phantom Crossings).
-- Parameters: network_table, pid

-- 1. Identify segments for surgical union (Using 1.0m tolerance for snapping)
DROP TABLE IF EXISTS surgical_context;
CREATE TEMP TABLE surgical_context AS
SELECT id, geometry, highway, is_project, project_id, parent_baseline_id, impedance
FROM {network_table}
WHERE (project_id = '{pid}' AND is_project = TRUE)
   OR (is_project = FALSE AND id IN (
       SELECT base.id FROM {network_table} base, {network_table} proj
       WHERE proj.project_id = '{pid}' AND proj.is_project = TRUE
         AND ST_DWithin(base.geometry, proj.geometry, 1.0)
         AND base.is_project = FALSE
   ));

-- 2. Execute Nodalization and Re-insertion
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM surgical_context) THEN
        -- 1. Create a snaped version of the context to ensure physical contact
        -- We snap projects to baseline for this surgical pass
        DROP TABLE IF EXISTS snapped_context;
        CREATE TEMP TABLE snapped_context AS
        SELECT 
            id,
            CASE 
                WHEN project_id = '{pid}' THEN ST_Snap(geometry, (SELECT ST_Union(geometry) FROM surgical_context WHERE is_project = FALSE), 1.0)
                ELSE geometry
            END as geometry,
            highway, is_project, project_id, parent_baseline_id, impedance
        FROM surgical_context;

        -- 2. Delete original segments from main table
        DELETE FROM {network_table} WHERE id IN (SELECT id FROM surgical_context);

        -- 3. Insert nodalized fragments with attribute inheritance via spatial join
        INSERT INTO {network_table} (geometry, highway, is_project, project_id, parent_baseline_id, impedance)
        WITH nodalized AS (
            SELECT (ST_Dump(ST_Node(ST_SnapToGrid(ST_Union(geometry), 0.001)))).geom as g
            FROM snapped_context
        )
        SELECT 
            n.g,
            ctx.highway,
            ctx.is_project,
            ctx.project_id,
            ctx.parent_baseline_id,
            ctx.impedance
        JOIN snapped_context ctx ON ST_DWithin(ST_LineInterpolatePoint(n.g, 0.5), ctx.geometry, 0.02);
    END IF;
END $$;

-- 3. Cleanup attributes for the new fragments
UPDATE {network_table} SET 
    length = ST_Length(geometry),
    cost = ST_Length(geometry) * COALESCE(impedance, 1.0)
WHERE project_id = '{pid}' OR id IN (SELECT id FROM surgical_context);
