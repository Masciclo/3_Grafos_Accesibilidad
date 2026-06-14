-- snap_and_shatter_projects.sql
-- Task 18.3 (Iterative + ST_Node Fragmenter): Ensures connectivity by reconstructive nodalization.
-- Parameters: network_table, mr_distance (Magnetismo a Referencia), zp_distance (Zona de Proyecto), pid

-- 1. IDENTIFY SNAPPING POINTS
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

-- 2. SNAP PROJECT TO BASE (Geometry Adjustment)
UPDATE {network_table} n SET geometry = ST_SetPoint(n.geometry, 0, s.snap_geom) FROM nodal_points s WHERE n.id = s.proj_edge_id AND ST_Equals(ST_StartPoint(n.geometry), s.orig_geom);
UPDATE {network_table} n SET geometry = ST_SetPoint(n.geometry, ST_NPoints(n.geometry)-1, s.snap_geom) FROM nodal_points s WHERE n.id = s.proj_edge_id AND ST_Equals(ST_EndPoint(n.geometry), s.orig_geom);

-- 3. RECONSTRUCTIVE NODALIZATION (The surgical part)
DO $$
DECLARE
    r RECORD;
BEGIN
    FOR r IN (
        SELECT base_edge_id, ST_Collect(snap_geom) as points
        FROM nodal_points
        GROUP BY base_edge_id
    ) LOOP
        -- Create fragments by nodalizing the line with the points
        -- We use ST_Union(line, points) + ST_Node as the definitive fragmenter
        INSERT INTO {network_table} (geometry, highway, is_project, project_id, parent_baseline_id, impedance)
        SELECT 
            (ST_Dump(ST_Node(ST_Union(ST_Snap(n.geometry, r.points, 0.05), r.points)))).geom as geom,
            n.highway, n.is_project, n.project_id, n.parent_baseline_id, n.impedance
        FROM {network_table} n
        WHERE n.id = r.base_edge_id;

        -- Remove original
        DELETE FROM {network_table} WHERE id = r.base_edge_id;
    END LOOP;
END $$;

-- 4. FORCED CONTINUITY
WITH zp_buffer AS (
    SELECT ST_Union(ST_Buffer(geometry, {zp_distance})) as geom
    FROM {network_table} WHERE is_project = TRUE AND project_id = '{pid}'
),
trapped_segments AS (
    SELECT n.id
    FROM {network_table} n, zp_buffer zp
    WHERE n.is_project = FALSE AND ST_Within(n.geometry, zp.geom)
      AND EXISTS (SELECT 1 FROM {network_table} p1 WHERE p1.is_project = TRUE AND p1.project_id = '{pid}' AND ST_DWithin(ST_StartPoint(n.geometry), p1.geometry, 0.01))
      AND EXISTS (SELECT 1 FROM {network_table} p2 WHERE p2.is_project = TRUE AND p2.project_id = '{pid}' AND ST_DWithin(ST_EndPoint(n.geometry), p2.geometry, 0.01))
)
UPDATE {network_table} SET is_project = TRUE, project_id = '{pid}', impedance = 0.5, highway = 'project_assimilated_bridge' WHERE id IN (SELECT id FROM trapped_segments);

-- 5. FINAL TOPOLOGICAL CLEANUP
UPDATE {network_table} SET geometry = ST_SnapToGrid(geometry, 0.01);
DELETE FROM {network_table} WHERE ST_Length(geometry) < 0.1;
