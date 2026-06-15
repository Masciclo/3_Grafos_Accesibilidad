-- snap_and_shatter_projects.sql
-- Task 18.3 (Iterative + Robust Nodalization): Ensures connectivity without crashing on invalid geometries.
-- Parameters: network_table, mr_distance (Magnetismo a Referencia), zp_distance (Zona de Proyecto), pid

-- 1. IDENTIFY SNAPPING POINTS
DROP TABLE IF EXISTS nodal_points;
CREATE TEMP TABLE nodal_points AS
WITH endpoints AS (
    -- Only for innovation or small stubs that need plugging
    SELECT id as proj_edge_id, ST_StartPoint(geometry) as geom FROM {network_table} WHERE is_project = TRUE AND project_id = '{pid}' AND geometry IS NOT NULL
    UNION ALL
    SELECT id as proj_edge_id, ST_EndPoint(geometry) as geom FROM {network_table} WHERE is_project = TRUE AND project_id = '{pid}' AND geometry IS NOT NULL
),
nearest_base AS (
    SELECT 
        e.proj_edge_id, e.geom as orig_geom,
        base.id as base_edge_id, base.geometry as base_geom,
        ST_LineLocatePoint(base.geometry, e.geom) as fraction
    FROM endpoints e
    CROSS JOIN LATERAL (
        SELECT id, geometry FROM {network_table} 
        WHERE is_project = FALSE AND ST_DWithin(e.geom, geometry, {mr_distance})
        ORDER BY e.geom <-> geometry LIMIT 1
    ) base
)
SELECT 
    proj_edge_id, base_edge_id, 
    ST_SnapToGrid(ST_LineInterpolatePoint(base_geom, fraction), 0.0001) as nodal_geom
FROM nearest_base;

-- 2. ALIGN PROJECT GEOMETRY (Safe update)
UPDATE {network_table} n 
SET geometry = ST_Snap(n.geometry, t.nodal_geom, 0.01)
FROM nodal_points t 
WHERE n.id = t.proj_edge_id;

-- 3. ALIGN AND SHATTER BASELINE (Robust Loop)
DO $$
DECLARE
    r RECORD;
BEGIN
    FOR r IN (
        SELECT base_edge_id, ST_Collect(nodal_geom) as points
        FROM nodal_points
        GROUP BY base_edge_id
    ) LOOP
        BEGIN
            INSERT INTO {network_table} (geometry, highway, is_project, project_id, parent_baseline_id, impedance, length, cost)
            SELECT 
                (ST_Dump(ST_Node(ST_Union(ST_Snap(n.geometry, r.points, 0.1), r.points)))).geom as geom,
                n.highway, n.is_project, n.project_id, n.parent_baseline_id, n.impedance, NULL, NULL
            FROM {network_table} n
            WHERE n.id = r.base_edge_id;

            DELETE FROM {network_table} WHERE id = r.base_edge_id;
        EXCEPTION WHEN OTHERS THEN
            RAISE WARNING 'Failed to nodalize edge %: %', r.base_edge_id, SQLERRM;
        END;
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
      AND EXISTS (SELECT 1 FROM {network_table} p1 WHERE p1.is_project = TRUE AND p1.project_id = '{pid}' AND ST_DWithin(ST_StartPoint(n.geometry), p1.geometry, 0.1))
      AND EXISTS (SELECT 1 FROM {network_table} p2 WHERE p2.is_project = TRUE AND p2.project_id = '{pid}' AND ST_DWithin(ST_EndPoint(n.geometry), p2.geometry, 0.1))
)
UPDATE {network_table} SET is_project = TRUE, project_id = '{pid}', impedance = 0.5, highway = 'project_assimilated_bridge' WHERE id IN (SELECT id FROM trapped_segments);

-- 5. FINAL TOPOLOGICAL CLEANUP
UPDATE {network_table} SET geometry = ST_SnapToGrid(geometry, 0.0001);
DELETE FROM {network_table} WHERE ST_Length(geometry) < 0.1 OR geometry IS NULL;

-- 6. RE-CALCULATE METRICS
UPDATE {network_table} 
SET length = ST_Length(geometry),
    cost = ST_Length(geometry) * impedance
WHERE length IS NULL OR cost IS NULL;
