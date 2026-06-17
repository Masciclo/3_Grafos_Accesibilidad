-- link_single_edge_project.sql
-- Description: Specialized high-fidelity system for linking single-edge projects.
-- Strategy: Zone-based Planarization + Topological Snapping + Forced Continuity Bridge.
-- Parameters: network_table, pid, mr_distance (snap), zp_distance (zone)

-- 1. DEFINE PROJECT ZONE & GET NEARBY REFERENCE EDGES
DROP TABLE IF EXISTS project_zone_context;
CREATE TEMP TABLE project_zone_context AS
SELECT id, geometry, highway, is_project, project_id, parent_baseline_id, impedance
FROM {network_table}
WHERE (project_id = '{pid}' AND is_project = TRUE)
   OR (is_project = FALSE AND id IN (
       SELECT base.id FROM {network_table} base, {network_table} proj
       WHERE proj.project_id = '{pid}' AND proj.is_project = TRUE
         AND ST_DWithin(base.geometry, proj.geometry, {zp_distance})
         AND base.is_project = FALSE
   ));

-- 2. PLANARIZE TO CHECK FOR ANY INTERSECTION
-- We use ST_Node(ST_Union) on the context to ensure all crossings are nodalized.
DO $$
BEGIN
    IF (SELECT count(*) FROM project_zone_context WHERE is_project = TRUE) > 0 THEN
        -- Delete original segments from main table to prepare for re-insertion
        DELETE FROM {network_table} WHERE id IN (SELECT id FROM project_zone_context);

        -- Insert nodalized fragments with Sovereignty Guard
        INSERT INTO {network_table} (geometry, highway, is_project, project_id, parent_baseline_id, impedance)
        WITH nodalized AS (
            SELECT (ST_Dump(ST_Node(ST_SnapToGrid(ST_Union(geometry), 0.001)))).geom as g
            FROM project_zone_context
        ),
        ranked_fragments AS (
            -- If a fragment matches both project and baseline, project wins (Sovereignty)
            SELECT 
                n.g,
                ctx.highway,
                ctx.is_project,
                ctx.project_id,
                ctx.parent_baseline_id,
                ctx.impedance,
                ROW_NUMBER() OVER(PARTITION BY n.g ORDER BY ctx.is_project DESC) as rank
            FROM nodalized n
            JOIN project_zone_context ctx ON ST_Within(ST_Centroid(n.g), ST_Buffer(ctx.geometry, 0.01))
        )
        SELECT g, highway, is_project, project_id, parent_baseline_id, impedance
        FROM ranked_fragments
        WHERE rank = 1;
    END IF;
END $$;

-- 3. TOPOLOGICAL SNAPPING (Magnetismo Topológico)
-- Close small gaps that planarization couldn't catch.
DROP TABLE IF EXISTS nodal_points;
CREATE TEMP TABLE nodal_points AS
WITH endpoints AS (
    SELECT id as proj_edge_id, ST_StartPoint(geometry) as geom FROM {network_table} WHERE is_project = TRUE AND project_id = '{pid}'
    UNION ALL
    SELECT id as proj_edge_id, ST_EndPoint(geometry) as geom FROM {network_table} WHERE is_project = TRUE AND project_id = '{pid}'
)
SELECT DISTINCT ON (e.geom)
    e.proj_edge_id,
    e.geom as orig_geom,
    base.id as base_edge_id,
    ST_ClosestPoint(base.geometry, e.geom) as snap_geom
FROM endpoints e
CROSS JOIN LATERAL (
    SELECT id, geometry FROM {network_table} 
    WHERE is_project = FALSE AND ST_DWithin(e.geom, geometry, {mr_distance})
    ORDER BY e.geom <-> geometry LIMIT 1
) base;

-- 3.1 Snap Project to Base
UPDATE {network_table} n SET geometry = ST_SetPoint(n.geometry, 0, s.snap_geom) FROM nodal_points s WHERE n.id = s.proj_edge_id AND ST_Equals(ST_StartPoint(n.geometry), s.orig_geom);
UPDATE {network_table} n SET geometry = ST_SetPoint(n.geometry, ST_NPoints(n.geometry)-1, s.snap_geom) FROM nodal_points s WHERE n.id = s.proj_edge_id AND ST_Equals(ST_EndPoint(n.geometry), s.orig_geom);

-- 3.2 Nodalize the snapped points on the baseline
DO $$
DECLARE
    r RECORD;
BEGIN
    FOR r IN (
        SELECT base_edge_id, ST_Collect(snap_geom) as points
        FROM nodal_points
        GROUP BY base_edge_id
    ) LOOP
        INSERT INTO {network_table} (geometry, highway, is_project, project_id, parent_baseline_id, impedance)
        SELECT 
            (ST_Dump(ST_Node(ST_Union(ST_Snap(n.geometry, r.points, 0.05), r.points)))).geom as geom,
            n.highway, n.is_project, n.project_id, n.parent_baseline_id, n.impedance
        FROM {network_table} n
        WHERE n.id = r.base_edge_id;

        DELETE FROM {network_table} WHERE id = r.base_edge_id;
    END LOOP;
END $$;

-- 4. FORCED CONTINUITY BRIDGE
-- Ensure "Innovation" projects are not isolated by tiny network gaps.
WITH zp_buffer AS (
    SELECT ST_Union(ST_Buffer(geometry, 2.0)) as geom -- Tight buffer for bridging
    FROM {network_table} WHERE is_project = TRUE AND project_id = '{pid}'
),
trapped_segments AS (
    SELECT n.id
    FROM {network_table} n, zp_buffer zp
    WHERE n.is_project = FALSE AND ST_Within(n.geometry, zp.geom)
      AND EXISTS (SELECT 1 FROM {network_table} p1 WHERE p1.is_project = TRUE AND p1.project_id = '{pid}' AND ST_DWithin(ST_StartPoint(n.geometry), p1.geometry, 0.05))
      AND EXISTS (SELECT 1 FROM {network_table} p2 WHERE p2.is_project = TRUE AND p2.project_id = '{pid}' AND ST_DWithin(ST_EndPoint(n.geometry), p2.geometry, 0.05))
)
UPDATE {network_table} SET is_project = TRUE, project_id = '{pid}', impedance = 0.5, highway = 'project_assimilated_bridge' WHERE id IN (SELECT id FROM trapped_segments);

-- 5. FINAL CLEANUP
UPDATE {network_table} SET geometry = ST_SnapToGrid(geometry, 0.001);
DELETE FROM {network_table} WHERE ST_Length(geometry) < 0.1;
